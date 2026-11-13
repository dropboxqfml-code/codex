"""Native integration proofs exercise visible comparison/session, progress and ZIP behavior."""

import csv
import importlib.util
import json
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("integrated_smoke", PROJECT / "packaging/smoke.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def saved_run(directory, *, geometry):
    directory.mkdir()
    fields = (
        "elapsed_s current_raw_A resistance_apparent_ohm native_r_ohm "
        "resistivity_ohm_m voltage_programmed_readback_V phase status_code quality_flags"
    ).split()
    with (directory / "readings.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        for index in range(8):
            writer.writerow(
                dict(
                    elapsed_s=index,
                    current_raw_A=(index + 1) * 1e-9,
                    resistance_apparent_ohm=3e9 / (index + 1),
                    resistivity_ohm_m=3e8 / (index + 1) if geometry else None,
                    voltage_programmed_readback_V=3,
                    phase="ACQUIRING",
                    status_code="N",
                    quality_flags="[]",
                )
            )
    (directory / "config.json").write_text(
        json.dumps({"settings": {"sample_id": "synthetic", "resource": "SIMULATION"}}),
        encoding="utf-8",
    )
    (directory / "metadata.json").write_text(json.dumps({"simulation": True}), encoding="utf-8")
    (directory / "raw_io.jsonl").write_text('{"synthetic":true}\n', encoding="utf-8")
    (directory / "run_status.json").write_text(
        json.dumps({"status": "completed", "final_output_state": "OFF"}), encoding="utf-8"
    )
    return directory


def test_native_comparison_session_proof_checks_actual_curves_and_reopened_source(qtbot, tmp_path):
    first = saved_run(tmp_path / "first", geometry=False)
    second = saved_run(tmp_path / "second", geometry=True)
    assert smoke.analysis_comparison_session_smoke(first, second, tmp_path / "output") == {
        "analysis_comparison_session_verified": True
    }


@pytest.mark.parametrize("broken", ["curves", "restore"])
def test_native_comparison_session_proof_rejects_wrong_graph_or_restored_source(
    qtbot, tmp_path, broken
):
    from keithley6517a.ui.result_dialog import SavedResultDialog

    class BrokenDialog(SavedResultDialog):
        def _draw(self, rows):
            super()._draw(rows)
            if broken == "curves" and len(self.saved_runs) > 1:
                self.comparison_curves[1]["current"].setData([0], [999])

        def load_session_path(self, path):
            ready = super().load_session_path(path)
            if ready and broken == "restore":
                self.active_index = 0
            return ready

    first = saved_run(tmp_path / "first", geometry=False)
    second = saved_run(tmp_path / "second", geometry=True)
    with pytest.raises(RuntimeError, match="curve differs|restore paths"):
        smoke.analysis_comparison_session_smoke(
            first, second, tmp_path / "output", dialog_factory=BrokenDialog
        )


def test_native_main_progress_and_local_zip_proof(qtbot, tmp_path):
    from keithley6517a.ui.main_window import MainWindow

    directory = saved_run(tmp_path / "run", geometry=True)
    window = MainWindow()
    try:
        assert smoke.progress_and_diagnostic_smoke(window, directory, tmp_path / "output") == {
            "estimated_progress_verified": True,
            "diagnostic_zip_export_verified": True,
        }
    finally:
        window.close()
        qtbot.waitUntil(lambda: window._closed, timeout=5000)


def test_native_main_proof_rejects_incorrect_eta(qtbot, tmp_path):
    from dataclasses import replace

    from keithley6517a.ui.main_window import MainWindow

    window = MainWindow()
    original = window._set_progress_plan

    def wrong_plan(config):
        original(config)
        tracker = window._progress
        estimate = tracker.estimate
        tracker.estimate = lambda: (
            replace(value, remaining_s=999) if (value := estimate()) is not None else None
        )

    window._set_progress_plan = wrong_plan
    try:
        with pytest.raises(RuntimeError, match="remaining dwell"):
            smoke.progress_and_diagnostic_smoke(
                window, saved_run(tmp_path / "run", geometry=True), tmp_path / "output"
            )
    finally:
        window.close()
        qtbot.waitUntil(lambda: window._closed, timeout=5000)
