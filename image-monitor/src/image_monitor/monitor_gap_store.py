"""Recover one certified list frontier without replaying an unbounded chain of scans."""

import hashlib
import json
import sqlite3

from image_monitor.candidate_finish import CandidateFinishError, _read_json, _same_json, _uuid
from image_monitor.queue import QueueError
from image_monitor.watch_store import _SCOPE_WHERE, MONITOR_SCOPE, _record

_UNAVAILABLE = (
    OSError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    IndexError,
    RecursionError,
    OverflowError,
    sqlite3.Error,
    CandidateFinishError,
)
_FIELDS = ("watch_name", "gallery_type", "gallery_id", "keyword", "search_type")


def _reference(source):
    return {"scan_id": source["source_scan_id"], "generation": source["source_generation"]}


def _valid_ref(ref):
    return (
        isinstance(ref, dict)
        and set(ref) == {"scan_id", "generation"}
        and _uuid(ref["scan_id"])
        and type(ref["generation"]) is int
        and ref["generation"] > 0
    )


def bookmark_seal(latest):
    """Bind the original planner evidence, previous frontier and committed scan identity."""
    if not latest or "gap_recovery" not in latest["result"]:
        return None
    raw = json.dumps(
        latest, ensure_ascii=True, sort_keys=True, allow_nan=False, separators=(",", ":")
    )
    return hashlib.sha256(b"image-monitor-gap-scan-v1\0" + raw.encode("ascii")).hexdigest()


def _sealed_source(queue, state, scan):
    result = scan["result"]
    marker = result.get("gap_recovery")
    if not isinstance(marker, dict) or scan["complete"] is not False:
        return None
    from image_monitor.candidate_save_selection import _database_path
    from image_monitor.watch_gap_recovery import valid_gap_bookmark
    from image_monitor.watch_runtime import confirmed_monitor_scan, historical_candidate_count

    value = marker.get("bookmark")
    if not valid_gap_bookmark(MONITOR_SCOPE, state, value):
        return None
    run_id = result["control"].get("monitor_run_id")
    if not _uuid(run_id):
        return None
    database = _database_path(queue)
    receipt = _read_json(database.parent / "runs" / run_id / "report.json")
    if (
        receipt.get("browser") != "chrome"
        or receipt.get("recent_pages_verified") is not True
        or not confirmed_monitor_scan(database, scan, expected_report=receipt)
    ):
        return None
    # A genuine later observation may refresh last_seen. The original identities
    # and first discovery of each recorded candidate must still agree.
    candidates = [row for row in result["observations"] if row["role"] == "candidate"]
    count = historical_candidate_count(queue, scan, {"candidates": candidates})
    if count is None or not _same_json(count, receipt.get("new_candidates")):
        return None
    stored_count = queue.connection.execute(
        "SELECT COUNT(*) FROM watch_candidates WHERE first_scan_id=?", (scan["scan_id"],)
    ).fetchone()[0]
    if count != stored_count:
        return None
    return value | {"source_scan_id": scan["scan_id"], "source_generation": scan["generation"]}


def _source_at(queue, state, ref):
    if not _valid_ref(ref) or ref["generation"] >= state["generation"]:
        return None
    if ref["generation"] < state["generation"] - 1:
        row = queue.connection.execute(
            f"SELECT * FROM watch_scans WHERE {_SCOPE_WHERE} AND generation=?",
            (*MONITOR_SCOPE.key(), state["generation"] - 1),
        ).fetchone()
        parent = _record(row)
        if parent is None or not _same_json(
            parent["result"].get("control", {}).get("gap_bookmark_before"), ref
        ):
            return None
        try:
            if _sealed_source(queue, state, parent) is not None:
                # The immediately preceding turn had already certified a newer
                # frontier. A later failure cannot roll it back to its predecessor.
                return None
        except _UNAVAILABLE:
            pass  # An unsealed advance legitimately retained its starting point.
    # A newer complete scan satisfied the previous target, including when its
    # new checkpoint happens to contain the same anchor IDs as the old one.
    superseded = queue.connection.execute(
        f"SELECT 1 FROM watch_scans WHERE {_SCOPE_WHERE} AND complete=1 "
        "AND generation>? AND generation<=? LIMIT 1",
        (*MONITOR_SCOPE.key(), ref["generation"], state["generation"]),
    ).fetchone()
    if superseded:
        return None
    row = queue.connection.execute(
        f"SELECT * FROM watch_scans WHERE {_SCOPE_WHERE} AND scan_id=? AND generation=?",
        (*MONITOR_SCOPE.key(), ref["scan_id"], ref["generation"]),
    ).fetchone()
    scan = _record(row)
    if scan is None or scan["complete"]:
        return None
    source_state = state | {
        "latest_scan": scan,
        "generation": scan["generation"],
        "updated_at": scan["observed_at"],
    }
    if "gap_recovery" in scan["result"]:
        return _sealed_source(queue, source_state, scan)
    # A migration can start from an existing closed four-page scan. If its
    # first new turn was interrupted, revalidate that original seed in place.
    if "gap_bookmark_before" in scan["result"].get("control", {}):
        return None
    from image_monitor.watch_runtime import gap_seed

    return gap_seed(queue, source_state)


def load_bookmark(queue, state):
    """Read the latest certified frontier or its single retained predecessor."""
    try:
        scan = state.get("latest_scan")
        if (
            not scan
            or scan["complete"]
            or state.get("checkpoint") is None
            or scan["generation"] != state["generation"]
            or tuple(scan.get(k) for k in _FIELDS) != MONITOR_SCOPE.key()
        ):
            return None
        try:
            value = _sealed_source(queue, state, scan)
        except _UNAVAILABLE:
            # The scan row may have committed just before a process exit, while
            # its final Chrome report was still missing or incomplete.
            value = None
        if value is not None:
            return value
        ref = scan["result"].get("control", {}).get("gap_bookmark_before")
        return _source_at(queue, state, ref)
    except _UNAVAILABLE:
        return None


def bind_bookmark(queue, scope, state, result, supplied):
    """Inside the scan transaction, retain exactly the preceding verified frontier."""
    if scope != MONITOR_SCOPE:
        if supplied is not None or "gap_recovery" in result:
            raise QueueError("Long-gap scans require the monitor scope")
        return result
    control = result.get("control", {})
    if isinstance(control, dict) and "gap_bookmark_before" in control:
        raise QueueError("A scan cannot choose its own preceding bookmark")
    current = load_bookmark(queue, state)
    if supplied is not None:
        if current is None:
            from image_monitor.watch_runtime import gap_seed

            current = gap_seed(queue, state)
        if current is None or not _same_json(current, supplied):
            raise QueueError("The supplied gap frontier changed before the scan commit")
    if "gap_recovery" in result:
        from image_monitor.watch_gap_recovery import GAP_STATUSES, valid_gap_bookmark

        if supplied is None:
            raise QueueError("The gap recovery plan has no verified preceding frontier")
        marker = result["gap_recovery"]
        if (
            not isinstance(marker, dict)
            or not isinstance(marker.get("status"), str)
            or marker["status"] not in GAP_STATUSES
            or "bookmark" not in marker
        ):
            raise QueueError("Invalid gap recovery marker")
        successor = marker["bookmark"]
        if successor is not None and (
            not valid_gap_bookmark(scope, state, successor)
            or "source_scan_id" in successor
            or "source_generation" in successor
        ):
            raise QueueError("Invalid successor gap frontier")
    if current is None:
        return result
    if not isinstance(control, dict):
        raise QueueError("A retained gap frontier requires scan control metadata")
    ref = _reference(current)
    if not _valid_ref(ref):
        raise QueueError("Invalid persisted gap frontier identity")
    return result | {"control": control | {"gap_bookmark_before": ref}}


def _preceding_state(queue, scope, previous_state):
    row = queue.connection.execute(
        f"SELECT * FROM watch_scans WHERE {_SCOPE_WHERE} AND generation=?",
        (*scope.key(), previous_state["generation"]),
    ).fetchone()
    parent = _record(row)
    if not parent:
        return None
    return previous_state | {"latest_scan": parent, "updated_at": parent["observed_at"]}


def replay_gap_scan(queue, scope, latest, previous_state, scan_time):
    """Recompute the plan with the same closed source consumed at the scan commit."""
    from image_monitor.watch_runtime import (
        DURABLE_GAP_SCHEMAS,
        FRONTIER_OVERLAP_SCHEMA,
        FRONTIER_RESTART_SCHEMA,
        PARTIAL_OVERLAP_SCHEMAS,
        _plan_observation,
        gap_seed,
    )

    result = latest["result"]
    control = result["control"]
    schema = control.get("historical_route_schema")
    if (
        scope != MONITOR_SCOPE
        or control.get("follow_up_page_limit") != 4
        or type(schema) is not int
        or schema not in DURABLE_GAP_SCHEMAS
    ):
        return None
    before = _preceding_state(queue, scope, previous_state)
    if before is None:
        return None
    bookmark = load_bookmark(queue, before) or gap_seed(queue, before)
    if bookmark is None or not _same_json(control.get("gap_bookmark_before"), _reference(bookmark)):
        return None
    return _plan_observation(
        scope,
        before,
        result["private_observation"],
        scan_time,
        4,
        bookmark,
        allow_head_overlap=True,
        allow_seed_crossing=True,
        allow_partial_overlap=schema in PARTIAL_OVERLAP_SCHEMAS,
        allow_frontier_overlap=schema == FRONTIER_OVERLAP_SCHEMA,
        allow_frontier_restart=schema == FRONTIER_RESTART_SCHEMA,
    )


def replay_gap_seed(queue, scope, latest, previous_state, scan_time, limit, remaining_bridges):
    """Verify a fresh early search-window transition and the document budget that allowed it."""
    from image_monitor.candidate_save_selection import _database_path
    from image_monitor.watch_gap_recovery import plan_gap_seed
    from image_monitor.watch_runtime import (
        _closed_partial_plan,
        _durable_historical_source,
        _plan_observation,
        gap_seed,
        historical_candidate_count,
    )

    result = latest["result"]
    if (
        scope != MONITOR_SCOPE
        or "gap_bookmark_before" in result["control"]
        or remaining_bridges < 1
    ):
        return None
    before = _preceding_state(queue, scope, previous_state)
    if before is None or load_bookmark(queue, before) is not None:
        return None
    parent = before["latest_scan"]
    parent_plan = _closed_partial_plan(_database_path(queue), queue, before, remaining_bridges - 1)
    expected_limit = 2
    if parent_plan is not None:
        if (
            historical_candidate_count(queue, parent, parent_plan) is None
            or gap_seed(queue, before, planned=parent_plan)
            or _durable_historical_source(queue, parent, parent_plan)
        ):
            return None
        expected_limit = min(4, len(parent["result"]["private_observation"]["pages"]) + 1)
    if limit != expected_limit:
        return None
    observed = result["private_observation"]
    if "gap_frontier_requested" in observed:
        return None
    crossed = observed.get("gap_seed_route") is True
    if crossed != any(page.get("search_pos") is not None for page in observed["pages"]):
        return None
    plan = _plan_observation(
        scope, before, observed, scan_time, limit if limit > 2 else None, allow_seed_crossing=True
    )
    if crossed:
        return plan
    preceding_reason = plan["gap_reason"]
    plan = plan_gap_seed(scope, before, observed["pages"], scan_time, plan)
    return plan if plan["gap_reason"] != preceding_reason else None
