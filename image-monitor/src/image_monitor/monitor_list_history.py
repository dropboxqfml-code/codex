"""Read the previous two monitor list checks from their original local evidence."""

import json
import re
import sqlite3
from pathlib import Path

from image_monitor.artifact_files import _plain_path
from image_monitor.candidate_finish import CandidateFinishError, _read_json, _same_json, _uuid
from image_monitor.queue import QueueStore
from image_monitor.watch_history import historical_route_details
from image_monitor.watch_images_check import _read_mode, _UnstableDatabase
from image_monitor.watch_lock import watch_run_lock
from image_monitor.watch_runtime import (
    DEFAULT_SCOPE,
    _cycle_summary,
    _stored_time,
    confirmed_monitor_scan,
    historical_candidate_count,
    monitor_scan_policy,
    verified_recent_plan,
)
from image_monitor.watch_store import (
    _SCOPE_WHERE,
    MAX_MONITOR_SCAN_PAGES,
    MONITOR_SCOPE,
    WatchStore,
)

_UNAVAILABLE = (
    OSError,
    ValueError,
    TypeError,
    KeyError,
    IndexError,
    AttributeError,
    OverflowError,
    RecursionError,
    sqlite3.Error,
    CandidateFinishError,
    _UnstableDatabase,
)


def _route_receipt(receipt):
    # alpha.9 predates the capability field. Earlier releases may supply a
    # genuine four-page parent but never chose a historical route themselves.
    if "historical_route_schema" not in receipt:
        return receipt.get("program_version") == "0.5.0-alpha.9"
    schema = receipt["historical_route_schema"]
    version = receipt.get("program_version")
    if type(schema) is not int or schema != 1 or not isinstance(version, str) or len(version) > 64:
        return False
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:-(alpha|beta|rc)\.([1-9]\d*))?", version, re.ASCII)
    if not match:
        return False
    release = tuple(int(part) for part in match.group(1, 2, 3))
    if release != (0, 5, 0):
        return release > (0, 5, 0)
    return match[4] != "alpha" or int(match[5]) >= 10


def _state_at(queue, current, scan):
    # A partial scan stores a proposed checkpoint. Only an earlier *complete*
    # scan supplies the coverage checkpoint that the running program used.
    row = queue.connection.execute(
        f"SELECT checkpoint_json FROM watch_scans WHERE {_SCOPE_WHERE} "
        "AND generation<=? AND complete=1 ORDER BY generation DESC LIMIT 1",
        (*MONITOR_SCOPE.key(), scan["generation"]),
    ).fetchone()
    return current | {
        "latest_scan": scan,
        "generation": scan["generation"],
        "updated_at": scan["observed_at"],
        "checkpoint": json.loads(row[0]) if row else None,
    }


def _historical_check(database, queue, before, after):
    latest, parent = after["latest_scan"], before["latest_scan"]
    control = latest["result"]["control"]
    if (
        latest["generation"] != parent["generation"] + 1
        or type(control.get("follow_up_page_limit")) is not int
        or control["follow_up_page_limit"] != MAX_MONITOR_SCAN_PAGES
        or _stored_time(latest["observed_at"])
        < _stored_time(parent["result"]["control"]["next_eligible_at"])
        or not _uuid(control.get("monitor_run_id"))
    ):
        return None
    receipt = _read_json(database.parent / "runs" / control["monitor_run_id"] / "report.json")
    if (
        not _route_receipt(receipt)
        or type(receipt.get("schema_version")) is not int
        or receipt["schema_version"] != 1
        or receipt.get("browser") != "chrome"
        or type(receipt.get("cycles_requested")) is not int
        or receipt.get("cycles_requested") != 1
        or type(receipt.get("cycles_completed")) is not int
        or receipt["cycles_completed"] != 1
        or (latest["complete"] is False and receipt.get("recent_pages_verified") is not True)
        or not confirmed_monitor_scan(database, latest, expected_report=receipt)
    ):
        return None
    limit, source = monitor_scan_policy(database, queue, before)
    if source is None or limit != MAX_MONITOR_SCAN_PAGES:
        return None
    plan = verified_recent_plan(queue, MONITOR_SCOPE, after)
    if plan is None:
        return None
    added = historical_candidate_count(queue, latest, plan)
    original_count = queue.connection.execute(
        "SELECT COUNT(*) FROM watch_candidates WHERE first_scan_id=?", (latest["scan_id"],)
    ).fetchone()[0]
    if (
        added is None
        or added != original_count
        or not _same_json(added, receipt.get("new_candidates"))
    ):
        return None
    observed = latest["result"]["private_observation"]
    expected = _cycle_summary(
        observed,
        plan,
        {"generation": latest["generation"], "candidates_added": added},
        follow_up_page_limit=limit,
    )
    if not _same_json(receipt.get("cycles"), [expected]):
        return None
    details = historical_route_details(before, latest, source)
    if details["historical_reason"] == "route_evidence_unverified":
        return None
    pages = [page["page"] for page in observed["pages"]]
    return {
        "status": "complete" if latest["complete"] else "partial",
        "reason": latest["gap_reason"],
        "pages_checked": len(pages),
        "page_limit": limit,
        "visited_page_numbers": pages,
        **details,
    }


def previous_list_checks(watch_root):
    """Diagnose individually confirmed historical turns among the latest two generations."""
    try:
        database = _plain_path(Path(watch_root) / "watch.sqlite")
        if database.drive.startswith("\\\\") or not database.is_file():
            return []
        with (
            watch_run_lock(database, DEFAULT_SCOPE, existing_only=True),
            _read_mode(database) as immutable,
            QueueStore(database, read_only=True, immutable=immutable) as queue,
        ):
            queue.connection.execute("BEGIN")
            summary = queue.summary()
            if summary["jobs"] or summary["posts"]:
                return []
            store = WatchStore(queue)
            current = store.get_state(MONITOR_SCOPE)
            if current["baseline"] is None:
                return []
            scans = store.list_scans(MONITOR_SCOPE, limit=3)
            if not scans or scans[0] != current["latest_scan"]:
                return []
            baseline = queue.connection.execute(
                f"SELECT checkpoint_json FROM watch_scans WHERE {_SCOPE_WHERE} "
                "AND complete=1 ORDER BY generation LIMIT 1",
                MONITOR_SCOPE.key(),
            ).fetchone()
            if not baseline or current["baseline"] != json.loads(baseline[0]) | {
                "mode": "new",
                "requires_published_at_filter": True,
            }:
                return []
            states = [_state_at(queue, current, scan) for scan in reversed(scans)]
            if states[-1] != current:
                return []
            checks = []
            for before, after in zip(states, states[1:], strict=False):
                if after["generation"] < current["generation"] - 1:
                    continue
                try:
                    check = _historical_check(database, queue, before, after)
                except _UNAVAILABLE:
                    continue
                if check is not None:
                    checks.append(check)
            return checks
    except _UNAVAILABLE:
        return []
