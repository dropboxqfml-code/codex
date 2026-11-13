"""Convert existing reading CSV files without opening an instrument or replacing data."""

import csv
import json
import os
from pathlib import Path

from .run_writer import analysis_header, analysis_includes_resistivity, analysis_line


def _read_sidecar(path):
    if not path.exists():
        return {}

    def invalid_constant(token):
        raise ValueError(f"Non-finite JSON value in {path.name}: {token}")

    try:
        value = json.loads(path.read_text(encoding="utf-8"), parse_constant=invalid_constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Invalid {path.name}: expected a JSON object")
    return value


def _reading_rows(stream):
    reader = csv.DictReader(stream)
    fields = set(reader.fieldnames or ())
    required = {"elapsed_s", "voltage_programmed_readback_V", "current_raw_A"}
    if not required <= fields or not fields & {"native_r_ohm", "resistance_apparent_ohm"}:
        raise ValueError("Expected a 6517A readings.csv with time, resistance, voltage, current")
    for line_number, row in enumerate(reader, start=2):
        if None in row or None in row.values():
            raise ValueError(f"Malformed readings.csv row {line_number}")
        yield line_number, row


def export_analysis(source, output=None):
    """Write one fixed SI-unit schema, keeping incomplete/flagged readings too."""
    source = Path(source).expanduser().resolve(strict=True)
    destination = (
        Path(output).expanduser().absolute()
        if output is not None
        else source.with_name("analysis.txt")
    )
    if destination.resolve() == source:
        raise ValueError("Analysis output must be a different file from readings.csv")
    metadata = _read_sidecar(source.with_name("metadata.json"))
    settings = _read_sidecar(source.with_name("config.json"))
    created = False
    count = 0
    try:
        with source.open(encoding="utf-8-sig", newline="") as stream:
            include_resistivity = analysis_includes_resistivity(
                (row for _, row in _reading_rows(stream)), metadata=metadata, settings=settings
            )
            stream.seek(0)
            with destination.open("x", encoding="utf-8", newline="") as target:
                created = True
                target.write(analysis_header(include_resistivity))
                for line_number, row in _reading_rows(stream):
                    try:
                        line = analysis_line(row, include_resistivity=include_resistivity)
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
