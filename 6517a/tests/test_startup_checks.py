"""Portable startup uses asynchronous, serial subprocesses before showing the GUI."""

import json
import sys

import pytest
from PySide6.QtCore import QProcess, QTimer
from PySide6.QtWidgets import QWidget

from keithley6517a.ui.startup_checks import StartupChecks

BUNDLE = dict(status="passed", hardware_verified=False, errors=[], verified_files=12)
SIMULATION = dict(status="completed", output_state="OFF", reading_count=5)


@pytest.fixture
def root(tmp_path):
    bundle = tmp_path / "가상 프로그램 bundle"
    for relative in ("runtime/python.exe", "tools/verify_bundle.py", "tools/launch.py"):
        path = bundle / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("")
    config = bundle / "app/examples/simulation_config.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps(dict(simulation=True, transport="simulation")))
    return bundle


def child(report, *, pause=0, code=0, stderr="progress visible"):
    program = (
        "import json, sys, time; "
        f"print({stderr!r}, file=sys.stderr, flush=True); "
        f"time.sleep({pause!r}); "
        f"print(json.dumps({report!r}, indent=2), flush=True); "
        f"sys.exit({code!r})"
    )
    return sys.executable, ["-u", "-X", "utf8", "-c", program]


def track(qtbot, widget):
    def close(value):
        value.close()
        qtbot.waitUntil(lambda: value.process is None, timeout=20000)
        if value.main_window is not None:
            value.main_window.close()

    qtbot.addWidget(widget, before_close_func=close)
    widget.show()
    return widget


def window_factory(qtbot, calls):
    def factory():
        calls.append("main")
        widget = QWidget()
        qtbot.addWidget(widget)
        return widget

    return factory


def test_portable_commands_are_fixed_isolated_and_simulation_only(root, qtbot):
    widget = track(qtbot, StartupChecks(root, auto_start=False))
    program, args = widget._command()
    assert program == str(root / "runtime/python.exe")
    assert args[:6] == ["-I", "-B", "-u", "-X", "utf8", str(root / "tools/verify_bundle.py")]
    assert args[-3:] == [str(root), "--progress", "--save-report"]
    widget.stage = "simulation"
    program, args = widget._command()
    assert args[6:8] == ["cli", "simulate"]
    assert "measure" not in args and "--resource" not in args and "--fast" in args
    assert args[args.index("--config") + 1] == str(root / "app/examples/simulation_config.json")
    assert args[args.index("--output") + 1] == str(root / "diagnostics/startup-simulation")


def test_sequence_remains_responsive_and_only_opens_main_after_both_reports(root, qtbot):
    order, opened, ticks = [], [], []

    def command(stage):
        order.append(stage)
        report = BUNDLE if stage == "bundle" else SIMULATION
        progress = "[CHECK] 3/12 files processed" if stage == "bundle" else "[READ] #1 가상 판독"
        return child(report, pause=0.15, stderr=progress)

    widget = track(
        qtbot,
        StartupChecks(
            root, command_factory=command, main_window_factory=window_factory(qtbot, opened)
        ),
    )
    timer = QTimer(widget)
    timer.timeout.connect(lambda: ticks.append(widget.state))
    timer.start(10)
    qtbot.waitUntil(lambda: "[CHECK]" in widget.details.toPlainText(), timeout=20000)
    assert not opened and widget.progress.maximum() == 12
    qtbot.waitUntil(lambda: widget.state == "passed", timeout=20000)
    timer.stop()
    assert order == ["bundle", "simulation"] and opened == ["main"]
    assert len(ticks) > 2
    assert widget.main_window.isVisible()
    assert "가상 판독" in widget.details.toPlainText()
    assert widget.stage_results == {"bundle": BUNDLE, "simulation": SIMULATION}
    saved = json.loads(widget.report_path.read_text(encoding="utf-8"))
    assert saved["status"] == "passed" and saved["checks"] == widget.stage_results
    assert saved["hardware_verified"] is False and saved["automatic_output_enable"] is False


@pytest.mark.parametrize(
    ("stage", "report", "exit_code"),
    [
        ("bundle", dict(BUNDLE, status="failed"), 0),
        ("bundle", BUNDLE, 2),
        ("bundle", ["not a report"], 0),
        ("simulation", dict(SIMULATION, output_state="UNKNOWN"), 0),
        ("simulation", dict(SIMULATION, reading_count=0), 0),
    ],
)
def test_failed_process_or_report_never_opens_measurement_ui(root, qtbot, stage, report, exit_code):
    order, opened = [], []

    def command(current):
        order.append(current)
        payload = report if current == stage else BUNDLE
        return child(payload, code=exit_code if current == stage else 0)

    widget = track(
        qtbot,
        StartupChecks(
            root, command_factory=command, main_window_factory=window_factory(qtbot, opened)
        ),
    )
    qtbot.waitUntil(lambda: widget.state == "failed", timeout=20000)
    assert not opened and widget.main_window is None
    assert order == (["bundle"] if stage == "bundle" else ["bundle", "simulation"])
    assert widget.isVisible() and widget.retry_button.isEnabled()
    saved = json.loads(widget.report_path.read_text())
    assert saved["status"] == "failed" and saved["stage"] == stage


def test_real_configuration_cannot_be_launched_by_automatic_self_test(root, qtbot):
    config = root / "app/examples/simulation_config.json"
    config.write_text(
        json.dumps(dict(simulation=False, transport="visa", resource="GPIB0::27::INSTR"))
    )
    commands, opened = [], []

    def command(stage):
        commands.append(stage)
        return child(BUNDLE)

    widget = track(
        qtbot,
        StartupChecks(
            root, command_factory=command, main_window_factory=window_factory(qtbot, opened)
        ),
    )
    qtbot.waitUntil(lambda: widget.state == "failed", timeout=20000)
    assert commands == ["bundle"] and not opened
    assert "가상 측정 설정" in widget.status_label.text()


def test_retry_runs_both_stages_fresh_after_failure(root, qtbot):
    commands, opened = [], []

    def command(stage):
        commands.append(stage)
        if len(commands) == 1:
            return child(dict(BUNDLE, status="failed"))
        return child(BUNDLE if stage == "bundle" else SIMULATION)

    widget = track(
        qtbot,
        StartupChecks(
            root, command_factory=command, main_window_factory=window_factory(qtbot, opened)
        ),
    )
    qtbot.waitUntil(lambda: widget.state == "failed", timeout=20000)
    first_report = widget.report_path
    assert not opened
    widget.retry_button.click()
    qtbot.waitUntil(lambda: widget.state == "passed", timeout=20000)
    assert commands == ["bundle", "bundle", "simulation"] and opened == ["main"]
    assert widget.report_path != first_report and first_report.is_file()


def test_closing_active_check_waits_for_its_child_exit_and_never_opens_main(root, qtbot):
    opened = []
    widget = track(
        qtbot,
        StartupChecks(
            root,
            command_factory=lambda stage: child(BUNDLE, pause=60),
            main_window_factory=window_factory(qtbot, opened),
        ),
    )
    qtbot.waitUntil(
        lambda: (
            widget.process is not None and widget.process.state() == QProcess.ProcessState.Running
        ),
        timeout=20000,
    )
    process = widget.process
    widget.close()
    qtbot.waitUntil(lambda: widget.state == "cancelled", timeout=20000)
    assert widget.process is None and not opened
    # QProcess may already have been deleted later; its owner no longer holds a live child.
    assert process is not widget.process
    assert json.loads(widget.report_path.read_text())["status"] == "cancelled"


def test_failed_to_start_is_reported_without_waiting_for_finished_signal(root, qtbot):
    opened = []
    widget = track(
        qtbot,
        StartupChecks(
            root,
            command_factory=lambda stage: (str(root / "missing-interpreter.exe"), []),
            main_window_factory=window_factory(qtbot, opened),
        ),
    )
    qtbot.waitUntil(lambda: widget.state == "failed", timeout=20000)
    assert widget.process is None and not opened
    assert "실행기" in widget.status_label.text()


def test_cancel_while_starting_finishes_even_when_failed_to_start_has_no_finished_signal(
    root, qtbot
):
    class FailedStartingProcess(QProcess):
        def start(self, program, args):
            self.starting = True
            QTimer.singleShot(0, self.fail)

        def state(self):
            return self.ProcessState.Starting if self.starting else self.ProcessState.NotRunning

        def terminate(self):
            pass

        def fail(self):
            self.starting = False
            self.errorOccurred.emit(self.ProcessError.FailedToStart)

    opened = []
    widget = track(
        qtbot,
        StartupChecks(
            root,
            process_factory=FailedStartingProcess,
            main_window_factory=window_factory(qtbot, opened),
            auto_start=False,
        ),
    )
    widget.begin()
    widget.close()
    assert widget.state == "cancelling"
    qtbot.waitUntil(lambda: widget.state == "cancelled", timeout=20000)
    assert widget.process is None and not widget.isVisible() and not opened
    assert json.loads(widget.report_path.read_text())["status"] == "cancelled"


def test_report_storage_failure_does_not_launch_main(root, qtbot):
    (root / "diagnostics").write_text("not a directory")
    opened = []
    widget = track(
        qtbot,
        StartupChecks(
            root,
            command_factory=lambda stage: child(BUNDLE if stage == "bundle" else SIMULATION),
            main_window_factory=window_factory(qtbot, opened),
        ),
    )
    qtbot.waitUntil(lambda: widget.state == "failed", timeout=20000)
    assert not opened and widget.report_path is None
    assert "보고서" in widget.status_label.text()
