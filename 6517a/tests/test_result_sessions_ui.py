"""Analysis settings restore only the saved view and never alter measurement data."""

import csv
import json
import shutil

import pytest

from keithley6517a.analysis.session import AnalysisSession, save_session
from keithley6517a.ui.result_dialog import SavedResultDialog


def source(directory, factor=1):
    directory.mkdir(parents=True)
    path = directory / "readings.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            [
                "elapsed_s",
                "current_raw_A",
                "voltage_programmed_readback_V",
                "resistance_apparent_ohm",
                "resistivity_ohm_m",
            ],
        )
        writer.writeheader()
        writer.writerows(
            dict(
                elapsed_s=index,
                current_raw_A=(index + 1) * factor * 1e-9,
                voltage_programmed_readback_V=1,
                resistance_apparent_ohm=(index + 1) * factor * 1e9,
                resistivity_ohm_m=(index + 1) * factor * 1e8,
            )
            for index in range(4)
        )
    (directory / "metadata.json").write_text('{"simulation":true}', encoding="utf-8")
    return path


def dialog(qtbot, path=None):
    widget = SavedResultDialog(path)
    qtbot.addWidget(widget)
    return widget


def test_session_roundtrip_restores_relative_paths_order_range_active_quantity_and_originals(
    qtbot, tmp_path, monkeypatch
):
    def forbidden(*args, **kwargs):
        pytest.fail("Loading an analysis view must not construct a hardware session")

    monkeypatch.setattr("keithley6517a.transport.visa.VisaTransport.__init__", forbidden)
    monkeypatch.setattr("keithley6517a.measurement.runner.MeasurementRunner.__init__", forbidden)
    root = tmp_path / "portable"
    first, second = source(root / "first"), source(root / "second", 3)
    originals = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    widget = dialog(qtbot, first)
    assert widget.add_paths([second]) and widget.select_source(1)
    widget.start_time.setValue(1)
    widget.end_time.setValue(2)
    assert widget.apply_range()
    widget.graph_tabs.setCurrentIndex(2)
    settings = root / "analysis-session.json"
    assert widget.save_session_to(settings)
    assert all(path.read_bytes() == content for path, content in originals.items())
    moved = tmp_path / "moved"
    shutil.copytree(root, moved)
    restored = dialog(qtbot)
    assert restored.load_session_path(moved / settings.name)
    assert [run.source_path for run in restored.saved_runs] == [
        (moved / "first/readings.csv").resolve(),
        (moved / "second/readings.csv").resolve(),
    ]
    assert restored.active_index == 1 and restored.saved_run is restored.saved_runs[1]
    assert restored.start_time.value() == 1 and restored.end_time.value() == 2
    assert restored.graph_tabs.currentIndex() == 2
    assert restored.statistics["resistivity_mean_ohm_m"] == 7.5e8
    assert len(restored.selected_rows) == 2 and len(restored.comparison_curves) == 2


@pytest.mark.parametrize("change", ["csv", "sidecar", "missing"])
def test_failed_restore_preserves_current_comparison_and_applied_view(qtbot, tmp_path, change):
    first, second = source(tmp_path / "first"), source(tmp_path / "second", 2)
    settings = tmp_path / "session.json"
    save_session(AnalysisSession((first, second), 1, 2, 1, "resistivity"), settings)
    widget = dialog(qtbot, first)
    original_run, original_statistics = widget.saved_run, dict(widget.statistics)
    if change == "missing":
        second.unlink()
    else:
        target = second if change == "csv" else second.parent / "metadata.json"
        target.write_text(target.read_text() + "\n", encoding="utf-8")
    assert not widget.load_session_path(settings)
    assert widget.saved_run is original_run and widget.statistics == original_statistics
    assert len(widget.saved_runs) == 1 and widget.active_index == 0
    assert widget.start_time.value() == 0 and widget.end_time.value() == 3
    assert widget.export_button.isEnabled() and "기존 분석 유지" in widget.status_label.text()


@pytest.mark.parametrize("interval", [(0, 100), (0.123456789, 2)])
def test_unsupported_restored_view_is_rejected_before_existing_analysis_changes(
    qtbot, tmp_path, interval
):
    path = source(tmp_path / "run")
    settings = tmp_path / "session.json"
    save_session(AnalysisSession((path,), *interval), settings)
    widget = dialog(qtbot, path)
    original = widget.saved_run
    assert not widget.load_session_path(settings)
    assert widget.saved_run is original and len(widget.selected_rows) == 4
    assert widget.start_time.value() == 0 and widget.end_time.value() == 3


def test_malformed_session_and_existing_destination_leave_original_files_untouched(qtbot, tmp_path):
    path = source(tmp_path / "run")
    widget = dialog(qtbot, path)
    broken = tmp_path / "bad.json"
    broken.write_text("{broken", encoding="utf-8")
    assert not widget.load_session_path(broken)
    assert widget.saved_run.source_path == path
    target = tmp_path / "existing.json"
    target.write_text("original settings", encoding="utf-8")
    assert not widget.save_session_to(target)
    assert target.read_text() == "original settings" and "다른 이름" in widget.status_label.text()
    assert not widget.save_session_to(path.parent / "config.json")
    assert not (path.parent / "config.json").exists()


def test_saving_after_source_changes_is_rejected_without_replacing_loaded_samples(qtbot, tmp_path):
    path = source(tmp_path / "run")
    widget = dialog(qtbot, path)
    original_rows = list(widget.selected_rows)
    (path.parent / "metadata.json").write_text('{"simulation":false}', encoding="utf-8")
    target = tmp_path / "stale.json"
    assert not widget.save_session_to(target) and not target.exists()
    assert widget.selected_rows == original_rows
    assert "저장 실패" in widget.status_label.text()


def test_pending_interval_blocks_session_save_until_explicit_apply(qtbot, tmp_path):
    widget = dialog(qtbot, source(tmp_path / "run"))
    widget.start_time.setValue(1)
    assert not widget.save_session_button.isEnabled()
    target = tmp_path / "session.json"
    assert not widget.save_session_to(target) and not target.exists()
    widget.apply_button.click()
    assert widget.save_session_button.isEnabled() and widget.save_session_to(target)
    data = json.loads(target.read_text())
    assert data


def test_session_buttons_follow_explicit_user_selected_paths(qtbot, tmp_path, monkeypatch):
    path = source(tmp_path / "run")
    widget = dialog(qtbot, path)
    settings = tmp_path / "chosen.json"
    monkeypatch.setattr(
        "keithley6517a.ui.result_dialog.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(settings), ""),
    )
    widget.save_session_button.click()
    assert settings.is_file()
    restored = dialog(qtbot)
    monkeypatch.setattr(
        "keithley6517a.ui.result_dialog.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(settings), ""),
    )
    restored.open_session_button.click()
    assert restored.saved_run.source_path == path
