"""Exercise the Windows trial's stop and request waits with unavailable console I/O."""

import io
from contextlib import contextmanager, nullcontext
from datetime import timedelta
from threading import Event

import pytest
from test_watch_runtime import FakeClock

from image_monitor import monitor_trial_progress as progress
from image_monitor.monitor_clock import wait_until


@pytest.mark.parametrize("trigger", ["enter", "time_limit"])
def test_blocked_console_cannot_hold_file_checkpoints_stop_or_teardown(
    monkeypatch, capsys, trigger
):
    writing, release, closed = Event(), Event(), Event()
    read_started, enter = Event(), Event()
    requested = Event()
    now = [0]
    monkeypatch.setattr(progress, "monotonic", lambda: now[0])
    monkeypatch.setattr(progress, "_HEARTBEAT_SECONDS", 0.02)

    class Blocked(io.StringIO):
        def write(self, data):
            writing.set()
            assert release.wait(5)
            return super().write(data)

    console = Blocked()

    @contextmanager
    def open_console():
        try:
            yield console
        finally:
            closed.set()

    def keyboard():
        read_started.set()
        if trigger == "time_limit":
            release.wait(5)
        return enter.is_set()

    class Log(io.StringIO):
        def flush(self):
            super().flush()
            if "현재 단계가 안전하게" in self.getvalue():
                requested.set()

    log = Log()
    monkeypatch.setattr(progress.sys, "stderr", log)
    trial = progress.MonitorTrial(open_console, keyboard)
    try:
        with trial.observe():
            trial.record("시작")
            assert writing.wait(2) and read_started.wait(2)
            for n in range(10):
                trial.record(f"작업 {n}")
            assert "작업 0" in log.getvalue() and "작업 9" in log.getvalue()
            if trigger == "enter":
                now[0] = 65
                enter.set()
            else:
                now[0] = 300
            # No call from the monitor owner is needed to detect either event.
            assert requested.wait(2)
            assert trial.should_stop() and trial.stop_trigger == trigger
            assert trial.stop_elapsed == now[0]
        assert not release.is_set() and not closed.is_set()
    finally:
        release.set()
    assert closed.wait(2)
    assert "작업 0" not in console.getvalue()


@pytest.mark.parametrize(("elapsed", "proceed"), [(60, True), (1694, False)])
def test_request_wait_logs_deadline_and_actual_wake_before_next_navigation(
    monkeypatch, capsys, elapsed, proceed
):
    clock = FakeClock()
    now = [0]
    monkeypatch.setattr(progress, "monotonic", lambda: now[0])
    trial = progress.MonitorTrial(lambda: nullcontext(progress.sys.stderr), None)

    def wake(seconds):
        assert seconds == 0.5
        clock.current += timedelta(seconds=elapsed)
        now[0] += elapsed

    clock.wait = wake
    with trial.observe():
        due = clock.now() + timedelta(seconds=60)
        assert wait_until(clock, due, trial.should_stop, label="본문 요청 간격 대기") is proceed
    log = capsys.readouterr().err
    assert "예정 60.0초" in log and f"실제 {elapsed}.0초" in log
    assert "요청 가능 시각" in log and "복귀 시각" in log
    if proceed:
        assert trial.stop_trigger is None
    else:
        assert trial.stop_trigger == "time_limit" and trial.stop_elapsed == elapsed
        assert log.index("시험 시간제한 종료 요청") < log.index("대기 복귀")


def test_process_returns_final_result_while_console_pipe_remains_full(tmp_path):
    import subprocess
    import sys
    import textwrap

    # Never drain stdout while the child runs. The OS, including Windows, will
    # keep its display writer blocked in a native write until process exit.
    program = textwrap.dedent("""
        import os, sys
        from contextlib import contextmanager
        from threading import Event
        from image_monitor import monitor_trial_progress as progress

        writing, returned = Event(), Event()
        class Display:
            def write(self, text):
                writing.set()
                os.write(1, b'x' * (4 * 1024 * 1024))
                returned.set()
            def flush(self):
                pass

        @contextmanager
        def open_console():
            yield Display()

        trial = progress.MonitorTrial(open_console, None)
        with trial.observe():
            trial.record('start')
            assert writing.wait(3)
            trial.record('after blocked native write')
            trial.started -= 301
            assert trial.should_stop()
        assert not returned.is_set()
        print('finished', trial.stop_trigger, file=sys.stderr, flush=True)
    """)
    path = tmp_path / "result.txt"
    with (
        path.open("wb") as log,
        subprocess.Popen(
            [sys.executable, "-c", program], stdout=subprocess.PIPE, stderr=log
        ) as proc,
    ):
        try:
            assert proc.wait(timeout=12) == 0, path.read_bytes()[-1500:]
        finally:
            if proc.poll() is None:
                proc.kill()
    data = path.read_bytes()
    assert b"after blocked native write" in data and b"finished time_limit" in data
