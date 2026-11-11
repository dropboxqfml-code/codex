"""Local VISA trial reports, without a voltage-setting or output-ON path.

Default probes list GPIB resources or send only *IDN? to an explicitly selected
resource. Protective OFF is a separate explicit option. Reports are written
after I/O cleanup so a disk failure cannot prevent an OFF attempt.
"""

from __future__ import annotations

import importlib.metadata
import json
import math
import os
import platform
import struct
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from . import __version__
from .driver.instrument import Instrument, parse_identity
from .storage.run_writer import atomic_json
from .transport.base import UnsupportedOperation
from .transport.visa import VisaTransport


def _wall_time():
    return datetime.now(UTC).isoformat()


def _setting(value):
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    return {"invalid_type": type(value).__name__}


def _environment():
    packages = {}
    for package in ("PyVISA", "PySide6-Essentials", "pyqtgraph", "numpy"):
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = None
    return {
        "operating_system": platform.system(),
        "os_release": platform.release(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "python_bitness": struct.calcsize("P") * 8,
        "packages": packages,
    }


def _issue(exc, stage):
    message = str(exc)
    lowered = message.lower()
    if isinstance(exc, UnsupportedOperation):
        code = "UNSUPPORTED_MODEL"
        action = (
            "6517A 모델과 전면 SCPI 언어 설정을 확인하세요. "
            "다른 모델에는 제어 명령을 보내지 않습니다."
        )
    elif stage == "validation":
        code = "INVALID_DIAGNOSTIC_SETTINGS"
        action = "선택한 GPIB resource, backend, 유한 timeout 및 terminator 설정을 확인하세요."
    elif isinstance(exc, (ImportError, ModuleNotFoundError)) or any(
        token in lowered
        for token in (
            "could not locate a visa implementation",
            "visa library",
            "visa implementation",
            "no matching architecture",
            "wrong elf class",
            "not a valid win32",
        )
    ):
        code = "VISA_BACKEND_UNAVAILABLE"
        action = (
            "어댑터 제조사 드라이버와 64비트 VISA runtime을 설치하세요. "
            "NI GPIB-USB는 NI-488.2와 NI-VISA 설치 및 NI MAX 인식을 확인하세요. "
            "backend/library 경로를 확인하세요. "
            "PyVISA 설치만으로 USB-GPIB 드라이버가 설치되지는 않습니다."
        )
    elif "intf_num_nconfig" in lowered:
        code = "GPIB_INTERFACE_NOT_CONFIGURED"
        action = (
            "NI MAX에서 GPIB-USB와 GPIB 보드 번호를 확인하세요. "
            "NI-488.2 드라이버 인식과 선택한 resource의 GPIB 번호를 확인하세요."
        )
    elif "rsrc_nfound" in lowered or "inv_rsrc_name" in lowered:
        code = "GPIB_RESOURCE_NOT_FOUND"
        action = (
            "NI MAX에서 확인한 GPIB 보드 번호와 장비 전면의 주소·SCPI 설정을 대조하세요. "
            "어댑터와 케이블 연결을 확인하고 resource를 직접 선택하세요."
        )
    elif "rsrc_busy" in lowered or "resource busy" in lowered or "locked" in lowered:
        code = "RESOURCE_BUSY"
        action = (
            "NI MAX/Connection Expert와 다른 제어 프로그램을 종료하세요. "
            "선택한 resource를 다시 확인하세요."
        )
    elif isinstance(exc, TimeoutError) or "tmo" in lowered or "timeout" in lowered:
        code = "IO_TIMEOUT"
        action = (
            "장비 전원·GPIB 주소·SCPI 언어·케이블·EOI/terminator와 timeout을 확인하세요. "
            "자동 재시도하지 않습니다."
        )
    else:
        code = "DIAGNOSTIC_FAILED"
        action = (
            "오류 단계와 raw_io.jsonl을 확인하세요. "
            "제조사 도구에서 장비 주소·드라이버 상태를 점검하세요."
        )
    return {
        "code": code,
        "stage": stage,
        "type": type(exc).__name__,
        "message": message,
        "action": action,
    }


def _validate(
    resource, backend, timeout_ms, read_termination, write_termination, send_end, confirm_off
):
    if resource is not None and (
        not isinstance(resource, str)
        or not resource.upper().startswith("GPIB")
        or not resource.strip()
    ):
        raise ValueError("Select an explicit VISA GPIB resource; serial/USBTMC is unsupported")
    if backend is not None and not isinstance(backend, str):
        raise ValueError("backend must be a VISA backend/library string or null")
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 60000:
        raise ValueError("timeout_ms must be an integer in 1..60000")
    for value in (read_termination, write_termination):
        if value is not None and not isinstance(value, str):
            raise ValueError("terminators must be strings or null")
    if type(send_end) is not bool or type(confirm_off) is not bool:
        raise ValueError("send_end and confirm_off must be booleans")
    if confirm_off and resource is None:
        raise ValueError("Protective OFF requires one explicitly selected GPIB resource")


def probe_backend(backend=None, *, transport_factory=None):
    """List only VISA GPIB resources. This function opens no instrument session."""
    factory = transport_factory or VisaTransport
    lister = getattr(factory, "list_resources", None)
    if lister is None:
        raise ValueError("Injected diagnostic transport must provide list_resources for discovery")
    return tuple(
        resource
        for resource in lister(backend or "")
        if isinstance(resource, str) and resource.upper().startswith("GPIB")
    )


def _backend_path(transport):
    manager = getattr(transport, "manager", None)
    library = getattr(manager, "visalib", None)
    if library is None:
        return None
    return str(getattr(library, "library_path", library))


def run_diagnostics(
    *,
    resource=None,
    backend=None,
    timeout_ms=2000,
    read_termination="\n",
    write_termination="\n",
    send_end=True,
    confirm_off=False,
    output_directory="diagnostics",
    transport_factory=None,
):
    """Return a strict-JSON report; operational and persistence errors are explicit.

    ``ok`` means this selected diagnostic completed, not commissioning or
    measurement readiness. Even a confirmed output OFF leaves residual charge
    UNVERIFIED. A successful IDN-only probe leaves output state UNKNOWN.
    Test-injected transports are explicitly labelled in every report/transcript.
    """
    diagnostic_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex
    report = {
        "schema_version": 1,
        "diagnostic_id": diagnostic_id,
        "software_version": __version__,
        "started_at": _wall_time(),
        "finished_at": None,
        "mode": "OUTPUT_OFF_CHECK" if confirm_off else ("IDN_ONLY" if resource else "DISCOVERY"),
        "ok": False,
        "stage": "validation",
        "environment": _environment(),
        "settings": {
            "resource": _setting(resource),
            "backend": _setting(backend),
            "timeout_ms": _setting(timeout_ms),
            "read_termination": _setting(read_termination),
            "write_termination": _setting(write_termination),
            "send_end": _setting(send_end),
        },
        "resources": [],
        "identity": None,
        "backend_library": None,
        "output_state": "UNKNOWN",
        "output_OFF_confirmed": False,
        "residual_voltage_state": "UNVERIFIED",
        "hardware_verified": False,
        "transport_origin": "injected" if transport_factory is not None else "visa",
        "simulation": None,
        "issues": [],
        "report_path": None,
        "raw_io_path": None,
        "report_saved": False,
        "output_ON_sent": False,
        "measurement_started": False,
    }
    transcript = []
    transport = instrument = None

    def record(item):
        transcript.append(
            dict(
                item,
                wall_time_iso8601=_wall_time(),
                monotonic_s=time.monotonic(),
                simulation=report["simulation"],
                transport_origin=report["transport_origin"],
            )
        )

    try:
        _validate(
            resource,
            backend,
            timeout_ms,
            read_termination,
            write_termination,
            send_end,
            confirm_off,
        )
        if resource is None:
            report["stage"] = "backend_discovery"
            report["resources"] = list(probe_backend(backend, transport_factory=transport_factory))
            if not report["resources"]:
                report["issues"].append(
                    {
                        "code": "NO_GPIB_RESOURCES",
                        "stage": report["stage"],
                        "message": "VISA library returned no GPIB resources",
                        "action": (
                            "제조사 도구에서 드라이버·VISA·어댑터 board와 "
                            "장비 GPIB 주소를 확인하세요."
                        ),
                    }
                )
            else:
                report["ok"] = True
        else:
            report["stage"] = "open"
            factory = transport_factory or VisaTransport
            transport = factory(
                resource,
                backend=backend or "",
                timeout_ms=timeout_ms,
                read_termination=read_termination,
                write_termination=write_termination,
                send_end=send_end,
            )
            report["simulation"] = bool(transport.is_simulation)
            if confirm_off:
                report["stage"] = "identify_and_confirm_off"
                instrument = Instrument(transport, io_callback=record)
                try:
                    report["identity"] = instrument.connect()
                finally:
                    report["backend_library"] = _backend_path(transport)
                report["output_state"] = instrument.output_state
                report["output_OFF_confirmed"] = report["output_state"] == "OFF"
                report["ok"] = report["output_OFF_confirmed"]
            else:
                transport.open()
                report["backend_library"] = _backend_path(transport)
                report["stage"] = "identify"
                record({"direction": "tx", "command": "*IDN?"})
                response = transport.query("*IDN?")
                record({"direction": "rx", "command": "*IDN?", "response": response})
                report["identity"] = parse_identity(response)
                report["ok"] = True
    except Exception as exc:
        report["issues"].append(_issue(exc, report["stage"]))
        report["ok"] = False
    finally:
        # All cleanup happens before output persistence. Logging cannot block OFF.
        if instrument is not None:
            try:
                instrument.close()
            except Exception as exc:
                report["issues"].append(_issue(exc, "close"))
                report["ok"] = False
            finally:
                if report["identity"] is None:
                    report["identity"] = instrument.identity
                report["output_state"] = instrument.output_state
                report["output_OFF_confirmed"] = instrument.output_state == "OFF"
                if not report["output_OFF_confirmed"]:
                    report["ok"] = False
                    if report["identity"] is not None:
                        report["issues"].append(
                            {
                                "code": "OUTPUT_OFF_UNCONFIRMED",
                                "stage": "confirm_off",
                                "message": "6517A output OFF could not be confirmed",
                                "action": (
                                    "장비가 출력을 유지할 수 있습니다. 승인된 현장 절차에 따라 "
                                    "독립 차단·방전 및 잔류 전압 확인을 수행하세요. "
                                    "USB 분리나 PC 종료를 출력 차단으로 간주하지 마세요."
                                ),
                            }
                        )
        elif transport is not None:
            try:
                transport.close()
            except Exception as exc:
                report["issues"].append(_issue(exc, "close"))
                report["ok"] = False
        report["finished_at"] = _wall_time()

    try:
        directory = Path(output_directory).expanduser().resolve() / diagnostic_id
        directory.mkdir(parents=True, exist_ok=False)
        raw_path = directory / "raw_io.jsonl"
        report_path = directory / "diagnostic.json"
        report["raw_io_path"] = str(raw_path)
        report["report_path"] = str(report_path)
        with raw_path.open("w", encoding="utf-8", newline="") as stream:
            for item in transcript:
                stream.write(json.dumps(item, ensure_ascii=False, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        report["report_saved"] = True
        report["stage"] = "completed" if report["ok"] else report["stage"]
        atomic_json(report_path, report)
    except Exception as exc:
        report["report_saved"] = False
        report["ok"] = False
        report["issues"].append(
            {
                "code": "REPORT_SAVE_FAILED",
                "stage": "save_report",
                "type": type(exc).__name__,
                "message": str(exc),
                "action": (
                    "쓰기 가능한 저장 폴더를 선택하세요. "
                    "출력 OFF 확인 결과는 별도 상태 항목을 확인하세요."
                ),
            }
        )
    return report
