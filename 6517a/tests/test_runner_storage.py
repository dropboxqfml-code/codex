import csv
import json
import threading
from dataclasses import replace

import pytest

from keithley6517a.clock import FakeClock
from keithley6517a.config import RunConfig
from keithley6517a.driver.instrument import Instrument
from keithley6517a.measurement.runner import MeasurementError, MeasurementRunner
from keithley6517a.storage.run_writer import RunWriter, recover_incomplete_runs, strict_json
from keithley6517a.transport.simulator import SimulatorTransport


def setup_runner(tmp_path, *, faults=None, callback=None, writer_factory=None, **options):
    settings = dict(
        output_directory=str(tmp_path),
        voltages=[1, 2],
        protocol="list",
        dwell_s=1,
        summary_window_s=1,
        sample_interval_s=0.1,
        nplc=1,
        current_trip_A=1e-7,
        residual_warning_ack=True,
    )
    config = RunConfig.from_dict(dict(settings, **options))
    clock = FakeClock()
    transport = SimulatorTransport(clock=clock, faults=faults, noise_A=0, absorption_A=0)
    instrument = Instrument(transport, clock)
    runner = MeasurementRunner(
        config,
        instrument=instrument,
        clock=clock,
        on_sample=callback,
        writer_factory=writer_factory,
    )
    return runner, transport, clock


def completed(runner):
    runner.connect()
    runner.arm()
    return runner.start()


def source_writes(transport):
    return [c for c in transport.commands if c.startswith(":SOUR:VOLT ")]


def test_complete_streaming_artifacts_unique_runs_and_strict_roundtrip(tmp_path):
    runner, transport, _ = setup_runner(tmp_path)
    result = completed(runner)
    assert result["status"] == "completed"
    assert result["output_state"] == "OFF"
    assert result["residual_voltage_state"] == "UNVERIFIED"
    directory = runner.run_directory
    expected = {
        "config.json",
        "metadata.json",
        "readings.csv",
        "summary.csv",
        "events.jsonl",
        "raw_io.jsonl",
        "run_status.json",
    }
    assert expected <= {p.name for p in directory.iterdir()}
    assert RunConfig.load(directory / "config.json") == runner.config
    for path in directory.glob("*.json"):
        json.loads(path.read_text(), parse_constant=lambda _: pytest.fail("Nonstandard JSON"))
    rows = list(csv.DictReader((directory / "readings.csv").open()))
    assert len(rows) >= 20
    assert all(float(r["read_end_monotonic_s"]) >= float(r["read_start_monotonic_s"]) for r in rows)
    summary = list(csv.DictReader((directory / "summary.csv").open()))
    assert len(summary) == 2
    assert all(float(r["R_from_mean_current_ohm"]) > 9e11 for r in summary)
    assert all(r["native_r_ohm"] == "" for r in rows)
    assert all(
        json.loads(line)["simulation"]
        for line in (directory / "raw_io.jsonl").read_text().splitlines()
    )
    assert transport.commands.count(":OUTP1 ON") == 1
    runner.shutdown()
    another, _, _ = setup_runner(tmp_path)
    completed(another)
    assert another.run_directory != directory
    another.shutdown()


def test_explicit_arm_start_and_no_on_for_load_connect_shutdown(tmp_path):
    runner, transport, _ = setup_runner(tmp_path)
    assert not transport.commands
    with pytest.raises(MeasurementError):
        runner.start()
    runner.connect()
    assert ":OUTP1 ON" not in transport.commands
    runner.arm()
    assert ":OUTP1 ON" not in transport.commands
    runner.shutdown()
    assert ":OUTP1 ON" not in transport.commands
    assert json.loads((runner.run_directory / "run_status.json").read_text())["status"] == "aborted"


@pytest.mark.parametrize(
    "fault",
    [
        "timeout_at_read",
        "malformed_at_read",
        "stale_at_read",
        "overflow_at_read",
        "underflow_at_read",
        "current_limit_at_read",
    ],
)
def test_fault_aborts_no_later_voltage_and_best_effort_off(tmp_path, fault):
    runner, transport, _ = setup_runner(tmp_path, faults={fault: 2})
    result = completed(runner)
    assert result["status"] == "aborted"
    assert runner.state == "FAULT"
    assert result["output_state"] == "OFF"
    assert ":SOUR:VOLT 2" not in source_writes(transport)
    assert any(c == ":OUTP1 OFF" for c in transport.commands[-8:])
    assert any(r.get("phase") == "ERROR" for r in runner.rows)


def test_usb_disconnect_keeps_hv_unknown_and_physical_source_may_remain_on(tmp_path):
    runner, transport, _ = setup_runner(tmp_path, faults={"disconnect_at_read": 2})
    result = completed(runner)
    assert result["status"] == "aborted"
    assert runner.state == "HV_STATE_UNKNOWN"
    assert runner.output_state == "UNKNOWN"
    assert transport.output  # disconnect cannot be equated to source OFF
    assert result["residual_voltage_state"] == "UNVERIFIED"


def test_software_trip_invalidates_sample_and_no_voltage_increase(tmp_path):
    runner, transport, _ = setup_runner(tmp_path, current_trip_A=5e-13)
    result = completed(runner)
    assert result["status"] == "aborted"
    assert "SOFTWARE_CURRENT_TRIP" in runner.rows[0]["quality_flags"]
    assert runner.rows[0]["valid_for_summary"] is False
    assert runner.rows[0]["resistance_apparent_ohm"] is None
    assert ":SOUR:VOLT 2" not in source_writes(transport)


def test_source_limit_invalidates_r(tmp_path):
    runner, _, _ = setup_runner(tmp_path, faults={"current_limit_at_read": 1})
    assert completed(runner)["status"] == "aborted"
    assert "SOURCE_CURRENT_LIMIT" in runner.rows[0]["quality_flags"]
    assert not runner.rows[0]["valid_for_summary"]
    assert runner.rows[0]["resistance_apparent_ohm"] is None


def test_interlock_one_cable_absent_cannot_arm(tmp_path):
    runner, transport, _ = setup_runner(tmp_path, faults={"cable_absent": True})
    runner.connect()
    with pytest.raises(MeasurementError, match="cable absent"):
        runner.arm()
    assert ":OUTP1 ON" not in transport.commands
    assert runner.output_state == "OFF"


def test_power_trip_invalidates_reading_and_stops(tmp_path):
    runner, transport, _ = setup_runner(tmp_path, power_limit_W=5e-13)
    assert completed(runner)["status"] == "aborted"
    assert "SOFTWARE_POWER_TRIP" in runner.rows[0]["quality_flags"]
    assert not runner.rows[0]["valid_for_summary"]
    assert ":SOUR:VOLT 2" not in source_writes(transport)


def test_safety_polled_during_long_sample_interval(tmp_path):
    runner, transport, clock = setup_runner(
        tmp_path, sample_interval_s=50, dwell_s=100, summary_window_s=10
    )
    clock.hook = lambda t: transport.faults.update(interlock=0) if t >= 3 else None
    assert completed(runner)["status"] == "aborted"
    assert clock.monotonic() < 3.4
    assert runner.output_state == "OFF"
    assert len([r for r in runner.rows if r["phase"] != "ERROR"]) == 1


def test_config_cannot_be_replaced_after_start_even_from_callback(tmp_path):
    runner, transport, _ = setup_runner(tmp_path)

    def attack(row):
        runner.config = replace(runner.config, current_trip_A=1)

    runner.on_sample = attack
    assert completed(runner)["status"] == "aborted"
    assert ":SOUR:VOLT 2" not in source_writes(transport)
    assert runner.output_state == "OFF"


def test_close_query_failure_does_not_leave_off_display(tmp_path):
    runner, transport, _ = setup_runner(tmp_path)
    runner.connect()
    original = runner.instrument.close

    def failing_close():
        transport.faults["output_query_failure"] = True
        original()

    runner.instrument.close = failing_close
    runner.shutdown()
    assert runner.output_state == "UNKNOWN"
    assert runner.state == "HV_STATE_UNKNOWN"


def test_interlock_latches_no_resume_after_closed(tmp_path):
    runner, transport, _ = setup_runner(tmp_path)
    runner.on_sample = lambda row: transport.faults.update(interlock=0)
    result = completed(runner)
    assert result["status"] == "aborted"
    assert ":SOUR:VOLT 2" not in source_writes(transport)
    transport.faults["interlock"] = 1
    with pytest.raises(MeasurementError):
        runner.start()
    with pytest.raises(MeasurementError):
        runner.arm()
    assert transport.commands.count(":OUTP1 ON") == 1


def test_off_failure_and_abort_cancel_exceptions_never_skip_off(tmp_path):
    runner, transport, _ = setup_runner(tmp_path)
    runner.connect()
    runner.arm()
    transport.faults.update(fail_abort=True, fail_cancel=True, fail_off=True)
    result = runner.start()
    assert result["status"] == "aborted"
    assert runner.output_state == "UNKNOWN"
    assert transport.commands.count(":OUTP1 OFF") >= 4  # takeover + final two attempts


def test_error_in_logging_and_abort_does_not_prevent_off(tmp_path):
    runner, transport, _ = setup_runner(tmp_path)
    runner.connect()
    runner.arm()
    original = runner.writer.event

    def broken(_):
        raise OSError("disk full")

    runner.writer.event = broken
    transport.faults.update(fail_abort=True, fail_cancel=True)
    result = runner.start()
    assert result["status"] == "aborted"
    assert not transport.output
    assert runner.output_state == "OFF"
    runner.writer.event = original


class DiskFailureWriter(RunWriter):
    def sample(self, row):
        raise OSError("disk full in sample")


def test_disk_failure_during_sample_aborts(tmp_path):
    runner, transport, _ = setup_runner(tmp_path, writer_factory=DiskFailureWriter)
    assert completed(runner)["status"] == "aborted"
    assert runner.output_state == "OFF"
    assert not transport.output
    assert ":SOUR:VOLT 2" not in source_writes(transport)


class FinalStatusFailureWriter(RunWriter):
    def status(self, status, *args, **kwargs):
        if status == "completed":
            raise OSError("final status full")
        super().status(status, *args, **kwargs)


def test_final_persistence_failure_never_reports_completed(tmp_path):
    runner, _, _ = setup_runner(tmp_path, writer_factory=FinalStatusFailureWriter)
    result = completed(runner)
    assert result["status"] == "aborted"
    assert runner.state == "FAULT"
    assert "persistence failed" in result["reason"]


def test_stop_long_wait_uses_virtual_time_and_does_not_raise_voltage(tmp_path):
    runner, transport, clock = setup_runner(
        tmp_path, dwell_s=100, summary_window_s=10, sample_interval_s=50
    )
    clock.hook = lambda now: runner.request_stop("fake clock stop") if now >= 3 else None
    result = completed(runner)
    assert result["status"] == "aborted"
    assert clock.monotonic() < 3.1
    assert runner.output_state == "OFF"
    assert ":SOUR:VOLT 2" not in source_writes(transport)


def test_stop_from_state_callback_prevents_next_source_write(tmp_path):
    runner, transport, _ = setup_runner(tmp_path)
    runner.on_event = lambda e: runner.request_stop() if e.get("state") == "RAMPING" else None
    assert completed(runner)["status"] == "aborted"
    assert ":SOUR:VOLT 1" not in source_writes(transport)


def test_native_mode_has_no_measured_current_and_separate_native_summary(tmp_path):
    runner, _, _ = setup_runner(tmp_path, mode="NATIVE_RESISTANCE")
    assert completed(runner)["status"] == "completed"
    rows = [r for r in runner.rows if r["phase"] != "ERROR"]
    assert all(r["current_raw_A"] is None for r in rows)
    assert all(r["native_r_ohm"] > 0 for r in rows)
    assert all(r["current_inferred_A"] is not None for r in rows)
    assert all(s["R_from_mean_current_ohm"] is None for s in runner.summaries)
    assert all(s["native_r_mean_ohm"] > 0 for s in runner.summaries)
    assert rows[0]["read_end_monotonic_s"] - rows[0]["read_start_monotonic_s"] == pytest.approx(
        runner.config.nplc / runner.config.line_frequency_hz
    )


def test_range_change_and_initial_settle_kept_but_excluded(tmp_path):
    runner, _, _ = setup_runner(
        tmp_path, faults={"range_change_at_read": 2}, exclude_initial_s=0.1, range_settle_s=0.2
    )
    assert completed(runner)["status"] == "completed"
    assert "SETTLING_EXCLUDED" in runner.rows[0]["quality_flags"]
    assert "RANGE_CHANGE_TIMING_UNCERTAIN" in runner.rows[1]["quality_flags"]
    assert runner.rows[1]["valid_for_summary"] is False
    assert any(e["event"] == "range_change" for e in runner.events)
    assert any(r["valid_for_summary"] for r in runner.rows)


def test_range_change_during_first_read_is_also_excluded(tmp_path):
    runner, _, _ = setup_runner(tmp_path, faults={"range_change_at_read": 1}, exclude_initial_s=0)
    assert completed(runner)["status"] == "completed"
    assert "RANGE_CHANGE_TIMING_UNCERTAIN" in runner.rows[0]["quality_flags"]
    assert "SETTLING_EXCLUDED" in runner.rows[0]["quality_flags"]
    assert not runner.rows[0]["valid_for_summary"]


def test_status_io_that_overshoots_wait_does_not_sleep_negative_time(tmp_path):
    runner, _, clock = setup_runner(tmp_path)
    runner.connect()
    runner.arm()
    runner.instrument.authorize_start(runner.config)
    runner.instrument.output_on()
    runner.output_state = "ON"
    original = runner.instrument.safety_status

    def slow_status():
        clock.sleep(0.2)
        return original()

    runner.instrument.safety_status = slow_status
    runner._wait_until(clock.monotonic() + 0.1)
    assert runner.output_state == "ON"
    runner.shutdown()


def test_slow_conversion_actual_interval_is_not_requested_interval(tmp_path):
    runner, _, _ = setup_runner(tmp_path, nplc=10, sample_interval_s=0.01)
    assert completed(runner)["status"] == "completed"
    assert runner.rows[1]["actual_sample_interval_s"] >= 10 / 60


def test_runner_single_owner_but_stop_threadsafe(tmp_path):
    runner, _, _ = setup_runner(tmp_path)
    runner.connect()
    errors = []

    def other():
        runner.request_stop()
        try:
            runner.arm()
        except Exception as exc:
            errors.append(exc)

    worker = threading.Thread(target=other)
    worker.start()
    worker.join()
    assert isinstance(errors[0], MeasurementError)
    runner.shutdown()


def test_changed_runner_config_blocked_before_on(tmp_path):
    runner, transport, _ = setup_runner(tmp_path)
    runner.connect()
    runner.arm()
    with pytest.raises(AttributeError):
        runner.config = replace(runner.config, voltages=(2, 3))
    assert ":OUTP1 ON" not in transport.commands
    runner.shutdown()


def test_incremental_csv_preserves_response_commas_newline_and_signed_values(tmp_path):
    config = RunConfig(output_directory=str(tmp_path))
    writer = RunWriter(config, {"simulation": True})
    writer.sample(
        {
            "current_raw_A": -1e-12,
            "raw_response": 'one,"two"\nthree',
            "quality_flags": ["signed"],
            "valid_for_summary": True,
        }
    )
    rows = list(csv.DictReader((writer.directory / "readings.csv").open()))
    assert rows[0]["raw_response"] == 'one,"two"\nthree'
    assert float(rows[0]["current_raw_A"]) == -1e-12
    assert json.loads(rows[0]["quality_flags"]) == ["signed"]
    writer.close()


def test_recover_incomplete_never_resumes_or_claims_off(tmp_path):
    writer = RunWriter(RunConfig(output_directory=str(tmp_path)), {})
    writer.status("running", "active", "ON")
    writer.close()
    assert recover_incomplete_runs(tmp_path) == [str(writer.directory)]
    status = json.loads((writer.directory / "run_status.json").read_text())
    assert status["status"] == "interrupted"
    assert status["final_output_state"] == "UNKNOWN"
    assert status["residual_voltage_state"] == "UNVERIFIED"
    assert recover_incomplete_runs(tmp_path) == []


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_strict_json_never_encodes_nan_inf(value):
    with pytest.raises(ValueError):
        strict_json({"value": value})
