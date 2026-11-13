"""Offline resistivity review uses recorded values and preserves saved source files."""

import csv
import json
import statistics

import pytest

from keithley6517a.storage.run_writer import ANALYSIS_HEADER, ANALYSIS_RESISTIVITY_HEADER
from keithley6517a.ui.result_dialog import SavedResultDialog


def _saved_csv(tmp_path, *, stored_resistivity=True, settings=None, rows=None):
    if rows is None:
        rows = [
            dict(
                elapsed_s=0,
                current_raw_A=1e-9,
                resistance_apparent_ohm=1e9,
                voltage_programmed_readback_V=1,
                resistivity_ohm_m=10,
            ),
            dict(
                elapsed_s=1,
                current_raw_A=2e-9,
                resistance_apparent_ohm=2e9,
                voltage_programmed_readback_V=4,
                resistivity_ohm_m=20,
            ),
            dict(
                elapsed_s=2,
                native_r_ohm=0,
                resistance_apparent_ohm=9e9,
                voltage_programmed_readback_V=0,
            ),
            dict(
                elapsed_s=3,
                current_raw_A=-1e-9,
                resistance_apparent_ohm=-1e9,
                voltage_programmed_readback_V=1,
                resistivity_ohm_m=40,
            ),
        ]
    fields = [
        "elapsed_s",
        "current_raw_A",
        "resistance_apparent_ohm",
        "native_r_ohm",
        "voltage_programmed_readback_V",
        "quality_flags",
        "phase",
        "status_code",
    ]
    if stored_resistivity:
        fields.append("resistivity_ohm_m")
    path = tmp_path / "readings.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        for values in rows:
            row = {key: value for key, value in values.items() if key in fields}
            row.update(quality_flags="[]", phase="ACQUIRING", status_code="N")
            writer.writerow(row)
    (tmp_path / "metadata.json").write_text('{"simulation":true}', encoding="utf-8")
    if settings is not None:
        (tmp_path / "config.json").write_text(json.dumps({"settings": settings}), encoding="utf-8")
    return path


def _dialog(qtbot, path):
    widget = SavedResultDialog(path)
    qtbot.addWidget(widget)
    return widget


def _curve(widget, name):
    x, y = widget.curves[name].getOriginalDataset()
    return ([] if x is None else list(x), [] if y is None else list(y))


def test_resistivity_is_third_statistic_and_graph_with_recorded_values(qtbot, tmp_path):
    widget = _dialog(qtbot, _saved_csv(tmp_path))
    assert widget.statistics_table.rowCount() == 3
    assert [widget.statistics_table.item(row, 0).text() for row in range(3)] == [
        "전류",
        "저항",
        "비저항",
    ]
    assert widget.graph_tabs.count() == 3
    assert [widget.graph_tabs.tabText(index) for index in range(3)] == [
        "전류 I(t)",
        "저항 R(t)",
        "비저항 ρ(t)",
    ]
    assert widget.statistics["resistivity_count"] == 3
    assert widget.statistics["resistivity_mean_ohm_m"] == pytest.approx(70 / 3)
    assert widget.statistics["resistivity_std_ohm_m"] == pytest.approx(
        statistics.stdev([10, 20, 40])
    )
    assert widget.statistics_table.item(2, 1).text() == "23.3333 Ω·m"
    assert widget.statistics_table.item(2, 2).text() == "15.2753 Ω·m"
    assert widget.statistics_table.item(2, 3).text() == "3"
    assert _curve(widget, "resistivity") == ([0, 1, 3], [10, 20, 40])
    assert widget.plots["resistivity"].getPlotItem().getAxis("left").labelText == "ρ (Ω·m)"


def test_selection_uses_recorded_rho_and_exports_five_columns_without_changes(qtbot, tmp_path):
    path = _saved_csv(tmp_path)
    before = {source.name: source.read_bytes() for source in tmp_path.iterdir()}
    widget = _dialog(qtbot, path)
    widget.start_time.setValue(1)
    widget.end_time.setValue(2)
    assert widget.apply_range()
    assert widget.statistics["resistivity_count"] == 1
    assert widget.statistics["resistivity_mean_ohm_m"] == 20
    assert widget.statistics["resistivity_std_ohm_m"] is None
    assert widget.statistics_table.item(2, 2).text() == "—"
    assert _curve(widget, "resistivity") == ([1], [20])
    destination = tmp_path / "selection.txt"
    assert widget.export_to(destination)["rows"] == 2
    assert destination.read_text() == (
        ANALYSIS_RESISTIVITY_HEADER
        + "1.0\t2000000000.0\t20.0\t4.0\t2e-09\n"
        + "2.0\t0.0\tnan\t0.0\tnan\n"
    )
    assert "5열" in widget.status_label.text()
    assert before == {name: (tmp_path / name).read_bytes() for name in before}
    original_export = destination.read_bytes()
    assert widget.export_to(destination) is None
    assert destination.read_bytes() == original_export
    assert "다른 이름" in widget.status_label.text()


def test_old_csv_with_incomplete_dimensions_has_no_rho_and_exports_four_columns(qtbot, tmp_path):
    path = _saved_csv(
        tmp_path,
        stored_resistivity=False,
        settings={"sample_length_mm": 10, "sample_width_mm": 2, "sample_depth_mm": 1},
    )
    original = path.read_bytes()
    widget = _dialog(qtbot, path)
    assert not widget.saved_run.include_resistivity
    assert widget.statistics["resistivity_count"] == 0
    assert widget.statistics_table.item(2, 1).text() == "—"
    assert widget.statistics_table.item(2, 2).text() == "—"
    assert widget.statistics_table.item(2, 3).text() == "0"
    assert _curve(widget, "resistivity") == ([], [])
    assert "저장된 비저항이 없습니다" in widget.status_label.text()
    destination = tmp_path / "legacy-selection.txt"
    assert widget.export_to(destination)["rows"] == 4
    lines = destination.read_text().splitlines()
    assert lines[0] == ANALYSIS_HEADER.rstrip("\n")
    assert all(len(line.split("\t")) == 4 for line in lines)
    assert "4열" in widget.status_label.text()
    assert path.read_bytes() == original


def test_complete_geometry_keeps_five_column_schema_without_inventing_missing_rho(qtbot, tmp_path):
    path = _saved_csv(
        tmp_path,
        stored_resistivity=False,
        settings={
            "sample_length_mm": 10,
            "sample_width_mm": 2,
            "sample_depth_mm": 1,
            "current_path_axis": "L",
        },
    )
    widget = _dialog(qtbot, path)
    assert widget.saved_run.include_resistivity
    assert widget.statistics["resistivity_count"] == 0
    assert widget.statistics_table.item(2, 1).text() == "—"
    assert _curve(widget, "resistivity") == ([], [])
    destination = tmp_path / "missing-rho-selection.txt"
    assert widget.export_to(destination)["rows"] == 4
    lines = destination.read_text().splitlines()
    assert lines[0] == ANALYSIS_RESISTIVITY_HEADER.rstrip("\n")
    assert all(len(line.split("\t")) == 5 for line in lines)
    assert all(line.split("\t")[2] == "nan" for line in lines[1:])
