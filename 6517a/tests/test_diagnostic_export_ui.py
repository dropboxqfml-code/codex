"""An idle GUI exports existing local records without connecting or modifying settings."""

import json
import zipfile

import pytest

from keithley6517a.ui.main_window import MainWindow


def close_window(qtbot, widget):
    widget.close()
    qtbot.waitUntil(lambda: widget._closed, timeout=20000)


@pytest.fixture
def window(qtbot):
    widget = MainWindow(lambda *a, **kw: pytest.fail("ZIP export must not create a runner"))
    qtbot.addWidget(widget, before_close_func=lambda value: close_window(qtbot, value))
    return widget


def test_idle_export_collects_known_sources_and_keeps_invalid_draft_without_hardware(
    window, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    run = tmp_path / "run"
    run.mkdir()
    original = b'{"status":"aborted","reason":"simulated storage fault"}'
    (run / "run_status.json").write_bytes(original)
    (run / "private-not-a-program-file.txt").write_text("do not copy", encoding="utf-8")
    diagnostic = tmp_path / "connection"
    diagnostic.mkdir()
    (diagnostic / "diagnostic.json").write_text('{"mode":"IDN_ONLY"}', encoding="utf-8")
    window._last_run_directory = str(run)
    window._last_diagnostic_directory = str(diagnostic)
    window.trip.setText("not a numeric trip")
    window.log.appendPlainText("SIMULATED ERROR: disk failure")
    before = window._base_config.copy()
    destination = tmp_path / "diagnostic.zip"
    assert window.export_diagnostic_button.isEnabled()
    result = window.export_diagnostics_to(destination)
    assert result and result["path"] == str(destination)
    with zipfile.ZipFile(destination) as archive:
        names = archive.namelist()
        assert "manifest.json" in names and "gui/log.txt" in names
        assert archive.read("source/run/run_status.json") == original
        assert "SIMULATED ERROR" in archive.read("gui/log.txt").decode("utf-8")
        assert "source/diagnostic/diagnostic.json" in names
        assert not any("private-not" in name for name in names)
        json.loads(archive.read("manifest.json"))
    assert window.worker.runner is None and window._base_config == before
    assert window.trip.text() == "not a numeric trip"
    assert (run / "run_status.json").read_bytes() == original
    assert "저장 완료" in window.diagnostic_label.text()
    existing = destination.read_bytes()
    assert window.export_diagnostics_to(destination) is None
    assert destination.read_bytes() == existing
    assert "저장 실패" in window.diagnostic_label.text()


@pytest.mark.parametrize(
    "status",
    [
        dict(state="ARMED", output_state="OFF"),
        dict(state="CONFIGURING", output_state="OFF"),
        dict(state="ACQUIRING", output_state="ON"),
        dict(state="STOPPING", output_state="ON"),
        dict(state="OUTPUT_OFF_CONFIRMED", output_state="OFF", worker_busy=True),
    ],
)
def test_busy_or_armed_export_is_blocked_even_when_called_directly(window, tmp_path, status):
    window._on_status(status)
    assert not window.export_diagnostic_button.isEnabled()
    assert window.export_diagnostics_to(tmp_path / "blocked.zip") is None
    assert not (tmp_path / "blocked.zip").exists()
    assert window.worker.runner is None


def test_no_run_yet_can_export_ui_context_and_cancel_is_side_effect_free(
    window, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    assert window.export_diagnostics_to(tmp_path / "empty-context.zip")
    with zipfile.ZipFile(tmp_path / "empty-context.zip") as archive:
        assert "manifest.json" in archive.namelist()
        assert not any(name.startswith("source/run/") for name in archive.namelist())
    monkeypatch.setattr(
        "keithley6517a.ui.main_window.QFileDialog.getSaveFileName", lambda *a, **kw: ("", "")
    )
    before = set(tmp_path.iterdir())
    window.export_diagnostic_button.click()
    assert set(tmp_path.iterdir()) == before
    assert window.worker.runner is None


def test_storage_error_is_inline_and_never_changes_instrument_state(window, tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("test disk full")

    monkeypatch.setattr("keithley6517a.storage.diagnostic_bundle.export_diagnostic_bundle", fail)
    assert window.export_diagnostics_to(tmp_path / "failure.zip") is None
    assert "test disk full" in window.diagnostic_label.text()
    assert window._state == "DISCONNECTED" and not window._busy
    assert window.worker.runner is None and not (tmp_path / "failure.zip").exists()
