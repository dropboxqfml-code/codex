"""Rectangular millimetre dimensions use an explicit current direction for volume rho."""

import json
from dataclasses import replace

import pytest

from keithley6517a.config import ConfigurationError, RunConfig
from keithley6517a.measurement.analysis import analyze_reading


def geometry(**updates):
    values = dict(
        sample_length_mm=20,
        sample_width_mm=10,
        sample_depth_mm=2,
        current_path_axis="D",
    )
    values.update(updates)
    return replace(RunConfig(), **values)


@pytest.mark.parametrize(
    ("axis", "area", "length", "rho"),
    [
        ("L", 20e-6, 20e-3, 1e6),
        ("W", 40e-6, 10e-3, 4e6),
        ("D", 200e-6, 2e-3, 1e8),
    ],
)
def test_all_current_axes_use_transverse_area_and_mm_to_si(axis, area, length, rho):
    config = geometry(current_path_axis=axis)
    assert config.effective_geometry_m == pytest.approx((area, length))
    result = analyze_reading(config, 1e-9, voltage_V=1)
    assert result["resistance_apparent_ohm"] == pytest.approx(1e9)
    assert result["resistivity_ohm_m"] == pytest.approx(rho)
    # SI calculation does not overwrite independent legacy input or the saved mm dimensions.
    assert config.area_m2 is None and config.thickness_m is None
    assert config.sample_length_mm == 20 and config.sample_width_mm == 10


@pytest.mark.parametrize(
    "updates",
    [
        {"current_path_axis": None},
        {"sample_length_mm": None},
        {"sample_width_mm": None},
        {"sample_depth_mm": None},
        {"sample_length_mm": None, "sample_width_mm": None, "sample_depth_mm": None},
    ],
)
def test_incomplete_dimensions_remain_metadata_without_inventing_resistivity(updates):
    config = geometry(**updates)
    assert config.effective_geometry_m == (None, None)
    result = analyze_reading(config, 1e-9, voltage_V=1)
    assert result["resistance_apparent_ohm"] == pytest.approx(1e9)
    assert result["resistivity_ohm_m"] is None
    assert RunConfig.from_dict(json.loads(json.dumps(config.to_dict()))) == config


def test_old_geometry_is_preserved_but_never_used_for_partial_new_dimensions():
    legacy = replace(RunConfig(), area_m2=1e-4, thickness_m=1e-3)
    assert legacy.effective_geometry_m == (1e-4, 1e-3)
    assert analyze_reading(legacy, 1e-9, voltage_V=1)["resistivity_ohm_m"] == pytest.approx(1e8)
    new = replace(
        legacy,
        sample_length_mm=20,
        sample_width_mm=10,
        sample_depth_mm=2,
        current_path_axis="L",
    )
    assert new.effective_geometry_m == pytest.approx((20e-6, 20e-3))
    assert new.area_m2 == legacy.area_m2 and new.thickness_m == legacy.thickness_m
    partial = replace(new, sample_width_mm=None)
    assert partial.effective_geometry_m == (None, None)
    assert analyze_reading(partial, 1e-9, voltage_V=1)["resistivity_ohm_m"] is None
    cleared = replace(
        new,
        sample_length_mm=None,
        sample_width_mm=None,
        sample_depth_mm=None,
        current_path_axis=None,
    )
    assert cleared == legacy and cleared.effective_geometry_m == legacy.effective_geometry_m


def test_dimensions_and_direction_survive_standalone_and_run_snapshot_json(tmp_path):
    config = geometry(sample_length_mm=12.5, sample_width_mm=2.25, sample_depth_mm=0.4)
    exported = config.to_dict()
    assert exported["sample_length_mm"] == 12.5 and exported["current_path_axis"] == "D"
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(exported), encoding="utf-8")
    assert RunConfig.load(path) == config
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "software": {"version": "geometry test", "commit": None},
                "settings": exported,
            }
        ),
        encoding="utf-8",
    )
    assert RunConfig.load(path) == config


def test_resistivity_uses_corrected_resistance_and_preserves_sign_and_native_basis():
    corrected = geometry(background_A=1e-9, background_approved=True, background_reference="test")
    result = analyze_reading(corrected, 2e-9, voltage_V=2)
    assert result["resistance_apparent_ohm"] == pytest.approx(1e9)
    assert result["resistance_corrected_ohm"] == pytest.approx(2e9)
    assert result["resistivity_ohm_m"] == pytest.approx(2e8)
    signed = analyze_reading(geometry(), -1e-9, voltage_V=1)
    assert signed["resistivity_ohm_m"] == pytest.approx(-1e8)
    native = analyze_reading(geometry(mode="NATIVE_RESISTANCE"), 3e9, voltage_V=1)
    assert native["resistivity_ohm_m"] == pytest.approx(3e8)
    assert native["current_raw_A"] is None


@pytest.mark.parametrize("options", [{"status": "O"}, {"current_limit": True}, {"voltage_V": 0}])
def test_invalid_or_zero_bias_readings_do_not_gain_a_resistivity(options):
    values = {"voltage_V": 1, **options}
    assert analyze_reading(geometry(), 1e-9, **values)["resistivity_ohm_m"] is None


@pytest.mark.parametrize("name", ["sample_length_mm", "sample_width_mm", "sample_depth_mm"])
@pytest.mark.parametrize("value", [0, -1])
def test_each_dimension_must_be_positive(name, value):
    with pytest.raises(ConfigurationError, match=name + " must be positive"):
        geometry(**{name: value})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "20", [20], 10**400])
def test_dimensions_are_finite_numeric_mm_not_booleans_or_strings(value):
    with pytest.raises(ConfigurationError, match="sample_length_mm must be finite numeric"):
        geometry(sample_length_mm=value)


@pytest.mark.parametrize("value", ["", "l", "Z", True, 1, ["D"]])
def test_current_direction_is_explicit_and_validated(value):
    with pytest.raises(ConfigurationError, match="current_path_axis"):
        geometry(current_path_axis=value)


@pytest.mark.parametrize(
    "dimensions",
    [
        (1e-200, 1e-200, 1e-200),
        (1e308, 1e308, 1e308),
        (5e-324, 1, 1),
        (1e308, 1, 1e-308),
        (1e-308, 1e154, 1e154),
    ],
)
def test_complete_geometry_rejects_unrepresentable_si_area_length_or_ratio(dimensions):
    length, width, depth = dimensions
    with pytest.raises(ConfigurationError, match="unrepresentable SI geometry"):
        geometry(
            sample_length_mm=length,
            sample_width_mm=width,
            sample_depth_mm=depth,
            current_path_axis="L",
        )


def test_resistivity_avoids_intermediate_overflow_and_classifies_unrepresentable_results():
    config = geometry(
        sample_length_mm=1e13,
        sample_width_mm=1e8,
        sample_depth_mm=1e8,
        current_path_axis="L",
        current_floor_A=1e-310,
    )
    row = analyze_reading(config, 1e-300, voltage_V=1)
    assert row["resistivity_ohm_m"] == pytest.approx(1e300)
    overflow = replace(config, sample_length_mm=0.01)
    assert analyze_reading(overflow, 1e-300, voltage_V=1)["resistivity_ohm_m"] is None
    underflow = replace(config, sample_width_mm=1e-142, sample_depth_mm=1e-142)
    assert analyze_reading(underflow, 1e30, voltage_V=1)["resistivity_ohm_m"] is None
