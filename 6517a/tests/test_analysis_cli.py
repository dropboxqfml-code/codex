"""Offline analysis conversion preserves readings and never touches VISA."""

import csv
import json
import math

import pytest

from keithley6517a import cli
from keithley6517a.storage.analysis_export import export_analysis


def reading_csv(path, rows):
    fields = [
        "elapsed_s",
        "resistance_apparent_ohm",
        "voltage_programmed_readback_V",
        "current_raw_A",
        "native_r_ohm",
        "valid_for_summary",
        "phase",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_offline_cli_exports_excluded_and_error_rows_without_opening_hardware(
    tmp_path, monkeypatch, capsys
):
    def forbidden(*args, **kwargs):
        pytest.fail("Offline conversion must not construct an instrument or runner")

    monkeypatch.setattr(cli, "MeasurementRunner", forbidden)
    monkeypatch.setattr("keithley6517a.transport.visa.VisaTransport.__init__", forbidden)
    source = reading_csv(
        tmp_path / "readings.csv",
        [
            dict(
                elapsed_s=0.125,
                resistance_apparent_ohm=-1e9,
                voltage_programmed_readback_V=1,
                current_raw_A=-1e-9,
                valid_for_summary=False,
                phase="SETTLING",
            ),
            dict(elapsed_s=2, native_r_ohm=2e9, phase="ERROR"),
        ],
    )
    original = source.read_bytes()
    assert cli.main(["export-analysis", str(source)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["rows"] == 2
    lines = (tmp_path / "analysis.txt").read_text().splitlines()
    assert lines[0] == "Time (s)\tResistance (Ohm)\tVoltage (V)\tCurrent (A)"
    assert list(map(float, lines[1].split("\t"))) == [0.125, -1e9, 1, -1e-9]
    missing = list(map(float, lines[2].split("\t")))
    assert missing[:2] == [2, 2e9] and all(math.isnan(value) for value in missing[2:])
    assert source.read_bytes() == original


def test_export_never_replaces_existing_analysis_or_source(tmp_path, capsys):
    source = reading_csv(tmp_path / "readings.csv", [])
    destination = tmp_path / "analysis.txt"
    destination.write_text("existing data")
    assert cli.main(["export-analysis", str(source)]) == 2
    assert json.loads(capsys.readouterr().err)["type"] == "FileExistsError"
    assert destination.read_text() == "existing data"
    with pytest.raises(ValueError, match="different file"):
        export_analysis(source, source)


@pytest.mark.parametrize(
    "bad_row", ["2,1e9,1,nan,,False,ACQUIRING", "2,1e9,1", "2,1e9,1,1e-9,,,X,extra"]
)
def test_bad_csv_cleans_new_output_and_preserves_original(tmp_path, bad_row):
    source = reading_csv(tmp_path / "readings.csv", [])
    with source.open("a", encoding="utf-8") as stream:
        stream.write("1,1e9,1,1e-9,,False,ACQUIRING\n" + bad_row + "\n")
    original = source.read_bytes()
    with pytest.raises(ValueError, match="row 3"):
        export_analysis(source)
    assert source.read_bytes() == original
    assert not (tmp_path / "analysis.txt").exists()


def test_custom_output_and_bad_header_are_explicit(tmp_path, capsys):
    source = reading_csv(tmp_path / "readings.csv", [])
    target = tmp_path / "four-columns.txt"
    assert cli.main(["export-analysis", str(source), "--output", str(target)]) == 0
    assert json.loads(capsys.readouterr().out)["rows"] == 0
    assert target.read_text().count("\n") == 1
    source.write_text("time,resistance\n1,1e9\n")
    with pytest.raises(ValueError, match="Expected a 6517A"):
        export_analysis(source)
    assert not (tmp_path / "analysis.txt").exists()
