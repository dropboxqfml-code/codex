import json
from dataclasses import FrozenInstanceError, replace

import pytest

from keithley6517a.config import ConfigurationError, RunConfig
from keithley6517a.measurement.analysis import StabilityTracker, analyze_reading, summarize
from keithley6517a.measurement.protocols import linear_staircase, schedule


def cfg(**updates):
    return RunConfig.from_dict(dict(current_trip_A=1e-7, residual_warning_ack=True, **updates))


def test_defaults_are_simulation_zero_bias_and_do_not_arm():
    config = RunConfig()
    assert config.simulation and config.voltages == (0,)
    assert config.voltage_ceiling_V == 10
    with pytest.raises(ConfigurationError, match="trip"):
        config.validate()


def test_snapshot_is_deeply_immutable_and_json_roundtrip():
    source = {"commissioning": {"fixture_id": "fixture", "observations": [0, 1]}}
    config = RunConfig.from_dict(source)
    source["commissioning"]["observations"].append(2)
    assert config.commissioning["observations"] == (0, 1)
    with pytest.raises(FrozenInstanceError):
        config.mode = "NATIVE_RESISTANCE"
    with pytest.raises(TypeError):
        config.commissioning["fixture_id"] = "other"
    assert (
        RunConfig.from_dict(json.loads(json.dumps(config.to_dict()))).to_dict() == config.to_dict()
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("voltages", [float("nan")]),
        ("dwell_s", float("inf")),
        ("sample_interval_s", 0),
        ("dwell_s", -1),
        ("thickness_m", 0),
        ("area_m2", -1),
        ("sample_interval_s", True),
        ("cycles", 1.0),
        ("relative_humidity_percent", 101),
        ("current_range_A", 1),
        ("nplc", 11),
        ("simulation", "true"),
        ("line_frequency_hz", 0),
        ("voltage_ceiling_V", 0),
        ("mode", "6517B"),
    ],
)
def test_invalid_inputs(field, value):
    with pytest.raises(ConfigurationError):
        RunConfig.from_dict({field: value})


def test_unknown_fields_and_strict_json(tmp_path):
    with pytest.raises(ConfigurationError, match="Unknown"):
        RunConfig.from_dict({"pretend_compliance": 1})
    for text in (
        '{"dwell_s": NaN}',
        '{"dwell_s":1,"dwell_s":2}',
        '{"sample_metadata":{"x":Infinity}}',
    ):
        path = tmp_path / "bad.json"
        path.write_text(text)
        with pytest.raises(ConfigurationError):
            RunConfig.load(path)


def test_ceiling_quantization_and_positive_only():
    with pytest.raises(ConfigurationError):
        cfg(voltages=[-1])
    config = cfg(voltages=[1.002], sample_limit_V=2)
    assert config.quantize_voltage(1.002) == 1.0
    assert config.quantize_voltage(-1.003) == -1.005
    assert config.effective_ceiling == 2
    with pytest.raises(ConfigurationError, match="quantized"):
        cfg(voltages=[1.003], voltage_ceiling_V=1.003)
    with pytest.raises(ConfigurationError):
        cfg(voltages=[1001], source_range_V=1000, voltage_ceiling_V=2000)


def test_saved_run_snapshot_wrapper_loads_approved_settings(tmp_path):
    config = cfg(voltages=[1.005], sample_metadata={"operator": "operator1"})
    wrapper = dict(
        schema_version=1,
        software=dict(
            version="0.1.0", commit=None, source_sha256="a" * 64, working_tree_dirty=True
        ),
        settings=config.to_dict(),
    )
    path = tmp_path / "config.json"
    path.write_text(json.dumps(wrapper))
    assert RunConfig.load(path).to_dict() == config.to_dict()


@pytest.mark.parametrize(
    "changes",
    [
        {"unknown": True},
        {"schema_version": True},
        {"schema_version": 2},
        {"software": []},
        {"settings": []},
        {"software": {"unknown": True}},
        {"software": {"working_tree_dirty": 1}},
        {"settings": {"unknown": 1}},
        {"software": {"commit": 0}},
        {"software": {"version": float("nan")}},
    ],
)
def test_malformed_saved_run_wrapper_rejected(tmp_path, changes):
    wrapper = dict(schema_version=1, software={}, settings={})
    wrapper.update(changes)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(wrapper))
    with pytest.raises(ConfigurationError):
        RunConfig.load(path)


def test_incomplete_snapshot_wrapper_rejected(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"schema_version":1,"settings":{}}')
    with pytest.raises(ConfigurationError, match="exactly"):
        RunConfig.load(path)


def test_real_cable_absent_despite_query_one_never_approves():
    real = cfg(
        simulation=False,
        transport="visa",
        resource="GPIB0::27::INSTR",
        resistive_limit_enabled=False,
        sample_limit_V=10,
        fixture_limit_V=10,
        cable_limit_V=10,
        rating_approval="experiment-1",
        commissioning={"interlock_query": 1},
    )
    with pytest.raises(ConfigurationError, match="commissioning"):
        real.validate()
    commissioned = replace(
        real,
        commissioning=dict(
            installation_confirmed=True,
            hardware_protection_reviewed=True,
            lid_open_zero=True,
            lid_closed_one=True,
            fixture_id="F1",
            approved_by="operator",
        ),
    )
    commissioned.validate()
    with pytest.raises(ConfigurationError, match="native"):
        replace(commissioned, mode="NATIVE_RESISTANCE").validate()


def test_protocol_bounds_and_independent_autorange():
    assert linear_staircase(0, 0.3, 0.1) == (0, 0.1, 0.2, 0.3)
    assert linear_staircase(2, -2, -1) == (2, 1, 0, -1, -2)
    for values in ((0, 1, -0.1), (0, 1, 0.3), (0, 1, 0), (0, 1000000, 1)):
        with pytest.raises(ValueError):
            linear_staircase(*values)
    config = cfg(protocol="list", voltages=[0, 1, 2], current_autorange=False, cycles=2)
    assert len(schedule(config)) == 6
    assert config.current_autorange is False
    with pytest.raises(ConfigurationError, match="maximum total"):
        replace(config, max_total_duration_s=1)


@pytest.mark.parametrize(
    "value,voltage,expected,flag",
    [
        (1e-9, 1, 1e9, None),
        (-1e-9, 1, -1e9, None),
        (0, 1, None, "NOT_RESOLVED"),
        (1e-16, 1, None, "NOT_RESOLVED"),
        (1e-9, 0, None, "ZERO_VOLTAGE_UNDEFINED_R"),
    ],
)
def test_signed_resistance_and_floor(value, voltage, expected, flag):
    row = analyze_reading(cfg(), value, voltage_V=voltage)
    assert row["resistance_apparent_ohm"] == (
        pytest.approx(expected) if expected is not None else None
    )
    assert row["native_r_ohm"] is None and row["current_inferred_A"] is None
    if flag:
        assert flag in row["quality_flags"]


@pytest.mark.parametrize("status", list("ZOURL"))
def test_status_is_not_normal_current(status):
    row = analyze_reading(cfg(), 1e-9, voltage_V=1, status=status)
    assert not row["valid_for_summary"]
    assert row["resistance_apparent_ohm"] is None


def test_sentinel_source_limit_and_unverified_series():
    row = analyze_reading(cfg(), 9.9e37, voltage_V=1)
    assert row["current_raw_A"] is None
    assert not row["valid_for_summary"]
    limited = analyze_reading(cfg(), 1e-9, voltage_V=1, current_limit=True)
    assert limited["resistance_apparent_ohm"] is None
    row = analyze_reading(cfg(series_resistance_ohm=1e6), 1e-9, voltage_V=1)
    assert row["voltage_dut_estimated_V"] is None
    assert row["resistance_corrected_ohm"] == pytest.approx(1e9)
    assert "SERIES_DROP_UNVERIFIED" in row["quality_flags"]


def test_transient_resistance_is_retained_but_excluded_from_summary():
    row = analyze_reading(cfg(), 1e-9, voltage_V=1, flags=["OUTSIDE_SUMMARY_WINDOW"])
    assert row["resistance_apparent_ohm"] == pytest.approx(1e9)
    assert not row["valid_for_summary"]


def test_native_and_corrected_are_separate_observables():
    row = analyze_reading(cfg(mode="NATIVE_RESISTANCE"), 2e9, voltage_V=2)
    assert row["current_raw_A"] is None
    assert row["current_inferred_A"] == 1e-9 and row["native_r_ohm"] == 2e9
    assert row["resistance_apparent_ohm"] is None
    config = cfg(background_A=1e-9, background_approved=True, background_reference="blank-1")
    row = analyze_reading(config, 2e-9, voltage_V=2)
    assert row["resistance_apparent_ohm"] == pytest.approx(1e9)
    assert row["resistance_corrected_ohm"] == pytest.approx(2e9)
    row = analyze_reading(config, 1e-9, voltage_V=2)
    assert row["resistance_apparent_ohm"] == pytest.approx(2e9)
    assert row["resistance_corrected_ohm"] is None


def make_rows(config, currents):
    rows = []
    for index, current in enumerate(currents):
        rows.append(
            dict(
                analyze_reading(config, current, voltage_V=1),
                elapsed_s=index,
                time_since_voltage_command_s=index,
                voltage_programmed_readback_V=1,
                current_range_A=2e-9,
            )
        )
    return rows


def test_summary_uses_mean_current_and_excludes_invalid_without_deletion():
    config = cfg(dwell_s=3, summary_window_s=3, exclude_initial_s=0)
    rows = make_rows(config, [1e-9, 3e-9, 9.9e37])
    summary = summarize(config, rows)
    assert summary["N"] == 2
    assert summary["R_from_mean_current_ohm"] == pytest.approx(5e8)
    assert summary["mean_individual_resistance_ohm"] != summary["R_from_mean_current_ohm"]
    assert len(rows) == 3


def test_slow_read_completing_after_dwell_is_retained_but_not_averaged():
    config = cfg(dwell_s=3, summary_window_s=2)
    rows = make_rows(config, [1e-9, 1e-9, 1e-9, 1e-9])
    late = dict(
        analyze_reading(config, 9e-9, voltage_V=1, flags=["AFTER_DWELL"]),
        elapsed_s=3.2,
        time_since_voltage_command_s=3.2,
        voltage_programmed_readback_V=1,
        current_range_A=2e-9,
    )
    rows.append(late)
    assert late["current_raw_A"] == 9e-9
    assert late["resistance_apparent_ohm"] == pytest.approx(1 / 9e-9)
    assert not late["valid_for_summary"]
    summary = summarize(config, rows)
    assert summary["N"] == 3
    assert summary["current_mean_A"] == pytest.approx(1e-9)
    assert len(rows) == 5
    # The aggregation boundary also protects callers that omitted the AFTER_DWELL flag.
    late["valid_for_summary"] = True
    assert summarize(config, rows)["N"] == 3


def test_stability_and_resolution_remain_distinct_and_need_new_windows():
    config = cfg(dwell_s=10, summary_window_s=10, min_dwell_s=2)
    rows = make_rows(config, [0] * 6)
    tracker = StabilityTracker(config)
    assert tracker.evaluate(rows)["stability"] == "NOT_STABLE"
    assert tracker.evaluate(rows)["stability"] == "NOT_STABLE"
    extra = dict(rows[-1], elapsed_s=6, time_since_voltage_command_s=6)
    result = tracker.evaluate(rows + [extra])
    assert result["stability"] == "STABLE"
    assert result["resolution"] == "NOT_RESOLVED"
    rows[-1]["current_range_A"] = 2e-8
    assert summarize(config, rows)["stability"] == "NOT_STABLE"


def test_geometry_si_conversion():
    row = analyze_reading(cfg(area_m2=1e-4, thickness_m=1e-3), 1e-9, voltage_V=1)
    assert row["resistivity_ohm_m"] == pytest.approx(1e8)
