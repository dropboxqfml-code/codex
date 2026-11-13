"""Compared runs keep their own stored samples, statistics and text schemas."""

import csv
import json
from pathlib import Path

import pytest

from keithley6517a.ui.result_dialog import SavedResultDialog


def stored_run(directory, *, scale=1, rho=True, simulation=True, times=(0, 1, 2)):
    directory.mkdir()
    fields = (
        "elapsed_s",
        "current_raw_A",
        "voltage_programmed_readback_V",
        "native_r_ohm",
        "resistance_apparent_ohm",
        "resistivity_ohm_m",
        "quality_flags",
        "phase",
        "status_code",
    )
    path = directory / "readings.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        for index, elapsed in enumerate(times):
            writer.writerow(
                dict(
                    elapsed_s=elapsed,
                    current_raw_A=(index + 1) * scale * 1e-9,
                    voltage_programmed_readback_V=1,
                    resistance_apparent_ohm=(index + 1) * scale * 1e9,
                    resistivity_ohm_m=(index + 1) * scale * 1e8 if rho else None,
                    quality_flags="[]",
                    phase="ACQUIRING",
                    status_code="N",
                )
            )
    (directory / "metadata.json").write_text(
        json.dumps({"simulation": simulation}), encoding="utf-8"
    )
    (directory / "config.json").write_text(
        json.dumps({"settings": {"sample_id": directory.name}}), encoding="utf-8"
    )
    return path


def widget(qtbot, path):
    dialog = SavedResultDialog(path)
    qtbot.addWidget(dialog)
    return dialog


def curve(dialog, source_index, quantity):
    xs, ys = dialog.comparison_curves[source_index][quantity].getOriginalDataset()
    return ([] if xs is None else list(xs), [] if ys is None else list(ys))


def test_overlay_keeps_relative_times_and_independent_statistics_without_hardware(
    qtbot, tmp_path, monkeypatch
):
    def forbidden(*args, **kwargs):
        pytest.fail("Offline comparison must not create an instrument session")

    monkeypatch.setattr("keithley6517a.transport.visa.VisaTransport.__init__", forbidden)
    monkeypatch.setattr("keithley6517a.measurement.runner.MeasurementRunner.__init__", forbidden)
    first = stored_run(tmp_path / "first")
    second = stored_run(tmp_path / "second", scale=4, simulation=False, times=(0.5, 1.5, 2.5))
    dialog = widget(qtbot, first)
    assert dialog.add_paths([second])
    assert len(dialog.saved_runs) == dialog.source_selector.count() == 2
    assert dialog.start_time.minimum() == 0 and dialog.end_time.maximum() == 2.5
    assert "[SIM]" in dialog.source_selector.itemText(0)
    assert "[VISA]" in dialog.source_selector.itemText(1)
    dialog.start_time.setValue(1)
    dialog.end_time.setValue(2)
    assert dialog.apply_range()
    xs, ys = curve(dialog, 0, "current")
    assert xs == [1, 2] and ys == pytest.approx([2e-9, 3e-9])
    assert curve(dialog, 1, "current") == ([1.5], [8e-9])
    assert curve(dialog, 1, "resistivity") == ([1.5], [8e8])
    assert dialog.comparison_statistics[0]["current_mean_A"] == pytest.approx(2.5e-9)
    assert dialog.comparison_statistics[1]["current_mean_A"] == 8e-9
    assert dialog.select_source(1)
    assert dialog.statistics["current_mean_A"] == 8e-9
    assert dialog.curves is dialog.comparison_curves[1]
    assert "VISA" in dialog.source_label.text() and "비교 2개" in dialog.source_label.text()
    dialog.graph_tabs.setCurrentIndex(2)
    assert "ρ 평균 800 MΩ·m" in dialog.source_selector.itemText(1)


def test_export_uses_only_active_run_and_its_own_four_or_five_columns(qtbot, tmp_path):
    first = stored_run(tmp_path / "with-rho")
    second = stored_run(tmp_path / "legacy", scale=5, rho=False)
    originals = {
        path: path.read_bytes() for source in (first, second) for path in source.parent.iterdir()
    }
    dialog = widget(qtbot, first)
    assert dialog.add_paths([second])
    assert dialog.select_source(1)
    assert dialog.statistics["resistivity_count"] == 0
    legacy_output = tmp_path / "legacy.txt"
    assert dialog.export_to(legacy_output)["rows"] == 3
    legacy_lines = legacy_output.read_text().splitlines()
    assert all(len(line.split("\t")) == 4 for line in legacy_lines)
    assert float(legacy_lines[1].split("\t")[1]) == 5e9
    assert dialog.select_source(0)
    rho_output = tmp_path / "rho.txt"
    assert dialog.export_to(rho_output)["rows"] == 3
    assert all(len(line.split("\t")) == 5 for line in rho_output.read_text().splitlines())
    assert all(path.read_bytes() == data for path, data in originals.items())
    before = rho_output.read_bytes()
    assert dialog.export_to(rho_output) is None and rho_output.read_bytes() == before


def test_add_is_transactional_and_duplicate_paths_do_not_create_extra_curves(qtbot, tmp_path):
    first = stored_run(tmp_path / "first")
    second = stored_run(tmp_path / "second")
    dialog = widget(qtbot, first)
    previous = dialog.saved_run
    assert not dialog.add_paths([second, tmp_path / "missing.csv"])
    assert dialog.saved_run is previous and len(dialog.saved_runs) == 1
    assert len(dialog.comparison_curves) == 1
    assert "기존 분석 유지" in dialog.status_label.text()
    assert dialog.add_paths([first.parent, Path(first)])
    assert len(dialog.saved_runs) == len(dialog.comparison_curves) == 1
    assert "이미 추가" in dialog.status_label.text()
    assert dialog.add_paths([second, first])
    assert len(dialog.saved_runs) == 2 and "중복 1개" in dialog.status_label.text()


def test_active_switch_does_not_apply_a_pending_interval_or_save_it(qtbot, tmp_path):
    dialog = widget(qtbot, stored_run(tmp_path / "first"))
    assert dialog.add_paths([stored_run(tmp_path / "second", scale=4)])
    dialog.start_time.setValue(1)
    assert not dialog.export_button.isEnabled() and not dialog.save_session_button.isEnabled()
    assert dialog.select_source(1)
    assert dialog.statistics["current_count"] == 3
    assert not dialog.export_button.isEnabled() and not dialog.save_session_button.isEnabled()
    assert dialog.export_to(tmp_path / "pending.txt") is None
    assert not dialog.save_session_to(tmp_path / "pending.json")
    assert not (tmp_path / "pending.txt").exists() and not (tmp_path / "pending.json").exists()
    dialog.apply_button.click()
    assert dialog.statistics["current_count"] == 2
    assert dialog.export_button.isEnabled() and dialog.save_session_button.isEnabled()


def test_removing_sources_rebuilds_legends_bounds_and_empty_state(qtbot, tmp_path):
    first = stored_run(tmp_path / "first")
    dialog = widget(qtbot, first)
    assert dialog.add_paths([stored_run(tmp_path / "late", times=(5, 6, 7))])
    assert dialog.select_source(1)
    assert dialog.remove_source(0)
    assert len(dialog.saved_runs) == 1 and dialog.active_index == 0
    assert dialog.start_time.value() == 5 and dialog.end_time.value() == 7
    assert len(dialog.plots["current"].getPlotItem().legend.items) == 1
    dialog.remove_button.click()
    assert dialog.saved_run is None and dialog.saved_runs == []
    assert not dialog.export_button.isEnabled() and not dialog.save_session_button.isEnabled()
    assert not dialog.remove_button.isEnabled()
    assert curve(dialog, 0, "current") == ([], [])
    assert dialog.statistics_table.item(2, 3).text() == "0"


def test_comparison_limit_failure_preserves_existing_data(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr("keithley6517a.ui.result_dialog.MAX_COMPARE_FILES", 2)
    dialog = widget(qtbot, stored_run(tmp_path / "first"))
    assert not dialog.add_paths([stored_run(tmp_path / "second"), stored_run(tmp_path / "third")])
    assert len(dialog.saved_runs) == 1 and "최대 2개" in dialog.status_label.text()


def test_comparison_file_button_uses_multiple_user_chosen_paths(qtbot, tmp_path, monkeypatch):
    first, second = stored_run(tmp_path / "first"), stored_run(tmp_path / "second")
    dialog = widget(qtbot, first)
    monkeypatch.setattr(
        "keithley6517a.ui.result_dialog.QFileDialog.getOpenFileNames",
        lambda *args, **kwargs: ([str(second)], ""),
    )
    dialog.add_button.click()
    assert len(dialog.saved_runs) == 2


def test_sample_names_are_plain_text_in_comparison_legends(qtbot, tmp_path):
    path = stored_run(tmp_path / "first")
    (path.parent / "config.json").write_text(
        json.dumps({"settings": {"sample_id": "<b>sample</b> & reference"}}), encoding="utf-8"
    )
    dialog = widget(qtbot, path)
    label = dialog.plots["current"].getPlotItem().legend.items[0][1]
    assert label.item.toPlainText() == "1. <b>sample</b> & reference [SIM]"
