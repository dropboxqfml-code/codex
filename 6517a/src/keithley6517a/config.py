"""Strict SI configuration and immutable, JSON-serializable execution snapshots."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, fields
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any


class ConfigurationError(ValueError):
    pass


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _freeze(v) for k, v in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(v) for v in value)
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise ConfigurationError("Metadata must contain strict finite JSON values")


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_plain(v) for v in value]
    return value


def _strict_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConfigurationError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ConfigurationError(f"Non-finite JSON constant: {value}")


@dataclass(frozen=True)
class RunConfig:
    schema_version: int = 1
    simulation: bool = True
    transport: str = "simulation"
    setup_policy: str = "verified_fixture"
    operator_setup_acknowledged: bool = False
    resource: str = ""
    visa_backend: str | None = None
    timeout_ms: int = 2000
    write_termination: str | None = "\n"
    read_termination: str | None = "\n"
    send_end: bool = True
    mode: str = "FVMI_CURRENT"
    protocol: str = "constant"
    sample_id: str = "sample"
    output_directory: str = "runs"
    note: str = ""
    voltages: tuple[float, ...] = (0.0,)
    cycles: int = 1
    dwell_s: float = 300.0
    min_dwell_s: float = 0.0
    exclude_initial_s: float = 0.0
    summary_window_s: float = 30.0
    sample_interval_s: float = 1.0
    range_settle_s: float = 1.0
    max_total_duration_s: float = 86400.0
    nplc: float = 10.0
    line_frequency_hz: float = 60.0
    current_autorange: bool = True
    current_range_A: float = 2e-9
    current_trip_A: float | None = None
    power_limit_W: float | None = None
    current_floor_A: float = 1e-14
    background_A: float | None = None
    background_approved: bool = False
    background_reference: str = ""
    background_uncertainty_A: float = 0.0
    background_sigma_multiplier: float = 3.0
    source_range_V: float = 100.0
    resistive_limit_enabled: bool | None = None
    voltage_ceiling_V: float = 10.0
    sample_limit_V: float | None = None
    fixture_limit_V: float | None = None
    cable_limit_V: float | None = None
    bipolar_authorized: bool = False
    rating_approval: str = ""
    residual_warning_ack: bool = False
    commissioning: Mapping[str, Any] = None
    sample_metadata: Mapping[str, Any] = None
    temperature_C: float | None = None
    relative_humidity_percent: float | None = None
    sample_length_mm: float | None = None
    sample_width_mm: float | None = None
    sample_depth_mm: float | None = None
    current_path_axis: str | None = None
    thickness_m: float | None = None
    area_m2: float | None = None
    series_resistance_ohm: float | None = None
    series_correction_verified: bool = False
    burden_estimate_V: float | None = None
    stability_min_samples: int = 5
    drift_fraction: float = 0.02
    noise_fraction: float = 0.02
    absolute_drift_A_per_s: float = 1e-15
    absolute_noise_A: float = 1e-14
    stability_consecutive: int = 2
    stop_policy: str = "immediate_off"
    seed: int = 6517
    simulation_resistance_ohm: float = 1e12

    def __post_init__(self) -> None:
        if not isinstance(self.voltages, (list, tuple)):
            raise ConfigurationError("voltages must be an array")
        object.__setattr__(self, "voltages", tuple(self.voltages))
        for name in ("commissioning", "sample_metadata"):
            value = getattr(self, name)
            if value is None:
                value = {}
            if not isinstance(value, Mapping):
                raise ConfigurationError(f"{name} must be an object")
            object.__setattr__(self, name, _freeze(value))
        self.validate(for_arm=False)

    @classmethod
    def from_dict(cls, value: Mapping) -> RunConfig:
        if not isinstance(value, Mapping):
            raise ConfigurationError("Configuration must be an object")
        unknown = set(value) - {f.name for f in fields(cls)}
        if unknown:
            raise ConfigurationError(f"Unknown configuration fields: {sorted(unknown)}")
        return cls(**value)

    @classmethod
    def load(cls, path: str | Path) -> RunConfig:
        try:
            value = json.loads(
                Path(path).read_text(encoding="utf-8"),
                object_pairs_hook=_strict_object,
                parse_constant=_reject_constant,
            )
        except (json.JSONDecodeError, TypeError) as exc:
            raise ConfigurationError(str(exc)) from exc
        if isinstance(value, Mapping) and ({"software", "settings"} & value.keys()):
            if set(value) != {"schema_version", "software", "settings"}:
                raise ConfigurationError(
                    "Run snapshot requires exactly schema_version/software/settings"
                )
            if type(value["schema_version"]) is not int or value["schema_version"] != 1:
                raise ConfigurationError("Unsupported run snapshot schema_version")
            if not isinstance(value["software"], Mapping) or not isinstance(
                value["settings"], Mapping
            ):
                raise ConfigurationError("Run snapshot software and settings must be objects")
            software = value["software"]
            known = {"version", "commit", "source_sha256", "working_tree_dirty"}
            if set(software) - known:
                raise ConfigurationError("Unknown software snapshot fields")
            for name in ("version", "source_sha256"):
                if name in software and not isinstance(software[name], str):
                    raise ConfigurationError(f"software.{name} must be a string")
            if (
                "commit" in software
                and software["commit"] is not None
                and not isinstance(software["commit"], str)
            ):
                raise ConfigurationError("software.commit must be a string or null")
            if (
                "working_tree_dirty" in software
                and type(software["working_tree_dirty"]) is not bool
            ):
                raise ConfigurationError("software.working_tree_dirty must be a boolean")
            value = value["settings"]
        return cls.from_dict(value)

    def to_dict(self) -> dict:
        return {f.name: _plain(getattr(self, f.name)) for f in fields(self)}

    @property
    def effective_ceiling(self) -> float:
        limits = [1000.0, self.voltage_ceiling_V]
        if self.setup_policy == "operator_low_voltage":
            limits.append(10.0)
        limits.extend(
            v
            for v in (self.sample_limit_V, self.fixture_limit_V, self.cable_limit_V)
            if v is not None
        )
        return min(limits)

    @property
    def current_threshold_A(self) -> float:
        return max(
            self.current_floor_A, self.background_sigma_multiplier * self.background_uncertainty_A
        )

    @property
    def effective_geometry_m(self) -> tuple[float | None, float | None]:
        """Return transverse area and current-path length in SI units.

        Rectangular dimensions describe full-face electrodes. Partial new inputs
        remain metadata; they never silently reuse an unrelated legacy geometry.
        Legacy area/thickness stay independent so clearing dimensions is reversible.
        """
        supplied = (
            self.sample_length_mm,
            self.sample_width_mm,
            self.sample_depth_mm,
            self.current_path_axis,
        )
        if not any(value is not None for value in supplied):
            return self.area_m2, self.thickness_m
        if any(value is None for value in supplied):
            return None, None
        dimensions = {
            "L": self.sample_length_mm * 1e-3,
            "W": self.sample_width_mm * 1e-3,
            "D": self.sample_depth_mm * 1e-3,
        }
        transverse = [value for axis, value in dimensions.items() if axis != self.current_path_axis]
        return transverse[0] * transverse[1], dimensions[self.current_path_axis]

    @property
    def voltage_resolution_V(self) -> float:
        return 0.005 if self.source_range_V == 100 else 0.05

    def quantize_voltage(self, voltage: float) -> float:
        step = Decimal(str(self.voltage_resolution_V))
        return float(
            (Decimal(str(voltage)) / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * step
        )

    def validate(self, for_arm: bool = True) -> None:
        for name in ("sample_length_mm", "sample_width_mm", "sample_depth_mm"):
            value = getattr(self, name)
            if value is None:
                continue
            try:
                valid = type(value) in (int, float) and math.isfinite(value)
            except OverflowError:
                valid = False
            if not valid:
                raise ConfigurationError(f"{name} must be finite numeric millimetres")
            if value <= 0:
                raise ConfigurationError(f"{name} must be positive")
        if self.current_path_axis is not None and (
            not isinstance(self.current_path_axis, str)
            or self.current_path_axis not in {"L", "W", "D"}
        ):
            raise ConfigurationError("current_path_axis must be L, W, D or null")
        if all(
            value is not None
            for value in (
                self.sample_length_mm,
                self.sample_width_mm,
                self.sample_depth_mm,
                self.current_path_axis,
            )
        ):
            area, length = self.effective_geometry_m
            if (
                not math.isfinite(area)
                or not math.isfinite(length)
                or area <= 0
                or length <= 0
                or not math.isfinite(area / length)
                or area / length <= 0
            ):
                raise ConfigurationError("Sample dimensions produce an unrepresentable SI geometry")
        if (
            self.resistive_limit_enabled is not None
            and type(self.resistive_limit_enabled) is not bool
        ):
            raise ConfigurationError("resistive_limit_enabled must be a boolean or null")
        bool_fields = (
            "send_end",
            "simulation",
            "current_autorange",
            "background_approved",
            "bipolar_authorized",
            "residual_warning_ack",
            "series_correction_verified",
            "operator_setup_acknowledged",
        )
        for name in bool_fields:
            if type(getattr(self, name)) is not bool:
                raise ConfigurationError(f"{name} must be a boolean")
        for name in (
            "schema_version",
            "timeout_ms",
            "cycles",
            "stability_min_samples",
            "stability_consecutive",
            "seed",
        ):
            if type(getattr(self, name)) is not int:
                raise ConfigurationError(f"{name} must be an integer")
        if self.schema_version != 1:
            raise ConfigurationError("Unsupported schema_version")
        if not 1 <= self.timeout_ms <= 60000:
            raise ConfigurationError("timeout_ms must be in 1..60000")
        if not 1 <= self.cycles <= 10000:
            raise ConfigurationError("cycles must be in 1..10000")
        if self.stability_min_samples < 3 or self.stability_consecutive < 1:
            raise ConfigurationError("Invalid stability sample/pass counts")
        for name in (
            "resource",
            "mode",
            "transport",
            "setup_policy",
            "protocol",
            "sample_id",
            "output_directory",
            "note",
            "background_reference",
            "rating_approval",
            "stop_policy",
        ):
            if not isinstance(getattr(self, name), str):
                raise ConfigurationError(f"{name} must be a string")
        for name in ("write_termination", "read_termination", "visa_backend"):
            if getattr(self, name) is not None and not isinstance(getattr(self, name), str):
                raise ConfigurationError(f"{name} must be a string or null")
        if not self.sample_id.strip() or not self.output_directory.strip():
            raise ConfigurationError("sample_id and output_directory are required")
        if self.mode not in {"FVMI_CURRENT", "NATIVE_RESISTANCE"}:
            raise ConfigurationError("Unknown measurement mode")
        if self.setup_policy not in {"verified_fixture", "operator_low_voltage"}:
            raise ConfigurationError("Unknown setup_policy")
        if self.transport not in {"simulation", "visa"}:
            raise ConfigurationError("Only simulation and VISA USB-GPIB are supported")
        if self.simulation != (self.transport == "simulation"):
            raise ConfigurationError("simulation must agree with transport")
        if self.protocol not in {"constant", "list", "staircase", "fixed_time"}:
            raise ConfigurationError("Unknown protocol")
        if self.stop_policy != "immediate_off":
            raise ConfigurationError("Only immediate_off is implemented")
        numeric_names = (
            "dwell_s",
            "min_dwell_s",
            "exclude_initial_s",
            "summary_window_s",
            "sample_interval_s",
            "range_settle_s",
            "max_total_duration_s",
            "nplc",
            "line_frequency_hz",
            "current_range_A",
            "current_trip_A",
            "power_limit_W",
            "current_floor_A",
            "background_A",
            "background_uncertainty_A",
            "background_sigma_multiplier",
            "source_range_V",
            "voltage_ceiling_V",
            "sample_limit_V",
            "fixture_limit_V",
            "cable_limit_V",
            "temperature_C",
            "relative_humidity_percent",
            "thickness_m",
            "area_m2",
            "series_resistance_ohm",
            "burden_estimate_V",
            "drift_fraction",
            "noise_fraction",
            "absolute_drift_A_per_s",
            "absolute_noise_A",
            "simulation_resistance_ohm",
        )
        for name in numeric_names:
            value = getattr(self, name)
            if value is None:
                if name in {
                    "current_trip_A",
                    "power_limit_W",
                    "background_A",
                    "sample_limit_V",
                    "fixture_limit_V",
                    "cable_limit_V",
                    "temperature_C",
                    "relative_humidity_percent",
                    "thickness_m",
                    "area_m2",
                    "series_resistance_ohm",
                    "burden_estimate_V",
                }:
                    continue
                raise ConfigurationError(f"{name} is required")
            if type(value) not in {int, float} or not math.isfinite(value):
                raise ConfigurationError(f"{name} must be finite numeric SI units")
        for name in (
            "dwell_s",
            "summary_window_s",
            "sample_interval_s",
            "max_total_duration_s",
            "current_range_A",
            "voltage_ceiling_V",
            "line_frequency_hz",
            "background_sigma_multiplier",
            "simulation_resistance_ohm",
        ):
            if getattr(self, name) <= 0:
                raise ConfigurationError(f"{name} must be positive")
        for name in (
            "min_dwell_s",
            "exclude_initial_s",
            "range_settle_s",
            "current_floor_A",
            "background_uncertainty_A",
            "drift_fraction",
            "noise_fraction",
            "absolute_drift_A_per_s",
            "absolute_noise_A",
        ):
            if getattr(self, name) < 0:
                raise ConfigurationError(f"{name} must be nonnegative")
        for name in (
            "current_trip_A",
            "power_limit_W",
            "sample_limit_V",
            "fixture_limit_V",
            "cable_limit_V",
            "thickness_m",
            "area_m2",
        ):
            if getattr(self, name) is not None and getattr(self, name) <= 0:
                raise ConfigurationError(f"{name} must be positive")
        if self.series_resistance_ohm is not None and self.series_resistance_ohm < 0:
            raise ConfigurationError("series_resistance_ohm cannot be negative")
        if self.source_range_V not in (100, 1000) or not 0.01 <= self.nplc <= 10:
            raise ConfigurationError("source range must be 100/1000 V; NPLC must be 0.01..10")
        if self.setup_policy == "operator_low_voltage":
            if self.source_range_V != 100:
                raise ConfigurationError(
                    "Operator low-voltage mode requires the 100 V source range"
                )
            if self.voltage_ceiling_V > 10:
                raise ConfigurationError("Operator low-voltage mode has an absolute 10 V ceiling")
        if self.line_frequency_hz not in (50, 60):
            raise ConfigurationError("line_frequency_hz must be explicitly 50 or 60 Hz")
        if self.current_range_A > 0.02:
            raise ConfigurationError("current_range_A exceeds 20 mA")
        if self.min_dwell_s > self.dwell_s or self.exclude_initial_s > self.dwell_s:
            raise ConfigurationError("Dwell cannot be shorter than minimum/excluded interval")
        if self.summary_window_s > self.dwell_s:
            raise ConfigurationError("summary_window_s cannot exceed dwell_s")
        if (
            self.relative_humidity_percent is not None
            and not 0 <= self.relative_humidity_percent <= 100
        ):
            raise ConfigurationError("Relative humidity must be in 0..100 percent")
        if bool(self.thickness_m is None) != bool(self.area_m2 is None):
            raise ConfigurationError("Provide both area_m2 and thickness_m, or neither")
        if self.background_A is not None and not (
            self.background_approved and self.background_reference
        ):
            raise ConfigurationError("Background correction needs approved matching reference")
        if self.background_uncertainty_A > 0 and not (
            self.background_approved and self.background_reference
        ):
            raise ConfigurationError("Background uncertainty needs an approved matching reference")
        if self.series_correction_verified and (
            self.series_resistance_ohm is None or self.burden_estimate_V is None
        ):
            raise ConfigurationError("Series correction requires verified resistance and burden")
        if not 1 <= len(self.voltages) <= 100000:
            raise ConfigurationError("Provide 1..100000 voltages")
        if self.protocol == "constant" and len(self.voltages) != 1:
            raise ConfigurationError("constant protocol requires exactly one voltage")
        for value in self.voltages:
            if type(value) not in {int, float} or not math.isfinite(value):
                raise ConfigurationError("Voltages must be finite numbers")
            if value < 0 and not self.bipolar_authorized:
                raise ConfigurationError("Negative voltage requires bipolar authorization")
            if max(abs(value), abs(self.quantize_voltage(value))) > min(
                self.effective_ceiling, self.source_range_V
            ):
                raise ConfigurationError(
                    "Requested/quantized voltage exceeds approved ceiling/range"
                )
        if self.dwell_s * len(self.voltages) * self.cycles > self.max_total_duration_s:
            raise ConfigurationError("Plan exceeds maximum total duration")
        if for_arm:
            if self.current_trip_A is None:
                raise ConfigurationError("Explicit software current trip is required to ARM")
            if not self.residual_warning_ack:
                raise ConfigurationError("Residual-charge warning acknowledgment is required")
            if not self.simulation:
                if self.resistive_limit_enabled is None:
                    raise ConfigurationError("Real ARM requires an explicit resistive-limit policy")
                if not self.resource or not self.resource.upper().startswith("GPIB"):
                    raise ConfigurationError("A selected VISA GPIB resource is required")
                if self.setup_policy == "operator_low_voltage":
                    if not self.operator_setup_acknowledged:
                        raise ConfigurationError("Operator setup acknowledgment is required to ARM")
                else:
                    if any(
                        v is None
                        for v in (self.sample_limit_V, self.fixture_limit_V, self.cable_limit_V)
                    ):
                        raise ConfigurationError("All physical voltage ratings are required")
                    if not self.rating_approval.strip():
                        raise ConfigurationError("Experiment/rating approval record is required")
                    required = ("installation_confirmed", "lid_open_zero", "lid_closed_one")
                    if any(self.commissioning.get(k) is not True for k in required):
                        raise ConfigurationError(
                            "Installed interlock and OFF-state 0/1 transition "
                            "commissioning required"
                        )
                    if self.commissioning.get("hardware_protection_reviewed") is not True:
                        raise ConfigurationError(
                            "Independent hardware protection review is required"
                        )
                    for name in ("fixture_id", "approved_by"):
                        value = self.commissioning.get(name)
                        if not isinstance(value, str) or not value.strip():
                            raise ConfigurationError(
                                "Commissioning fixture identity and approver required"
                            )
                if self.mode == "NATIVE_RESISTANCE":
                    raise ConfigurationError(
                        "Real native resistance disabled: measured-current trip unverified"
                    )
