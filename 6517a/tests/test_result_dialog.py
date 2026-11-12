"""Saved-result analysis is offline, explicit, and preserves the original readings."""

import csv
import json
import math

import pytest

from keithley6517a.storage.run_writer import ANALYSIS_HEADER
from keithley6517a.ui.result_dialog import SavedResultDialog


def saved_csv(tmp_path, rows=None):
    if rows is None:
        rows = [
            dict(
                elapsed_s=0.6719999999986612,
                current_raw_A=1e-9,
                resistance_apparent_ohm=1e9,
                voltage_programmed_readback_V=1,
                quality_flags=["OUTSIDE_SUMMARY_WINDOW", "SERIES_DROP_UNVERIFIED"],
            ),
            dict(
                elapsed_s=1,
                current_raw_A=2e-9,
                resistance_apparent_ohm=2e9,
                voltage_programmed_readback_V=4,
            ),
            dict(
                elapsed_s=2,
                native_r_ohm=0,
                resistance_apparent_ohm=9e9,
                current_inferred_A=99e-9,
                voltage_programmed_readback_V=0,
            ),
            dict(
                elapsed_s=3,
                current_raw_A=-1e-9,
                resistance_apparent_ohm=-1e9,
                voltage_programmed_readback_V=1,
            ),
        ]
    fields = [
        "elapsed_s",
        "current_raw_A",
        "resistance_apparent_ohm",
        "native_r_ohm",
        "current_inferred_A",
        "voltage_programmed_readback_V",
        "valid_for_summary",
        "quality_flags",
        "phase",
        "status_code",
    ]
    path = tmp_path / "readings.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        for row in rows:
            row = dict(row)
            row["quality_flags"] = json.dumps(row.get("quality_flags", []))
            row.setdefault("valid_for_summary", False)
            row.setdefault("phase", "ACQUIRING")
            row.setdefault("status_code", "N")
            writer.writerow(row)
    (tmp_path / "metadata.json").write_text('{"simulation":true}', encoding="utf-8")
    (tmp_path / "run_status.json").write_text(
        '{"status":"aborted","reason":"user STOP","final_output_state":"OFF"}',
        encoding="utf-8",
    )
    return path


def dialog(qtbot, path=None):
    widget = SavedResultDialog(path)
    qtbot.addWidget(widget)
    return widget


def test_opening_saved_result_never_opens_visa_or_constructs_runner(qtbot, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Reviewing saved data must not access a hardware session")

    monkeypatch.setattr("keithley6517a.transport.visa.VisaTransport.__init__", forbidden)
    monkeypatch.setattr("keithley6517a.measurement.runner.MeasurementRunner.__init__", forbidden)
    path = saved_csv(tmp_path)
    original = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    widget = dialog(qtbot, path)
    assert widget.saved_run is not None
    assert len(widget.selected_rows) == 4
    assert "SIMULATION" in widget.source_label.text()
    assert "사용자 중지" in widget.source_label.text()
    assert widget.statistics["current_count"] == 3
    assert widget.statistics["resistance_count"] == 4
    assert widget.statistics["invalid_count"] == 0
    assert widget.statistics["current_mean_A"] == pytest.approx(2e-9 / 3)
    assert widget.statistics["resistance_mean_ohm"] == pytest.approx(0.5e9)
    assert original == {p.name: p.read_bytes() for p in tmp_path.iterdir()}


def test_interval_selection_updates_graphs_statistics_and_exports_exact_rows(qtbot, tmp_path):
    path = saved_csv(tmp_path)
    widget = dialog(qtbot, path.parent)
    assert len(widget.selected_rows) == 4  # outward-rounded full bounds retain first row
    widget.start_time.setValue(1)
    widget.end_time.setValue(2)
    assert not widget.export_button.isEnabled()
    widget.apply_button.click()
    assert widget.export_button.isEnabled()
    assert [row["elapsed_s"] for row in widget.selected_rows] == [1, 2]
    assert widget.statistics["current_mean_A"] == 2e-9
    assert widget.statistics["current_std_A"] is None
    assert widget.statistics["resistance_mean_ohm"] == 1e9
    assert widget.statistics["resistance_std_ohm"] == pytest.approx(math.sqrt(2) * 1e9)
    x, y = widget.curves["resistance"].getOriginalDataset()
    assert list(x) == [1, 2] and list(y) == [2e9, 0]
    destination = tmp_path / "selected.txt"
    result = widget.export_to(destination)
    assert result["rows"] == 2
    assert destination.read_text() == (
        ANALYSIS_HEADER + "1.0\t2000000000.0\t4.0\t2e-09\n2.0\t0.0\t0.0\tnan\n"
    )
    widget.full_range_button.click()
    assert len(widget.selected_rows) == 4


def test_single_value_missing_std_and_existing_export_are_explicit(qtbot, tmp_path):
    path = saved_csv(tmp_path)
    widget = dialog(qtbot, path)
    widget.start_time.setValue(3)
    widget.end_time.setValue(3)
    assert widget.apply_range()
    assert widget.statistics_table.item(0, 1).text() == "-1 nA"
    assert widget.statistics_table.item(0, 2).text() == "—"
    destination = tmp_path / "already.txt"
    destination.write_text("previous data")
    assert widget.export_to(destination) is None
    assert destination.read_text() == "previous data"
    assert "다른 이름" in widget.status_label.text()


def test_bad_source_and_reversed_interval_have_visible_errors(qtbot, tmp_path):
    path = saved_csv(tmp_path)
    widget = dialog(qtbot, path)
    widget.start_time.setValue(3)
    widget.end_time.setValue(1)
    assert not widget.apply_range()
    assert "구간 확인" in widget.status_label.text()
    assert not widget.export_button.isEnabled()
    bad = tmp_path / "wrong.csv"
    bad.write_text("time,resistance\n1,1e9\n")
    assert not widget.load_path(bad)
    assert widget.saved_run is None
    assert "파일 확인" in widget.status_label.text()
    assert not widget.export_button.isEnabled()
    assert widget.statistics_table.item(0, 1).text() == "—"


def test_empty_result_and_empty_interval_do_not_export(qtbot, tmp_path):
    path = saved_csv(tmp_path, [])
    widget = dialog(qtbot, path)
    assert widget.saved_run is not None
    assert not widget.export_button.isEnabled()
    assert "판독 데이터 없음" in widget.selection_label.text()
    path = saved_csv(tmp_path)
    assert widget.load_path(path)
    widget.start_time.setValue(2.1)
    widget.end_time.setValue(2.5)
    assert widget.apply_range()
    assert widget.selected_rows == []
    target = tmp_path / "empty.txt"
    assert widget.export_to(target) is None and not target.exists()


def test_open_and_export_buttons_use_user_chosen_paths(qtbot, tmp_path, monkeypatch):
    source = saved_csv(tmp_path)
    target = tmp_path / "chosen.txt"
    widget = dialog(qtbot)
    monkeypatch.setattr(
        "keithley6517a.ui.result_dialog.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(source), ""),
    )
    monkeypatch.setattr(
        "keithley6517a.ui.result_dialog.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(target), ""),
    )
    widget.open_button.click()
    assert len(widget.selected_rows) == 4
    widget.export_button.click()
    assert target.read_text().startswith(ANALYSIS_HEADER)
    assert "TXT 저장 완료" in widget.status_label.text()
