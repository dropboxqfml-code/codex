"""Dwell estimates follow acquired step ages and never certify output completion."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from keithley6517a.config import RunConfig
from keithley6517a.ui.main_window import MainWindow
from keithley6517a.ui.progress import MeasurementProgress, duration_text


def plan(*, points=(1,), cycles=1, dwell=10):
    return replace(
        RunConfig(),
        protocol="constant" if len(points) == 1 else "list",
        voltages=points,
        cycles=cycles,
        dwell_s=dwell,
        summary_window_s=min(1, dwell),
    )


def sample(cycle, step, age, elapsed=1000):
    return dict(
        cycle_index=cycle,
        step_index=step,
        time_since_voltage_command_s=age,
        elapsed_s=elapsed,
        phase="ACQUIRING",
    )


def test_constant_estimate_uses_step_age_not_global_elapsed_or_a_host_clock():
    progress = MeasurementProgress(plan(dwell=300))
    assert progress.estimate() is None and not progress.running
    progress.start()
    assert progress.update_step(0, 0)
    assert progress.update_sample(sample(0, 0, 10, elapsed=1000))
    estimate = progress.estimate()
    assert estimate.total_steps == estimate.step_number == 1
    assert estimate.remaining_s == 290
    assert estimate.fraction == pytest.approx(1 / 30)
    assert estimate.elapsed_s == 1000
    # Repainting during a slow read leaves the last acquired time basis unchanged.
    assert progress.estimate() == estimate


def test_sweep_cycles_include_all_remaining_steps_and_ignore_step_overrun():
    progress = MeasurementProgress(plan(points=(1, 2, 3), cycles=2))
    progress.start()
    progress.update_sample(sample(1, 0, 2))
    estimate = progress.estimate()
    assert estimate.total_steps == 6 and estimate.step_number == 4
    assert estimate.remaining_s == 28
    assert estimate.fraction == pytest.approx(32 / 60)
    progress.update_sample(sample(1, 0, 30))
    assert progress.estimate().remaining_s == 20
    assert progress.estimate().fraction == pytest.approx(4 / 6)
    progress.update_step(1, 1)
    assert progress.estimate().remaining_s == 20


@pytest.mark.parametrize(
    "row",
    [
        sample(0, 0, -1),
        sample(0, 0, float("nan")),
        sample(0, 0, float("inf")),
        sample(0, 0, True),
        sample(0, 0, "1"),
        sample(0, 2, 1),
        sample(True, 0, 1),
        dict(sample(0, 0, 1), phase="ERROR"),
    ],
)
def test_invalid_record_does_not_advance_the_last_estimate(row):
    progress = MeasurementProgress(plan())
    progress.start()
    progress.update_sample(sample(0, 0, 2))
    original = progress.estimate()
    assert not progress.update_sample(row)
    assert progress.estimate() == original


def test_duplicate_older_records_do_not_reverse_progress_or_resume_after_stop():
    progress = MeasurementProgress(plan(points=(1, 2), cycles=2))
    progress.start()
    progress.update_sample(sample(1, 0, 5, elapsed=30))
    expected = progress.estimate()
    assert not progress.update_sample(sample(0, 1, 9, elapsed=20))
    assert progress.update_sample(sample(1, 0, 2, elapsed=15))
    assert progress.estimate() == expected
    progress.finishing = True
    assert not progress.update_sample(sample(1, 1, 9))
    progress.finish("stopped")
    assert not progress.running and progress.outcome == "stopped"
    assert not progress.update_step(1, 1)
    progress.start()
    assert progress.estimate() is None and progress.outcome is None


def test_invalid_age_cannot_advance_to_a_future_step():
    progress = MeasurementProgress(plan(points=(1, 2)))
    progress.start()
    progress.update_sample(sample(0, 0, 5))
    expected = progress.estimate()
    assert not progress.update_sample(sample(0, 1, None))
    assert not progress.update_sample(sample(0, 1, 10**1000))
    assert progress.estimate() == expected


@pytest.mark.parametrize("changes", [dict(dwell=0), dict(dwell=float("inf")), dict(cycles=True)])
def test_invalid_plan_is_rejected(changes):
    values = dict(voltages=(1,), cycles=1, dwell_s=10)
    values.update({{"dwell": "dwell_s"}.get(key, key): value for key, value in changes.items()})
    with pytest.raises(ValueError):
        MeasurementProgress(SimpleNamespace(**values))


@pytest.mark.parametrize(
    ("seconds", "text"),
    [(0, "0초"), (0.01, "1초"), (60, "1분 00초"), (3661, "1시간 01분 01초")],
)
def test_remaining_display_rounds_up(seconds, text):
    assert duration_text(seconds) == text


def close_window(qtbot, widget):
    widget.close()
    qtbot.waitUntil(lambda: widget._closed, timeout=20000)


@pytest.fixture
def window(qtbot):
    widget = MainWindow(lambda *a, **kw: pytest.fail("Display must not create a runner"))
    qtbot.addWidget(widget, before_close_func=lambda value: close_window(qtbot, value))
    return widget


def start_display(window, config=None):
    window._set_progress_plan(config or plan())
    window._progress.start()
    window._on_status(dict(state="ACQUIRING", output_state="ON", worker_busy=True))
    window._on_event(dict(event="voltage_step", cycle_index=0, step_index=0))


def test_main_window_estimate_is_frozen_and_uses_virtual_sample_time(window):
    start_display(window, plan(points=(1, 2), cycles=2, dwell=10))
    window.dwell.setValue(1000)
    window._on_sample(sample(1, 0, 5, elapsed=100))
    assert "3/4단계" in window.progress_label.text()
    assert "15초" in window.progress_label.text()
    assert window.progress_bar.value() == 62
    original = window.progress_label.text()
    window._refresh_progress()
    assert window.progress_label.text() == original
    assert window.worker.runner is None


def test_zero_estimate_and_off_still_wait_for_durable_idle_completion(window):
    start_display(window)
    window._on_sample(sample(0, 0, 10))
    assert "종료처리중" in window.progress_label.text()
    assert window.progress_bar.value() == 99
    window._on_status(dict(state="OUTPUT_OFF_CONFIRMED", output_state="OFF", worker_busy=True))
    assert "종료처리중" in window.progress_label.text()
    result = dict(status="completed", elapsed_s=12, reading_count=2)
    window._on_status(
        dict(state="OUTPUT_OFF_CONFIRMED", output_state="OFF", worker_busy=True, run_result=result)
    )
    assert window.progress_bar.value() == 99
    window._on_status(
        dict(state="OUTPUT_OFF_CONFIRMED", output_state="OFF", worker_busy=False, run_result=result)
    )
    assert window.progress_label.text() == "측정 완료" and window.progress_bar.value() == 100


def test_completed_record_without_confirmed_off_does_not_show_completion(window):
    start_display(window)
    window._on_sample(sample(0, 0, 10))
    window._on_status(
        dict(
            state="HV_STATE_UNKNOWN",
            output_state="UNKNOWN",
            worker_busy=False,
            run_result=dict(status="completed"),
        )
    )
    assert "종료처리중" in window.progress_label.text()
    assert window.progress_bar.value() < 100


@pytest.mark.parametrize(("outcome", "label"), [("stopped", "사용자 중지"), ("aborted", "오류")])
def test_stop_and_fault_remove_remaining_time_without_marking_plan_complete(window, outcome, label):
    start_display(window)
    window._on_sample(sample(0, 0, 2))
    window._on_status(
        dict(
            state="FAULT" if outcome == "aborted" else "OUTPUT_OFF_CONFIRMED",
            output_state="OFF",
            worker_busy=False,
            run_result=dict(status=outcome),
        )
    )
    assert label in window.progress_label.text() and "남은 시간" not in window.progress_label.text()
    assert window.progress_bar.value() == 20
    window._on_status(dict(state="DISCONNECTED", output_state="UNKNOWN", worker_busy=False))
    assert window._progress is None and window.progress_label.isHidden()


def test_armed_does_not_begin_countdown_and_close_disables_zip(window):
    window._set_progress_plan(plan())
    window._on_status(dict(state="ARMED", output_state="OFF", worker_busy=False))
    assert "측정 대기" in window.progress_label.text() and not window._progress.running
    assert not window.export_diagnostic_button.isEnabled()
