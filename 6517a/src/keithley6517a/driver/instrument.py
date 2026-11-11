"""Manual-verified 6517A control with connection-scoped commissioning and START.

VISA commands are implemented from the supplied manual, but not hardware tested.
Native resistance on real hardware stays blocked: inferred current is not a
verified measured-current protection channel.
"""

import json
import math
import re
import time
import uuid
from decimal import ROUND_HALF_UP, Decimal

from ..config import RunConfig
from ..transport.base import CommunicationError, UnsupportedOperation
from .commands import (
    COMMON_PROFILE,
    FORMAT,
    MANUAL_REVISION,
    MANUAL_SHA256,
    MANUAL_VERIFIED,
    ONE_SHOT_PROFILE,
    function_profile,
)
from .parser import ProtocolError, parse_reading


def _get(config, name, default=None):
    return config.get(name, default) if isinstance(config, dict) else getattr(config, name, default)


def _snapshot(config):
    data = config.to_dict() if hasattr(config, "to_dict") else dict(vars(config))
    return json.dumps(data, sort_keys=True, allow_nan=False)


def parse_identity(response: str) -> dict:
    """Validate 6517A without sending any model-specific command or claiming control."""
    fields = [s.strip() for s in response.split(",")]
    if len(fields) != 4 or not re.fullmatch(r"(?:MODEL\s+)?6517A", fields[1], re.I):
        raise UnsupportedOperation(f"Only model 6517A is supported; received {response!r}")
    return {
        "manufacturer": fields[0],
        "model": "6517A",
        "serial": fields[2],
        "firmware": fields[3],
        "raw_idn": response,
    }


class Instrument:
    def __init__(self, transport, clock=None, io_callback=None):
        self.transport = transport
        self.clock = clock or time
        self.io_callback = io_callback
        self.output_state = "UNKNOWN"
        self.identity = None
        self.config = None
        self.mode = "FVMI_CURRENT"
        self.last_reading_number = None
        self.configured = False
        self._identified = False
        self.last_safety = None
        self.voltage_programmed = 0.0
        self.source_range_V = 100.0
        self.io_guard = None
        self._configured_snapshot = None
        self._start_permit = None
        self._commissioning = {
            "ready": False,
            "fixture_id": "",
            "approved_by": "",
            "open_observed": False,
            "closed_observed": False,
            "session_id": "",
        }

    @property
    def commissioning(self):
        return dict(self._commissioning)

    @property
    def is_simulation(self):
        return self.transport.is_simulation

    def _emit(self, event, safety=False):
        event = {**event, "simulation": self.is_simulation, "monotonic_s": self.clock.monotonic()}
        if self.io_callback:
            try:
                self.io_callback(event)
            except Exception:
                if not safety:
                    raise

    def _write(self, command, safety=False):
        if not safety and self.io_guard:
            self.io_guard()
        self._emit({"direction": "tx", "command": command}, safety)
        if not safety and self.io_guard:
            self.io_guard()
        self.transport.write(command)

    def _query(self, command, safety=False):
        if not safety and self.io_guard:
            self.io_guard()
        self._emit({"direction": "tx", "command": command}, safety)
        if not safety and self.io_guard:
            self.io_guard()
        response = self.transport.query(command)
        self._emit({"direction": "rx", "command": command, "response": response}, safety)
        return response

    @staticmethod
    def _bool(response):
        response = response.strip().upper()
        if response not in ("0", "1", "OFF", "ON"):
            raise ProtocolError(f"Invalid boolean reply: {response!r}")
        return response in ("1", "ON")

    @staticmethod
    def _number(response):
        value = float(response.strip())
        if not math.isfinite(value):
            raise ProtocolError("Non-finite setting readback")
        return value

    def connect(self):
        self.identity = None
        self.configured = self._identified = False
        self.config = None
        self.output_state = "UNKNOWN"
        self.last_reading_number = None
        self._start_permit = self._configured_snapshot = None
        self._commissioning = {
            "ready": False,
            "fixture_id": "",
            "approved_by": "",
            "open_observed": False,
            "closed_observed": False,
            "session_id": uuid.uuid4().hex,
        }
        self.transport.open()
        try:
            identity = parse_identity(self._query("*IDN?"))
        except Exception:
            self.transport.close()
            raise
        self._identified = True
        self.identity = {
            **identity,
            "simulation": self.is_simulation,
            "manual_verified": MANUAL_VERIFIED,
            "manual_revision": MANUAL_REVISION,
            "manual_sha256": MANUAL_SHA256,
            "hardware_verified": False,
            "real_fvmi_profile_available": True,
        }
        errors = self.safe_off()
        if self.output_state != "OFF":
            raise CommunicationError(
                "Takeover failed to confirm OFF; physically isolate source: " + "; ".join(errors)
            )
        return self.identity

    def commission_interlock(self, expected, fixture_id, approved_by):
        """Observe OFF-state 0 then 1; query=1 alone never proves an installed cable."""
        if not self._identified:
            raise RuntimeError("Connect and identify before commissioning")
        if type(expected) is not int or expected not in (0, 1):
            raise ValueError("Expected interlock observation must be integer 0 or 1")
        if not isinstance(fixture_id, str) or not fixture_id.strip():
            raise ValueError("A physical fixture identity is required")
        if not isinstance(approved_by, str) or not approved_by.strip():
            raise ValueError("Commissioning approver is required")
        self._start_permit = self._configured_snapshot = None
        self.configured = False
        try:
            self.output_state = "UNKNOWN"
            if self._bool(self._query(":OUTP1?")):
                raise RuntimeError("Commissioning requires confirmed output OFF")
            self.output_state = "OFF"
            actual = int(self._bool(self._query(":SYST:INT?")))
            if actual != expected:
                raise RuntimeError(f"Expected interlock {expected}, observed {actual}")
            if expected == 0:
                self._commissioning.update(
                    ready=False,
                    fixture_id=fixture_id,
                    approved_by=approved_by,
                    open_observed=True,
                    closed_observed=False,
                    open_monotonic_s=self.clock.monotonic(),
                )
            else:
                if not (
                    self._commissioning["open_observed"]
                    and self._commissioning["fixture_id"] == fixture_id
                    and self._commissioning["approved_by"] == approved_by
                ):
                    raise RuntimeError("Observe lid-open=0 first on this connection and fixture")
                self._commissioning.update(
                    ready=True, closed_observed=True, closed_monotonic_s=self.clock.monotonic()
                )
            return self.commissioning
        except Exception:
            self._commissioning.update(ready=False, open_observed=False, closed_observed=False)
            self._start_permit = None
            raise

    def _require_real_approval(self, config):
        if bool(_get(config, "simulation", self.is_simulation)) != self.is_simulation or (
            self.identity is not None and self.identity["simulation"] != self.is_simulation
        ):
            raise UnsupportedOperation("Transport identity and approved simulation mode disagree")
        if self.is_simulation:
            return
        if not MANUAL_VERIFIED:
            raise UnsupportedOperation("The 6517A command profile must be manual verified")
        if not isinstance(config, RunConfig) or config.simulation:
            raise UnsupportedOperation("Real control requires a validated immutable real RunConfig")
        config.validate(for_arm=True)
        if config.mode != "FVMI_CURRENT":
            raise UnsupportedOperation(
                "Real native resistance has no verified current-trip channel"
            )
        record = config.commissioning
        if not (
            self._commissioning["ready"]
            and self._commissioning["fixture_id"] == record.get("fixture_id")
            and self._commissioning["approved_by"] == record.get("approved_by")
        ):
            raise RuntimeError(
                "OFF-state interlock 0/1 commissioning is required on this connection"
            )

    def _verify(self, command, expected):
        actual = self._query(command).strip().upper().strip("'\"")
        if isinstance(expected, bool):
            good = self._bool(actual) is expected
        elif isinstance(expected, (int, float)):
            good = math.isclose(self._number(actual), expected, rel_tol=1e-6, abs_tol=1e-15)
        else:
            expected = str(expected).upper()
            aliases = {
                "MANUAL": "MAN",
                "NORMAL": "NORM",
                "ASCII": "ASC",
                "IMMEDIATE": "IMM",
                "NEVER": "NEV",
                "CURRENT": "CURR",
                "CURRENT:DC": "CURR",
                "CURR:DC": "CURR",
                "RESISTANCE": "RES",
            }
            if command == ":FORM:ELEM?":
                names = {
                    "READING": "READ",
                    "STATUS": "STAT",
                    "UNITS": "UNIT",
                    "RNUMBER": "RNUM",
                    "VSOURCE": "VSO",
                }
                tokens = [names.get(token.strip(), token.strip()) for token in actual.split(",")]
                good = len(tokens) == 5 and set(tokens) == set(FORMAT.split(","))
            else:
                good = aliases.get(actual, actual) == aliases.get(expected, expected)
        if not good:
            raise ProtocolError(
                f"Setting mismatch {command}: expected {expected!r}, got {actual!r}"
            )
        return actual

    def _set(self, key, value, expected=None):
        self._write(f"{key} {value}")
        self._verify(key + "?", expected if expected is not None else value)
        self._check_errors(key)

    def _check_errors(self, context):
        errors = self.errors()
        if errors:
            raise ProtocolError(f"Instrument errors after {context}: {errors!r}")

    def _profile(self, items):
        for write, query, expected in items:
            self._write(write)
            self._verify(query, expected)
            self._check_errors(write)

    def _settle(self, seconds):
        deadline = self.clock.monotonic() + seconds
        while self.clock.monotonic() < deadline:
            if self.io_guard:
                self.io_guard()
            self.clock.sleep(min(0.05, deadline - self.clock.monotonic()))

    def errors(self):
        errors = []
        for _ in range(16):
            response = self._query(":SYST:ERR?")
            code = response.split(",", 1)[0].strip()
            if code in ("0", "+0"):
                return errors
            errors.append(response)
        raise ProtocolError("Error queue did not terminate after 16 entries: " + repr(errors))

    def configure(self, config):
        self.configured = False
        self._start_permit = self._configured_snapshot = None
        if not self._identified or self.output_state != "OFF":
            raise RuntimeError("Configuration requires identified model and confirmed output OFF")
        self._require_real_approval(config)
        self.output_state = "UNKNOWN"
        self._verify(":OUTP1?", False)
        self.output_state = "OFF"
        if hasattr(config, "validate"):
            config.validate()
        if bool(_get(config, "simulation", self.is_simulation)) != self.is_simulation:
            raise RuntimeError("Transport and approved simulation setting disagree")
        self.config = config
        self.mode = _get(config, "mode", "FVMI_CURRENT")
        self.source_range_V = _get(config, "source_range_V", 100)
        self._set(":INIT:CONT", "OFF", False)
        self._write(":TSEQ:ABOR")
        self._write(":ABOR")
        self._verify("*OPC?", 1)
        self._check_errors("abort/idle")
        self._verify(":OUTP1?", False)
        self._set(":SYST:ZCH", "ON", True)
        self._set(":SYST:ZCOR", "OFF", False)
        self._set(":SENS:RES:VSC", "MAN", "MAN")
        self._set(":SENS:RES:MSEL", "NORM", "NORM")
        # Existing standby setpoint may exceed a new limit. Zero it before range/limit enable.
        self._write(":SOUR:VOLT 0")
        self._verify(":SOUR:VOLT?", 0)
        self._check_errors("zero source setting")
        self.voltage_programmed = 0.0
        self._set(":SOUR:VOLT:RANG", self.source_range_V, self.source_range_V)
        ceiling = _get(config, "voltage_ceiling_V", 10)
        for name in ("sample_limit_V", "fixture_limit_V", "cable_limit_V"):
            value = _get(config, name)
            if value is not None:
                ceiling = min(ceiling, value)
        self._set(":SOUR:VOLT:LIM", ceiling, ceiling)
        self._set(":SOUR:VOLT:LIM:STAT", "ON", True)
        self._set(":SOUR:VOLT:MCON", "ON", True)
        resistive_limit = _get(config, "resistive_limit_enabled", False) is True
        self._set(":SOUR:CURR:RLIM:STAT", "ON" if resistive_limit else "OFF", resistive_limit)
        native = self.mode == "NATIVE_RESISTANCE"
        self._set(":SENS:FUNC", "'RES'" if native else "'CURR'", "RES" if native else "CURR")
        range_key = ":SENS:RES:MAN:CRANG" if native else ":SENS:CURR:RANG"
        auto = _get(config, "current_autorange", True)
        self._set(range_key + ":AUTO", "OFF", False)
        # 2-60: zero correction survives uprange, requires re-zero on downrange.
        # Start auto-ranging from the lowest 20 pA range so it never goes below zeroed range.
        zero_range = 20e-12 if auto else _get(config, "current_range_A", 2e-9)
        self._set(range_key, zero_range, zero_range)
        zero_range_readback = self._number(self._query(range_key + "?"))
        self._profile(COMMON_PROFILE)
        self._profile(ONE_SHOT_PROFILE)
        self._profile(function_profile(native))
        nplc_key = ":SENS:RES:NPLC" if native else ":SENS:CURR:NPLC"
        self._set(nplc_key, _get(config, "nplc", 10), _get(config, "nplc", 10))
        self.transport.line_frequency_hz = _get(config, "line_frequency_hz", 60)
        self._set(":FORM:DATA", "ASC", "ASC")
        self._set(":FORM:ELEM", FORMAT, FORMAT)
        settle_s = _get(config, "range_settle_s", 0.2)
        self._settle(settle_s)
        self._verify(":OUTP1?", False)
        self._verify(":SYST:ZCH?", True)
        self._write(":SYST:ZCOR:ACQ")
        self._verify("*OPC?", 1)
        self._check_errors("zero correction acquire")
        self._set(":SYST:ZCH", "OFF", False)
        self._set(":SYST:ZCOR", "ON", True)
        self._set(range_key + ":AUTO", "ON" if auto else "OFF", auto)
        self._verify(":SENS:RES:VSC?", "MAN")
        self._verify(":SOUR:VOLT?", 0)
        self._check_errors("final configuration")
        status = self.safety_status()
        if status["output_state"] != "OFF" or status["interlock"] != 1 or status["zero_check"]:
            raise ProtocolError("Configuration did not establish required safe state")
        if not self.is_simulation and status.get("fixture_installation_confirmed") is False:
            raise ProtocolError("Installed interlock commissioning is missing")
        self.configured = True
        self._configured_snapshot = _snapshot(config)
        return {
            "source_range_V": self.source_range_V,
            "voltage_ceiling_V": ceiling,
            "manual_vsource": True,
            "normal_resistance": True,
            "zero_correct_range_A": zero_range_readback,
            "zero_settle_requested_s": settle_s,
            "zero_correct_time_monotonic_s": self.clock.monotonic(),
            "zero_correct_temperature_C": _get(config, "temperature_C"),
            "zero_correct_valid_for_uprange_per_manual": True,
            "zero_correct_native_mode_hardware_verified": False,
            "nplc": _get(config, "nplc", 10),
            "line_frequency_hz": _get(config, "line_frequency_hz", 60),
            "line_frequency_basis": "USER_PROVIDED_NOT_INDEPENDENTLY_QUERIED",
            "one_shot": True,
            "manual_revision": MANUAL_REVISION,
            "manual_sha256": MANUAL_SHA256,
            "hardware_verified": False,
            "commissioning": self.commissioning,
            "resistive_limit_enabled": resistive_limit,
        }

    def authorize_start(self, config):
        """One-use START permit; configuration/connection alone cannot enable output."""
        self._start_permit = None
        if not self.configured or self._configured_snapshot != _snapshot(config):
            raise RuntimeError("START requires the exact configured immutable snapshot")
        self._require_real_approval(config)
        status = self.safety_status()
        if (
            status["output_state"] != "OFF"
            or status["interlock"] != 1
            or status["current_limit"]
            or status["zero_check"]
            or status.get("fixture_installation_confirmed") is False
        ):
            raise RuntimeError("START safety authorization failed")
        self._verify(":SOUR:VOLT?", 0)
        self._verify(":SENS:RES:VSC?", "MAN")
        self._check_errors("START authorization")
        self._start_permit = self._configured_snapshot

    def output_on(self):
        permit, self._start_permit = self._start_permit, None
        if permit is None or permit != self._configured_snapshot:
            raise RuntimeError("Explicit one-use START authorization required")
        if self._configured_snapshot != _snapshot(self.config):
            raise RuntimeError("Configuration changed after START authorization")
        self._require_real_approval(self.config)
        if not self.configured or self.output_state != "OFF" or self.voltage_programmed != 0:
            raise RuntimeError(
                "START requires configured instrument, confirmed OFF and zero setpoint"
            )
        status = self.safety_status()
        if (
            status["output_state"] != "OFF"
            or status["interlock"] != 1
            or status["current_limit"]
            or status["zero_check"]
            or status.get("fixture_installation_confirmed") is False
        ):
            raise RuntimeError("START safety checks failed")
        self._verify(":SOUR:VOLT?", 0)
        self._check_errors("output enable")
        self.output_state = "UNKNOWN"
        self._write(":OUTP1 ON")
        self._verify(":OUTP1?", True)
        self.output_state = "ON"

    def set_voltage(self, voltage):
        if not self.configured:
            raise UnsupportedOperation("Source writes require validated configuration")
        self._require_real_approval(self.config)
        if not math.isfinite(voltage):
            raise ValueError("Non-finite voltage")
        ceiling = _get(self.config, "voltage_ceiling_V", 10)
        for name in ("sample_limit_V", "fixture_limit_V", "cable_limit_V"):
            rating = _get(self.config, name)
            if rating is not None:
                ceiling = min(ceiling, rating)
        if abs(voltage) > min(1000, ceiling, self.source_range_V):
            raise ValueError("Voltage ceiling exceeded")
        if voltage < 0 and not _get(self.config, "bipolar_authorized", False):
            raise ValueError("Negative voltage is not authorized")
        status = self.safety_status()
        if status["interlock"] != 1 or status["current_limit"] or status["zero_check"]:
            raise RuntimeError("Voltage change blocked by safety status")
        resolution = 0.005 if self.source_range_V == 100 else 0.05
        if hasattr(self.config, "quantize_voltage"):
            programmed = self.config.quantize_voltage(voltage)
        else:
            step = Decimal(str(resolution))
            programmed = float(
                (Decimal(str(voltage)) / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * step
            )
        if abs(programmed) > min(1000, ceiling, self.source_range_V):
            raise ValueError("Quantized voltage ceiling exceeded")
        self._write(f":SOUR:VOLT {programmed:.8g}")
        actual = self._number(self._query(":SOUR:VOLT?"))
        if abs(actual - programmed) > resolution / 2 + 1e-10:
            raise ProtocolError("Voltage readback mismatch/clamp")
        self._check_errors("source voltage step")
        self.voltage_programmed = actual
        return actual

    def safety_status(self):
        if not self._identified:
            raise RuntimeError("Identify model before control/status queries")
        start = self.clock.monotonic()
        try:
            self.output_state = "ON" if self._bool(self._query(":OUTP1?")) else "OFF"
            current_limit = self._bool(self._query(":SOUR:CURR:LIM:STAT?"))
            interlock = int(self._bool(self._query(":SYST:INT?")))
            zero_check = self._bool(self._query(":SYST:ZCH?"))
            zero_correct = self._bool(self._query(":SYST:ZCOR?"))
            range_query = (
                ":SENS:RES:MAN:CRANG?" if self.mode == "NATIVE_RESISTANCE" else ":SENS:CURR:RANG?"
            )
            current_range = self._number(self._query(range_query))
        except Exception:
            self.output_state = "UNKNOWN"
            self.configured = False
            self._start_permit = None
            self._commissioning.update(ready=False, open_observed=False, closed_observed=False)
            raise
        self.last_safety = {
            "output_state": self.output_state,
            "current_limit": current_limit,
            "interlock": interlock,
            "zero_check": zero_check,
            "zero_correct": zero_correct,
            "current_range": current_range,
            "query_start_monotonic_s": start,
            "query_end_monotonic_s": self.clock.monotonic(),
            "atomic_snapshot": False,
            "fixture_installation_confirmed": self._commissioning["ready"],
        }
        if interlock != 1 or current_limit:
            self._commissioning.update(ready=False, open_observed=False, closed_observed=False)
            self._start_permit = None
            self.configured = False
        if self.is_simulation:
            self.last_safety["fixture_installation_confirmed"] = not self.transport.faults.get(
                "cable_absent", False
            )
        return self.last_safety

    def read(self, mode=None):
        if not self.configured:
            raise RuntimeError("Configure before READ")
        response = self._query(":READ?")
        parsed = parse_reading(response, mode or self.mode)
        if parsed.reading_number < 0:
            raise ProtocolError("Negative RNUM is a pre-trigger buffer reading, not live READ data")
        if (
            self.last_reading_number is not None
            and parsed.reading_number <= self.last_reading_number
        ):
            raise ProtocolError("STALE_READING: repeated/backwards RNUM; abort rather than retry")
        self.last_reading_number = parsed.reading_number
        resolution = 0.005 if self.source_range_V == 100 else 0.05
        expected_source = self.voltage_programmed if self.output_state == "ON" else 0.0
        if abs(parsed.voltage_reported - expected_source) > resolution / 2 + 1e-10:
            raise ProtocolError("Reported source setting mismatch")
        return parsed

    def safe_off(self):
        self.output_state = "UNKNOWN"
        self.configured = False
        self._start_permit = self._configured_snapshot = None
        self._commissioning.update(ready=False, open_observed=False, closed_observed=False)
        errors = []
        if not self._identified:
            return ["Model unverified; no model-specific writes sent"]
        actions = [
            ("cancel_io", self.transport.cancel_or_abort_io_if_supported),
            ("output_off_first", lambda: self._write(":OUTP1 OFF", safety=True)),
            ("test_sequence_abort", lambda: self._write(":TSEQ:ABOR", safety=True)),
            ("continuous_off", lambda: self._write(":INIT:CONT OFF", safety=True)),
            ("abort", lambda: self._write(":ABOR", safety=True)),
            ("output_off_second", lambda: self._write(":OUTP1 OFF", safety=True)),
        ]
        for name, action in actions:
            try:
                action()
            except Exception as exc:
                errors.append(f"{name}: {type(exc).__name__}: {exc}")
        try:
            if not self._bool(self._query(":OUTP1?", safety=True)):
                self.output_state = "OFF"
            else:
                errors.append("Output still ON after OFF attempts")
        except Exception as exc:
            errors.append(f"confirm_off: {type(exc).__name__}: {exc}")
        # No zero-check/configuration write here can delay protective OFF.
        return errors

    def close(self):
        errors = self.safe_off() if self._identified else []
        try:
            self.transport.close()
        finally:
            self._identified = False
            self.configured = False
        return errors
