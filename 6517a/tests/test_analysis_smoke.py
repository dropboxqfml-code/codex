"""Release smoke rejects missing, filtered, or relabeled analysis text data."""

import csv
import importlib.util
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("analysis_smoke", PROJECT / "packaging/smoke.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)

HEADER = "Time (s)\tResistance (Ohm)\tVoltage (V)\tCurrent (A)\n"
ROWS = "0.7\t-1000000000.0\t1.0\t-1e-09\n1.7\t0.0\t0.0\tnan\n"


def sample_run(directory):
    rows = [
        dict(
            elapsed_s=0.7,
            resistance_apparent_ohm=-1e9,
            voltage_programmed_readback_V=1,
            current_raw_A=-1e-9,
            valid_for_summary=False,
        ),
        dict(
            elapsed_s=1.7,
            resistance_apparent_ohm=1e12,
            native_r_ohm=0,
            voltage_programmed_readback_V=0,
            current_raw_A=None,
            current_inferred_A=1e-9,
            valid_for_summary=False,
        ),
    ]
    fields = sorted({key for row in rows for key in row})
    with (directory / "readings.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_native_smoke_compares_all_rows_and_preserves_native_zero_and_missing_raw_current(tmp_path):
    sample_run(tmp_path)
    (tmp_path / "analysis.txt").write_text(HEADER + ROWS, encoding="utf-8")
    assert smoke.analysis_export_smoke(tmp_path) == 2


@pytest.mark.parametrize(
    "text",
    [
        HEADER.replace("Resistance (Ohm)", "Current (A)") + ROWS,
        HEADER + ROWS.splitlines(keepends=True)[0],
        HEADER + ROWS + ROWS.splitlines(keepends=True)[0],
        HEADER + ROWS.replace("\t0.0\t0.0\tnan", "\t1000000000000.0\t0.0\t1e-9"),
        HEADER + ROWS + "extra metadata\n",
    ],
)
def test_native_smoke_rejects_changed_schema_data_or_row_count(tmp_path, text):
    sample_run(tmp_path)
    (tmp_path / "analysis.txt").write_text(text, encoding="utf-8")
    with pytest.raises(RuntimeError):
        smoke.analysis_export_smoke(tmp_path)
