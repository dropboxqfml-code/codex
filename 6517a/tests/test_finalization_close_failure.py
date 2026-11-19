"""Terminal success is persisted only after data streams close without failure."""

import json
from dataclasses import replace

import pytest

from keithley6517a.clock import FakeClock
from keithley6517a.config import RunConfig
from keithley6517a.measurement.runner import MeasurementRunner
from keithley6517a.storage.run_writer import RunWriter


def prepared(tmp_path, *, writer_factory=None, arm=True):
    config = replace(
        RunConfig(),
        output_directory=str(tmp_path),
        voltages=(1,),
        dwell_s=0.3,
        summary_window_s=0.3,
        sample_interval_s=0.1,
        nplc=0.1,
        current_trip_A=1e-8,
        residual_warning_ack=True,
        simulation_resistance_ohm=1e9,
    )
    runner = MeasurementRunner(config, clock=FakeClock(), writer_factory=writer_factory)
    runner.connect()
    if arm:
        runner.arm()
    return runner, runner.instrument.transport


def status(runner):
    return json.loads((runner.run_directory / "run_status.json").read_text())


class CloseFailureHandle:
    def __init__(self, stream, before_close=None):
        self.stream = stream
        self.before_close = before_close

    @property
    def closed(self):
        return self.stream.closed

    def close(self):
        if self.before_close:
            self.before_close()
        self.stream.close()
        raise OSError("data-stream close failed")


@pytest.mark.parametrize("stop", [False, True])
def test_underlying_close_failure_is_aborted_in_result_and_persisted_status(tmp_path, stop):
    runner, transport = prepared(tmp_path)
    writer = runner.writer
    writes = []
    original_status = writer.status

    def record_status(outcome, *args, **kwargs):
        if outcome in {"completed", "stopped", "aborted"}:
            assert writer.closed  # No terminal success may precede close validation.
        writes.append(outcome)
        return original_status(outcome, *args, **kwargs)

    writer.status = record_status

    def already_off():
        assert not transport.output and runner.output_state == "OFF"
        assert transport.commands[-1] == ":OUTP1?"

    writer.handles[0] = CloseFailureHandle(writer.handles[0], already_off)
    if stop:
        runner.on_sample = lambda _: runner.request_stop("user STOP")
    try:
        result = runner.start()
        persisted = status(runner)
        assert result["status"] == persisted["status"] == "aborted"
        assert result["reason"] == persisted["reason"]
        assert "data-stream close failed" in result["reason"]
        assert runner.state == persisted["software_state"] == "FAULT"
        assert result["output_state"] == persisted["final_output_state"] == "OFF"
        assert not transport.output
        assert "completed" not in writes and "stopped" not in writes
        assert writer.close_errors and writer.closed
        assert all(stream.closed for stream in writer.handles)
        assert any(event["event"] == "writer_close_failed" for event in runner.events)
        assert transport.commands.count(":OUTP1 ON") == 1
    finally:
        runner.shutdown()


class RaisingCloseWriter(RunWriter):
    def close(self):
        super().close()
        raise OSError("writer close raised")


def test_custom_writer_close_exception_is_caught_after_protective_off(tmp_path):
    runner, transport = prepared(tmp_path, writer_factory=RaisingCloseWriter)
    try:
        result = runner.start()
        assert result["status"] == "aborted" and runner.state == "FAULT"
        assert "writer close raised" in result["reason"]
        assert result["reason"] == status(runner)["reason"]
        assert status(runner)["status"] == "aborted"
        assert result["output_state"] == "OFF" and not transport.output
    finally:
        runner.shutdown()


class TerminalStatusFailureWriter(RunWriter):
    fail_all = False

    def status(self, outcome, *args, **kwargs):
        if outcome in {"completed", "stopped"} or (self.fail_all and outcome == "aborted"):
            assert self.closed
            raise OSError("terminal status write failed")
        super().status(outcome, *args, **kwargs)


@pytest.mark.parametrize("stop", [False, True])
def test_status_error_remains_aborted_even_when_aborted_fallback_is_saved(tmp_path, stop):
    runner, transport = prepared(tmp_path, writer_factory=TerminalStatusFailureWriter)
    if stop:
        runner.on_sample = lambda _: runner.request_stop("user STOP")
    try:
        result = runner.start()
        assert result["status"] == status(runner)["status"] == "aborted"
        assert result["reason"] == status(runner)["reason"]
        assert "terminal status write failed" in result["reason"]
        assert runner._storage_error is not None
        assert runner.state == "FAULT" and result["output_state"] == "OFF"
        assert not transport.output
    finally:
        runner.shutdown()


def test_both_terminal_writes_fail_without_leaving_a_false_success_record(tmp_path):
    class AllTerminalStatusFailure(TerminalStatusFailureWriter):
        fail_all = True

    runner, transport = prepared(tmp_path, writer_factory=AllTerminalStatusFailure)
    try:
        result = runner.start()
        assert result["status"] == "aborted" and runner.state == "FAULT"
        assert "terminal status update failed" in result["reason"]
        # The existing running marker remains recoverable; success was never written.
        assert status(runner)["status"] == "running"
        assert any(event["event"] == "terminal_status_update_failed" for event in runner.events)
        assert result["output_state"] == "OFF" and not transport.output
    finally:
        runner.shutdown()


def test_close_failure_does_not_turn_unknown_output_into_confirmed_off(tmp_path):
    runner, transport = prepared(tmp_path, writer_factory=RaisingCloseWriter)

    def disconnect_status(_):
        transport.faults["output_query_failure"] = True
        runner.request_stop("user STOP")

    runner.on_sample = disconnect_status
    try:
        result = runner.start()
        assert result["status"] == status(runner)["status"] == "aborted"
        assert result["output_state"] == status(runner)["final_output_state"] == "UNKNOWN"
        assert runner.state == status(runner)["software_state"] == "HV_STATE_UNKNOWN"
        assert "output OFF unconfirmed" in result["reason"]
        assert "writer close raised" in result["reason"]
    finally:
        transport.faults.clear()
        runner.shutdown()


def test_partial_writer_initialization_keeps_original_error_and_closes_opened_streams(
    tmp_path, monkeypatch
):
    writer = RunWriter.__new__(RunWriter)
    original_open = RunWriter._open

    def fail_after_first_stream(self, name):
        if name == "analysis.txt":
            raise OSError("original initialization failed")
        stream = original_open(self, name)
        self.handles[-1] = CloseFailureHandle(stream)
        return stream

    monkeypatch.setattr(RunWriter, "_open", fail_after_first_stream)
    with pytest.raises(OSError, match="original initialization failed"):
        writer.__init__(replace(RunConfig(), output_directory=str(tmp_path)), {})
    assert writer.closed and writer.close_errors
    assert all(stream.closed for stream in writer.handles)
    # Idempotent cleanup retains the failure rather than clearing it.
    assert writer.close() == writer.close_errors


def test_known_storage_error_before_arm_cannot_become_normal_stop(tmp_path):
    runner, transport = prepared(tmp_path, arm=False)
    runner._storage_error = OSError("connected callback failed")
    try:
        result = runner.cancel_pending("user STOP")
        assert result["status"] == "aborted"
        assert "connected callback failed" in result["reason"]
        assert runner.state == "FAULT" and result["output_state"] == "OFF"
        assert runner.writer is None and runner.run_directory is None
        assert not transport.output and ":OUTP1 ON" not in transport.commands
    finally:
        runner.shutdown()
