"""Convert existing reading CSV files without opening an instrument or replacing data."""

import csv
import os
from pathlib import Path

from .run_writer import ANALYSIS_HEADER, analysis_line


def export_analysis(source, output=None):
    """Write a new four-column analysis file, keeping incomplete/flagged readings too."""
    source = Path(source).expanduser().resolve(strict=True)
    destination = (
        Path(output).expanduser().absolute()
        if output is not None
        else source.with_name("analysis.txt")
    )
    if destination.resolve() == source:
        raise ValueError("Analysis output must be a different file from readings.csv")
    created = False
    count = 0
    try:
        with source.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            fields = set(reader.fieldnames or ())
            required = {"elapsed_s", "voltage_programmed_readback_V", "current_raw_A"}
            if not required <= fields or not fields & {
                "native_r_ohm",
                "resistance_apparent_ohm",
            }:
                raise ValueError(
                    "Expected a 6517A readings.csv with time, resistance, voltage, current"
                )
            with destination.open("x", encoding="utf-8", newline="") as target:
                created = True
                target.write(ANALYSIS_HEADER)
                for line_number, row in enumerate(reader, start=2):
                    if None in row or None in row.values():
                        raise ValueError(f"Malformed readings.csv row {line_number}")
                    try:
                        line = analysis_line(row)
                    except (ValueError, TypeError, OverflowError) as exc:
                        raise ValueError(f"Invalid readings.csv row {line_number}: {exc}") from exc
                    target.write(line)
                    count += 1
                target.flush()
                os.fsync(target.fileno())
    except BaseException:
        if created:
            destination.unlink(missing_ok=True)
        raise
    return {"analysis_file": str(destination), "rows": count}
