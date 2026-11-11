"""Diagnostic trials use injected transports; they do not certify real VISA hardware."""

import json
from pathlib import Path

import pytest

from keithley6517a.clock import FakeClock
from keithley6517a.diagnostics import probe_backend, run_diagnostics
from keithley6517a.transport.base import CommunicationError
from keithley6517a.transport.simulator import SimulatorTransport


class Factory:
    def __init__(self, faults=None, *, output=False, resources=None):
        self.bus = SimulatorTransport(clock=FakeClock(), faults=faults)
        self.bus.output = output
        self.arguments = None
        self.resources = tuple(resources or ("GPIB1::5::INSTR",))
        self.discovery_backend = None

    def __call__(self, resource, **kwargs):
        self.arguments = dict(resource=resource, **kwargs)
        return self.bus

    def list_resources(self, backend):
        self.discovery_backend = backend
        return self.resources


def run(tmp_path, factory, **options):
    settings = dict(
        resource="GPIB1::5::INSTR",
        backend="test-library",
        output_directory=tmp_path,
        transport_factory=factory,
    )
    return run_diagnostics(**dict(settings, **options))


def test_discovery_only_lists_gpib_resources_without_instrument_io(tmp_path):
    factory = Factory(resources=("GPIB1::5::INSTR", "ASRL1::INSTR", "USB::DEVICE"))
    report = run(tmp_path, factory, resource=None)
    assert report["ok"] is True
    assert report["mode"] == "DISCOVERY"
    assert report["resources"] == ["GPIB1::5::INSTR"]
    assert report["output_state"] == "UNKNOWN"
    assert report["output_OFF_confirmed"] is False
    assert factory.discovery_backend == "test-library"
    assert factory.arguments is None
    assert factory.bus.commands == []


def test_idn_only_probe_preserves_an_existing_on_state_and_does_not_claim_off(tmp_path):
    factory = Factory(output=True)
    report = run(tmp_path, factory)
    assert report["ok"] is True
    assert report["mode"] == "IDN_ONLY"
    assert report["identity"]["model"] == "6517A"
    assert report["identity"]["serial"] == "SIM0001"
    assert report["output_state"] == "UNKNOWN"
    assert report["output_OFF_confirmed"] is False
    assert factory.bus.commands == ["*IDN?"]
    assert factory.bus.output is True
    assert factory.bus.opened is False
    assert report["hardware_verified"] is False


def test_explicit_off_check_logs_only_protective_off_and_never_configures_or_enables(tmp_path):
    factory = Factory(output=True)
    report = run(tmp_path, factory, confirm_off=True)
    assert report["ok"] is True
    assert report["mode"] == "OUTPUT_OFF_CHECK"
    assert report["output_state"] == "OFF"
    assert report["output_OFF_confirmed"] is True
    assert report["residual_voltage_state"] == "UNVERIFIED"
    assert report["identity"]["manual_verified"] is True
    assert report["identity"]["hardware_verified"] is False
    assert ":OUTP1 OFF" in factory.bus.commands
    assert ":TSEQ:ABOR" in factory.bus.commands
    assert ":OUTP1 ON" not in factory.bus.commands
    assert not any(command.startswith(":SOUR:VOLT ") for command in factory.bus.commands)
    assert factory.bus.output is False
    assert factory.bus.opened is False


@pytest.mark.parametrize("confirm_off", [False, True])
def test_wrong_model_gets_only_idn_even_for_requested_off_check(tmp_path, confirm_off):
    factory = Factory({"idn": "KEITHLEY,MODEL 6517B,OTHER,1.0"}, output=True)
    report = run(tmp_path, factory, confirm_off=confirm_off)
    assert report["ok"] is False
    assert report["issues"][0]["code"] == "UNSUPPORTED_MODEL"
    assert report["output_state"] == "UNKNOWN"
    assert report["output_OFF_confirmed"] is False
    assert factory.bus.commands == ["*IDN?"]
    assert factory.bus.output is True
    assert factory.bus.opened is False


def test_off_failure_preserves_unknown_and_attempts_off_during_cleanup(tmp_path):
    factory = Factory({"fail_off": True}, output=True)
    report = run(tmp_path, factory, confirm_off=True)
    assert report["ok"] is False
    assert report["output_state"] == "UNKNOWN"
    assert report["output_OFF_confirmed"] is False
    assert report["residual_voltage_state"] == "UNVERIFIED"
    assert factory.bus.commands.count(":OUTP1 OFF") == 4
    assert report["identity"]["model"] == "6517A"
    assert any(issue["code"] == "OUTPUT_OFF_UNCONFIRMED" for issue in report["issues"])
    assert ":OUTP1 ON" not in factory.bus.commands
    assert factory.bus.output is True
    assert factory.bus.opened is False


def test_recording_failure_does_not_prevent_protective_off(tmp_path):
    blocked = tmp_path / "file-not-directory"
    blocked.write_text("Existing file must not be overwritten")
    factory = Factory(output=True)
    report = run(tmp_path, factory, confirm_off=True, output_directory=blocked)
    assert report["ok"] is False
    assert report["report_saved"] is False
    assert report["issues"][-1]["code"] == "REPORT_SAVE_FAILED"
    assert report["output_state"] == "OFF"
    assert report["output_OFF_confirmed"] is True
    assert factory.bus.output is False
    assert blocked.read_text() == "Existing file must not be overwritten"


def test_reports_and_transcripts_are_unique_strict_json_and_label_injection(tmp_path, monkeypatch):
    monkeypatch.setenv("UNRELATED_DIAGNOSTIC_SECRET", "DO-NOT-COPY-SECRET-VALUES")
    first = run(tmp_path, Factory(), confirm_off=True)
    second = run(tmp_path, Factory())
    assert first["report_path"] != second["report_path"]
    assert first["diagnostic_id"] != second["diagnostic_id"]
    document = json.loads(
        Path(first["report_path"]).read_text(), parse_constant=lambda value: pytest.fail(value)
    )
    assert document == first
    assert document["transport_origin"] == "injected"
    assert document["simulation"] is True
    assert document["hardware_verified"] is False
    text = Path(first["raw_io_path"]).read_text()
    records = [json.loads(line) for line in text.splitlines()]
    assert records
    assert all(item["transport_origin"] == "injected" and item["simulation"] for item in records)
    assert all(item["wall_time_iso8601"].endswith("+00:00") for item in records)
    assert "DO-NOT-COPY-SECRET-VALUES" not in text + json.dumps(document)


@pytest.mark.parametrize(
    "settings",
    [
        {"timeout_ms": 0},
        {"timeout_ms": -1},
        {"timeout_ms": float("nan")},
        {"timeout_ms": float("inf")},
        {"timeout_ms": True},
        {"resource": "ASRL1::INSTR"},
        {"read_termination": ["\n"]},
        {"write_termination": 1},
        {"send_end": 1},
        {"confirm_off": "yes"},
        {"backend": 17},
        {"resource": None, "confirm_off": True},
    ],
)
def test_invalid_settings_are_reported_without_io_and_never_emit_nonfinite_json(tmp_path, settings):
    factory = Factory()
    report = run(tmp_path, factory, **settings)
    assert report["ok"] is False
    assert report["issues"][0]["code"] == "INVALID_DIAGNOSTIC_SETTINGS"
    assert factory.bus.commands == []
    assert factory.arguments is None
    assert report["report_saved"] is True
    json.dumps(report, allow_nan=False)


def test_backend_failure_has_actionable_vendor_runtime_guidance(tmp_path):
    class MissingBackend:
        @staticmethod
        def list_resources(_):
            raise ValueError("Could not locate a VISA implementation")

    report = run(tmp_path, MissingBackend, resource=None)
    assert report["ok"] is False
    assert report["stage"] == "backend_discovery"
    assert report["issues"][0]["code"] == "VISA_BACKEND_UNAVAILABLE"
    assert "runtime" in report["issues"][0]["action"]


def test_no_resources_is_distinct_from_missing_backend(tmp_path):
    factory = Factory()
    factory.resources = ()
    report = run(tmp_path, factory, resource=None)
    assert report["ok"] is False
    assert report["issues"][0]["code"] == "NO_GPIB_RESOURCES"
    assert factory.arguments is None


def test_finite_io_settings_are_forwarded_to_selected_transport(tmp_path):
    factory = Factory()
    run(
        tmp_path,
        factory,
        timeout_ms=1200,
        read_termination=None,
        write_termination="\r\n",
        send_end=False,
    )
    assert factory.arguments == dict(
        resource="GPIB1::5::INSTR",
        backend="test-library",
        timeout_ms=1200,
        read_termination=None,
        write_termination="\r\n",
        send_end=False,
    )


def test_cleanup_failure_is_visible_without_losing_confirmed_output_state(tmp_path):
    factory = Factory(output=True)
    original = factory.bus.close

    def broken_close():
        original()
        raise CommunicationError("Injected cleanup failure")

    factory.bus.close = broken_close
    report = run(tmp_path, factory, confirm_off=True)
    assert report["ok"] is False
    assert report["output_state"] == "OFF"
    assert report["issues"][-1]["stage"] == "close"
    assert factory.bus.output is False


def test_probe_does_not_fall_back_to_real_visa_when_injected_lister_missing():
    with pytest.raises(ValueError, match="Injected"):
        probe_backend(transport_factory=lambda resource, **kwargs: None)
