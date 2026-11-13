"""Display-only estimates from the approved dwell plan and recorded sample ages."""

from __future__ import annotations

import math
from dataclasses import dataclass


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def duration_text(seconds):
    """Round up a remaining estimate without displaying a premature zero."""
    seconds = max(0, math.ceil(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    if hours:
        return f"{hours}시간 {minutes:02d}분 {seconds:02d}초"
    if minutes:
        return f"{minutes}분 {seconds:02d}초"
    return f"{seconds}초"


@dataclass(frozen=True)
class ProgressEstimate:
    total_steps: int
    step_number: int
    remaining_s: float
    fraction: float
    elapsed_s: float | None


class MeasurementProgress:
    """Track a fixed plan without reading an instrument or consulting a host clock.

    Elapsed acquisition time may include command/readback overhead. It is shown
    independently: future dwell is estimated using the current step's own age.
    This also keeps virtual-clock simulation consistent with the recorded data.
    """

    def __init__(self, config):
        self.points_per_cycle = len(config.voltages)
        self.cycles = config.cycles
        self.dwell_s = config.dwell_s
        if (
            self.points_per_cycle < 1
            or type(self.cycles) is not int
            or self.cycles < 1
            or not _finite(self.dwell_s)
            or self.dwell_s <= 0
        ):
            raise ValueError("Progress requires a finite positive dwell and nonempty plan")
        self.total_steps = self.points_per_cycle * self.cycles
        self.planned_total_s = self.total_steps * self.dwell_s
        if not math.isfinite(self.planned_total_s):
            raise ValueError("Progress plan duration must be finite")
        self.running = False
        self.finishing = False
        self.outcome = None
        self._step = None
        self._step_age_s = 0.0
        self._elapsed_s = None

    def start(self):
        self.running = True
        self.finishing = False
        self.outcome = None
        self._step = None
        self._step_age_s = 0.0
        self._elapsed_s = None

    def update_step(self, cycle_index, step_index):
        if (
            not self.running
            or self.finishing
            or type(cycle_index) is not int
            or type(step_index) is not int
            or not 0 <= cycle_index < self.cycles
            or not 0 <= step_index < self.points_per_cycle
        ):
            return False
        step = cycle_index * self.points_per_cycle + step_index
        if self._step is not None and step < self._step:
            return False
        if step != self._step:
            self._step = step
            self._step_age_s = 0.0
        return True

    def update_sample(self, row):
        if not self.running or self.finishing or row.get("phase") == "ERROR":
            return False
        age = row.get("time_since_voltage_command_s")
        if not _finite(age) or age < 0:
            return False
        cycle = row.get("cycle_index")
        index = row.get("step_index")
        if cycle is not None or index is not None:
            if not self.update_step(cycle, index):
                return False
        if self._step is None:
            return False
        self._step_age_s = max(self._step_age_s, age)
        elapsed = row.get("elapsed_s")
        if _finite(elapsed) and elapsed >= 0:
            self._elapsed_s = max(self._elapsed_s or 0.0, elapsed)
        return True

    def estimate(self):
        if self._step is None:
            return None
        age = min(self._step_age_s, self.dwell_s)
        remaining = (self.total_steps - self._step - 1) * self.dwell_s + self.dwell_s - age
        return ProgressEstimate(
            total_steps=self.total_steps,
            step_number=self._step + 1,
            remaining_s=max(0.0, remaining),
            fraction=min(1.0, max(0.0, (self._step * self.dwell_s + age) / self.planned_total_s)),
            elapsed_s=self._elapsed_s,
        )

    def finish(self, outcome):
        self.running = False
        self.finishing = False
        self.outcome = outcome
