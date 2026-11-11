"""Injectable monotonic scheduling and timezone-aware wall timestamps."""

import time
from datetime import UTC, datetime, timedelta


class Clock:
    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def wall_time(self) -> str:
        return datetime.now(UTC).isoformat()


class FakeClock:
    """Deterministic virtual time. Hook can inject cooperative STOP during a wait."""

    def __init__(self, hook=None):
        self.now = 0.0
        self.hook = hook

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("Negative sleep")
        self.now += seconds
        if self.hook:
            self.hook(self.now)

    def wall_time(self) -> str:
        return (datetime(2026, 11, 11, tzinfo=UTC) + timedelta(seconds=self.now)).isoformat()
