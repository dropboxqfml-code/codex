"""Durable final outcomes are visible; opening past data never operates hardware."""

import json
from dataclasses import replace

import pytest

from keithley6517a import cli
from keithley6517a.clock import FakeClock
from keithley6517a.config import RunConfig
from keithley6517a.measurement.runner import MeasurementRunner
from keithley6517a.ui.main_window import MainWindow


def close_widget(qtbot, widget):
    widget.close()
    qtbot.waitUntil(lambda: widget._closed, timeout=20000)


@pytest.fixture
def window(qtbot):
    widget = MainWindow(lambda *a, **kw: pytest.fail("Review must not connect an instrument"))
    qtbot.addWidget(widget, before_close_func=lambda value: close_widget(qtbot, value))
    widget._load_controls(
        replace(RunConfig(), current_trip_A=1e-8, residual_warning_ack=True).to_dict()
    )
    return widget


@pytest.mark.parametrize(
    ("outcome", "title", "state"),
    [
        ("completed", "정상 완료", "OUTPUT_OFF_CONFIRMED"),
        ("stopped", "사용자 중지", "OUTPUT_OFF_CONFIRMED"),
        ("aborted", "오류 종료", "FAULT"),
    ],
)
def test_terminal_outcomes_show_saved_count_without_confusing_stop_and_fault(
    window, outcome, title, state
):
    window._on_status(
        dict(
            state=state,
            output_state="OFF",
            run_started=True,
            run_result=dict(status=outcome, reason="test reason", reading_count=2, elapsed_s=1.25),
        )
    )
    assert title in window.result_status_label.text()
    assert "2행" in window.result_status_label.text()
    assert "1.25 s" in window.result_status_label.text()
    if outcome == "stopped":
        assert "사용자 중지" in window.workflow_label.text()
        assert "장비 확인 필요" not in window.workflow_label.text()
    elif outcome == "aborted":
        assert "test reason" in window.workflow_label.text()
    assert not window.arm_button.isEnabled() and not window.start_button.isEnabled()


def test_output_off_during_finalization_stays_busy_and_disables_review(window):
    window._on_status(
        dict(
            state="OUTPUT_OFF_CONFIRMED",
            output_state="OFF",
            worker_busy=True,
            can_arm=True,
            can_start=True,
        )
    )
    assert window._busy
    assert not window.review_results_button.isEnabled()
    assert not window.arm_button.isEnabled() and not window.start_button.isEnabled()
    assert not window.disconnect_button.isEnabled()


def test_settings_repair_waits_for_idle_disconnect_before_opening_dialog(
    window, qtbot, monkeypatch
):
    opened = []
    monkeypatch.setattr(window, "_setup_test", lambda: opened.append(window._busy))
    window._edit_after_disconnect = True
    window._on_status(dict(state="DISCONNECTED", output_state="OFF", worker_busy=True))
    qtbot.wait(1)
    assert window._edit_after_disconnect and not opened
    window._on_status(dict(state="DISCONNECTED", output_state="UNKNOWN", worker_busy=False))
    qtbot.waitUntil(lambda: bool(opened), timeout=20000)
    assert opened == [False] and not window._edit_after_disconnect


def test_past_result_review_opens_without_connecting_or_loading_run_settings(window, monkeypatch):
    opened = []

    class Dialog:
        def __init__(self, path=None, parent=None):
            opened.append(path)
            assert parent is window

        def exec(self):
            return 0

    monkeypatch.setattr("keithley6517a.ui.result_dialog.SavedResultDialog", Dialog)
    original = window.config_from_controls()
    assert window.review_results_button.isEnabled()
    window.review_results_button.click()
    assert opened == [None]
    assert window.worker.runner is None
    assert window.config_from_controls() == original


def stopped_runner(config, *, clock=None, on_sample=None, on_event=None):
    def sample(row):
        if on_sample:
            on_sample(row)
        if len(runner.rows) >= 2:
            runner.request_stop("user STOP")

    runner = MeasurementRunner(
        config, clock=clock or FakeClock(), on_sample=sample, on_event=on_event
    )
    return runner


def stop_config(tmp_path):
    return replace(
        RunConfig(),
        output_directory=str(tmp_path),
        voltages=(1,),
        simulation_resistance_ohm=1e9,
        current_trip_A=1e-8,
        residual_warning_ack=True,
        dwell_s=10,
        summary_window_s=1,
        sample_interval_s=0.1,
        nplc=0.1,
    )


def test_real_worker_stop_shows_durable_result_and_enables_offline_review(qtbot, tmp_path):
    widget = MainWindow(stopped_runner)
    qtbot.addWidget(widget, before_close_func=lambda value: close_widget(qtbot, value))
    widget._load_controls(stop_config(tmp_path).to_dict())
    widget.connect_button.click()
    qtbot.waitUntil(lambda: widget.arm_button.isEnabled(), timeout=20000)
    widget.arm_button.click()
    qtbot.waitUntil(lambda: widget.start_button.isEnabled(), timeout=20000)
    widget.start_button.click()
    qtbot.waitUntil(lambda: widget._last_run_result.get("status") == "stopped", timeout=20000)
    assert not widget._busy and widget._state == "OUTPUT_OFF_CONFIRMED"
    assert widget.worker.runner.writer.closed
    assert "사용자 중지" in widget.result_status_label.text()
    assert "2행" in widget.result_status_label.text()
    assert widget.review_results_button.isEnabled()
    assert widget.repair_button.text() == "연결 종료 후 설정 수정"
    saved = json.loads((widget.worker.runner.run_directory / "run_status.json").read_text())
    assert saved["status"] == "stopped" and saved["reading_count"] == 2


def test_gui_stop_while_armed_finalizes_without_pressing_start(qtbot, tmp_path):
    widget = MainWindow(lambda config, **kw: MeasurementRunner(config, clock=FakeClock(), **kw))
    qtbot.addWidget(widget, before_close_func=lambda value: close_widget(qtbot, value))
    widget._load_controls(stop_config(tmp_path).to_dict())
    widget.connect_button.click()
    qtbot.waitUntil(lambda: widget.arm_button.isEnabled(), timeout=20000)
    widget.arm_button.click()
    qtbot.waitUntil(lambda: widget.start_button.isEnabled(), timeout=20000)
    widget.stop_button.click()
    assert not widget.start_button.isEnabled()
    qtbot.waitUntil(lambda: widget._last_run_result.get("status") == "stopped", timeout=20000)
    runner = widget.worker.runner
    assert runner.writer.closed and not widget._busy
    assert widget._last_run_result["reading_count"] == 0
    assert ":OUTP1 ON" not in runner.instrument.transport.commands
    assert "사용자 중지" in widget.result_status_label.text()
    assert not widget.start_button.isEnabled() and not widget.arm_button.isEnabled()


def test_cli_user_stop_has_explicit_stop_feedback_and_interrupt_exit_code(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(cli, "MeasurementRunner", stopped_runner)
    path = tmp_path / "sim.json"
    path.write_text(json.dumps(stop_config(tmp_path).to_dict()))
    assert cli.main(["simulate", "--config", str(path), "--fast", "--progress"]) == 130
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["status"] == "stopped" and result["reading_count"] == 2
    assert result["output_state"] == "OFF"
    assert "[STOP]" in captured.err and "[FAIL]" not in captured.err


def test_cli_stop_during_arm_does_not_call_start(tmp_path, monkeypatch, capsys):
    def factory(config, *, clock=None, on_sample=None, on_event=None):
        def event(item):
            if on_event:
                on_event(item)
            if item.get("state") == "CONFIGURING":
                runner.request_stop("user STOP")

        runner = MeasurementRunner(config, clock=clock, on_sample=on_sample, on_event=event)
        return runner

    monkeypatch.setattr(cli, "MeasurementRunner", factory)
    path = tmp_path / "sim.json"
    path.write_text(json.dumps(stop_config(tmp_path).to_dict()))
    assert cli.main(["simulate", "--config", str(path), "--fast", "--progress"]) == 130
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["status"] == "stopped" and result["reading_count"] == 0
    assert "[STOP]" in captured.err
    assert "[START]" not in captured.err and "[FAIL]" not in captured.err
