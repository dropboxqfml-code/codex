"""Finite, endpoint-checked voltage schedules, never an automatic high-voltage profile."""

import math
from dataclasses import dataclass
from decimal import Decimal


def linear_staircase(
    start: float, stop: float, step: float, max_points: int = 100000
) -> tuple[float, ...]:
    for value in (start, stop, step):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("Staircase values must be finite numbers")
    if step == 0 or (stop - start) * step < 0:
        raise ValueError("Step direction does not reach stop")
    first, last, stride = map(lambda v: Decimal(str(v)), (start, stop, step))
    count = int((last - first) // stride) + 1
    if count < 1 or count > max_points:
        raise ValueError("Staircase point count out of bounds")
    values = tuple(float(first + n * stride) for n in range(count))
    if Decimal(str(values[-1])) != last:
        raise ValueError("Endpoint must be exactly reachable; specify an explicit list otherwise")
    return values


@dataclass(frozen=True)
class Step:
    step_index: int
    cycle_index: int
    voltage_requested_V: float
    dwell_s: float


def schedule(config):
    config.validate(for_arm=True)
    return tuple(
        Step(step_index, cycle_index, voltage, config.dwell_s)
        for cycle_index in range(config.cycles)
        for step_index, voltage in enumerate(config.voltages)
    )
