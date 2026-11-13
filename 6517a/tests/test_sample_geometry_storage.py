"""Sample dimensions are recorded once and resistivity is preserved in the wide CSV."""

import csv
import json
from dataclasses import replace

import pytest

from keithley6517a.clock import FakeClock
from keithley6517a.config import RunConfig
from keithley6517a.measurement.runner import MeasurementRunner


def config(tmp_path, **changes):
    values = dict(
        output_directory=str(tmp_path),
        sample_id="RECTANGULAR-SAMPLE",
        voltages=(1,),
        current_trip_A=1e-8,
        residual_warning_ack=True,
        simulation_resistance_ohm=1e9,
        dwell_s=0.5,
        summary_window_s=0.5,
        sample_interval_s=0.1,
        nplc=0.1,
        sample_length_mm=20,
        sample_width_mm=10,
        sample_depth_mm=2,
        current_path_axis="D",
    )
    values.update(changes)
    return replace(RunConfig(), **values)


def complete(config):
    runner = MeasurementRunner(config, clock=FakeClock())
    try:
        runner.connect()
        runner.arm()
        result = runner.start()
        assert result["status"] == "completed" and result["output_state"] == "OFF"
        return runner.run_directory
    finally:
        runner.shutdown()


def test_geometry_and_resistivity_roundtrip_with_five_column_export(tmp_path):
    settings = config(tmp_path)
    folder = complete(settings)
    assert RunConfig.load(folder / "config.json") == settings
    geometry = json.loads((folder / "metadata.json").read_text())["sample_geometry"]
    assert geometry["dimensions_mm"] == {"L": 20, "W": 10, "D": 2}
    assert geometry["current_path_axis"] == "D" and geometry["complete"] is True
    assert geometry["model"] == "rectangular_full_face"
    assert geometry["area_m2"] == pytest.approx(2e-4)
    assert geometry["current_path_length_m"] == pytest.approx(2e-3)
    assert geometry["resistivity_unit"] == "ohm m"
    with (folder / "readings.csv").open(newline="") as stream:
        readings = list(csv.DictReader(stream))
    valid = [row for row in readings if row["resistance_corrected_ohm"]]
    assert valid
    for row in valid:
        assert float(row["resistivity_ohm_m"]) == pytest.approx(
            float(row["resistance_corrected_ohm"]) * 0.1
        )
    lines = (folder / "analysis.txt").read_text().splitlines()
    assert lines[0] == ("Time (s)\tResistance (Ohm)\tResistivity (Ohm m)\tVoltage (V)\tCurrent (A)")
    assert len(lines) == len(readings) + 1
    assert all(len(line.split("\t")) == 5 for line in lines)
    for row, line in zip(readings, lines[1:], strict=True):
        assert float(line.split("\t")[2]) == pytest.approx(float(row["resistivity_ohm_m"]))


@pytest.mark.parametrize(
    "changes",
    [dict(current_path_axis=None), dict(sample_depth_mm=None)],
)
def test_incomplete_geometry_saves_known_dimensions_and_resistance_without_resistivity(
    tmp_path, changes
):
    settings = config(tmp_path, **changes)
    folder = complete(settings)
    geometry = json.loads((folder / "metadata.json").read_text())["sample_geometry"]
    assert geometry["dimensions_mm"]["L"] == 20
    assert geometry["complete"] is False
    assert geometry["area_m2"] is None and geometry["current_path_length_m"] is None
    with (folder / "readings.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows and any(row["resistance_apparent_ohm"] for row in rows)
    assert all(row["resistivity_ohm_m"] == "" for row in rows)
    lines = (folder / "analysis.txt").read_text().splitlines()
    assert lines[0] == "Time (s)\tResistance (Ohm)\tVoltage (V)\tCurrent (A)"
    assert len(lines) == len(rows) + 1
    assert all(len(line.split("\t")) == 4 for line in lines)
