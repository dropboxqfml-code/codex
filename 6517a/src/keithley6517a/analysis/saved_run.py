"""Read-only saved readings, explicit time selections, and offline statistics."""

from __future__ import annotations

import csv
import json
import math
import os
import statistics
from dataclasses import dataclass, field
from pathlib import Path

from ..storage.run_writer import (
    analysis_header,
    analysis_includes_resistivity,
    analysis_line,
)

_NUMERIC_FIELDS = {
    "elapsed_s",
    "current_raw_A",
    "current_inferred_A",
    "voltage_programmed_readback_V",
    "native_r_ohm",
    "resistance_apparent_ohm",
    "resistivity_ohm_m",
}
_INFORMATIONAL_FLAGS = {
    "OUTSIDE_SUMMARY_WINDOW",
    "AFTER_DWELL",
    "SETTLING_EXCLUDED",
    "RANGE_CHANGE_TIMING_UNCERTAIN",
    "SERIES_DROP_UNVERIFIED",
    "RANGE_NUMBER_GAP",
    "READING_NUMBER_GAP_NOT_PROOF_OF_LOSS",
    "INFERRED_CURRENT_NOT_MEASURED",
    "ZERO_VOLTAGE_UNDEFINED_R",
    "NOT_RESOLVED",
    "SIMULATED",
}


def _finite(value):
    return type(value) in (float, int) and math.isfinite(value)


@dataclass(frozen=True)
class SavedRun:
    source_path: Path
    directory: Path
    rows: list[dict]
    status: dict
    metadata: dict
    settings: dict = field(default_factory=dict)

    @property
    def include_resistivity(self) -> bool:
        """Keep the whole run's text schema when exporting any selected interval."""
        return analysis_includes_resistivity(self.rows, self.metadata, self.settings)

    @property
    def start_s(self) -> float | None:
        return min(
            (row["elapsed_s"] for row in self.rows if _finite(row.get("elapsed_s"))), default=None
        )

    @property
    def end_s(self) -> float | None:
        return max(
            (row["elapsed_s"] for row in self.rows if _finite(row.get("elapsed_s"))), default=None
        )


def _sidecar(path: Path) -> dict:
    if not path.exists():
        return {}

    def nonstandard(value):
        raise ValueError(f"{path.name}: 유한하지 않은 JSON 값 {value}")

    value = json.loads(path.read_text(encoding="utf-8-sig"), parse_constant=nonstandard)
    if not isinstance(value, dict):
        raise ValueError(f"{path.name}: JSON 객체가 필요합니다.")
    return value


def load_saved_run(path) -> SavedRun:
    """Load readings.csv or its run directory; never apply saved hardware settings."""
    source = Path(path).expanduser().resolve(strict=True)
    if source.is_dir():
        source = (source / "readings.csv").resolve(strict=True)
    rows = []
    with source.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        header = reader.fieldnames or []
        fields = set(header)
        required = {"elapsed_s", "current_raw_A", "voltage_programmed_readback_V"}
        if (
            len(fields) != len(header)
            or not required <= fields
            or not fields & {"native_r_ohm", "resistance_apparent_ohm"}
        ):
            raise ValueError("readings.csv의 시간·저항·전압·전류 열을 확인하세요.")
        for index, raw in enumerate(reader, start=2):
            if None in raw or None in raw.values():
                raise ValueError(f"CSV {index}행의 열 개수를 확인하세요.")
            row = dict(raw)
            for field in _NUMERIC_FIELDS:
                token = row.get(field, "").strip()
                if not token:
                    row[field] = None
                    continue
                try:
                    value = float(token)
                except (ValueError, OverflowError) as exc:
                    raise ValueError(f"CSV {index}행의 {field} 값이 숫자가 아닙니다.") from exc
                if not math.isfinite(value):
                    raise ValueError(f"CSV {index}행의 {field} 값은 유한해야 합니다.")
                row[field] = value
            flags = row.get("quality_flags", "").strip()
            try:
                flags = json.loads(flags) if flags else []
            except json.JSONDecodeError as exc:
                raise ValueError(f"CSV {index}행의 quality_flags 형식을 확인하세요.") from exc
            if not isinstance(flags, list) or any(not isinstance(flag, str) for flag in flags):
                raise ValueError(f"CSV {index}행의 quality_flags는 문자열 목록이어야 합니다.")
            row["quality_flags"] = flags
            valid = row.get("valid_for_summary", "").strip()
            if valid not in {"", "True", "False", "true", "false"}:
                raise ValueError(f"CSV {index}행의 valid_for_summary 형식을 확인하세요.")
            row["valid_for_summary"] = None if not valid else valid.lower() == "true"
            rows.append(row)
    snapshot = _sidecar(source.parent / "config.json")
    settings = snapshot.get("settings", snapshot)
    if not isinstance(settings, dict):
        raise ValueError("config.json: settings는 JSON 객체여야 합니다.")
    return SavedRun(
        source_path=source,
        directory=source.parent,
        rows=rows,
        status=_sidecar(source.parent / "run_status.json"),
        metadata=_sidecar(source.parent / "metadata.json"),
        settings=settings,
    )


def select_rows(saved: SavedRun, start_s: float, end_s: float) -> list[dict]:
    """Select inclusive elapsed-time bounds, retaining source order and quality flags."""
    if not _finite(start_s) or not _finite(end_s):
        raise ValueError("분석 구간은 유한한 초(s) 값으로 입력하세요.")
    if start_s > end_s:
        raise ValueError("분석 시작 시간은 종료 시간 이하여야 합니다.")
    return [
        row
        for row in saved.rows
        if _finite(row.get("elapsed_s")) and start_s <= row["elapsed_s"] <= end_s
    ]


def _eligible(row):
    # A custom user-selected interval is independent of the acquisition's summary window.
    # Instrument errors/trips remain excluded from statistics, even if raw numbers exist.
    return (
        _finite(row.get("elapsed_s"))
        and row.get("phase") != "ERROR"
        and row.get("status_code") in (None, "", "N")
        and not (set(row.get("quality_flags") or ()) - _INFORMATIONAL_FLAGS)
    )


def _stats(values):
    if not values:
        return None, None
    mean = statistics.mean(values)
    try:
        deviation = statistics.stdev(values) if len(values) > 1 else None
    except OverflowError:
        deviation = None
    if deviation is not None and not math.isfinite(deviation):
        deviation = None
    return mean, deviation


def summarize_rows(rows) -> dict:
    """Sample statistics from stored values; never infer missing current or resistivity."""
    rows = list(rows)
    eligible = [row for row in rows if _eligible(row)]
    current = [row["current_raw_A"] for row in eligible if _finite(row.get("current_raw_A"))]
    resistance = []
    for row in eligible:
        value = row.get("native_r_ohm")
        if value is None:
            value = row.get("resistance_apparent_ohm")
        if _finite(value):
            resistance.append(value)
    mean_i, std_i = _stats(current)
    mean_r, std_r = _stats(resistance)
    resistivity = [
        row["resistivity_ohm_m"] for row in eligible if _finite(row.get("resistivity_ohm_m"))
    ]
    mean_rho, std_rho = _stats(resistivity)
    return dict(
        row_count=len(rows),
        invalid_count=len(rows) - len(eligible),
        current_count=len(current),
        current_mean_A=mean_i,
        current_std_A=std_i,
        resistance_count=len(resistance),
        resistance_mean_ohm=mean_r,
        resistance_std_ohm=std_r,
        resistivity_count=len(resistivity),
        resistivity_mean_ohm_m=mean_rho,
        resistivity_std_ohm_m=std_rho,
    )


def export_selection(saved: SavedRun, output, start_s: float, end_s: float) -> dict:
    """Write selected rows using the whole run's four/five-column text schema."""
    rows = select_rows(saved, start_s, end_s)
    include_resistivity = saved.include_resistivity
    destination = Path(output).expanduser().absolute()
    if destination.resolve() == saved.source_path.resolve():
        raise ValueError("TXT 저장 경로는 원본 readings.csv와 달라야 합니다.")
    created = False
    try:
        with destination.open("x", encoding="utf-8", newline="") as stream:
            created = True
            stream.write(analysis_header(include_resistivity))
            for row in rows:
                stream.write(
                    analysis_line(row, include_resistivity=True)
                    if include_resistivity
                    else analysis_line(row)
                )
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        if created:
            destination.unlink(missing_ok=True)
        raise
    return {"analysis_file": str(destination), "rows": len(rows)}
