"""Failed ARM retains its original error and transcript after protective OFF."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from keithley6517a.clock import FakeClock
from keithley6517a.config import RunConfig
from keithley6517a.driver.instrument import Instrument
from keithley6517a.driver.parser import ProtocolError
from keithley6517a.measurement.runner import MeasurementRunner
from keithley6517a.transport.simulator import SimulatorTransport


def prepared(tmp_path, *, failure=None):
    config = replace(
        RunConfig(),
        output_directory=str(tmp_path),
        current_trip_A=1e-8,
        residual_warning_ack=True,
        dwell_s=0.5,
        summary_window_s=0.5,
        sample_interval_s=0.1,
        nplc=0.1,
    )
    clock = FakeClock()
    transport = SimulatorTransport(clock=clock)
    instrument = Instrument(transport, clock)
    if failure is not None:

        def failed_configuration(_config):
            # Model the reported failure directly; do not depend on which valid
            # zero-correct method the normal production profile selects.
            instrument._write(":SYST:ZCH ON")
            instrument._write(":SYST:ZCOR:ACQ")
            transport.errors.append(failure)
            instrument._check_errors("zero correction acquire")

        instrument.configure = failed_configuration
    runner = MeasurementRunner(config, instrument=instrument, clock=clock)
    runner.connect()
    return runner, transport


def read_json(path):
    def invalid_constant(value):
        pytest.fail(f"Nonstandard JSON constant in diagnostic: {value}")

    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=invalid_constant)


@pytest.mark.parametrize(
    "failure",
    ['-200,"Execution error"', '+513,"Calibration data lost"'],
)
def test_arm_error_preserves_lossless_transcript_only_after_off(tmp_path, monkeypatch, failure):
    runner, transport = prepared(tmp_path, failure=failure)
    opened_after_off = []
    original_open = Path.open

    def observed_open(path, mode="r", *args, **kwargs):
        if mode == "x" and "arm-failures" in path.parts:
            assert not transport.output and runner.output_state == "OFF"
            assert runner.state == "FAULT"
            assert transport.commands[-1] == ":OUTP1?"
            opened_after_off.append(list(transport.commands))
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", observed_open)
    try:
        with pytest.raises(ProtocolError, match="zero correction acquire") as error:
            runner.arm()
        report = runner.last_arm_failure_report
        assert report["report_saved"] and not report["ok"]
        assert report["stage"] == "arm_configuration"
        assert report["error"] == str(error.value) and failure in report["error"]
        assert report["exception_type"] == type(error.value).__name__
        assert report["state"] == "FAULT" and report["output_state"] == "OFF"
        assert report["residual_voltage_state"] == "UNVERIFIED"
        assert report["settings"] == runner.config.to_dict()
        assert report["identity"] == runner.identity and report["simulation"]
        assert report["hardware_verified"] is False
        assert report["raw_io_may_be_truncated"] is False
        assert runner.writer is None and runner.run_directory is None
        folder = Path(report["report_path"]).parent
        assert folder.parent == tmp_path / "arm-failures"
        assert set(path.name for path in folder.iterdir()) == {"diagnostic.json", "raw_io.jsonl"}
        assert read_json(report["report_path"]) == report
        raw = [
            json.loads(line)
            for line in Path(report["raw_io_path"]).read_text(encoding="utf-8").splitlines()
        ]
        assert raw == list(runner._transcript)
        assert len(raw) == report["raw_io_entries"]
        assert any(item.get("response") == failure for item in raw)
        assert all("wall_time_iso8601" in item and "monotonic_s" in item for item in raw)
        assert any(item.get("event") == "arm_failed" for item in report["events"])
        assert report["events"][-1]["state"] == "FAULT"
        assert len(opened_after_off) == 2
        assert all(commands == transport.commands for commands in opened_after_off)
        assert ":OUTP1 ON" not in transport.commands
        assert not runner.can_arm and not runner.can_start
    finally:
        runner.shutdown()


def test_failed_diagnostic_sync_keeps_original_arm_exception_and_off(tmp_path, monkeypatch):
    runner, transport = prepared(tmp_path, failure='-200,"Execution error"')

    def fail_sync(_descriptor):
        assert runner.state == "FAULT" and runner.output_state == "OFF"
        raise OSError("diagnostic disk is full")

    monkeypatch.setattr("keithley6517a.measurement.runner.os.fsync", fail_sync)
    try:
        with pytest.raises(ProtocolError, match="zero correction acquire"):
            runner.arm()
        report = runner.last_arm_failure_report
        assert not report["report_saved"]
        assert "diagnostic disk is full" in report["report_error"]
        assert "-200" in report["error"]
        assert report["report_path"] is None and report["raw_io_path"] is None
        assert runner.output_state == "OFF" and not transport.output
        assert ":OUTP1 ON" not in transport.commands
        assert list((tmp_path / "arm-failures").iterdir()) == []
    finally:
        runner.shutdown()


def test_report_serialization_failure_cannot_replace_arm_error(tmp_path, monkeypatch):
    runner, transport = prepared(tmp_path, failure='-200,"Execution error"')
    original_dumps = json.dumps

    def fail_dumps(value, **kwargs):
        if isinstance(value, dict) and value.get("direction"):
            raise ValueError("diagnostic encoding failed")
        return original_dumps(value, **kwargs)

    monkeypatch.setattr("keithley6517a.measurement.runner.json.dumps", fail_dumps)
    try:
        with pytest.raises(ProtocolError, match="zero correction acquire"):
            runner.arm()
        assert not runner.last_arm_failure_report["report_saved"]
        assert "diagnostic encoding failed" in runner.last_arm_failure_report["report_error"]
        assert runner.output_state == "OFF" and not transport.output
        assert not (tmp_path / "arm-failures").exists()
    finally:
        runner.shutdown()


def test_reconnection_resets_failure_pointer_and_reports_never_replace_previous_files(tmp_path):
    runner, _ = prepared(tmp_path, failure='-200,"Execution error"')
    try:
        with pytest.raises(ProtocolError):
            runner.arm()
        first = Path(runner.last_arm_failure_report["report_path"]).parent
        original = {path.name: path.read_bytes() for path in first.iterdir()}
        runner.shutdown()
        runner.connect()
        assert runner.last_arm_failure_report == {}
        with pytest.raises(ProtocolError):
            runner.arm()
        second = Path(runner.last_arm_failure_report["report_path"]).parent
        assert first != second
        assert {path.name: path.read_bytes() for path in first.iterdir()} == original
        assert len(list((tmp_path / "arm-failures").iterdir())) == 2
    finally:
        runner.shutdown()


def test_report_directory_collision_preserves_existing_diagnostic(tmp_path, monkeypatch):
    from datetime import UTC, datetime
    from types import SimpleNamespace

    runner, _ = prepared(tmp_path, failure='-200,"Execution error"')
    monkeypatch.setattr(
        "keithley6517a.measurement.runner.datetime",
        SimpleNamespace(now=lambda _zone: datetime(2026, 11, 17, tzinfo=UTC)),
    )
    monkeypatch.setattr(
        "keithley6517a.measurement.runner.uuid.uuid4", lambda: SimpleNamespace(hex="fixed-id")
    )
    try:
        with pytest.raises(ProtocolError):
            runner.arm()
        folder = Path(runner.last_arm_failure_report["report_path"]).parent
        original = {path.name: path.read_bytes() for path in folder.iterdir()}
        runner.shutdown()
        runner.connect()
        with pytest.raises(ProtocolError):
            runner.arm()
        assert not runner.last_arm_failure_report["report_saved"]
        assert "FileExistsError" in runner.last_arm_failure_report["report_error"]
        assert {path.name: path.read_bytes() for path in folder.iterdir()} == original
        assert len(list((tmp_path / "arm-failures").iterdir())) == 1
    finally:
        runner.shutdown()


def test_successful_measurement_has_no_arm_failure_snapshot(tmp_path):
    runner, _ = prepared(tmp_path)
    try:
        runner.arm()
        assert runner.last_arm_failure_report == {}
        assert runner.run_directory is not None
        result = runner.start()
        assert result["status"] == "completed" and result["output_state"] == "OFF"
        assert runner.last_arm_failure_report == {}
        assert not (tmp_path / "arm-failures").exists()
    finally:
        runner.shutdown()


def test_cooperative_stop_during_arm_keeps_stopped_classification_without_fault_snapshot(tmp_path):
    runner, transport = prepared(tmp_path)

    def stop_configuring(event):
        if event.get("event") == "state" and event.get("state") == "CONFIGURING":
            runner.request_stop("user STOP")

    runner.on_event = stop_configuring
    try:
        result = runner.arm()
        assert result["status"] == "stopped"
        assert result["output_state"] == "OFF" and not transport.output
        assert runner.last_arm_failure_report == {}
        assert not (tmp_path / "arm-failures").exists()
        assert ":OUTP1 ON" not in transport.commands
    finally:
        runner.shutdown()
