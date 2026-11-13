"""Stored resistivity remains optional and selected TXT keeps the source run's schema."""

import csv
import json
import math

import pytest

from keithley6517a.analysis.saved_run import (
    SavedRun,
    export_selection,
    load_saved_run,
    select_rows,
    summarize_rows,
)
from keithley6517a.storage.run_writer import ANALYSIS_HEADER, ANALYSIS_RESISTIVITY_HEADER

FIELDS = [
    "elapsed_s",
    "current_raw_A",
    "voltage_programmed_readback_V",
    "native_r_ohm",
    "resistance_apparent_ohm",
    "resistivity_ohm_m",
    "valid_for_summary",
    "quality_flags",
    "phase",
    "status_code",
]
GEOMETRY = {
    "dimensions_mm": {"L": 20, "W": 10, "D": 2},
    "current_path_axis": "D",
    "area_m2": 2e-4,
    "current_path_length_m": 2e-3,
    "complete": True,
}
SETTINGS = {
    "sample_length_mm": 20,
    "sample_width_mm": 10,
    "sample_depth_mm": 2,
    "current_path_axis": "D",
}


def point(elapsed, **changes):
    row = dict(
        elapsed_s=elapsed,
        current_raw_A=1e-9,
        voltage_programmed_readback_V=1,
        resistance_apparent_ohm=1e9,
        resistivity_ohm_m=None,
        valid_for_summary=False,
        quality_flags=["OUTSIDE_SUMMARY_WINDOW", "SIMULATED"],
        phase="ACQUIRING",
        status_code="N",
    )
    row.update(changes)
    return row


def saved_csv(directory, rows, *, rho_column=True, metadata=None, settings=None, wrapped=True):
    source = directory / "readings.csv"
    fields = FIELDS if rho_column else [name for name in FIELDS if name != "resistivity_ohm_m"]
    with source.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            data = {name: row.get(name) for name in fields}
            data["quality_flags"] = json.dumps(data["quality_flags"])
            writer.writerow(data)
    if metadata is not None:
        (directory / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    if settings is not None:
        snapshot = {"schema_version": 1, "settings": settings} if wrapped else settings
        (directory / "config.json").write_text(json.dumps(snapshot), encoding="utf-8")
    return source


def test_optional_rho_is_loaded_as_number_or_none_including_legacy_csv(tmp_path):
    source = saved_csv(tmp_path, [point(0, resistivity_ohm_m=-2.5), point(1)])
    saved = load_saved_run(source)
    assert saved.rows[0]["resistivity_ohm_m"] == -2.5
    assert isinstance(saved.rows[0]["resistivity_ohm_m"], float)
    assert saved.rows[1]["resistivity_ohm_m"] is None
    source = saved_csv(tmp_path, [point(0)], rho_column=False)
    legacy = load_saved_run(source)
    assert legacy.rows[0]["resistivity_ohm_m"] is None
    assert not legacy.include_resistivity


@pytest.mark.parametrize("token", ["nan", "Infinity", "-inf", "not-a-number"])
def test_rho_must_be_finite_and_errors_identify_field_and_csv_record(tmp_path, token):
    source = saved_csv(tmp_path, [point(0), point(1, resistivity_ohm_m=token)])
    before = source.read_bytes()
    with pytest.raises(ValueError, match="CSV 3.*resistivity_ohm_m"):
        load_saved_run(source)
    assert source.read_bytes() == before


def test_resistivity_statistics_use_inclusive_interval_and_sample_standard_deviation(tmp_path):
    source = saved_csv(
        tmp_path,
        [
            point(3, resistivity_ohm_m=900),
            point(2, resistivity_ohm_m=4),
            point(0, resistivity_ohm_m=-2),
            point(1, resistivity_ohm_m=0),
            point(1.5),
        ],
    )
    selected = select_rows(load_saved_run(source), 0, 2)
    result = summarize_rows(selected)
    assert [row["elapsed_s"] for row in selected] == [2, 0, 1, 1.5]
    assert result["row_count"] == 4 and result["invalid_count"] == 0
    assert result["resistivity_count"] == 3
    assert result["resistivity_mean_ohm_m"] == pytest.approx(2 / 3)
    assert result["resistivity_std_ohm_m"] == pytest.approx(math.sqrt(28 / 3))


def test_rho_statistics_share_error_policy_but_keep_user_selected_summary_exclusions():
    rows = [
        point(0, resistivity_ohm_m=2),
        point(1, resistivity_ohm_m=4, quality_flags=["SETTLING_EXCLUDED"]),
        point(2, resistivity_ohm_m=100, phase="ERROR"),
        point(3, resistivity_ohm_m=1000, quality_flags=["SOFTWARE_CURRENT_TRIP"]),
        point(4, resistivity_ohm_m=10000, status_code="O"),
        point(5, resistivity_ohm_m=100000, quality_flags=["UNKNOWN_FUTURE_FLAG"]),
    ]
    result = summarize_rows(rows)
    assert result["invalid_count"] == 4
    assert result["current_count"] == result["resistance_count"] == result["resistivity_count"] == 2
    assert result["resistivity_mean_ohm_m"] == 3
    assert result["resistivity_std_ohm_m"] == pytest.approx(math.sqrt(2))


def test_no_stored_rho_is_invented_from_resistance_and_single_value_has_no_deviation():
    missing = summarize_rows([point(0), point(1, resistance_apparent_ohm=2e9)])
    assert missing["resistance_count"] == 2 and missing["resistivity_count"] == 0
    assert missing["resistivity_mean_ohm_m"] is missing["resistivity_std_ohm_m"] is None
    single = summarize_rows([point(0, resistivity_ohm_m=-0.0), point(1)])
    assert single["resistivity_count"] == 1 and single["resistivity_mean_ohm_m"] == 0
    assert single["resistivity_std_ohm_m"] is None
    empty = summarize_rows([])
    assert empty["resistivity_count"] == 0
    assert empty["resistivity_mean_ohm_m"] is empty["resistivity_std_ohm_m"] is None


def test_selection_of_missing_rho_keeps_whole_run_five_column_schema_and_error_rows(tmp_path):
    source = saved_csv(
        tmp_path,
        [
            point(0, resistivity_ohm_m=8),
            point(1),
            point(2, current_raw_A=None, resistance_apparent_ohm=None, phase="ERROR"),
        ],
    )
    saved = load_saved_run(source)
    assert saved.include_resistivity
    assert all(row["resistivity_ohm_m"] is None for row in select_rows(saved, 1, 2))
    before = source.read_bytes()
    output = tmp_path / "selection.txt"
    export_selection(saved, output, 1, 2)
    assert output.read_text() == (
        ANALYSIS_RESISTIVITY_HEADER
        + "1.0\t1000000000.0\tnan\t1.0\t1e-09\n"
        + "2.0\tnan\tnan\t1.0\tnan\n"
    )
    assert source.read_bytes() == before


@pytest.mark.parametrize(
    "metadata",
    [
        {"analysis_text": {"include_resistivity": True}},
        {"sample_geometry": GEOMETRY},
    ],
)
def test_zero_voltage_or_legacy_missing_rho_still_has_five_columns_with_recorded_geometry(
    tmp_path, metadata
):
    source = saved_csv(
        tmp_path,
        [point(0, voltage_programmed_readback_V=0, resistance_apparent_ohm=None)],
        rho_column=False,
        metadata=metadata,
    )
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    saved = load_saved_run(source)
    assert saved.include_resistivity
    output = tmp_path / "selection.txt"
    export_selection(saved, output, 0, 0)
    assert output.read_text() == ANALYSIS_RESISTIVITY_HEADER + "0.0\tnan\tnan\t0.0\t1e-09\n"
    assert all((tmp_path / name).read_bytes() == content for name, content in before.items())


@pytest.mark.parametrize("wrapped", [True, False])
def test_config_snapshot_geometry_is_read_only_and_preserves_legacy_five_column_schema(
    tmp_path, wrapped
):
    source = saved_csv(tmp_path, [point(0)], settings=SETTINGS, wrapped=wrapped)
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    saved = load_saved_run(source)
    assert saved.settings == SETTINGS and saved.include_resistivity
    output = tmp_path / "selection.txt"
    export_selection(saved, output, 0, 0)
    assert output.read_text().startswith(ANALYSIS_RESISTIVITY_HEADER)
    assert all((tmp_path / name).read_bytes() == content for name, content in before.items())


@pytest.mark.parametrize(
    "settings",
    [
        {"sample_id": "test specimen"},
        {"sample_length_mm": 20, "sample_width_mm": 10},
        {"sample_length_mm": 20, "sample_width_mm": 10, "sample_depth_mm": 2},
    ],
)
def test_sample_id_or_incomplete_geometry_leaves_exact_four_column_text(tmp_path, settings):
    source = saved_csv(tmp_path, [point(0)], settings=settings)
    saved = load_saved_run(source)
    assert not saved.include_resistivity
    output = tmp_path / "selection.txt"
    export_selection(saved, output, 0, 0)
    assert output.read_text() == ANALYSIS_HEADER + "0.0\t1000000000.0\t1.0\t1e-09\n"


def test_new_explicit_schema_overrides_geometry_only_while_stored_rho_retains_five_columns(
    tmp_path,
):
    metadata = {
        "analysis_text": {"include_resistivity": False},
        "sample_geometry": GEOMETRY,
    }
    source = saved_csv(tmp_path, [point(0)], metadata=metadata)
    assert not load_saved_run(source).include_resistivity
    source = saved_csv(tmp_path, [point(0, resistivity_ohm_m=0)], metadata=metadata)
    assert load_saved_run(source).include_resistivity


def test_saved_run_optional_settings_keep_direct_constructor_compatible(tmp_path):
    saved = SavedRun(tmp_path / "readings.csv", tmp_path, [point(0)], {}, {})
    assert saved.settings == {} and not saved.include_resistivity


def test_invalid_config_settings_are_reported_without_modifying_source(tmp_path):
    source = saved_csv(tmp_path, [point(0)])
    config = tmp_path / "config.json"
    config.write_text('{"settings": []}', encoding="utf-8")
    before = source.read_bytes()
    with pytest.raises(ValueError, match="config.json.*settings"):
        load_saved_run(source)
    assert source.read_bytes() == before and config.read_text() == '{"settings": []}'
