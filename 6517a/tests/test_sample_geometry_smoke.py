"""The Windows geometry smoke verifies saved units and five-column resistivity TXT."""

import csv
import importlib.util
import json
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "geometry_bundle_smoke", PROJECT / "packaging/smoke.py"
)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def geometry_run(directory):
    directory.mkdir()
    settings = dict(
        sample_length_mm=20,
        sample_width_mm=10,
        sample_depth_mm=2,
        current_path_axis="D",
    )
    (directory / "config.json").write_text(json.dumps({"settings": settings}), encoding="utf-8")
    geometry = dict(
        dimensions_mm={"L": 20, "W": 10, "D": 2},
        current_path_axis="D",
        area_m2=2e-4,
        current_path_length_m=2e-3,
    )
    (directory / "metadata.json").write_text(
        json.dumps({"sample_geometry": geometry}), encoding="utf-8"
    )
    rows = [
        dict(
            elapsed_s=1,
            resistance_apparent_ohm=1e9,
            resistance_corrected_ohm=1e9,
            resistivity_ohm_m=1e8,
            voltage_programmed_readback_V=1,
            current_raw_A=1e-9,
        ),
        dict(
            elapsed_s=2,
            resistance_apparent_ohm=2e9,
            resistance_corrected_ohm=2e9,
            resistivity_ohm_m=2e8,
            voltage_programmed_readback_V=1,
            current_raw_A=5e-10,
        ),
    ]
    with (directory / "readings.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (directory / "analysis.txt").write_text(
        "Time (s)\tResistance (Ohm)\tResistivity (Ohm m)\tVoltage (V)\tCurrent (A)\n"
        "1.0\t1000000000.0\t100000000.0\t1.0\t1e-9\n"
        "2.0\t2000000000.0\t200000000.0\t1.0\t5e-10\n",
        encoding="utf-8",
    )
    return directory


def test_geometry_smoke_checks_saved_units_and_five_column_export(tmp_path):
    directory = geometry_run(tmp_path / "sample")
    assert smoke.verify_sample_geometry(directory) == 2


@pytest.mark.parametrize("broken", ["axis", "area", "rho", "txt"])
def test_geometry_smoke_rejects_wrong_axis_units_rho_or_extra_txt_columns(tmp_path, broken):
    directory = geometry_run(tmp_path / "sample")
    if broken in {"axis", "area"}:
        path = directory / "metadata.json"
        metadata = json.loads(path.read_text())
        metadata["sample_geometry"]["current_path_axis" if broken == "axis" else "area_m2"] = (
            "L" if broken == "axis" else 200
        )
        path.write_text(json.dumps(metadata), encoding="utf-8")
    else:
        path = directory / ("readings.csv" if broken == "rho" else "analysis.txt")
        text = path.read_text()
        path.write_text(
            text.replace("100000000.0", "1000000000.0")
            if broken == "rho"
            else text.replace("Current (A)", "Current (A)\tResistivity (Ohm m)"),
            encoding="utf-8",
        )
    with pytest.raises(RuntimeError):
        smoke.verify_sample_geometry(directory)


def test_native_geometry_smoke_uses_synthetic_measurements_and_exports_resistivity(
    tmp_path, monkeypatch
):
    def no_instrument(*args, **kwargs):
        pytest.fail("Sample geometry smoke must not create a VISA session")

    monkeypatch.setattr("keithley6517a.transport.visa.VisaTransport.__init__", no_instrument)
    directory = smoke.sample_geometry_resistivity_smoke(tmp_path / "runs")
    assert smoke.verify_sample_geometry(directory) > 0
    lines = (directory / "analysis.txt").read_text().splitlines()
    assert all(len(line.split("\t")) == 5 for line in lines)
