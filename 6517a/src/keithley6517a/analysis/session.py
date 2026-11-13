"""Portable, read-only analysis selections; never apply measurement settings."""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path

_KIND = "6517A-analysis-session"
_VERSION = 1
_QUANTITIES = {"current", "resistance", "resistivity"}
_SIDECARS = ("metadata.json", "config.json", "run_status.json")
_RESULT_NAMES = (
    *_SIDECARS,
    "readings.csv",
    "analysis.txt",
    "summary.csv",
    "raw_io.jsonl",
    "events.jsonl",
)
_MAX_SOURCES = 64
_TIME_LIMIT_S = 1e12


@dataclass(frozen=True)
class AnalysisSession:
    sources: tuple[Path, ...]
    start_s: float
    end_s: float
    active_index: int = 0
    quantity: str = "current"


def _interval(start, end):
    for value in (start, end):
        if type(value) not in (int, float):
            raise ValueError("분석 구간은 유한한 초(s) 값이어야 합니다.")
        try:
            valid = math.isfinite(value) and abs(value) <= _TIME_LIMIT_S
        except OverflowError:
            valid = False
        if not valid:
            raise ValueError("분석 구간은 ±1e12 s 이내의 유한한 값이어야 합니다.")
    if start > end:
        raise ValueError("분석 시작 시간은 종료 시간 이하여야 합니다.")


def _selection(start, end, active_index, quantity, count):
    _interval(start, end)
    if not 1 <= count <= _MAX_SOURCES:
        raise ValueError(f"분석 파일은 1–{_MAX_SOURCES}개를 지정하세요.")
    if type(active_index) is not int or not 0 <= active_index < count:
        raise ValueError("선택된 분석 파일 번호를 확인하세요.")
    if not isinstance(quantity, str) or quantity not in _QUANTITIES:
        raise ValueError("분석 물리량은 current, resistance, resistivity 중 하나여야 합니다.")


def _source(value, base=None):
    if not isinstance(value, (str, Path)) or not str(value):
        raise ValueError("분석 원본 경로를 확인하세요.")
    try:
        path = Path(value).expanduser()
        if base is not None and not path.is_absolute():
            path = base / path
        path = path.resolve(strict=True)
        if not path.is_file():
            raise ValueError(f"분석 원본이 파일이 아닙니다: {path}")
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError(f"분석 원본을 찾거나 읽을 수 없습니다: {value}") from exc
    return path


def _unique_sources(sources):
    if len(set(sources)) != len(sources):
        raise ValueError("같은 분석 원본 파일을 중복 지정할 수 없습니다.")


def _sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _fingerprints(source):
    try:
        sidecars = {}
        for name in _SIDECARS:
            path = source.parent / name
            sidecars[name] = _sha256(path) if path.exists() else None
        return _sha256(source), sidecars
    except OSError as exc:
        raise ValueError(f"분석 원본을 읽을 수 없습니다: {source}") from exc


def source_fingerprints(path) -> dict:
    """Capture the CSV and optional sidecars used by an already-loaded analysis."""
    digest, sidecars = _fingerprints(_source(path))
    return {"sha256": digest, "sidecars": sidecars}


def _stored_path(source, directory):
    try:
        return Path(os.path.relpath(source, directory)).as_posix()
    except ValueError:
        # Windows relpath cannot cross drives; keep the selected absolute path.
        return source.as_posix()


def save_session(session: AnalysisSession, output, *, expected_fingerprints=None) -> dict:
    """Write a new settings JSON with source fingerprints, preserving all originals."""
    if not isinstance(session, AnalysisSession):
        raise ValueError("AnalysisSession 분석 설정이 필요합니다.")
    if not isinstance(session.sources, (tuple, list)):
        raise ValueError("분석 원본 파일 목록을 확인하세요.")
    _selection(
        session.start_s, session.end_s, session.active_index, session.quantity, len(session.sources)
    )
    destination = Path(output).expanduser().absolute()
    directory = destination.parent.resolve(strict=True)
    sources = tuple(_source(source) for source in session.sources)
    _unique_sources(sources)
    reserved = set(sources) | {
        (source.parent / name).resolve() for source in sources for name in _RESULT_NAMES
    }
    if destination.resolve() in reserved:
        raise ValueError("분석 설정은 측정 원본·결과 파일과 다른 이름으로 저장하세요.")
    if expected_fingerprints is not None and (
        not isinstance(expected_fingerprints, (tuple, list))
        or len(expected_fingerprints) != len(sources)
    ):
        raise ValueError("불러온 분석 원본의 SHA-256 목록을 확인하세요.")
    records = []
    for index, source in enumerate(sources):
        digest, sidecars = _fingerprints(source)
        if expected_fingerprints is not None and expected_fingerprints[index] != {
            "sha256": digest,
            "sidecars": sidecars,
        }:
            raise ValueError(f"불러온 분석 원본이 변경됐습니다. 결과를 다시 여세요: {source}")
        records.append(
            {"path": _stored_path(source, directory), "sha256": digest, "sidecars": sidecars}
        )
    payload = {
        "kind": _KIND,
        "schema_version": _VERSION,
        "sources": records,
        "start_s": session.start_s,
        "end_s": session.end_s,
        "active_index": session.active_index,
        "quantity": session.quantity,
    }
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    created = False
    try:
        with destination.open("x", encoding="utf-8", newline="") as stream:
            created = True
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        if created:
            destination.unlink(missing_ok=True)
        raise
    return {"session_file": str(destination), "source_count": len(sources)}


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"분석 설정에 중복 JSON 항목이 있습니다: {key}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"분석 설정에 유한하지 않은 JSON 값이 있습니다: {value}")


def _digest(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def load_session(path) -> AnalysisSession:
    """Read saved selections and verify their inputs before returning any new state."""
    source = Path(path).expanduser().resolve(strict=True)
    try:
        value = json.loads(
            source.read_text(encoding="utf-8-sig"),
            object_pairs_hook=_strict_object,
            parse_constant=_invalid_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"분석 설정 JSON을 확인하세요: {source.name}") from exc
    expected = {"kind", "schema_version", "sources", "start_s", "end_s", "active_index", "quantity"}
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("분석 설정의 필수 항목과 파일 형식을 확인하세요.")
    if (
        value["kind"] != _KIND
        or type(value["schema_version"]) is not int
        or value["schema_version"] != _VERSION
    ):
        raise ValueError("지원하지 않는 분석 설정 형식 또는 버전입니다.")
    records = value["sources"]
    if not isinstance(records, list):
        raise ValueError("분석 원본 파일 목록을 확인하세요.")
    _selection(
        value["start_s"], value["end_s"], value["active_index"], value["quantity"], len(records)
    )
    sources = []
    for record in records:
        if (
            not isinstance(record, dict)
            or set(record) != {"path", "sha256", "sidecars"}
            or not isinstance(record["path"], str)
            or not record["path"]
            or not _digest(record["sha256"])
            or not isinstance(record["sidecars"], dict)
            or set(record["sidecars"]) != set(_SIDECARS)
            or any(item is not None and not _digest(item) for item in record["sidecars"].values())
        ):
            raise ValueError("분석 원본 경로·SHA-256 기록을 확인하세요.")
        selected = _source(record["path"], source.parent)
        digest, sidecars = _fingerprints(selected)
        if digest != record["sha256"] or sidecars != record["sidecars"]:
            raise ValueError(
                f"분석 원본이 설정 저장 후 변경됐습니다. 결과를 다시 여세요: {selected}"
            )
        sources.append(selected)
    _unique_sources(sources)
    return AnalysisSession(
        sources=tuple(sources),
        start_s=value["start_s"],
        end_s=value["end_s"],
        active_index=value["active_index"],
        quantity=value["quantity"],
    )
