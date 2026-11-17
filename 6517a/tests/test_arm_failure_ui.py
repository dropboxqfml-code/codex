"""ARM failures remain available to the idle GUI's local diagnostic ZIP export."""

import json
import zipfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from keithley6517a.clock import FakeClock
from keithley6517a.config import RunConfig
from keithley6517a.measurement.runner import MeasurementRunner
from keithley6517a.ui.main_window import InstrumentWorker, MainWindow


def test_worker_failure_snapshot_survives_disconnect_and_clears_on_new_connection():
    config = RunConfig()
    report = {
        "report_saved": True,
        "report_path": "diagnostics/arm-failure/diagnostic.json",
        "raw_io_path": "diagnostics/arm-failure/raw_io.jsonl",
        "error": '-200,"Execution error"',
    }

    class SnapshotRunner(SimpleNamespace):
        def shutdown(self):
            self.closed = True

        def connect(self):
            self.state = "OUTPUT_OFF_CONFIRMED"
            self.output_state = "OFF"

    fresh = SnapshotRunner(
        config=config,
        state="DISCONNECTED",
        output_state="UNKNOWN",
        last_arm_failure_report={},
    )
    worker = InstrumentWorker(lambda *args, **kwargs: fresh)
    previous = SnapshotRunner(
        config=config,
        state="FAULT",
        output_state="OFF",
        last_arm_failure_report=report,
    )
    worker.runner = previous
    observed = []
    worker.status.connect(observed.append)
    worker.snapshot()
    assert observed[-1]["arm_failure_report"] == report
    worker.dispatch(("disconnect", None))
    assert previous.closed
    assert observed[-1]["state"] == "DISCONNECTED"
    assert observed[-1]["arm_failure_report"] == report
    worker.dispatch(("connect", config))
    assert observed[-1]["arm_failure_report"] == {}
    assert worker.runner is fresh
    worker.dispatch(("shutdown", None))


def close_window(qtbot, widget):
    widget.close()
    qtbot.waitUntil(lambda: widget._closed, timeout=20000)


@pytest.mark.parametrize(
    ("code", "message"), [(-200, "Execution error"), (513, "Calibration data lost")]
)
def test_failed_simulated_arm_exposes_original_error_and_exports_transcript_after_off(
    qtbot, tmp_path, monkeypatch, code, message
):
    monkeypatch.chdir(tmp_path)
    runners = []

    def factory(config, **callbacks):
        runner = MeasurementRunner(config, clock=FakeClock(), **callbacks)

        def failed_configuration(settings):
            runner.instrument._write(":SYST:ZCH ON")
            runner.instrument._write(":SYST:ZCOR ON")
            runner.instrument.transport.errors.append(f'{code},"{message}"')
            runner.instrument._check_errors("zero correction enable")

        runner.instrument.configure = failed_configuration
        runners.append(runner)
        return runner

    window = MainWindow(factory)
    qtbot.addWidget(window, before_close_func=lambda widget: close_window(qtbot, widget))
    config = replace(
        RunConfig(),
        output_directory=str(tmp_path / "runs"),
        voltages=(1,),
        current_trip_A=1e-8,
        residual_warning_ack=True,
        simulation_resistance_ohm=1e9,
        dwell_s=0.5,
        summary_window_s=0.5,
        nplc=0.1,
    )
    window._load_controls(config.to_dict())
    window._connect()
    qtbot.waitUntil(lambda: window._can_arm and not window._busy, timeout=10000)
    window._send("arm")
    qtbot.waitUntil(
        lambda: (
            window._state == "FAULT" and bool(window._last_arm_failure_report) and not window._busy
        ),
        timeout=10000,
    )
    runner = runners[0]
    report = runner.last_arm_failure_report
    assert runner.run_directory is None and runner.writer is None
    assert window.output_label.text() == "OUTPUT OFF"
    assert str(code) in window._last_error and message in window._last_error
    assert not window.arm_button.isEnabled() and not window.start_button.isEnabled()
    assert window._last_diagnostic_directory == str(Path(report["report_path"]).parent)
    assert "ARM 실패 기록 저장" in window.diagnostic_label.text()
    assert window.export_diagnostic_button.isEnabled()
    assert ":OUTP1 ON" not in runner.instrument.transport.commands
    destination = tmp_path / f"arm-failure-{code}.zip"
    assert window.export_diagnostics_to(destination)
    with zipfile.ZipFile(destination) as archive:
        saved = json.loads(archive.read("source/diagnostic/diagnostic.json"))
        raw = archive.read("source/diagnostic/raw_io.jsonl").decode("utf-8")
        log = archive.read("gui/log.txt").decode("utf-8")
    assert saved["report_saved"] is True
    assert message in saved["error"] and str(code) in saved["error"]
    assert ":SYST:ZCOR ON" in raw and message in raw
    assert message in log
    assert window.worker.runner is runner
    window._send("disconnect")
    qtbot.waitUntil(lambda: window._state == "DISCONNECTED" and not window._busy, timeout=10000)
    assert window._last_arm_failure_report["report_path"] == report["report_path"]
    assert "진단 ZIP 저장 완료" in window.diagnostic_label.text()


def test_failure_record_write_error_is_visible_without_replacing_original_arm_error(
    qtbot, tmp_path
):
    window = MainWindow(
        lambda *args, **kwargs: pytest.fail("Status display must not create runner")
    )
    qtbot.addWidget(window, before_close_func=lambda widget: close_window(qtbot, widget))
    window._last_error = 'ProtocolError: -200,"Execution error"'
    window._last_diagnostic_directory = str(tmp_path / "earlier-diagnostic")
    window._on_status(
        {
            "state": "FAULT",
            "output_state": "OFF",
            "arm_failure_report": {
                "report_saved": False,
                "report_path": None,
                "raw_io_path": None,
                "error": '-200,"Execution error"',
                "report_error": "test disk full",
            },
        }
    )
    assert window._last_error == 'ProtocolError: -200,"Execution error"'
    assert "ARM 실패 기록 저장 실패" in window.diagnostic_label.text()
    assert "test disk full" in window.diagnostic_label.text()
    assert window._last_diagnostic_directory == str(tmp_path / "earlier-diagnostic")
    assert not window.arm_button.isEnabled() and not window.start_button.isEnabled()
    assert window.worker.runner is None
