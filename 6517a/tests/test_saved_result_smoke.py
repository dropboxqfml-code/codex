"""Bundled smoke proves stopped runs and the offline result UI, without VISA sessions."""

import csv
import importlib.util
import json
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("saved_result_smoke", PROJECT / "packaging/smoke.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def saved_rows(directory):
    directory.mkdir()
    fields = [
        "elapsed_s",
        "current_raw_A",
        "resistance_apparent_ohm",
        "native_r_ohm",
        "voltage_programmed_readback_V",
        "phase",
        "status_code",
        "valid_for_summary",
        "quality_flags",
    ]
    with (directory / "readings.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        for index in range(6):
            writer.writerow(
                dict(
                    elapsed_s=index,
                    current_raw_A=(index + 1) * 1e-9,
                    resistance_apparent_ohm=1e9 / (index + 1),
                    voltage_programmed_readback_V=1,
                    phase="ACQUIRING",
                    status_code="N",
                    valid_for_summary=False,
                    quality_flags=json.dumps(["OUTSIDE_SUMMARY_WINDOW"]),
                )
            )
    (directory / "run_status.json").write_text(
        json.dumps({"status": "stopped", "final_output_state": "OFF"}), encoding="utf-8"
    )
    (directory / "metadata.json").write_text(json.dumps({"simulation": True}), encoding="utf-8")


def test_native_stop_smoke_checks_retained_rows_and_partial_summary(tmp_path):
    directory = smoke.user_stop_smoke(tmp_path / "runs")
    assert smoke.analysis_export_smoke(directory) == 2
    assert (directory / "summary.csv").read_bytes() == b""
    assert json.loads((directory / "run_status.json").read_text())["status"] == "stopped"


def test_native_review_smoke_checks_statistics_selection_and_read_only_source(qtbot, tmp_path):
    directory = tmp_path / "saved"
    saved_rows(directory)
    original = {path.name: path.read_bytes() for path in directory.iterdir()}
    exported = tmp_path / "selected.txt"
    assert smoke.saved_result_review_smoke(directory, exported) == 2
    assert len(exported.read_text().splitlines()) == 3
    assert {path.name: path.read_bytes() for path in directory.iterdir()} == original


def test_native_review_smoke_detects_incorrect_display_statistics(qtbot, tmp_path):
    from keithley6517a.ui.result_dialog import SavedResultDialog

    class IncorrectStatistics(SavedResultDialog):
        def apply_range(self):
            ready = super().apply_range()
            if ready:
                self.statistics["current_mean_A"] = 1e6
            return ready

    directory = tmp_path / "saved"
    saved_rows(directory)
    with pytest.raises(RuntimeError, match="statistic differs"):
        smoke.saved_result_review_smoke(
            directory, tmp_path / "selected.txt", dialog_factory=IncorrectStatistics
        )


def test_native_review_smoke_forbids_measurement_session_creation(qtbot, tmp_path):
    from keithley6517a.config import RunConfig
    from keithley6517a.measurement.runner import MeasurementRunner

    directory = tmp_path / "saved"
    saved_rows(directory)
    original = MeasurementRunner.__init__

    def session_factory():
        return MeasurementRunner(RunConfig())

    with pytest.raises(RuntimeError, match="attempted to create an instrument session"):
        smoke.saved_result_review_smoke(
            directory, tmp_path / "selected.txt", dialog_factory=session_factory
        )
    assert MeasurementRunner.__init__ is original
