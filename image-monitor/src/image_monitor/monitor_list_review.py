"""Explain a stopped list check from its own local scan and final Chrome report."""

import sqlite3
from pathlib import Path

from image_monitor.artifact_files import _plain_path
from image_monitor.candidate_finish import CandidateFinishError, _read_json, _same_json, _uuid
from image_monitor.candidate_save_selection import _database_path
from image_monitor.monitor_diagnosis import MAX_DIAGNOSIS_BYTES
from image_monitor.monitor_gap_report import public_recovery_pages
from image_monitor.queue import QueueStore
from image_monitor.watch_diagnosis import (
    _TRANSPORT,
    _TRANSPORT_ERRORS,
    DIAGNOSIS_REASONS,
    PLANNER_ISSUES,
    _public_page,
)
from image_monitor.watch_images_check import _read_mode, _UnstableDatabase
from image_monitor.watch_lock import watch_list_lock
from image_monitor.watch_planner import WatchPlanError, _list_url, _scope
from image_monitor.watch_runtime import (
    DEFAULT_SCOPE,
    PARTIAL_COVERAGE_GAPS,
    _control,
    _cycle_summary,
    _stored_time,
    confirmed_monitor_scan,
)
from image_monitor.watch_store import _SCOPE_WHERE, MAX_MONITOR_SCAN_PAGES, MONITOR_SCOPE, _record

_STAGES = frozenset(
    """preflight baseline_check cursor_check browser_scan browser_close watch_result
    receipt_check scan_record route_check transport_check planner_check candidate_check
    partial_check queue_check stored_scan""".split()
)
_WATCH_STATUS = {"watch_test_completed", "watch_test_partial", "watch_test_failed"}
_WATCH_STAGE = {
    "eligibility_check",
    "list_observation",
    "persist_scan",
    "complete",
    "waiting_between_cycles",
    "blocked",
}
_ERROR_TYPES = {
    "Error",
    "TimeoutError",
    "ConnectionError",
    "HTTPStatusError",
    "HTTPError",
    "DCSnapshotError",
    "WatchBrowserError",
    "WatchPlanError",
    "QueueError",
    "ValueError",
    "OSError",
    "PermissionError",
    "RuntimeError",
    "NativeUIError",
}
_GAPS = (
    DIAGNOSIS_REASONS
    | PARTIAL_COVERAGE_GAPS
    | {
        "list_navigation_unverified",
        "historical_source_unverified",
        "empty_baseline_requires_end",
        "pagination_cycle",
        "max_pages",
    }
)
_SCOPE_FIELDS = ("watch_name", "gallery_type", "gallery_id", "keyword", "search_type")
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


def public_list_review(value):
    """Allow only bounded labels/counts when a review is displayed or reloaded."""
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("stage"), str)
        or value["stage"] not in _STAGES
    ):
        return None
    result = {"stage": value["stage"]}
    if value.get("evidence") == "worker_report":
        watch_stage = value.get("watch_stage")
        if (
            value["stage"] == "watch_result"
            and value.get("watch_status") == "watch_test_failed"
            and isinstance(watch_stage, str)
            and watch_stage in _WATCH_STAGE
        ):
            result.update(
                evidence="worker_report", watch_status="watch_test_failed", watch_stage=watch_stage
            )
            error = value.get("error_type")
            if isinstance(error, str) and error in _ERROR_TYPES:
                result["error_type"] = error
        return result
    if value.get("evidence") != "committed_scan":
        return result
    result["evidence"] = "committed_scan"
    for field, allowed in (
        ("watch_status", _WATCH_STATUS),
        ("watch_stage", _WATCH_STAGE),
        ("transport", _TRANSPORT),
        ("error_type", _ERROR_TYPES),
        ("error_code", _TRANSPORT_ERRORS),
        ("gap_reason", _GAPS),
        ("planner_issue", PLANNER_ISSUES),
    ):
        item = value.get(field)
        if isinstance(item, str) and item in allowed:
            result[field] = item
    http = value.get("http_status")
    if type(http) is int and 100 <= http <= 599:
        result["http_status"] = http
    numbers = public_recovery_pages(value.get("visited_page_numbers"))
    if numbers is not None:
        result["visited_page_numbers"] = numbers
    pages = value.get("pages")
    if isinstance(pages, list) and len(pages) <= MAX_MONITOR_SCAN_PAGES:
        result["pages"] = []
        for index, page in enumerate(pages):
            if not isinstance(page, dict):
                return {"stage": value["stage"]}
            number = numbers[index] if numbers and index < len(numbers) else None
            fields = _public_page(page, number)
            result["pages"].append(
                {
                    key: fields[key]
                    for key in (
                        "page",
                        "status",
                        "layout_status",
                        "profile_issue",
                        "ordinary_rows",
                        "excluded_rows",
                        "unsafe_exclusions",
                    )
                    if fields[key] is not None
                }
            )
    return result


def _route_numbers(outcome):
    visits = outcome["navigation"]
    expected = _scope(MONITOR_SCOPE)
    try:
        numbers = [_list_url(visit["url"], expected)["page"] for visit in visits]
        for page, visit in zip(outcome["pages"], visits, strict=False):
            if page.get("url") != visit.get("url"):
                return None
        return public_recovery_pages(numbers)
    except (KeyError, TypeError, WatchPlanError):
        return None


def _bound_review(database, queue, scan, raw, stage):
    result = scan["result"]
    control = _control({"latest_scan": scan})
    run_id = control.get("monitor_run_id")
    if (
        tuple(scan.get(k) for k in _SCOPE_FIELDS) != MONITOR_SCOPE.key()
        or not _uuid(run_id)
        or not _uuid(scan.get("scan_id"))
        or type(scan["generation"]) is not int
        or scan["generation"] < 1
        or result.get("complete") is not scan["complete"]
        or result.get("gap_reason") != scan["gap_reason"]
        or _stored_time(result["observed_at"]) != _stored_time(scan["observed_at"])
        or _stored_time(scan["observed_at"]) > _stored_time(control["finished_at"])
    ):
        return None
    if scan["generation"] > 1:
        parent = queue.connection.execute(
            "SELECT json_extract(result_json,'$.control.next_eligible_at') FROM watch_scans "
            f"WHERE {_SCOPE_WHERE} AND generation=?",
            (*MONITOR_SCOPE.key(), scan["generation"] - 1),
        ).fetchone()
        if parent is None or _stored_time(scan["observed_at"]) < _stored_time(parent[0]):
            return None
    path = database.parent / "runs" / run_id / "report.json"
    report = _read_json(path)
    if raw is not None and not _same_json(raw, report):
        return None
    status = report.get("status")
    if (
        not _same_json(report.get("schema_version"), 1)
        or report.get("mode") != "bounded_live_list_discovery"
        or report.get("discovery_only") is not True
        or report.get("browser") != "chrome"
        or report.get("browser_closed") is not True
        or not isinstance(report.get("report_path"), str)
        or Path(report["report_path"]) != path
        or not isinstance(status, str)
        or status not in _WATCH_STATUS
        or not _same_json(report.get("cycles_requested"), 1)
        or not _same_json(report.get("cycles_completed"), 1)
        or not _same_json(report.get("interval_seconds"), control["interval_seconds"])
        or _stored_time(report["next_eligible_at_local"])
        != _stored_time(control["next_eligible_at"])
    ):
        return None
    # Failed alpha.12 reports have no coverage receipt. Their run-specific final
    # report still records the committed generation, full cycle summary and deadline.
    if scan["complete"] or "closed_monitor_scan" in report:
        if not confirmed_monitor_scan(database, scan, expected_report=report):
            return None
    elif (
        status not in {"watch_test_partial", "watch_test_failed"}
        or report.get("reason") != scan["gap_reason"]
    ):
        return None
    if (
        raw is None
        and status == "watch_test_partial"
        and report.get("recent_pages_verified") is True
    ):
        return None
    outcome = result["private_observation"]
    pages, visits = outcome["pages"], outcome["navigation"]
    if (
        not isinstance(pages, list)
        or not isinstance(visits, list)
        or not len(pages) <= len(visits) <= MAX_MONITOR_SCAN_PAGES
        or control.get("transport_status") != outcome.get("status")
        or not _same_json(control.get("http_status"), outcome.get("http_status"))
    ):
        return None
    if status == "watch_test_failed" and (
        outcome.get("status") not in {"network_error", "http_error", "inspection_error"}
        or not _same_json(report.get("error_type"), outcome.get("error_type"))
    ):
        return None
    if not scan["complete"]:
        gap = queue.connection.execute(
            f"SELECT 1 FROM watch_gaps WHERE {_SCOPE_WHERE} "
            "AND scan_id=? AND generation=? AND observed_at=? AND reason=?",
            (
                *MONITOR_SCOPE.key(),
                scan["scan_id"],
                scan["generation"],
                scan["observed_at"],
                scan["gap_reason"],
            ),
        ).fetchone()
        if gap is None:
            return None
    added = queue.connection.execute(
        "SELECT count(*) FROM watch_candidates WHERE first_scan_id=?", (scan["scan_id"],)
    ).fetchone()[0]
    baseline_created = (
        scan["complete"]
        and queue.connection.execute(
            f"SELECT 1 FROM watch_scans WHERE {_SCOPE_WHERE} "
            "AND generation<? AND complete=1 LIMIT 1",
            (*MONITOR_SCOPE.key(), scan["generation"]),
        ).fetchone()
        is None
    )
    summary = _cycle_summary(
        outcome,
        {
            "complete": scan["complete"],
            "gap_reason": scan["gap_reason"],
            "scan_result": result,
            "baseline": {} if baseline_created else None,
        },
        {"generation": scan["generation"], "candidates_added": added},
        follow_up_page_limit=control.get("follow_up_page_limit"),
    )
    if not _same_json(report.get("cycles"), [summary]) or not _same_json(
        report.get("new_candidates"), added
    ):
        return None
    return public_list_review(
        {
            "stage": stage,
            "evidence": "committed_scan",
            "watch_status": status,
            "watch_stage": report.get("last_stage"),
            "transport": outcome.get("status"),
            "error_type": report.get("error_type"),
            "error_code": outcome.get("error_code"),
            "http_status": outcome.get("http_status"),
            "gap_reason": scan["gap_reason"],
            "planner_issue": result.get("planner_issue"),
            "visited_page_numbers": _route_numbers(outcome),
            "pages": summary["page_checks"],
        }
    )


def _latest_scan(queue):
    # Bind the current state, scan, scope, generation and timestamp in SQLite before
    # parsing private JSON. A later successful generation supersedes an earlier stop.
    row = queue.connection.execute(
        f"SELECT * FROM watch_scans WHERE {_SCOPE_WHERE} "
        "AND (scan_id,generation,observed_at) IN "
        f"(SELECT latest_scan_id,generation,updated_at FROM watch_state WHERE {_SCOPE_WHERE}) "
        "AND length(CAST(result_json AS BLOB))<=? AND length(CAST(checkpoint_json AS BLOB))<=?",
        (*MONITOR_SCOPE.key(), *MONITOR_SCOPE.key(), MAX_DIAGNOSIS_BYTES, MAX_DIAGNOSIS_BYTES),
    ).fetchone()
    return _record(row)


def current_list_review(database, queue, before, after, raw, *, stage):
    """Explain this invocation while the caller holds the list lease."""
    try:
        if _database_path(queue) != database or not isinstance(raw, dict):
            return None
        scan = _latest_scan(queue)
        if (
            not scan
            or before["generation"] + 1 != after["generation"]
            or scan["generation"] != after["generation"]
            or scan["observed_at"] != after["updated_at"]
            or not _same_json(scan, after["latest_scan"])
        ):
            return None
        if before["generation"] > 0:
            parent = before["latest_scan"]
            matched = queue.connection.execute(
                f"SELECT 1 FROM watch_scans WHERE {_SCOPE_WHERE} "
                "AND scan_id=? AND generation=? AND observed_at=?",
                (
                    *MONITOR_SCOPE.key(),
                    parent["scan_id"],
                    before["generation"],
                    before["updated_at"],
                ),
            ).fetchone()
            if matched is None:
                return None
        return _bound_review(database, queue, scan, raw, stage)
    except _UNAVAILABLE:
        return None


def previous_list_review(watch_root):
    """Explain the latest committed generation only when it records a review-compatible stop."""
    try:
        database = _plain_path(Path(watch_root).absolute() / "watch.sqlite")
        if database.drive.startswith("\\\\") or not database.is_file():
            return None
        with (
            watch_list_lock(database, DEFAULT_SCOPE, existing_only=True),
            _read_mode(database) as immutable,
            QueueStore(database, read_only=True, immutable=immutable) as queue,
        ):
            queue.connection.execute("BEGIN")
            if queue.schema_version < 4:
                return None
            counts = queue.summary()
            if counts["jobs"] or counts["posts"]:
                return None
            scan = _latest_scan(queue)
            if not scan or scan["complete"] or scan["gap_reason"] == "requested_stop":
                return None
            result = _bound_review(database, queue, scan, None, "stored_scan")
            if result is None or result.get("http_status") in (401, 403, 404, 410, 429, 503):
                return None
            if result.get("watch_status") == "watch_test_failed":
                result["stage"] = "watch_result"
            return result
    except _UNAVAILABLE:
        return None
