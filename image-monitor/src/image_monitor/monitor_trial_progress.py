"""Live evidence and cooperative stopping for the two-cycle Windows launcher."""

import sys
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Event, Lock, Thread
from time import monotonic

_CURRENT = ContextVar("automatic_monitor_trial", default=None)
_TRIAL_SECONDS = 300
_HEARTBEAT_SECONDS = 60


def trial_stage(label):
    trial = _CURRENT.get()
    if trial is not None:
        trial.record(label, stage=label)


class MonitorTrial:
    def __init__(self, console, keyboard):
        self.console = console
        self.keyboard = keyboard
        self.started = monotonic()
        self.stage = "자동 감시 시작"
        self.stop_trigger = None
        self._output = Lock()
        self._stop = Lock()

    def record(self, text, *, stage=None):
        with self._output:
            if stage:
                self.stage = stage
            elapsed = int(monotonic() - self.started)
            line = f"[시험 {elapsed}초] {text}"
            # stderr is the CMD's open result TXT, including on a forced exit.
            print(line, file=sys.stderr, flush=True)
            if self.console is not sys.stderr:
                print(line, file=self.console, flush=True)

    def should_stop(self):
        with self._stop:
            if self.stop_trigger is None:
                if monotonic() - self.started >= _TRIAL_SECONDS:
                    self.stop_trigger = "time_limit"
                elif self.keyboard and self.keyboard():
                    self.stop_trigger = "enter"
            return self.stop_trigger is not None

    @contextmanager
    def observe(self):
        done = Event()

        def heartbeat():
            while not done.wait(_HEARTBEAT_SECONDS):
                if self.should_stop():
                    self.record(
                        f"종료 요청 · 현재 단계가 안전하게 끝나기를 기다립니다 · {self.stage}"
                    )
                    return
                self.record(f"진행 중 · 마지막 단계 {self.stage}")

        token = _CURRENT.set(self)
        thread = Thread(target=heartbeat, name="monitor-trial-progress", daemon=True)
        try:
            thread.start()
            yield
        finally:
            done.set()
            if thread.is_alive():
                thread.join()
            _CURRENT.reset(token)
