"""Live evidence and cooperative stopping for the two-cycle Windows launcher."""

import sys
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Condition, Event, Thread
from time import monotonic

_CURRENT = ContextVar("automatic_monitor_trial", default=None)
_TRIAL_SECONDS = 300
_HEARTBEAT_SECONDS = 60


def trial_stop_requested():
    trial = _CURRENT.get()
    return trial is not None and trial.should_stop()


def save_due_after_trial(clock, due):
    trial = _CURRENT.get()
    if trial is None or trial.should_stop():
        return False
    remaining = trial.started + _TRIAL_SECONDS - monotonic()
    delay = (due - clock.now()).total_seconds()
    if delay <= 0 or delay < remaining:
        return False
    trial.record(
        f"저장 가능 시각이 시험 종료 시각 이후입니다 · 다음 실행에서 저장 재개 가능 · "
        f"요청 가능 시각 {due.isoformat(timespec='seconds')}",
        stage="저장 대기 이월",
    )
    return True


def trial_stage(label):
    trial = _CURRENT.get()
    if trial is not None:
        trial.record(label, stage=label)


@contextmanager
def trial_wait(label, clock, now, due):
    trial = _CURRENT.get()
    if trial is None:
        yield
        return
    start = monotonic()
    trial.record(
        f"{label} · 예정 {max(0, (due - now).total_seconds()):.1f}초 · "
        f"요청 가능 시각 {due.isoformat(timespec='seconds')}",
        stage=label,
    )
    try:
        yield
    finally:
        trial.record(
            f"{label} 복귀 · 실제 {monotonic() - start:.1f}초 · "
            f"복귀 시각 {clock.now().isoformat(timespec='seconds')}"
        )


class MonitorTrial:
    def __init__(self, open_console, keyboard):
        self.open_console = open_console
        self.keyboard = keyboard
        self.started = monotonic()
        self.stage = "자동 감시 시작"
        self.stop_trigger = None
        self.stop_elapsed = None
        self.enter_elapsed = None
        self._changed = Condition()
        self._latest = None
        self._done = Event()

    def record(self, text, *, stage=None):
        with self._changed:
            if stage:
                self.stage = stage
            elapsed = int(monotonic() - self.started)
            line = f"[시험 {elapsed}초] {text}"
            print(line, file=sys.stderr, flush=True)
            self._latest = line
            self._changed.notify()

    def _display(self):
        # The display owns the console handle, including close. QuickEdit can
        # suspend a console write for an arbitrary time.
        try:
            with self.open_console() as console:
                if console is sys.stderr:
                    return
                while True:
                    with self._changed:
                        self._changed.wait_for(
                            lambda: self._latest is not None or self._done.is_set()
                        )
                        line, self._latest = self._latest, None
                        if line is None:
                            return
                    print(line, file=console, flush=True)
        except (OSError, ValueError):
            return

    def _check_stop(self, *, enter=False):
        with self._changed:
            elapsed = monotonic() - self.started
            if enter and self.enter_elapsed is None:
                self.enter_elapsed = int(elapsed)
                self.record("실행 창 Enter 입력 확인")
            if self.stop_trigger is None and (enter or elapsed >= _TRIAL_SECONDS):
                self.stop_trigger = "time_limit" if elapsed >= _TRIAL_SECONDS else "enter"
                self.stop_elapsed = int(elapsed)
                reason = "시험 시간제한" if self.stop_trigger == "time_limit" else "Enter 입력"
                self.record(
                    f"{reason} 종료 요청 · 현재 단계가 안전하게 끝나기를 기다립니다 · {self.stage}"
                )
            return self.stop_trigger is not None

    def should_stop(self):
        return self._check_stop()

    def _read_enter(self):
        # Console input can also stall. Never hold a monitor lock while polling it.
        try:
            while not self._done.is_set():
                if self.keyboard():
                    with self._changed:
                        if not self._done.is_set():
                            self._check_stop(enter=True)
                    return
                self._done.wait(0.1)
        except (OSError, ValueError):
            return

    def _heartbeat(self):
        while not self.should_stop():
            left = self.started + _TRIAL_SECONDS - monotonic()
            if self._done.wait(max(0, min(_HEARTBEAT_SECONDS, left))):
                return
            if not self.should_stop():
                self.record(f"진행 중 · 마지막 단계 {self.stage}")

    @contextmanager
    def observe(self):
        token = _CURRENT.set(self)
        heartbeat = Thread(target=self._heartbeat, name="monitor-trial-progress", daemon=True)
        threads = [
            Thread(target=self._display, name="monitor-trial-console", daemon=True),
            heartbeat,
        ]
        if self.keyboard:
            threads.append(Thread(target=self._read_enter, name="monitor-trial-input", daemon=True))
        try:
            for thread in threads:
                thread.start()
            yield
        finally:
            with self._changed:
                self._done.set()
                self._changed.notify_all()
            # Only console I/O may still be blocked; it owns no report resource.
            for thread in threads:
                if thread.is_alive():
                    thread.join(timeout=None if thread is heartbeat else 0.1)
            _CURRENT.reset(token)
