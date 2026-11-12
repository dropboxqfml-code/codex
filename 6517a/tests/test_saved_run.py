"""Saved results are analysed offline without changing measurement files or permissions."""

import csv
import json
import math

import pytest

from keithley6517a.analysis.saved_run import (
    export_selection,
    load_saved_run,
    select_rows,
    summarize_rows,
)
from keithley6517a.storage.run_writer import ANALYSIS_HEADER

FIELDS = [
    "elapsed_s",
    "current_raw_A",
    "current_inferred_A",
    "voltage_programmed_readback_V",
    "native_r_ohm",
    "resistance_apparent_ohm",
    "valid_for_summary",
    "quality_flags",
    "phase",
    "status_code",
    "raw_response",
]


def saved_csv(directory, rows):
    source = directory / "readings.csv"
    with source.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            row = dict(row)
            if isinstance(row.get("quality_flags"), list):
                row["quality_flags"] = json.dumps(row["quality_flags"])
            writer.writerow(row)
    return source


def point(elapsed, **changes):
    row = dict(
        elapsed_s=elapsed,
        current_raw_A=1e-9,
        voltage_programmed_readback_V=1,
        resistance_apparent_ohm=1e9,
        valid_for_summary=False,
        quality_flags=["OUTSIDE_SUMMARY_WINDOW", "SERIES_DROP_UNVERIFIED"],
        phase="ACQUIRING",
        status_code="N",
    )
    row.update(changes)
    return row


def test_load_folder_and_bom_csv_preserve_source_order_and_optional_metadata(tmp_path):
    source = saved_csv(tmp_path, [point(3), point(1), point(2)])
    status = {"status": "aborted", "reason": "user STOP", "final_output_state": "OFF"}
    metadata = {"simulation": True, "comment": "saved text is data, never a command"}
    (tmp_path / "run_status.json").write_text(json.dumps(status))
    (tmp_path / "metadata.json").write_text(json.dumps(metadata))
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    saved = load_saved_run(tmp_path)
    assert saved.source_path == source.resolve() and saved.directory == tmp_path.resolve()
    assert [row["elapsed_s"] for row in saved.rows] == [3, 1, 2]
    assert saved.start_s == 1 and saved.end_s == 3
    assert saved.status == status and saved.metadata == metadata
    assert all(row["valid_for_summary"] is False for row in saved.rows)
    assert saved.rows[0]["quality_flags"] == [
        "OUTSIDE_SUMMARY_WINDOW",
        "SERIES_DROP_UNVERIFIED",
    ]
    assert load_saved_run(source).rows == saved.rows
    assert before == {path.name: path.read_bytes() for path in tmp_path.iterdir()}


def test_selection_is_inclusive_and_retains_original_order(tmp_path):
    source = saved_csv(tmp_path, [point(2), point(3), point(0), point(1), point(2.0001)])
    saved = load_saved_run(source)
    assert [row["elapsed_s"] for row in select_rows(saved, 1, 2)] == [2, 1]
    assert [row["elapsed_s"] for row in select_rows(saved, 1, 1)] == [1]
    assert select_rows(saved, 10, 11) == []
    assert saved.status == saved.metadata == {}


@pytest.mark.parametrize("bounds", [(2, 1), (float("nan"), 1), (0, float("inf")), (True, 2)])
def test_bad_time_ranges_are_rejected_before_export(tmp_path, bounds):
    saved = load_saved_run(saved_csv(tmp_path, [point(1)]))
    with pytest.raises(ValueError):
        select_rows(saved, *bounds)
    with pytest.raises(ValueError):
        export_selection(saved, tmp_path / "selection.txt", *bounds)
    assert not (tmp_path / "selection.txt").exists()


def test_custom_statistics_include_summary_exclusions_but_not_errors_or_trips():
    rows = [
        point(0, current_raw_A=1, native_r_ohm=0, resistance_apparent_ohm=999),
        point(1, current_raw_A=3, resistance_apparent_ohm=20, quality_flags=["SETTLING_EXCLUDED"]),
        point(2, current_raw_A=100, phase="ERROR"),
        point(3, current_raw_A=1000, quality_flags=["SOFTWARE_CURRENT_TRIP"]),
        point(4, current_raw_A=10000, status_code="O"),
        point(5, current_raw_A=100000, quality_flags=["UNKNOWN_FUTURE_FLAG"]),
    ]
    result = summarize_rows(rows)
    assert result["row_count"] == 6 and result["invalid_count"] == 4
    assert result["current_count"] == result["resistance_count"] == 2
    assert result["current_mean_A"] == 2
    assert result["current_std_A"] == pytest.approx(math.sqrt(2))
    assert result["resistance_mean_ohm"] == 10
    assert result["resistance_std_ohm"] == pytest.approx(math.sqrt(200))


def test_missing_raw_current_is_not_replaced_by_inferred_current():
    result = summarize_rows(
        [
            point(
                1,
                current_raw_A=None,
                current_inferred_A=1e-9,
                native_r_ohm=-1e9,
                quality_flags=["INFERRED_CURRENT_NOT_MEASURED"],
            ),
            point(2, current_raw_A=-0.0, resistance_apparent_ohm=None),
        ]
    )
    assert result["current_count"] == 1 and result["current_mean_A"] == 0
    assert result["resistance_count"] == 1 and result["resistance_mean_ohm"] == -1e9
    assert result["current_std_A"] is result["resistance_std_ohm"] is None
    empty = summarize_rows([])
    assert empty["row_count"] == empty["invalid_count"] == 0
    assert empty["current_mean_A"] is empty["resistance_mean_ohm"] is None


def test_empty_readings_have_no_invented_time_bounds(tmp_path):
    saved = load_saved_run(saved_csv(tmp_path, []))
    assert saved.start_s is saved.end_s is None
    assert saved.rows == []


def test_finite_extreme_values_do_not_return_an_infinite_statistic():
    result = summarize_rows([point(0, current_raw_A=1.7e308), point(1, current_raw_A=-1.7e308)])
    assert result["current_count"] == 2 and result["current_mean_A"] == 0
    assert result["current_std_A"] is None


@pytest.mark.parametrize("value", ["not-a-number", "nan", "Infinity"])
def test_bad_numeric_data_has_field_and_record_number(tmp_path, value):
    source = saved_csv(tmp_path, [point(1), point(2, current_raw_A=value)])
    with pytest.raises(ValueError, match="CSV 3.*current_raw_A"):
        load_saved_run(source)


@pytest.mark.parametrize("flags", ["not JSON", '{"unsafe":true}', "[1]"])
def test_quality_flags_must_be_a_string_list(tmp_path, flags):
    source = saved_csv(tmp_path, [point(1, quality_flags=flags)])
    with pytest.raises(ValueError, match="quality_flags"):
        load_saved_run(source)


@pytest.mark.parametrize(
    "contents",
    [
        "time,current\n1,1e-9\n",
        "elapsed_s,current_raw_A,current_raw_A,voltage_programmed_readback_V,native_r_ohm\n",
        "elapsed_s,current_raw_A,voltage_programmed_readback_V,native_r_ohm\n1,1e-9\n",
        "elapsed_s,current_raw_A,voltage_programmed_readback_V,native_r_ohm\n1,1e-9,1,1e9,extra\n",
    ],
)
def test_malformed_schema_or_row_width_is_not_silently_repaired(tmp_path, contents):
    source = tmp_path / "readings.csv"
    source.write_text(contents)
    with pytest.raises(ValueError):
        load_saved_run(source)


@pytest.mark.parametrize("contents", ["[]", "{broken", '{"value":NaN}'])
def test_malformed_sidecar_is_reported_without_modifying_data(tmp_path, contents):
    source = saved_csv(tmp_path, [point(1)])
    metadata = tmp_path / "metadata.json"
    metadata.write_text(contents)
    before = source.read_bytes()
    with pytest.raises(ValueError):
        load_saved_run(source)
    assert source.read_bytes() == before and metadata.read_text() == contents


def test_selection_export_keeps_flagged_rows_and_exact_four_column_format(tmp_path):
    source = saved_csv(
        tmp_path,
        [
            point(0),
            point(1, current_raw_A=-1e-9, resistance_apparent_ohm=-1e9),
            point(2, current_raw_A=None, current_inferred_A=1e-9, native_r_ohm=0),
            point(3, current_raw_A=None, resistance_apparent_ohm=None, phase="ERROR"),
        ],
    )
    saved = load_saved_run(source)
    before = source.read_bytes()
    destination = tmp_path / "selection.txt"
    result = export_selection(saved, destination, 1, 3)
    assert result == {"analysis_file": str(destination), "rows": 3}
    assert destination.read_text() == (
        ANALYSIS_HEADER
        + "1.0\t-1000000000.0\t1.0\t-1e-09\n"
        + "2.0\t0.0\t1.0\tnan\n"
        + "3.0\tnan\t1.0\tnan\n"
    )
    assert source.read_bytes() == before


def test_selection_export_never_replaces_source_or_existing_output(tmp_path):
    source = saved_csv(tmp_path, [point(1)])
    saved = load_saved_run(source)
    with pytest.raises(ValueError, match="readings.csv"):
        export_selection(saved, source, 0, 2)
    target = tmp_path / "selection.txt"
    target.write_text("existing analysis")
    with pytest.raises(FileExistsError):
        export_selection(saved, target, 0, 2)
    assert target.read_text() == "existing analysis"


def test_failed_selection_export_removes_only_its_new_file(tmp_path, monkeypatch):
    from keithley6517a.analysis import saved_run as module

    source = saved_csv(tmp_path, [point(1), point(2)])
    saved = load_saved_run(source)
    original = source.read_bytes()
    real_line = module.analysis_line

    def fail_second(row):
        if row["elapsed_s"] == 2:
            raise OSError("disk full")
        return real_line(row)

    monkeypatch.setattr(module, "analysis_line", fail_second)
    with pytest.raises(OSError, match="disk full"):
        export_selection(saved, tmp_path / "selection.txt", 0, 2)
    assert not (tmp_path / "selection.txt").exists()
    assert source.read_bytes() == original
