"""Freeze one reviewed candidate for a repeat-safe native-save pilot.

The caller holds the watch scope lease while selecting or updating navigation
control. This sidecar never changes discovery records or adds image jobs.
"""

import json
import os
import re
import stat
import uuid
from datetime import datetime
from pathlib import Path

from image_monitor.artifact_files import ArtifactError, _plain_path, _sync_directory
from image_monitor.candidate_policy import CandidatePolicyError, classify_candidate_detail
from image_monitor.candidate_save_policy import (
    MONITOR_SCOPE,
    REVIEWED_SCOPE,
    CandidateSavePermit,
    CandidateSavePolicyError,
    make_candidate_save_permit,
)
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.queue import QueueError, QueueStore, _json_data
from image_monitor.watch_store import WatchScope, WatchStore, _record, _scope

MANIFEST_NAME = "candidate-save-selection.json"
MONITOR_MANIFEST_NAME = "monitor-save-selection.json"
MAX_SELECTION_BYTES = 64 * 1024
_MODE = "single_reviewed_candidate_native_save"
_SCOPE_KEYS = ("watch_name", "gallery_type", "gallery_id", "keyword", "search_type")
_FIELDS = {
    "schema_version",
    "mode",
    "scope",
    "post_id",
    "first_scan_id",
    "detail_attempt_id",
    "evidence_sha256",
    "control",
}


def selection_manifest_name(scope: WatchScope) -> str:
    """Map only the two reviewed scopes to separate fixed selection files."""
    if not isinstance(scope, WatchScope):
        raise QueueError("Candidate selection requires a reviewed watch scope")
    key = scope.key()
    if key == REVIEWED_SCOPE:
        return MANIFEST_NAME
    if key == MONITOR_SCOPE:
        return MONITOR_MANIFEST_NAME
    raise QueueError("Candidate selection scope is outside the reviewed pilots")


def _path(value):
    try:
        path = _plain_path(Path(value))
    except (ArtifactError, TypeError, ValueError) as error:
        raise QueueError("Candidate selection path must be local and plain") from error
    if path.name not in {MANIFEST_NAME, MONITOR_MANIFEST_NAME} or str(path).startswith("\\\\"):
        raise QueueError("Candidate selection must use its dedicated local filename")
    return path


def _regular(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise QueueError("Candidate selection must be a regular non-reparse file")
    if info.st_size > MAX_SELECTION_BYTES:
        raise QueueError("Candidate selection exceeds its metadata limit")
    return info


def _same_file(before, after):
    return (
        os.path.samestat(before, after)
        and before.st_size == after.st_size
        and before.st_mtime_ns == after.st_mtime_ns
    )


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise QueueError("Candidate selection contains duplicate JSON fields")
        result[key] = value
    return result


def _control(value):
    if not isinstance(value, dict) or type(value.get("blocked")) is not bool:
        raise QueueError("Candidate selection control requires an explicit boolean block state")
    _json_data(value, "Candidate selection control")
    for key in ("started_at", "finished_at", "next_eligible_at"):
        if key not in value:
            continue
        try:
            parsed = datetime.fromisoformat(value[key])
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError
        except (TypeError, ValueError, OverflowError) as error:
            raise QueueError("Candidate selection control timing is invalid") from error
    if "interval_seconds" in value and (
        type(value["interval_seconds"]) is not int or not 60 <= value["interval_seconds"] <= 300
    ):
        raise QueueError("Candidate selection control interval is invalid")
    if (
        "http_status" in value
        and value["http_status"] is not None
        and (type(value["http_status"]) is not int or not 100 <= value["http_status"] <= 599)
    ):
        raise QueueError("Candidate selection HTTP status is invalid")


def _validate(value):
    if (
        not isinstance(value, dict)
        or set(value) != _FIELDS
        or type(value.get("schema_version")) is not int
        or value["schema_version"] != 1
        or value.get("mode") != _MODE
    ):
        raise QueueError("Candidate selection has an unknown format")
    scope = value.get("scope")
    if not isinstance(scope, dict) or set(scope) != set(_SCOPE_KEYS):
        raise QueueError("Candidate selection watch scope is invalid")
    try:
        selection_manifest_name(WatchScope(**scope))
    except (TypeError, ValueError) as error:
        raise QueueError("Candidate selection watch scope is invalid") from error
    if not isinstance(value.get("post_id"), str) or not re.fullmatch(
        r"[1-9][0-9]{0,19}", value["post_id"]
    ):
        raise QueueError("Candidate selection post identity is invalid")
    for key in ("first_scan_id", "detail_attempt_id"):
        if not isinstance(value.get(key), str) or not re.fullmatch(r"[0-9a-f]{32}", value[key]):
            raise QueueError("Candidate selection observation identity is invalid")
    if not isinstance(value.get("evidence_sha256"), str) or not re.fullmatch(
        r"[0-9a-f]{64}", value["evidence_sha256"]
    ):
        raise QueueError("Candidate selection evidence digest is invalid")
    _control(value.get("control"))
    return value


def _read(path):
    try:
        named = _regular(path)
    except FileNotFoundError:
        return None, None
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    )
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not _same_file(named, opened):
            raise QueueError("Candidate selection changed while opening it")
        data = stream.read(MAX_SELECTION_BYTES + 1)
        after = os.fstat(stream.fileno())
    if len(data) > MAX_SELECTION_BYTES or not _same_file(opened, after):
        raise QueueError("Candidate selection changed while reading it")
    if not _same_file(after, _regular(path)):
        raise QueueError("Candidate selection path changed while reading it")
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, ValueError, RecursionError) as error:
        raise QueueError("Candidate selection JSON is invalid") from error
    _validate(value)
    if path.name != selection_manifest_name(WatchScope(**value["scope"])):
        raise QueueError("Candidate selection filename does not match its watch scope")
    return value, after


def read_selection(path: Path) -> dict | None:
    """Read only the owned, bounded manifest; malformed existing data is preserved."""
    return _read(_path(path))[0]


def _write(path, value, expected=None):
    _validate(value)
    if _path(path).name != selection_manifest_name(WatchScope(**value["scope"])):
        raise QueueError("Candidate selection filename does not match its watch scope")
    data = (_json_data(value, "Candidate selection") + "\n").encode("utf-8")
    if len(data) > MAX_SELECTION_BYTES:
        raise QueueError("Candidate selection exceeds its metadata limit")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        _path(path)
        if expected is None:
            if os.name == "nt":
                # Windows rename refuses a preexisting destination.
                os.rename(temporary, path)
            else:
                os.link(temporary, path, follow_symlinks=False)
                temporary.unlink()
        else:
            if not _same_file(expected, _regular(path)):
                raise QueueError("Candidate selection changed before its control update")
            os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def write_selection_control(path: Path, control: dict) -> None:
    """Update only navigation control on an existing selection under the scope lease."""
    path = _path(path)
    value, identity = _read(path)
    if value is None:
        raise QueueError("A candidate selection is required before navigation control")
    _control(control)
    if value["control"]["blocked"] and control["blocked"] is not True:
        raise QueueError("A candidate access block requires explicit manual recovery")
    value["control"] = control
    _write(path, value, expected=identity)


def _database_path(queue):
    row = next(
        (row for row in queue.connection.execute("PRAGMA database_list") if row[1] == "main"),
        None,
    )
    if row is None or not row[2]:
        raise QueueError("A persisted watch database is required for candidate selection")
    try:
        return _plain_path(Path(row[2]))
    except ArtifactError as error:
        raise QueueError("The candidate watch database path is not plain") from error


def selection_service_blocked(queue: QueueStore) -> bool:
    """Honor a persisted native-navigation block for every watch scope in this DB."""
    root = _database_path(queue).parent
    # Read both even when one is already blocked: malformed evidence in either
    # pilot is preserved and prevents navigation for every scope in this DB.
    values = [read_selection(root / name) for name in (MANIFEST_NAME, MONITOR_MANIFEST_NAME)]
    return any(value is not None and value["control"]["blocked"] for value in values)


def _candidate(queue, scope, post_id):
    row = queue.connection.execute(
        "SELECT * FROM watch_candidates WHERE watch_name=? AND gallery_type=? AND gallery_id=? "
        "AND keyword=? AND search_type=? AND post_id=?",
        (*_scope(scope), post_id),
    ).fetchone()
    if row is None:
        raise QueueError("The selected candidate is no longer present")
    return _record(row)


def _permit(candidate, baseline, detail):
    try:
        return make_candidate_save_permit(candidate, baseline, detail)
    except (CandidateSavePolicyError, CandidatePolicyError, TypeError, ValueError) as error:
        raise QueueError("Candidate save evidence requires review") from error


def _manifest(scope, candidate, detail, permit):
    return {
        "schema_version": 1,
        "mode": _MODE,
        "scope": dict(zip(_SCOPE_KEYS, scope.key(), strict=True)),
        "post_id": candidate["post_id"],
        "first_scan_id": candidate["first_scan_id"],
        "detail_attempt_id": detail["attempt_id"],
        "evidence_sha256": permit.fingerprint,
        "control": {"blocked": False},
    }


def select_candidate_save(
    queue: QueueStore, scope: WatchScope, manifest_path: Path
) -> CandidateSavePermit | None:
    """Freeze one eligible completed detail; repeat calls must retain that exact binding."""
    name = selection_manifest_name(scope)
    path = _path(manifest_path)
    if path != _database_path(queue).parent / name:
        raise QueueError("Candidate selection must stay beside its watch database")
    existing = read_selection(path)
    claims = set()
    if not queue.read_only:
        from image_monitor.monitor_save_ledger import recent_save_claims

        claims = recent_save_claims(_database_path(queue))
    baseline = WatchStore(queue).get_state(scope)["baseline"]
    if existing is not None:
        if existing["post_id"] in claims:
            raise QueueError("The frozen post has already been claimed by a recent save")
        if existing["scope"] != dict(zip(_SCOPE_KEYS, scope.key(), strict=True)):
            raise QueueError("The frozen candidate selection belongs to another watch scope")
        candidate = _candidate(queue, scope, existing["post_id"])
        detail = CandidateDetailStore(queue).get(existing["detail_attempt_id"])
        if detail is None or candidate["first_scan_id"] != existing["first_scan_id"]:
            raise QueueError("The frozen candidate discovery evidence changed")
        permit = _permit(candidate, baseline, detail)
        expected = _manifest(scope, candidate, detail, permit)
        if any(existing[key] != expected[key] for key in _FIELDS - {"control"}):
            raise QueueError("The frozen candidate save evidence changed")
        return permit
    # Read-only callers may verify an existing binding, never create a sidecar
    # if it disappeared between their existence check and this reread.
    if queue.read_only or baseline is None or queue.schema_version < 5:
        return None
    rows = queue.connection.execute(
        "SELECT attempt_id,post_id,result_json FROM candidate_details WHERE watch_name=? "
        "AND gallery_type=? AND gallery_id=? AND keyword=? AND search_type=? "
        "AND status='completed' ORDER BY started_at,attempt_id",
        scope.key(),
    )
    for row in rows:
        if row["post_id"] in claims:
            continue
        detail = CandidateDetailStore(queue).get(row["attempt_id"])
        result = detail["result"]
        observation = result.get("private_observation") if isinstance(result, dict) else None
        if not isinstance(observation, dict):
            raise QueueError("Completed candidate inspection evidence is missing")
        if (
            observation.get("http_status") in {404, 410}
            and observation.get("status") == "http_error"
        ):
            continue
        snapshot = observation.get("snapshot")
        if observation.get("status") != "observed" or not isinstance(snapshot, dict):
            raise QueueError("Completed candidate body evidence is missing")
        images = snapshot.get("images")
        counts = snapshot.get("image_counts")
        if not isinstance(images, list) or not isinstance(counts, dict):
            raise QueueError("Completed candidate image evidence is invalid")
        if (
            not images
            and type(counts.get("included_unique")) is int
            and counts["included_unique"] == 0
            and type(counts.get("pending")) is int
            and counts["pending"] == 0
        ):
            continue
        candidate = _candidate(queue, scope, row["post_id"])
        try:
            classification = classify_candidate_detail(candidate, baseline, snapshot)
        except CandidatePolicyError as error:
            raise QueueError("Completed candidate identity requires review") from error
        if classification["time_status"] == "before_baseline":
            continue
        permit = _permit(candidate, baseline, detail)
        _write(path, _manifest(scope, candidate, detail, permit))
        return permit
    return None
