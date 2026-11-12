"""Signed apparent resistance and explicitly limited, unsmoothed window statistics."""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable, Mapping


def _finite(value):
    return type(value) in (float, int) and math.isfinite(value)


def _ratio(numerator, denominator):
    if numerator is None or denominator is None or denominator == 0:
        return None
    value = numerator / denominator
    return value if math.isfinite(value) else None


def analyze_reading(
    config,
    value: float | None,
    *,
    voltage_V: float,
    status: str = "N",
    flags: Iterable[str] = (),
    current_limit: bool = False,
    zero_check: bool = False,
) -> dict:
    """No DUT-voltage measurement or unverified series correction is invented.

    Parser-provided status/sentinel flags remain attached. Instrument readings are
    never relabelled as unfiltered ADC data, and inferred current has its own field.
    """
    quality = list(dict.fromkeys(flags))
    status_flags = {
        "Z": "ZERO_CHECK",
        "O": "OVERFLOW",
        "U": "UNDERFLOW",
        "R": "REFERENCE",
        "L": "OUT_OF_LIMIT",
    }
    if status != "N":
        quality.append(status_flags.get(status, "UNKNOWN_STATUS"))
    if not _finite(value):
        quality.append("NONFINITE_OR_MISSING")
        value = None
    if value is not None and abs(value) >= 9e37:
        quality.append("SENTINEL")
        value = None
    if current_limit:
        quality.append("SOURCE_CURRENT_LIMIT")
    if zero_check:
        quality.append("ZERO_CHECK")
    if not _finite(voltage_V):
        raise ValueError("Voltage readback must be finite")
    summary_exclusions = {
        "OUTSIDE_SUMMARY_WINDOW",
        "AFTER_DWELL",
        "SETTLING_EXCLUDED",
        "RANGE_CHANGE_TIMING_UNCERTAIN",
    }
    invalid_flags = (
        set(quality)
        - summary_exclusions
        - {
            "SERIES_DROP_UNVERIFIED",
            "RANGE_NUMBER_GAP",
            "READING_NUMBER_GAP_NOT_PROOF_OF_LOSS",
        }
    )
    valid = not invalid_flags
    result = dict(
        current_raw_A=None,
        current_background_A=None,
        current_corrected_A=None,
        current_inferred_A=None,
        resistance_apparent_ohm=None,
        resistance_corrected_ohm=None,
        native_r_ohm=None,
        resistance_lower_bound_ohm=None,
        resistivity_ohm_m=None,
        voltage_dut_estimated_V=None,
        voltage_basis="SOURCE_PROGRAMMED_READBACK_NOT_DUT_MEASUREMENT",
        valid_for_summary=valid and not summary_exclusions.intersection(quality),
    )
    if config.mode == "FVMI_CURRENT":
        result["current_raw_A"] = value
        background = config.background_A
        corrected = value - (background or 0.0) if value is not None else None
        result["current_background_A"] = background
        result["current_corrected_A"] = corrected
        if voltage_V == 0:
            quality.append("ZERO_VOLTAGE_UNDEFINED_R")
        elif valid and corrected is not None:
            if abs(value) > config.current_threshold_A:
                result["resistance_apparent_ohm"] = _ratio(voltage_V, value)
            if abs(corrected) <= config.current_threshold_A:
                quality.append("NOT_RESOLVED")
            else:
                result["resistance_corrected_ohm"] = _ratio(voltage_V, corrected)
            if config.series_correction_verified and result["resistance_corrected_ohm"] is not None:
                estimate = (
                    voltage_V - value * config.series_resistance_ohm - config.burden_estimate_V
                )
                result["voltage_dut_estimated_V"] = estimate
                result["resistance_corrected_ohm"] = _ratio(estimate, corrected)
                result["voltage_basis"] = "VERIFIED_SERIES_MODEL_ESTIMATE_NOT_MEASUREMENT"
            else:
                quality.append("SERIES_DROP_UNVERIFIED")
    else:
        if voltage_V == 0:
            quality.append("ZERO_VOLTAGE_UNDEFINED_R")
        elif valid and value is not None and value != 0:
            result["native_r_ohm"] = value
            result["current_inferred_A"] = _ratio(voltage_V, value)
            quality.append("INFERRED_CURRENT_NOT_MEASURED")
        elif value == 0:
            quality.append("ZERO_NATIVE_R")
            result["valid_for_summary"] = False
    resistance = (
        result["native_r_ohm"]
        if config.mode == "NATIVE_RESISTANCE"
        else result["resistance_corrected_ohm"]
    )
    area, length = config.effective_geometry_m
    if resistance is not None and area is not None and length is not None:
        rho = resistance * (area / length)
        if math.isfinite(rho) and (rho != 0 or resistance == 0):
            result["resistivity_ohm_m"] = rho
    result["quality_flags"] = list(dict.fromkeys(quality))
    return result


def _stats(values: list[float], times: list[float]) -> dict:
    if not values:
        return dict(
            mean=None,
            median=None,
            standard_deviation=None,
            minimum=None,
            maximum=None,
            slope=None,
            N=0,
            actual_window_start_s=None,
            actual_window_end_s=None,
            actual_window_duration_s=None,
        )
    mean_t = statistics.fmean(times)
    mean_v = statistics.fmean(values)
    denominator = sum((t - mean_t) ** 2 for t in times)
    slope = (
        sum((t - mean_t) * (v - mean_v) for t, v in zip(times, values, strict=True)) / denominator
        if denominator > 0
        else None
    )
    return dict(
        mean=mean_v,
        median=statistics.median(values),
        standard_deviation=statistics.stdev(values) if len(values) > 1 else None,
        minimum=min(values),
        maximum=max(values),
        slope=slope,
        N=len(values),
        actual_window_start_s=min(times),
        actual_window_end_s=max(times),
        actual_window_duration_s=max(times) - min(times),
    )


def summarize(config, rows: list[Mapping]) -> dict:
    """Summarize one constant-voltage step; raw/transient rows are not mutated."""
    selected = [
        r
        for r in rows
        if r.get("valid_for_summary")
        and r.get("time_since_voltage_command_s", config.dwell_s)
        >= max(config.exclude_initial_s, config.dwell_s - config.summary_window_s)
        and r.get("time_since_voltage_command_s", config.dwell_s) <= config.dwell_s
    ]
    field = "current_corrected_A" if config.mode == "FVMI_CURRENT" else "native_r_ohm"
    selected = [r for r in selected if _finite(r.get(field))]
    times = [float(r.get("elapsed_s", r.get("time_since_voltage_command_s", 0))) for r in selected]
    values = [float(r[field]) for r in selected]
    stats = _stats(values, times)
    voltages = {r.get("voltage_programmed_readback_V") for r in selected}
    if len(voltages) > 1:
        raise ValueError("A summary must contain one constant source voltage")
    voltage = next(iter(voltages), None)
    result = dict(
        stats,
        mode=config.mode,
        voltage_programmed_readback_V=voltage,
        R_from_mean_current_ohm=None,
        native_r_mean_ohm=None,
        current_inferred_mean_A=None,
        current_mean_A=None,
        mean_individual_resistance_ohm=None,
        stability="NOT_STABLE",
        resolution="NOT_RESOLVED",
        uncertainty_model="NOT_IMPLEMENTED",
        current_threshold_A=config.current_threshold_A,
        threshold_method="max(user_floor, sigma_multiplier * approved_background_uncertainty)",
    )
    if not selected:
        return result
    if config.mode == "FVMI_CURRENT":
        result["current_mean_A"] = stats["mean"]
        if voltage != 0 and abs(stats["mean"]) > config.current_threshold_A:
            result["R_from_mean_current_ohm"] = _ratio(voltage, stats["mean"])
            result["resolution"] = "RESOLVED"
        individual = [
            r["resistance_corrected_ohm"]
            for r in selected
            if _finite(r.get("resistance_corrected_ohm"))
        ]
        result["mean_individual_resistance_ohm"] = (
            statistics.fmean(individual) if individual else None
        )
    else:
        result["native_r_mean_ohm"] = stats["mean"]
        result["current_inferred_mean_A"] = _ratio(voltage, stats["mean"])
        result["resolution"] = "NATIVE_INSTRUMENT_READING"
    # This diagnostic does not terminate acquisition early and does not certify DC equilibrium.
    ranges = {r.get("current_range_A") for r in selected}
    last_step_t = max(r.get("time_since_voltage_command_s", 0) for r in selected)
    if (
        config.mode == "FVMI_CURRENT"
        and stats["N"] >= config.stability_min_samples
        and len(ranges) == 1
        and last_step_t >= config.min_dwell_s
        and stats["slope"] is not None
    ):
        scale = max(abs(stats["median"]), config.current_threshold_A)
        span = stats["actual_window_duration_s"]
        drift_ok = abs(stats["slope"]) <= max(
            config.absolute_drift_A_per_s, config.drift_fraction * scale / max(span, 1e-12)
        )
        noise_ok = stats["standard_deviation"] <= max(
            config.absolute_noise_A, config.noise_fraction * scale
        )
        if drift_ok and noise_ok:
            result["stability"] = "STABLE_WINDOW"
    return result


class StabilityTracker:
    """Require successive passing windows; resolution remains a separate field."""

    def __init__(self, config):
        self.config = config
        self.passes = 0
        self.last_window = None

    def evaluate(self, rows: list[Mapping]) -> dict:
        result = summarize(self.config, rows)
        marker = (result["actual_window_end_s"], result["N"])
        if marker != self.last_window:
            self.passes = self.passes + 1 if result["stability"] == "STABLE_WINDOW" else 0
            self.last_window = marker
        result["stability"] = (
            "STABLE" if self.passes >= self.config.stability_consecutive else "NOT_STABLE"
        )
        result["consecutive_passing_windows"] = self.passes
        return result
