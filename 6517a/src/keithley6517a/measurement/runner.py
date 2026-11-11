"""One worker owns every instrument call; cross-thread STOP only sets an Event."""

from __future__ import annotations

import hashlib
import math
import subprocess
import threading
from collections import deque
from pathlib import Path

from .. import __version__
from ..clock import Clock
from ..config import RunConfig
from ..storage.run_writer import RunWriter
from .analysis import analyze_reading, summarize


class MeasurementError(RuntimeError):
    pass


class StopRequested(MeasurementError):
    pass


class MeasurementRunner:
    def __init__(
        self,
        config: RunConfig,
        instrument=None,
        clock=None,
        writer_factory=None,
        on_sample=None,
        on_event=None,
    ):
        self._config = config
        self.clock = clock or Clock()
        self.writer_factory = writer_factory or RunWriter
        self.on_sample = on_sample
        self.on_event = on_event
        self.state = "DISCONNECTED"
        self.output_state = "UNKNOWN"
        self.residual_voltage_state = "UNVERIFIED"
        self.identity = {}
        self.run_directory = None
        self.rows = []
        self.summaries = []
        self.events = deque(maxlen=10000)
        self._transcript = deque(maxlen=10000)
        self._stop = threading.Event()
        self._stop_reason = "user stop"
        self._owner = None
        self.writer = None
        self._storage_error = None
        self._started = False
        self._connected = False
        self._armed_config = None
        self._last_number = None
        self._start_time = None
        self._next_safety_poll = 0.0
        if instrument is None:
            from ..driver.instrument import Instrument

            if config.simulation:
                from ..transport.simulator import SimulatorTransport

                transport = SimulatorTransport(clock=self.clock, seed=config.seed)
            else:
                from ..transport.visa import VisaTransport

                transport = VisaTransport(
                    config.resource,
                    backend=config.visa_backend,
                    timeout_ms=config.timeout_ms,
                    read_termination=config.read_termination,
                    write_termination=config.write_termination,
                    send_end=config.send_end,
                )
            instrument = Instrument(transport, self.clock, io_callback=self._io)
        self.instrument = instrument
        # Test-injected instruments still use the same logging path.
        if hasattr(self.instrument, "io_callback"):
            self.instrument.io_callback = self._io
        self.instrument.io_guard = self._checkpoint

    @property
    def config(self):
        """Read-only even from non-GUI callers; execution cannot replace the approval."""
        return self._config

    @property
    def can_arm(self):
        return (
            self.state == "OUTPUT_OFF_CONFIRMED"
            and not self._started
            and (self.config.simulation or self.commissioning.get("ready") is True)
        )

    @property
    def can_start(self):
        return self.state == "ARMED" and not self._started

    @property
    def commissioning(self):
        return dict(getattr(self.instrument, "commissioning", {}))

    def commission_interlock(self, expected: int):
        """OFF-only observation; it never tests the lid by energizing the source."""
        self._check_owner()
        if self.state != "OUTPUT_OFF_CONFIRMED" or self._started:
            raise MeasurementError("Interlock observations require a fresh OFF connection")
        if type(expected) is not int or expected not in (0, 1):
            raise MeasurementError("Expected interlock observation must be 0 or 1")
        fixture = self.config.commissioning.get("fixture_id", "")
        approver = self.config.commissioning.get("approved_by", "")
        if not fixture or not approver:
            raise MeasurementError("Fixture identity and commissioning approver are required")
        try:
            result = self.instrument.commission_interlock(expected, fixture, approver)
            self.output_state = self.instrument.output_state
            self._event(
                "interlock_commissioning",
                expected=expected,
                commissioning=self.commissioning,
                output_state=self.output_state,
            )
            return result
        except Exception as exc:
            self._event("interlock_commissioning_failed", expected=expected, reason=str(exc))
            self._safe_off()
            self._state("FAULT" if self.output_state == "OFF" else "HV_STATE_UNKNOWN")
            raise

    def _check_owner(self):
        owner = threading.get_ident()
        if self._owner is None:
            self._owner = owner
        if self._owner != owner:
            raise MeasurementError("Instrument I/O belongs to a single worker thread")

    def _io(self, item):
        item = dict(
            item,
            wall_time_iso8601=self.clock.wall_time(),
            monotonic_s=self.clock.monotonic(),
            simulation=self.config.simulation,
        )
        self._transcript.append(item)
        if self.writer and not self.writer.closed:
            try:
                self.writer.raw_io(item)
            except Exception as exc:
                # Logging failures must not prevent OFF writes in the safety path.
                self._storage_error = exc

    def _event(self, event, **values):
        item = dict(
            event=event,
            wall_time_iso8601=self.clock.wall_time(),
            monotonic_s=self.clock.monotonic(),
            **values,
        )
        self.events.append(item)
        if self.writer and not self.writer.closed:
            try:
                self.writer.event(item)
            except Exception as exc:
                self._storage_error = exc
        if self.on_event:
            try:
                self.on_event(item)
            except Exception as exc:
                self._storage_error = exc

    def _state(self, state):
        self.state = state
        self._event(
            "state",
            state=state,
            output_state=self.output_state,
            residual_voltage_state=self.residual_voltage_state,
        )

    def _checkpoint(self):
        if self._stop.is_set():
            raise StopRequested(self._stop_reason)
        if self._storage_error:
            raise MeasurementError(f"Storage/callback failed: {self._storage_error}")
        if self._start_time is not None:
            if self.clock.monotonic() - self._start_time >= self.config.max_total_duration_s:
                raise MeasurementError("Maximum total run duration exceeded")

    def _wait_until(self, deadline):
        while self.clock.monotonic() < deadline:
            self._checkpoint()
            if self.output_state == "ON" and self.clock.monotonic() >= self._next_safety_poll:
                status = self.instrument.safety_status()
                self._validate_status(status, expected_output="ON")
                self._next_safety_poll = self.clock.monotonic() + 0.25
            remaining = deadline - self.clock.monotonic()
            if remaining > 0:
                self.clock.sleep(min(0.05, remaining))
        self._checkpoint()

    def connect(self):
        self._check_owner()
        if self.state != "DISCONNECTED":
            raise MeasurementError("Disconnect before changing the connection")
        if self.config.simulation != self.instrument.is_simulation:
            raise MeasurementError("Configuration and transport disagree about simulation mode")
        # Explicit reconnection creates a new experiment context; it never replays old writes.
        self._stop.clear()
        self._started = False
        self._storage_error = self._armed_config = self._last_number = self._start_time = None
        self._next_safety_poll = 0.0
        self.writer = None
        self.run_directory = None
        self.rows.clear()
        self.summaries.clear()
        self.events.clear()
        self._transcript.clear()
        self._state("CONNECTED_UNVERIFIED")
        try:
            self.identity = self.instrument.connect()
            self._connected = True
            self.output_state = self.instrument.output_state
            if self.output_state != "OFF":
                raise MeasurementError("Takeover could not confirm output OFF; isolate locally")
            self._state("OUTPUT_OFF_CONFIRMED")
            return self.identity
        except Exception:
            # The driver never sends model-specific writes to a different model.
            self.output_state = getattr(self.instrument, "output_state", "UNKNOWN")
            self._state("HV_STATE_UNKNOWN" if self.output_state != "OFF" else "FAULT")
            raise

    def _safe_off(self):
        errors = []
        failed = False
        try:
            errors = self.instrument.safe_off() or []
        except Exception as exc:
            failed = True
            errors.append(str(exc))
        self.output_state = (
            "UNKNOWN" if failed else getattr(self.instrument, "output_state", "UNKNOWN")
        )
        self._event(
            "output_stop",
            errors=[str(e) for e in errors],
            output_state=self.output_state,
            residual_voltage_state="UNVERIFIED",
        )
        return errors

    def arm(self):
        self._check_owner()
        if self.state != "OUTPUT_OFF_CONFIRMED" or self._started:
            raise MeasurementError("ARM requires a fresh connection with confirmed output OFF")
        self.config.validate(for_arm=True)
        self._checkpoint()
        self._state("CONFIGURING")
        try:
            settings_readback = self.instrument.configure(self.config)
            status = self.instrument.safety_status()
            self._validate_status(status, expected_output="OFF")
            # Static approval records cannot replace OFF-only observations on this connection.
            self._armed_config = RunConfig.from_dict(self.config.to_dict())
            try:
                commit = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=True,
                ).stdout.strip()
                dirty = bool(
                    subprocess.run(
                        ["git", "status", "--porcelain"],
                        capture_output=True,
                        text=True,
                        timeout=2,
                        check=True,
                    ).stdout.strip()
                )
            except (OSError, subprocess.SubprocessError):
                commit = None
                dirty = None
            source_digest = hashlib.sha256()
            source_root = Path(__file__).resolve().parents[1]
            for path in sorted(source_root.rglob("*.py")):
                source_digest.update(path.relative_to(source_root).as_posix().encode())
                source_digest.update(path.read_bytes())
            metadata = dict(
                schema_version=1,
                software_version=__version__,
                software_commit=commit,
                software_working_tree_dirty=dirty,
                software_source_sha256=source_digest.hexdigest(),
                identity=self.identity,
                simulation=self.config.simulation,
                sample=self.config.to_dict()["sample_metadata"],
                commissioning=self.config.to_dict()["commissioning"],
                connection_commissioning=self.commissioning,
                rating_approval=self.config.rating_approval,
                temperature_C=self.config.temperature_C,
                relative_humidity_percent=self.config.relative_humidity_percent,
                safety_status_not_atomic=True,
                voltage_basis="programmed source setting, not independently measured DUT voltage",
                source_current_limit="Fixed hardware limits; software trip is not compliance",
                residual_voltage_state="UNVERIFIED",
                simulation_truth=getattr(self.instrument.transport, "truth", None),
                settings=self.config.to_dict(),
                settings_readback=settings_readback,
            )
            self.writer = self.writer_factory(self._armed_config, metadata)
            self.run_directory = self.writer.directory
            for item in self._transcript:
                self.writer.raw_io(item)
            for item in self.events:
                self.writer.event(item)
            self._checkpoint()
            self._state("ARMED")
        except Exception as exc:
            self._event("arm_failed", reason=str(exc))
            self._safe_off()
            self._state("FAULT" if self.output_state == "OFF" else "HV_STATE_UNKNOWN")
            self._finalize("aborted", str(exc))
            raise

    def request_stop(self, reason="user stop"):
        """Only cross-thread operation; never opens a second VISA session or performs I/O."""
        self._stop_reason = str(reason)
        self._stop.set()

    def _validate_status(self, status, expected_output=None):
        self.output_state = status.get("output_state", "UNKNOWN")
        if self.output_state == "UNKNOWN":
            raise MeasurementError("Output unknown; local physical isolation may be necessary")
        if expected_output and self.output_state != expected_output:
            raise MeasurementError(f"Expected output {expected_output}, got {self.output_state}")
        if status.get("interlock") != 1:
            raise MeasurementError("Interlock open or unknown; reapproval required")
        if status.get("fixture_installation_confirmed") is False:
            raise MeasurementError("Interlock cable absent; query=1 is not commissioning")
        if status.get("current_limit") is not False:
            raise MeasurementError("Source current limit active or unknown")
        if status.get("zero_check") is not False:
            raise MeasurementError("Zero Check active or unknown")

    def start(self):
        self._check_owner()
        if self.state != "ARMED" or self._started:
            raise MeasurementError("Explicit ARM is required before START")
        if self.config != self._armed_config:
            raise MeasurementError("Run configuration differs from approved immutable snapshot")
        self._started = True
        self._start_time = self.clock.monotonic()
        result, reason = "completed", "Schedule completed"
        try:
            self._checkpoint()
            self._validate_status(self.instrument.safety_status(), expected_output="OFF")
            # Configure guarantees a zero setpoint; explicitly verify again before enabling.
            actual = self.instrument.set_voltage(0.0)
            if abs(actual) > 1e-9:
                raise MeasurementError("Zero setpoint not confirmed before output ON")
            self._checkpoint()
            self.writer.status("running", "Explicit START", "OFF")
            self._checkpoint()
            self.instrument.authorize_start(self._armed_config)
            self._checkpoint()
            self.instrument.output_on()
            self._validate_status(self.instrument.safety_status(), expected_output="ON")
            for cycle in range(self.config.cycles):
                for index, voltage in enumerate(self.config.voltages):
                    self._checkpoint()
                    self._validate_status(self.instrument.safety_status(), expected_output="ON")
                    self._run_step(cycle, index, voltage)
        except Exception as exc:
            result, reason = "aborted", str(exc)
            self._event("abort", reason=reason, exception=type(exc).__name__)
            if not isinstance(exc, StopRequested):
                self._record_error_sample(reason)
        finally:
            self._state("STOPPING")
            self._safe_off()
            if self.output_state != "OFF":
                result = "aborted"
                reason += "; output OFF unconfirmed: HV_STATE_UNKNOWN"
                self._state("HV_STATE_UNKNOWN")
            elif result == "aborted":
                self._state("FAULT")
            else:
                self._state("OUTPUT_OFF_CONFIRMED")
            if self._storage_error:
                result = "aborted"
                reason += f"; persistence failed: {self._storage_error}"
                if self.output_state == "OFF":
                    self._state("FAULT")
            self._finalize(result, reason)
            if self._storage_error:
                result = "aborted"
                reason = f"{reason}; final persistence failed: {self._storage_error}"
                if self.output_state == "OFF":
                    self._state("FAULT")
        return dict(
            status=result,
            reason=reason,
            run_directory=str(self.run_directory),
            output_state=self.output_state,
            residual_voltage_state="UNVERIFIED",
        )

    def _run_step(self, cycle, index, voltage):
        self._state("RAMPING")
        self._checkpoint()
        command_start = self.clock.monotonic()
        programmed = self.instrument.set_voltage(voltage)
        command_end = self.clock.monotonic()
        expected = self.config.quantize_voltage(voltage)
        if not math.isfinite(programmed) or abs(programmed - expected) > 1e-7:
            raise MeasurementError("Source setting readback mismatch/clamp")
        self._event(
            "voltage_step",
            step_index=index,
            cycle_index=cycle,
            voltage_requested_V=voltage,
            voltage_quantized_V=expected,
            voltage_programmed_readback_V=programmed,
            command_start_monotonic_s=command_start,
            command_complete_monotonic_s=command_end,
            electrical_transition_time_independently_measured=False,
        )
        step_rows = []
        deadline = command_end + self.config.dwell_s
        next_sample = command_end
        last_range = None
        range_invalid_until = command_end
        previous_read_start = None
        while self.clock.monotonic() < deadline:
            self._wait_until(min(next_sample, deadline))
            if self.clock.monotonic() >= deadline:
                break
            before = self.instrument.safety_status()
            self._validate_status(before, expected_output="ON")
            read_start = self.clock.monotonic()
            parsed = self.instrument.read(self.config.mode)
            read_end = self.clock.monotonic()
            after = self.instrument.safety_status()
            self.output_state = after.get("output_state", "UNKNOWN")
            flags = list(parsed.flags)
            trip_current = parsed.value
            if self.config.mode == "NATIVE_RESISTANCE":
                trip_current = programmed / parsed.value if parsed.value not in (None, 0) else None
            software_trip = (
                trip_current is not None and abs(trip_current) >= self.config.current_trip_A
            )
            power_trip = (
                trip_current is not None
                and self.config.power_limit_W is not None
                and abs(programmed * trip_current) >= self.config.power_limit_W
            )
            if software_trip:
                flags.append("SOFTWARE_CURRENT_TRIP")
            if power_trip:
                flags.append("SOFTWARE_POWER_TRIP")
            if after.get("interlock") != 1:
                flags.append("INTERLOCK_OPEN_OR_UNKNOWN")
            if after.get("fixture_installation_confirmed") is False:
                flags.append("INTERLOCK_INSTALLATION_UNCONFIRMED")
            if self.output_state != "ON":
                flags.append("OUTPUT_NOT_ON")
            since_step = read_end - command_end
            if parsed.reading_number is None or (
                self._last_number is not None and parsed.reading_number <= self._last_number
            ):
                flags.append("STALE_OR_DUPLICATE_READING")
            elif self._last_number is not None and parsed.reading_number != self._last_number + 1:
                flags.append("READING_NUMBER_GAP_NOT_PROOF_OF_LOSS")
            self._last_number = parsed.reading_number
            if parsed.voltage_reported is None or abs(parsed.voltage_reported - programmed) > 1e-7:
                flags.append("VOLTAGE_READBACK_MISMATCH")
            current_range = after.get("current_range")
            prior_range = before.get("current_range") if last_range is None else last_range
            if current_range != prior_range or current_range != before.get("current_range"):
                range_invalid_until = read_end + self.config.range_settle_s
                flags.append("RANGE_CHANGE_TIMING_UNCERTAIN")
                self._event(
                    "range_change",
                    previous_range_A=prior_range,
                    current_range_A=current_range,
                    previous_status_query_monotonic_s=read_start,
                    excluded_until_monotonic_s=range_invalid_until,
                )
            last_range = current_range
            phase = "ACQUIRING"
            if since_step < self.config.exclude_initial_s or read_end < range_invalid_until:
                phase = "SETTLING"
                flags.append("SETTLING_EXCLUDED")
            if since_step < max(
                self.config.min_dwell_s, self.config.dwell_s - self.config.summary_window_s
            ):
                flags.append("OUTSIDE_SUMMARY_WINDOW")
            if since_step > self.config.dwell_s:
                flags.append("AFTER_DWELL")
            self._state(phase)
            analysis = analyze_reading(
                self.config,
                parsed.value,
                voltage_V=programmed,
                status=parsed.status,
                flags=flags,
                current_limit=after.get("current_limit") is not False,
                zero_check=after.get("zero_check") is not False,
            )
            row = dict(
                sample_id=self.config.sample_id,
                mode=self.config.mode,
                step_index=index,
                cycle_index=cycle,
                phase=phase,
                wall_time_iso8601=self.clock.wall_time(),
                elapsed_s=read_end - self._start_time,
                time_since_voltage_command_s=since_step,
                read_start_monotonic_s=read_start,
                read_end_monotonic_s=read_end,
                actual_sample_interval_s=None
                if previous_read_start is None
                else read_start - previous_read_start,
                voltage_requested_V=voltage,
                voltage_programmed_readback_V=programmed,
                voltage_reported_by_instrument_V=parsed.voltage_reported,
                **analysis,
                current_range_A=current_range,
                source_range_V=self.config.source_range_V,
                nplc=self.config.nplc,
                source_output_state=self.output_state,
                source_current_limit_state=after.get("current_limit"),
                interlock_query=after.get("interlock"),
                zero_check_state=after.get("zero_check"),
                zero_correct_state=after.get("zero_correct"),
                status_code=parsed.status,
                reading_number=parsed.reading_number,
                temperature_C=self.config.temperature_C,
                relative_humidity_percent=self.config.relative_humidity_percent,
                raw_response=parsed.raw,
                status_query_start_monotonic_s=read_end,
                status_query_end_monotonic_s=self.clock.monotonic(),
            )
            previous_read_start = read_start
            self.rows.append(row)
            step_rows.append(row)
            self.writer.sample(row)
            if self.on_sample:
                self.on_sample(dict(row))
            self._checkpoint()
            self._validate_status(after, expected_output="ON")
            if software_trip:
                raise MeasurementError("Software current trip (not programmable compliance)")
            if power_trip:
                raise MeasurementError("Software power trip")
            fatal = {"STALE_OR_DUPLICATE_READING", "VOLTAGE_READBACK_MISMATCH", "ZERO_NATIVE_R"}
            if programmed != 0 or self.config.mode == "FVMI_CURRENT":
                fatal.update({"SENTINEL", "ZERO_CHECK_SENTINEL"})
            if fatal.intersection(row["quality_flags"]) or parsed.status != "N":
                raise MeasurementError(
                    "Invalid instrument state/reading: " + str(row["quality_flags"])
                )
            next_sample = max(next_sample + self.config.sample_interval_s, read_end)
        summary = summarize(self.config, step_rows)
        summary.update(step_index=index, cycle_index=cycle, voltage_requested_V=voltage)
        self.summaries.append(summary)
        self.writer.summaries(self.summaries)
        self._event("step_summary", **summary)

    def _record_error_sample(self, reason):
        row = dict(
            sample_id=self.config.sample_id,
            mode=self.config.mode,
            phase="ERROR",
            wall_time_iso8601=self.clock.wall_time(),
            elapsed_s=self.clock.monotonic() - self._start_time,
            valid_for_summary=False,
            quality_flags=["RUN_ABORTED", reason],
            source_output_state=self.output_state,
        )
        self.rows.append(row)
        try:
            if self.writer:
                self.writer.sample(row)
        except Exception as exc:
            self._storage_error = exc

    def _finalize(self, result, reason):
        if self.writer:
            try:
                self.writer.status(
                    result,
                    reason,
                    self.output_state,
                    software_state=self.state,
                    wall_time_iso8601=self.clock.wall_time(),
                )
            except Exception as exc:
                self._storage_error = exc
                self.events.append(dict(event="status_persistence_failed", reason=str(exc)))
            finally:
                self.writer.close()

    def shutdown(self):
        self._check_owner()
        self.request_stop("GUI close/disconnect")
        if self._connected:
            self._safe_off()
            if self.writer and not self.writer.closed:
                self._finalize("aborted", "Disconnected before completion")
        try:
            self.instrument.close()
        finally:
            self.output_state = getattr(self.instrument, "output_state", "UNKNOWN")
            self._connected = False
            self._state("DISCONNECTED" if self.output_state == "OFF" else "HV_STATE_UNKNOWN")
            if self.output_state != "OFF" and self.writer:
                self._finalize("aborted", "Final disconnect could not confirm output OFF")
