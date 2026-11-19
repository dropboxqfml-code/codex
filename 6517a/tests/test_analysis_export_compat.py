"""CLI and saved-result analysis interpret the same legacy Windows data consistently."""

import json

import pytest

from keithley6517a.analysis.saved_run import load_saved_run
from keithley6517a.storage.analysis_export import export_analysis
from keithley6517a.storage.run_writer import ANALYSIS_RESISTIVITY_HEADER


@pytest.mark.parametrize(
    "name,payload",
    [
        ("metadata.json", {"analysis_text": {"include_resistivity": True}}),
        ("config.json", {"settings": {"area_m2": 2e-4, "thickness_m": 2e-3}}),
    ],
)
def test_bom_sidecars_keep_cli_and_gui_export_schema_consistent(tmp_path, name, payload):
    source = tmp_path / "readings.csv"
    source.write_text(
        "elapsed_s,current_raw_A,voltage_programmed_readback_V,resistance_apparent_ohm\n"
        "1,1e-9,1,1e9\n",
        encoding="utf-8-sig",
    )
    sidecar = tmp_path / name
    sidecar.write_text(json.dumps(payload), encoding="utf-8-sig")
    before = {path: path.read_bytes() for path in (source, sidecar)}
    assert load_saved_run(source).include_resistivity is True
    result = export_analysis(source)
    assert result["rows"] == 1
    assert (tmp_path / "analysis.txt").read_text() == (
        ANALYSIS_RESISTIVITY_HEADER + "1.0\t1000000000.0\tnan\t1.0\t1e-09\n"
    )
    assert all(path.read_bytes() == content for path, content in before.items())


def test_duplicate_csv_columns_cannot_silently_replace_values_in_cli_export(tmp_path):
    source = tmp_path / "readings.csv"
    source.write_text(
        "elapsed_s,elapsed_s,current_raw_A,voltage_programmed_readback_V,"
        "resistance_apparent_ohm\n1,99,1e-9,1,1e9\n",
        encoding="utf-8",
    )
    original = source.read_bytes()
    with pytest.raises(ValueError):
        load_saved_run(source)
    with pytest.raises(ValueError, match="readings.csv"):
        export_analysis(source)
    assert source.read_bytes() == original
    assert not (tmp_path / "analysis.txt").exists()
