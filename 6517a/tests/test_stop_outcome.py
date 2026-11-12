"""A user STOP is a saved partial run; known faults and failed OFF never become STOP."""

import csv
import json
from dataclasses import replace

import pytest

from keithley6517a.clock import FakeClock
from keithley6517a.config import RunConfig
from keithley6517a.driver.instrument import Instrument
from keithley6517a.measurement.runner import MeasurementError, MeasurementRunner
from keithley6517a.storage.run_writer import RunWriter, recover_incomplete_runs
from keithley6517a.transport.simulator import SimulatorTransport


def prepared_runner(tmp_path, *, writer_factory=None, faults=None, arm=True, **settings):
    config = replace(
        RunConfig(),
        **dict(
            dict(
                output_directory=str(tmp_path),
                voltages=(1, 2),
                protocol="list",
                dwell_s=300,
                summary_window_s=30,
                sample_interval_s=0.1,
                nplc=1,
                current_trip_A=1e-8,
                residual_warning_ack=True,
            ),
            **settings,
        ),
    )
    clock = FakeClock()
    transport = SimulatorTransport(
        clock=clock,
        faults=faults,
        resistance_ohm=1e9,
        noise_A=0,
        absorption_A=0,
        offset_A=0,
    )
    runner = MeasurementRunner(
        config, instrument=Instrument(transport, clock), clock=clock, writer_factory=writer_factory
    )
    runner.connect()
    if arm:
        runner.arm()
    return runner, transport


def persisted_rows(runner):
    with (runner.run_directory / "readings.csv").open() as stream:
        return list(csv.DictReader(stream))


def test_user_stop_retains_partial_readings_and_persists_distinct_terminal_status(tmp_path):
    runner, transport = prepared_runner(tmp_path)
    runner.on_sample = lambda _: runner.request_stop("user STOP") if len(runner.rows) == 2 else None
    try:
        result = runner.start()
        assert result["status"] == "stopped" and result["reason"] == "user STOP"
        assert runner.state == "OUTPUT_OFF_CONFIRMED" and result["output_state"] == "OFF"
        assert runner.writer.closed and not transport.output
        assert result["reading_count"] == len(persisted_rows(runner)) == 2
        assert result["elapsed_s"] > 0
        assert all(row["phase"] != "ERROR" for row in persisted_rows(runner))
        assert not runner.summaries and (runner.run_directory / "summary.csv").read_bytes() == b""
        assert len((runner.run_directory / "analysis.txt").read_text().splitlines()) == 3
        assert ":SOUR:VOLT 2" not in transport.commands
        assert transport.commands.count(":OUTP1 ON") == 1
        assert any(event["event"] == "stop_requested" for event in runner.events)
        assert not any(event["event"] == "abort" for event in runner.events)
        assert not runner.can_arm and not runner.can_start
        with pytest.raises(MeasurementError, match="fresh connection"):
            runner.arm()
        status = json.loads((runner.run_directory / "run_status.json").read_text())
        assert status["status"] == "stopped" and status["software_state"] == "OUTPUT_OFF_CONFIRMED"
        assert status["reading_count"] == 2 and status["elapsed_s"] == result["elapsed_s"]
        assert recover_incomplete_runs(tmp_path) == []
        runner.shutdown()
        assert (
            json.loads((runner.run_directory / "run_status.json").read_text())["status"]
            == "stopped"
        )
    finally:
        if runner.state != "DISCONNECTED":
            runner.shutdown()


def test_completed_run_keeps_existing_completed_status_with_saved_counts(tmp_path):
    runner, transport = prepared_runner(tmp_path, dwell_s=0.5, summary_window_s=0.5)
    try:
        result = runner.start()
        assert result["status"] == "completed" and result["output_state"] == "OFF"
        assert result["reading_count"] == len(persisted_rows(runner)) > 0
        assert result["elapsed_s"] >= 1
        assert len(runner.summaries) == 2 and not transport.output
    finally:
        runner.shutdown()


def test_completed_schedule_cleanup_error_is_aborted_even_when_output_is_confirmed_off(tmp_path):
    runner, transport = prepared_runner(tmp_path, dwell_s=0.5, summary_window_s=0.5)

    def after_step(event):
        if event.get("event") == "step_summary" and len(runner.summaries) == 2:
            transport.faults.update(fail_abort=True, fail_cancel=True)

    runner.on_event = after_step
    try:
        result = runner.start()
        assert len(runner.summaries) == 2  # the measurement schedule itself completed
        assert result["status"] == "aborted" and "output stop reported errors" in result["reason"]
        assert result["output_state"] == "OFF" and runner.state == "FAULT"
        assert not transport.output
        assert (
            json.loads((runner.run_directory / "run_status.json").read_text())["status"]
            == "aborted"
        )
    finally:
        transport.faults.clear()
        runner.shutdown()


@pytest.mark.parametrize("arm", [False, True])
def test_owner_cancels_pending_preparation_without_calling_start_or_enabling_output(tmp_path, arm):
    runner, transport = prepared_runner(tmp_path, arm=arm)
    try:
        runner.request_stop("user STOP")  # GUI-thread side only sets the Event
        result = runner.cancel_pending("user STOP")
        assert result["status"] == "stopped" and result["reading_count"] == 0
        assert result["elapsed_s"] is None
        assert runner.state == "OUTPUT_OFF_CONFIRMED" and not transport.output
        assert ":OUTP1 ON" not in transport.commands and not runner.can_arm and not runner.can_start
        if arm:
            assert runner.writer.closed
            assert len((runner.run_directory / "analysis.txt").read_text().splitlines()) == 1
            assert (
                json.loads((runner.run_directory / "run_status.json").read_text())["status"]
                == "stopped"
            )
        else:
            assert result["run_directory"] is None and runner.writer is None
        commands = list(transport.commands)
        assert runner.cancel_pending("duplicate STOP") is None
        assert transport.commands == commands
        with pytest.raises(MeasurementError, match="Explicit ARM"):
            runner.start()
    finally:
        runner.shutdown()


@pytest.mark.parametrize("state", ["FAULT", "HV_STATE_UNKNOWN"])
def test_pending_cancel_never_relabels_an_existing_fault(tmp_path, state):
    runner, transport = prepared_runner(tmp_path)
    try:
        runner.state = state
        commands = list(transport.commands)
        assert runner.cancel_pending("user STOP after error") is None
        assert runner.state == state and transport.commands == commands
    finally:
        runner.shutdown()


def test_stop_during_arm_configuration_returns_stopped_without_enabling_output(tmp_path):
    runner, transport = prepared_runner(tmp_path, arm=False)
    runner.on_event = lambda event: (
        runner.request_stop("STOP during preparation")
        if event.get("state") == "CONFIGURING"
        else None
    )
    try:
        result = runner.arm()
        assert result["status"] == "stopped" and result["reading_count"] == 0
        assert result["elapsed_s"] is None and runner.state == "OUTPUT_OFF_CONFIRMED"
        assert not runner.can_arm and not runner.can_start
        assert ":OUTP1 ON" not in transport.commands
        assert runner.cancel_pending("queued STOP") is None
    finally:
        runner.shutdown()


def test_stop_after_arm_files_are_prepared_closes_and_persists_stopped(tmp_path):
    runner = None

    def factory(config, metadata):
        writer = RunWriter(config, metadata)
        runner.request_stop("STOP after file preparation")
        return writer

    runner, transport = prepared_runner(tmp_path, arm=False, writer_factory=factory)
    try:
        result = runner.arm()
        assert result["status"] == "stopped" and runner.writer.closed
        assert runner.state == "OUTPUT_OFF_CONFIRMED" and result["reading_count"] == 0
        assert ":OUTP1 ON" not in transport.commands
        assert (
            json.loads((runner.run_directory / "run_status.json").read_text())["status"]
            == "stopped"
        )
    finally:
        runner.shutdown()


def test_pending_cancel_reports_off_cleanup_errors_as_aborted(tmp_path):
    runner, transport = prepared_runner(tmp_path)
    transport.faults.update(fail_abort=True, fail_cancel=True)
    try:
        result = runner.cancel_pending("user STOP")
        assert result["status"] == "aborted" and result["output_state"] == "OFF"
        assert runner.state == "FAULT" and ":OUTP1 ON" not in transport.commands
    finally:
        transport.faults.clear()
        runner.shutdown()


def test_stop_while_armed_cannot_enable_output_and_is_an_empty_stopped_run(tmp_path):
    runner, transport = prepared_runner(tmp_path)
    try:
        runner.request_stop("cancelled before source ON")
        result = runner.start()
        assert result["status"] == "stopped" and result["reading_count"] == 0
        assert ":OUTP1 ON" not in transport.commands
        assert runner.state == "OUTPUT_OFF_CONFIRMED" and not runner.can_start
        assert len((runner.run_directory / "analysis.txt").read_text().splitlines()) == 1
    finally:
        runner.shutdown()


@pytest.mark.parametrize(
    ("settings", "faults", "reason"),
    [
        ({"current_trip_A": 5e-10}, {}, "Software current trip"),
        ({}, {"current_limit_at_read": 1}, "Source current limit active"),
    ],
)
def test_known_reading_fault_wins_over_simultaneous_stop(tmp_path, settings, faults, reason):
    runner, transport = prepared_runner(tmp_path, faults=faults, **settings)
    runner.on_sample = lambda _: runner.request_stop("simultaneous user STOP")
    try:
        result = runner.start()
        assert result["status"] == "aborted" and reason in result["reason"]
        assert runner.state == "FAULT" and not transport.output
        assert any(row["phase"] == "ERROR" for row in runner.rows)
        assert (
            json.loads((runner.run_directory / "run_status.json").read_text())["status"]
            == "aborted"
        )
    finally:
        runner.shutdown()


def test_known_storage_error_wins_over_simultaneous_stop(tmp_path):
    runner, transport = prepared_runner(tmp_path)

    def on_sample(_):
        runner.request_stop("simultaneous user STOP")
        runner._storage_error = OSError("disk full during recording")

    runner.on_sample = on_sample
    try:
        result = runner.start()
        assert result["status"] == "aborted" and "disk full" in result["reason"]
        assert runner.state == "FAULT" and not transport.output
        assert any(event["event"] == "abort" for event in runner.events)
    finally:
        runner.shutdown()


def test_elapsed_safety_deadline_wins_over_simultaneous_stop(tmp_path):
    runner, transport = prepared_runner(tmp_path)

    def on_sample(_):
        runner.request_stop("simultaneous user STOP")
        runner.clock.now = runner._start_time + runner.config.max_total_duration_s

    runner.on_sample = on_sample
    try:
        result = runner.start()
        assert result["status"] == "aborted" and "Maximum total run duration" in result["reason"]
        assert runner.state == "FAULT" and not transport.output
    finally:
        runner.shutdown()


@pytest.mark.parametrize("fail_off", [False, True])
def test_off_cleanup_error_or_unknown_state_cannot_be_classified_as_user_stop(tmp_path, fail_off):
    runner, transport = prepared_runner(tmp_path)

    def on_sample(_):
        transport.faults.update(fail_abort=True, fail_cancel=True, fail_off=fail_off)
        runner.request_stop("user STOP")

    runner.on_sample = on_sample
    try:
        result = runner.start()
        assert result["status"] == "aborted"
        assert runner.state == ("HV_STATE_UNKNOWN" if fail_off else "FAULT")
        assert result["output_state"] == ("UNKNOWN" if fail_off else "OFF")
        status = json.loads((runner.run_directory / "run_status.json").read_text())
        assert status["status"] == "aborted"
    finally:
        transport.faults.clear()
        runner.shutdown()


class StoppedStatusFailureWriter(RunWriter):
    def status(self, status, *args, **kwargs):
        if status == "stopped":
            raise OSError("stopped status persistence failed")
        super().status(status, *args, **kwargs)


def test_failed_final_status_never_returns_stopped(tmp_path):
    runner, transport = prepared_runner(tmp_path, writer_factory=StoppedStatusFailureWriter)
    runner.on_sample = lambda _: runner.request_stop("user STOP")
    try:
        result = runner.start()
        assert result["status"] == "aborted" and "persistence failed" in result["reason"]
        assert runner.state == "FAULT" and not transport.output
        assert result["reading_count"] == len(persisted_rows(runner)) == 1
        assert (
            json.loads((runner.run_directory / "run_status.json").read_text())["status"]
            != "stopped"
        )
    finally:
        runner.shutdown()
