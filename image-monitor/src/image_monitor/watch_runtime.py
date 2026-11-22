"""Bounded live list-discovery trial; never starts native saving or image work."""

import json
import time
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from image_monitor import PUBLIC_VERSION
from image_monitor.artifact_files import _plain_path
from image_monitor.candidate_finish import CandidateFinishError, _read_json, _uuid
from image_monitor.native_probe import write_report
from image_monitor.native_ui import NativeUIError, require_windows
from image_monitor.queue import QueueError, QueueStore
from image_monitor.retry import retry_after
from image_monitor.search_list import build_list_url
from image_monitor.watch_browser import HeadlessWatchBrowser
from image_monitor.watch_diagnosis import diagnose_list_page
from image_monitor.watch_history import (
    MAX_HISTORICAL_PAGE,
    historical_source,
    plan_historical_prefix,
    plan_historical_scan,
)
from image_monitor.watch_lock import WatchRunBusy, watch_run_lock
from image_monitor.watch_planner import (
    WatchPlanError,
    next_poll_at,
    plan_scan,
    plan_verified_page_prefix,
)
from image_monitor.watch_store import (
    MAX_MONITOR_SCAN_PAGES,
    MONITOR_SCOPE,
    WatchScope,
    WatchStore,
    _record,
)

SERVICE_SCOPE = "dcinside"
PARTIAL_COVERAGE_GAPS = frozenset(
    {"anchor_not_reached", "overlap_incomplete", "historical_boundary_changed"}
)
DEFAULT_SCOPE = WatchScope("검색 감시 시험", "normal", "comic_new6", "ai", "search_subject_memo")


class _Clock:
    def now(self):
        return datetime.now(UTC)

    def wait(self, seconds):
        # Short waits keep cancellation responsive; no missed-poll catch-up loop.
        deadline = time.monotonic() + seconds
        while (remaining := deadline - time.monotonic()) > 0:
            time.sleep(min(remaining, 1))


def _stamp(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise QueueError("Watch clock must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _stored_time(value):
    try:
        parsed = datetime.fromisoformat(value)
        _stamp(parsed)
        return parsed
    except (TypeError, ValueError) as error:
        raise QueueError("Stored watch timing is invalid") from error


def _control(state):
    latest = state.get("latest_scan")
    if latest is None:
        if state.get("generation") != 0:
            raise QueueError("Stored watch scan metadata is missing")
        return {}
    result = latest.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("control"), dict):
        raise QueueError("Stored watch control metadata is invalid")
    control = result["control"]
    if type(control.get("blocked")) is not bool:
        raise QueueError("Stored watch block metadata is invalid")
    interval = control.get("interval_seconds")
    if type(interval) is not int or not 60 <= interval <= 300:
        raise QueueError("Stored watch interval is invalid")
    finished = _stored_time(control.get("finished_at"))
    due = _stored_time(control.get("next_eligible_at"))
    if due < next_poll_at(finished, interval_seconds=interval):
        raise QueueError("Stored watch cooldown is invalid")
    return control


def _list_service_blocked(queue):
    if queue.schema_version < 4:
        return False
    broken = queue.connection.execute(
        "SELECT 1 FROM watch_state w LEFT JOIN watch_scans s ON s.scan_id=w.latest_scan_id "
        "WHERE s.scan_id IS NULL OR "
        "w.watch_name!=s.watch_name OR w.gallery_type!=s.gallery_type OR "
        "w.gallery_id!=s.gallery_id OR w.keyword!=s.keyword OR w.search_type!=s.search_type OR "
        "w.generation!=s.generation LIMIT 1"
    ).fetchone()
    if broken is not None:
        raise QueueError("Stored list state does not identify its latest scan")
    latest = "FROM watch_state w JOIN watch_scans s ON s.scan_id=w.latest_scan_id WHERE "
    invalid = queue.connection.execute(
        "SELECT 1 " + latest + "(json_type(s.result_json,'$.control') IS NOT NULL AND "
        "json_type(s.result_json,'$.control')!='object') OR "
        "(json_type(s.result_json,'$.control.blocked') IS NOT NULL AND "
        "json_type(s.result_json,'$.control.blocked') NOT IN ('true','false')) LIMIT 1"
    ).fetchone()
    if invalid is not None:
        raise QueueError("Stored list block metadata is invalid")
    return (
        queue.connection.execute(
            "SELECT 1 " + latest + "json_type(s.result_json,'$.control.blocked')='true' LIMIT 1"
        ).fetchone()
        is not None
    )


def _eligibility(queue, state, now):
    from image_monitor.candidate_save_selection import _database_path, selection_service_blocked
    from image_monitor.candidate_store import detail_service_blocked
    from image_monitor.monitor_save_ledger import batch_service_blocked

    if (
        detail_service_blocked(queue)
        or selection_service_blocked(queue)
        or _list_service_blocked(queue)
        or batch_service_blocked(_database_path(queue))
    ):
        return "blocked", None
    control = _control(state)
    if control.get("blocked") is True:
        return "blocked", None
    due = now
    if control.get("next_eligible_at") is not None:
        due = max(due, _stored_time(control["next_eligible_at"]))
    shared = queue.connection.execute(
        "SELECT not_before FROM service_limits WHERE scope=?", (SERVICE_SCOPE,)
    ).fetchone()
    if shared is not None:
        due = max(due, _stored_time(shared[0]))
    return ("waiting" if due > now else "ready"), due


def _count_candidates(queue, scope=DEFAULT_SCOPE):
    return queue.connection.execute(
        "SELECT COUNT(*) FROM watch_candidates WHERE watch_name=? AND gallery_type=? "
        "AND gallery_id=? AND keyword=? AND search_type=?",
        scope.key(),
    ).fetchone()[0]


def _empty_plan(state, observed_at, reason, scope=DEFAULT_SCOPE):
    checkpoint = state.get("checkpoint") or {
        "anchor_ids": [],
        "observed_at": _stamp(observed_at),
        "source_url": build_list_url(scope.gallery_type, scope.gallery_id, scope.keyword),
    }
    return {
        "observed_at": observed_at,
        "expected_generation": state["generation"],
        "scan_result": {
            "mode": "live_discovery_trial",
            "layout_status": "unverified",
            "synthetic_fixture": False,
            "queue_eligible": False,
            "save_approved": False,
            "observed_at": _stamp(observed_at),
            "complete": False,
            "gap_reason": reason,
        },
        "candidates": [],
        "checkpoint": checkpoint,
        "complete": False,
        "gap_reason": reason,
        "baseline": None,
    }


def _cycle_summary(outcome, plan, persisted, *, follow_up_page_limit=None):
    pages = outcome.get("pages", [])
    exclusions = [row for page in pages for row in page.get("excluded_rows", [])]
    history = plan["scan_result"].get("historical_follow_up")
    boundary = history["boundary_page"] if history else None
    if boundary is None and follow_up_page_limit == MAX_MONITOR_SCAN_PAGES:
        boundary = outcome.get("historical_boundary_page")
    summary = {
        "generation": persisted["generation"],
        "status": outcome["status"],
        "http_status": outcome.get("http_status"),
        "navigation_attempts": len(outcome.get("navigation", [])),
        "page_count": len(pages),
        "page_statuses": [page.get("status") for page in pages],
        "layout_statuses": [page.get("layout_status") for page in pages],
        "page_checks": [
            diagnose_list_page(page, ordinal, historical_boundary_page=boundary)
            for ordinal, page in enumerate(pages, 1)
        ],
        "ordinary_rows": sum(len(page.get("rows", [])) for page in pages),
        "excluded_counts": dict(Counter(row.get("reason", "unknown") for row in exclusions)),
        "excluded_evidence": [
            {
                key: row[key]
                for key in (
                    "row_order",
                    "reason",
                    "number_kind",
                    "link_schemes",
                    "field_counts",
                    "role_flags",
                )
                if key in row
            }
            for row in exclusions[:20]
        ],
        "complete": plan["complete"],
        "gap_reason": plan["gap_reason"],
        "baseline_created": plan["baseline"] is not None,
        "new_candidates": persisted["candidates_added"],
    }
    if follow_up_page_limit is not None:
        summary["follow_up_page_limit"] = follow_up_page_limit
    if history:
        summary["visited_page_numbers"] = [page["page"] for page in pages]
        summary["historical_boundary_page"] = boundary
    return summary


def _observed_page_chain(outcome, max_pages=2):
    """Require one successful document navigation per snapshot, in page order."""
    if not isinstance(outcome, dict):
        return False
    pages = outcome.get("pages", [])
    visits = outcome.get("navigation", [])
    if (
        outcome.get("status") != "observed"
        or not isinstance(pages, list)
        or not 2 <= len(pages) <= max_pages
        or not isinstance(visits, list)
        or len(visits) != len(pages)
        or (max_pages > 2 and outcome.get("retry_after") is not None)
    ):
        return False
    return _matched_documents(pages, visits, follow_up=max_pages > 2) and (
        outcome.get("http_status") == visits[-1]["http_status"]
    )


def _matched_documents(pages, visits, *, follow_up):
    previous = None
    for page, visit in zip(pages, visits, strict=True):
        if not isinstance(page, dict) or not isinstance(visit, dict):
            return False
        http = visit.get("http_status")
        if (
            type(http) is not int
            or not 200 <= http < 300
            or visit.get("url") != page.get("url")
            or page.get("status") != "observed"
            or not page.get("rows")
            or (follow_up and visit.get("retry_after") is not None)
        ):
            return False
        if follow_up:
            try:
                stamp = _stored_time(page.get("observed_at"))
            except QueueError:
                return False
            if previous is not None and stamp < previous:
                return False
            previous = stamp
    return True


def _follow_up_transport(outcome, limit):
    pages, visits = outcome.get("pages"), outcome.get("navigation")
    if (
        not isinstance(pages, list)
        or not isinstance(visits, list)
        or not len(pages) <= len(visits) <= limit
        or any(not isinstance(v, dict) for v in visits)
    ):
        return False
    if outcome["status"] == "observed":
        if not pages or len(pages) != len(visits) or outcome.get("retry_after") is not None:
            return False
    elif len(visits) > len(pages) + 1:
        return False
    if visits and outcome.get("http_status") != visits[-1].get("http_status"):
        return False
    # A failed final document (e.g. HTTP 429) has a navigation but no snapshot.
    return _matched_documents(pages, visits[: len(pages)], follow_up=True)


def _plan_observation(scope, state, outcome, observed_at, follow_up_limit, source=None):
    pages = outcome.get("pages", [])
    if follow_up_limit and not _follow_up_transport(outcome, follow_up_limit):
        return _empty_plan(state, observed_at, "list_navigation_unverified", scope)
    historical = len(pages) >= 3 and pages[2].get("page") != 3
    try:
        if historical:
            if not source or follow_up_limit != MAX_MONITOR_SCAN_PAGES:
                return _empty_plan(state, observed_at, "list_navigation_unverified", scope)
            plan = plan_historical_scan(scope, state, pages, observed_at, source)
        else:
            plan = plan_scan(scope, state, pages, observed_at, allow_verified_live=True)
        if follow_up_limit and plan["complete"] and len(plan["scan_result"]["pages"]) != len(pages):
            return _empty_plan(state, observed_at, "list_navigation_unverified", scope)
        return plan
    except WatchPlanError as error:
        reason = "list_profile_unverified_or_incomplete"
        prefix = None
        if error.issue == "snapshot_layout" and _observed_page_chain(outcome, follow_up_limit or 2):
            if historical:
                prefix = plan_historical_prefix(scope, state, pages, observed_at, source)
            else:
                prefix = plan_verified_page_prefix(scope, state, pages, observed_at)
        plan = prefix or _empty_plan(state, observed_at, reason, scope)
        plan["scan_result"]["planner_issue"] = error.issue
        return plan


def verified_recent_plan(queue, scope, state, *, remaining_bridges=MAX_HISTORICAL_PAGE - 4):
    """Replay the latest verified list chain from the checkpoint that preceded it."""
    latest = state["latest_scan"]
    scope_fields = ("watch_name", "gallery_type", "gallery_id", "keyword", "search_type")
    if not (
        latest
        and state["baseline"] is not None
        and (
            latest["gap_reason"] is None
            if latest["complete"]
            else latest["gap_reason"] in PARTIAL_COVERAGE_GAPS
        )
        and latest["generation"] == state["generation"]
        and tuple(latest.get(key) for key in scope_fields) == scope.key()
    ):
        return None
    result = latest["result"]
    observed = result.get("private_observation", {})
    control = _control(state)
    page_limit = 2
    if "follow_up_page_limit" in control:
        page_limit = control["follow_up_page_limit"]
        if (
            scope != MONITOR_SCOPE
            or type(page_limit) is not int
            or not 3 <= page_limit <= MAX_MONITOR_SCAN_PAGES
        ):
            return None
    if (
        not _observed_page_chain(observed, page_limit)
        or control.get("transport_status") != "observed"
        or control.get("blocked") is not False
        or control.get("http_status") != observed.get("http_status")
    ):
        return None
    pages = observed["pages"]
    # Partial scans preserve the last complete checkpoint. Complete scans replace
    # it. Replay from the actual preceding complete record in both cases.
    previous = queue.connection.execute(
        "SELECT checkpoint_json, observed_at, gap_reason FROM watch_scans WHERE "
        "watch_name=? AND gallery_type=? AND gallery_id=? AND keyword=? AND search_type=? "
        "AND generation<? AND complete=1 ORDER BY generation DESC LIMIT 1",
        (*scope.key(), state["generation"]),
    ).fetchone()
    if previous is None or previous["gap_reason"] is not None:
        return None
    previous_checkpoint = json.loads(previous["checkpoint_json"])
    if (
        not isinstance(previous_checkpoint, dict)
        or _stored_time(previous_checkpoint.get("observed_at"))
        != _stored_time(previous["observed_at"])
        or state["checkpoint"]
        != (latest["checkpoint"] if latest["complete"] else previous_checkpoint)
    ):
        return None
    scan_time = _stored_time(result["observed_at"])
    if scan_time != _stored_time(latest["observed_at"]) or scan_time != _stored_time(
        state["updated_at"]
    ):
        return None
    try:
        previous_state = state | {
            "generation": state["generation"] - 1,
            "checkpoint": previous_checkpoint,
        }
        if "historical_follow_up" in result:
            if page_limit != MAX_MONITOR_SCAN_PAGES or remaining_bridges < 1:
                return None
            marker = result["historical_follow_up"]
            if not isinstance(marker, dict):
                return None
            row = queue.connection.execute(
                "SELECT * FROM watch_scans WHERE watch_name=? AND gallery_type=? "
                "AND gallery_id=? AND keyword=? AND search_type=? AND generation=? AND scan_id=?",
                (*scope.key(), previous_state["generation"], marker.get("source_scan_id")),
            ).fetchone()
            parent = _record(row)
            if parent is None:
                return None
            parent_state = previous_state | {
                "latest_scan": parent,
                "updated_at": parent["observed_at"],
            }
            from image_monitor.candidate_save_selection import _database_path

            parent_plan = _closed_partial_plan(
                _database_path(queue), queue, parent_state, remaining_bridges - 1
            )
            source = _durable_historical_source(queue, parent, parent_plan)
            if not source or source["boundary_page"] != marker.get("boundary_page"):
                return None
            planned = plan_historical_scan(scope, previous_state, pages, scan_time, source)
        else:
            planned = plan_scan(scope, previous_state, pages, scan_time, allow_verified_live=True)
    except WatchPlanError:
        return None
    if (
        planned["complete"] != latest["complete"]
        or planned["gap_reason"] != latest["gap_reason"]
        or len(planned["scan_result"]["pages"]) != len(pages)
        or planned["checkpoint"] != latest["checkpoint"]
        or planned["scan_result"]
        != {k: v for k, v in result.items() if k not in ("control", "private_observation")}
    ):
        return None
    gap = queue.connection.execute(
        "SELECT watch_name,gallery_type,gallery_id,keyword,search_type,reason,generation,"
        "observed_at FROM watch_gaps WHERE scan_id=?",
        (latest["scan_id"],),
    ).fetchone()
    expected_gap = (*scope.key(), latest["gap_reason"], state["generation"], latest["observed_at"])
    if latest["complete"]:
        return planned if gap is None else None
    if gap is None or tuple(gap) != expected_gap:
        return None
    return planned


def matches_partial_coverage_scan(queue, scope, state, report):
    """Match a single-cycle dashboard report against the exact durable scan."""
    planned = verified_recent_plan(queue, scope, state)
    return _matches_partial_summary(queue, state, report, planned)


def _matches_partial_summary(queue, state, report, planned):
    latest = state["latest_scan"]
    if not (
        latest
        and latest["complete"] is False
        and latest["gap_reason"] == report.get("reason")
        and report.get("cycles_completed") == 1
        and report.get("browser_closed") is True
        and report.get("error_type") is None
    ):
        return False
    if planned is None:
        return False
    added = queue.connection.execute(
        "SELECT COUNT(*) FROM watch_candidates WHERE first_scan_id=?", (latest["scan_id"],)
    ).fetchone()[0]
    summary = _cycle_summary(
        latest["result"]["private_observation"],
        planned,
        {"generation": state["generation"], "candidates_added": added},
        follow_up_page_limit=latest["result"]["control"].get("follow_up_page_limit"),
    )
    return (
        report.get("cycles") == [summary]
        and report.get("new_candidates") == added
        and _stored_time(report.get("next_eligible_at_local"))
        == _stored_time(latest["result"]["control"]["next_eligible_at"])
    )


def share_watch_report(report):
    # List titles/authors, source URLs/cursors and local state paths stay private.
    keys = (
        "schema_version",
        "program_version",
        "status",
        "mode",
        "discovery_only",
        "images_saved",
        "image_jobs_created",
        "browser",
        "browser_version",
        "browser_closed",
        "last_stage",
        "error_type",
        "reason",
        "recent_pages_verified",
        "cycles_requested",
        "cycles_completed",
        "interval_seconds",
        "cycles",
        "candidate_count",
        "baseline_initialized",
        "new_candidates",
        "next_eligible_at_local",
    )
    return {key: report[key] for key in keys if key in report}


def confirmed_monitor_scan(database: Path, latest: dict, *, expected_report=None) -> bool:
    """Verify browser cleanup for this exact monitor scan using its final local report."""
    if not isinstance(latest, dict) or not isinstance(latest.get("result"), dict):
        return False
    fields = ("watch_name", "gallery_type", "gallery_id", "keyword", "search_type")
    control = latest["result"].get("control")
    if not isinstance(control, dict) or tuple(latest.get(k) for k in fields) != MONITOR_SCOPE.key():
        return False
    run_id = control.get("monitor_run_id")
    if not _uuid(run_id) or not _uuid(latest.get("scan_id")):
        return False
    try:
        report = _read_json(database.parent / "runs" / run_id / "report.json")
        if expected_report is not None and report != expected_report:
            return False
        if not isinstance(report, dict) or report.get("closed_monitor_scan") != {
            "run_id": run_id,
            "scan_id": latest["scan_id"],
            "scope": list(MONITOR_SCOPE.key()),
        }:
            return False
        cycles = report.get("cycles")
        complete, gap = latest["complete"], latest["gap_reason"]
        return (
            report.get("mode") == "bounded_live_list_discovery"
            and report.get("discovery_only") is True
            and report.get("browser_closed") is True
            and report.get("error_type", "missing") is None
            and (
                complete is True
                and gap is None
                or complete is False
                and gap in PARTIAL_COVERAGE_GAPS
            )
            and report.get("status")
            == ("watch_test_completed" if complete else "watch_test_partial")
            and report.get("reason") == gap
            and isinstance(cycles, list)
            and 1 <= len(cycles) <= 2
            and report.get("cycles_completed") == len(cycles)
            and isinstance(cycles[-1], dict)
            and cycles[-1].get("generation") == latest["generation"]
            and _stored_time(report.get("next_eligible_at_local"))
            == _stored_time(control.get("next_eligible_at"))
        )
    except (OSError, ValueError, CandidateFinishError, RecursionError):
        return False


def _closed_partial_plan(database, queue, state, remaining_bridges):
    """Bind the partial plan to its closed Chrome receipt at the given generation."""
    latest = state.get("latest_scan")
    if not latest or latest.get("gap_reason") not in PARTIAL_COVERAGE_GAPS:
        return None
    try:
        run_id = latest["result"]["control"]["monitor_run_id"]
        if not _uuid(run_id):
            return None
        receipt = _read_json(database.parent / "runs" / run_id / "report.json")
        if (
            confirmed_monitor_scan(database, latest, expected_report=receipt)
            and receipt.get("browser") == "chrome"
            and receipt.get("recent_pages_verified") is True
            and receipt.get("cycles_requested") == 1
        ):
            planned = verified_recent_plan(
                queue, MONITOR_SCOPE, state, remaining_bridges=remaining_bridges
            )
            if _matches_partial_summary(queue, state, receipt, planned):
                return planned
    except (OSError, ValueError, TypeError, KeyError, QueueError, CandidateFinishError):
        pass
    return None


def monitor_scan_policy(database, queue, state):
    """Determine both the request limit and any verified historical boundary."""
    if state.get("baseline") is None:
        return 1, None
    planned = _closed_partial_plan(database, queue, state, MAX_HISTORICAL_PAGE - 4)
    if planned is None:
        return 2, None
    latest = state["latest_scan"]
    page_count = len(latest["result"]["private_observation"]["pages"])
    source = _durable_historical_source(queue, latest, planned)
    return min(page_count + 1, MAX_MONITOR_SCAN_PAGES), source


def _durable_historical_source(queue, latest, planned):
    if not planned:
        return None
    source = historical_source(latest)
    if source is None:
        return None
    # A later real scan can refresh last_seen, but the original identity and
    # first discovery must still exist for *every* post carried across the gap.
    candidates = {row["post_id"]: row["post_url"] for row in planned["candidates"]}
    rows = queue.connection.execute(
        "SELECT c.post_id,c.post_url FROM watch_candidates c JOIN watch_scans s ON "
        "s.scan_id=c.first_scan_id AND s.observed_at=c.first_seen_at AND "
        "(s.watch_name,s.gallery_type,s.gallery_id,s.keyword,s.search_type)="
        "(c.watch_name,c.gallery_type,c.gallery_id,c.keyword,c.search_type) "
        "WHERE (c.watch_name,c.gallery_type,c.gallery_id,c.keyword,c.search_type)=(?,?,?,?,?) "
        "AND s.generation<=? AND c.post_id IN (SELECT value FROM json_each(?))",
        (*MONITOR_SCOPE.key(), latest["generation"], json.dumps(list(candidates))),
    )
    return source if dict(rows) == candidates else None


def run_watch_trial(
    work_root: Path,
    browser="chrome",
    *,
    cycles=2,
    interval_seconds=60,
    backend_factory=HeadlessWatchBrowser,
    clock=None,
    scope=DEFAULT_SCOPE,
    should_stop=None,
    follow_up_gaps=False,
):
    require_windows()
    if browser not in {"chrome", "edge"} or type(cycles) is not int or not 1 <= cycles <= 2:
        raise NativeUIError("Choose a supported browser and one or two watch cycles")
    if type(interval_seconds) is not int or not 60 <= interval_seconds <= 300:
        raise NativeUIError("The watch trial interval must be an integer from 60 to 300 seconds")
    try:
        reviewed_scope = (
            isinstance(scope, WatchScope) and scope.key()[1:] == DEFAULT_SCOPE.key()[1:]
        )
    except QueueError:
        reviewed_scope = False
    if not reviewed_scope:
        raise NativeUIError("The watch trial requires the reviewed gallery and search scope")
    if type(follow_up_gaps) is not bool or (
        follow_up_gaps and (scope != MONITOR_SCOPE or browser != "chrome" or cycles != 1)
    ):
        raise NativeUIError("List gap follow-up requires one automatic Chrome monitor cycle")
    if should_stop is not None and not callable(should_stop):
        raise NativeUIError("The watch stop condition must be callable")
    clock = clock or _Clock()
    next_poll_at(clock.now(), interval_seconds=interval_seconds)
    base = Path(work_root).resolve()
    if str(base).startswith("\\\\"):
        raise NativeUIError("A local watch state directory is required")
    _plain_path(base)
    base.mkdir(parents=True, exist_ok=True)
    database = _plain_path(base / "watch.sqlite")
    run_directory = base / "runs" / uuid.uuid4().hex
    run_directory.mkdir(parents=True)
    report_path = run_directory / "report.json"
    report = {
        "schema_version": 1,
        "program_version": PUBLIC_VERSION,
        "mode": "bounded_live_list_discovery",
        "status": "watch_test_failed",
        "discovery_only": True,
        "images_saved": False,
        "image_jobs_created": 0,
        "browser": browser,
        "browser_closed": True,
        "last_stage": "eligibility_check",
        "error_type": None,
        "cycles_requested": cycles,
        "cycles_completed": 0,
        "interval_seconds": interval_seconds,
        "cycles": [],
        "new_candidates": 0,
    }
    backend = None
    try:

        def stopped():
            if should_stop is None:
                return False
            value = should_stop()
            if type(value) is not bool:
                raise QueueError("The watch stop condition must return a boolean")
            return value

        with watch_run_lock(database, DEFAULT_SCOPE), QueueStore(database) as queue:
            store = WatchStore(queue)
            if queue.summary()["jobs"]:
                raise QueueError("The watch trial requires its separate discovery database")
            state = store.get_state(scope)
            eligibility, due = _eligibility(queue, state, clock.now())
            if stopped():
                report.update(status="watch_test_cancelled", reason="requested_stop")
            elif eligibility == "blocked":
                report.update(reason="access_block_requires_review", last_stage="blocked")
            elif eligibility == "waiting":
                report.update(status="watch_waiting", reason="persisted_cooldown")
                report["next_eligible_at_local"] = due.astimezone(
                    ZoneInfo("Asia/Seoul")
                ).isoformat()
            else:
                backend_options = {"now": clock.now}
                if should_stop is not None:
                    backend_options["should_stop"] = should_stop
                backend = backend_factory(browser, **backend_options)
                with backend:
                    report["browser_closed"] = False
                    report["browser_version"] = backend.browser_version
                    for index in range(cycles):
                        state = store.get_state(scope)
                        if stopped():
                            report.update(status="watch_test_cancelled", reason="requested_stop")
                            break
                        eligibility, due = _eligibility(queue, state, clock.now())
                        if eligibility == "blocked":
                            report.update(
                                reason="access_block_requires_review", last_stage="blocked"
                            )
                            break
                        if eligibility == "waiting":
                            remaining = (due - clock.now()).total_seconds()
                            if index == 0 or remaining > interval_seconds:
                                report.update(status="watch_waiting", reason="persisted_cooldown")
                                break
                            report["last_stage"] = "waiting_between_cycles"
                            write_report(report_path, report)
                            clock.wait(max(0, remaining))
                            eligibility, due = _eligibility(
                                queue, store.get_state(scope), clock.now()
                            )
                            if eligibility != "ready":
                                report.update(status="watch_waiting", reason="cooldown_not_elapsed")
                                break
                        if stopped():
                            report.update(status="watch_test_cancelled", reason="requested_stop")
                            break
                        observed_at = clock.now()
                        report["last_stage"] = "list_observation"
                        page_limit = 1 if state["baseline"] is None else 2
                        source = None
                        if follow_up_gaps:
                            page_limit, source = monitor_scan_policy(database, queue, state)
                        follow_up_limit = page_limit if page_limit > 2 else None
                        follow_up_state = state | {"historical_source": source} if source else state
                        # Commit before navigation so cancellation or a process failure
                        # cannot immediately repeat the same request on the next run.
                        queue.defer_service(
                            SERVICE_SCOPE,
                            next_poll_at(observed_at, interval_seconds=interval_seconds),
                        )
                        try:
                            outcome = backend.scan(
                                scope,
                                observed_at,
                                max_pages=page_limit,
                                **({"follow_up_state": follow_up_state} if follow_up_limit else {}),
                            )
                        finally:
                            finished_at = clock.now()
                            queue.defer_service(
                                SERVICE_SCOPE,
                                next_poll_at(finished_at, interval_seconds=interval_seconds),
                            )
                        plan = _plan_observation(
                            scope, state, outcome, observed_at, follow_up_limit, source
                        )
                        if plan["scan_result"].get("historical_follow_up") is not None:
                            current = store.get_state(scope)
                            if (
                                current["generation"] != state["generation"]
                                or monitor_scan_policy(database, queue, current)[1] != source
                            ):
                                plan = _empty_plan(
                                    state, observed_at, "historical_source_unverified", scope
                                )
                        cancelled = outcome["status"] == "cancelled" or stopped()
                        failed = outcome["status"] != "observed" and not cancelled
                        if failed or cancelled:
                            reason = (
                                "requested_stop"
                                if cancelled
                                else "list_transport_or_inspection_failure"
                            )
                            plan.update(complete=False, gap_reason=reason, baseline=None)
                            plan["scan_result"].update(complete=False, gap_reason=reason)
                        next_at = next_poll_at(finished_at, interval_seconds=interval_seconds)
                        status = outcome.get("http_status")
                        blocked = status in {401, 403, 404, 410}
                        if status in {429, 503}:
                            try:
                                server_due = retry_after(outcome.get("retry_after"), finished_at)
                            except ValueError:
                                server_due = None
                            if server_due is not None:
                                next_at = max(next_at, server_due)
                            queue.defer_service(SERVICE_SCOPE, next_at)
                        plan["scan_result"]["control"] = {
                            "finished_at": _stamp(finished_at),
                            "next_eligible_at": _stamp(next_at),
                            "interval_seconds": interval_seconds,
                            "blocked": blocked,
                            "http_status": status,
                            "transport_status": outcome["status"],
                        }
                        if scope == MONITOR_SCOPE:
                            plan["scan_result"]["control"]["monitor_run_id"] = run_directory.name
                        if follow_up_limit is not None:
                            plan["scan_result"]["control"]["follow_up_page_limit"] = follow_up_limit
                        plan["scan_result"]["private_observation"] = outcome
                        report["last_stage"] = "persist_scan"
                        persisted = store.persist_scan(scope, **plan)
                        summary = _cycle_summary(
                            outcome, plan, persisted, follow_up_page_limit=follow_up_limit
                        )
                        report["cycles"].append(summary)
                        report["cycles_completed"] += 1
                        report["new_candidates"] += persisted["candidates_added"]
                        report["next_eligible_at_local"] = next_at.astimezone(
                            ZoneInfo("Asia/Seoul")
                        ).isoformat()
                        write_report(report_path, report)
                        if cancelled:
                            report.update(
                                status="watch_test_cancelled",
                                reason="requested_stop",
                                error_type=None,
                            )
                            break
                        if failed:
                            report.update(
                                status="watch_test_failed",
                                reason="access_block_requires_review" if blocked else reason,
                                error_type=outcome.get("error_type"),
                            )
                            break
                        if not plan["complete"]:
                            report.update(status="watch_test_partial", reason=plan["gap_reason"])
                            break
                        if index + 1 == cycles:
                            report.update(status="watch_test_completed", last_stage="complete")
                report["browser_closed"] = backend.browser_closed
            state = store.get_state(scope)
            report["baseline_initialized"] = state["baseline"] is not None
            report["candidate_count"] = _count_candidates(queue, scope)
            if queue.summary()["jobs"]:
                # The separate watch DB must never silently become an image worker.
                report.update(
                    status="watch_test_failed", reason="unexpected_image_jobs_in_watch_db"
                )
            elif (
                report["status"] == "watch_test_partial"
                and report["browser_closed"] is True
                and state["generation"] == report["cycles"][-1]["generation"]
                and verified_recent_plan(queue, scope, state) is not None
            ):
                report["recent_pages_verified"] = True
            if (
                scope == MONITOR_SCOPE
                and report["browser_closed"] is True
                and (
                    report["status"] == "watch_test_completed"
                    or report.get("recent_pages_verified") is True
                )
            ):
                # Only the final report, written after leaving the owned browser, can
                # certify this scan. A process lost after the DB commit leaves no proof.
                report["closed_monitor_scan"] = {
                    "run_id": run_directory.name,
                    "scan_id": persisted["scan_id"],
                    "scope": list(scope.key()),
                }
    except WatchRunBusy:
        report.update(status="watch_busy", reason="another_scan_owns_this_scope")
    except KeyboardInterrupt:
        report.update(
            status="watch_test_cancelled", error_type="KeyboardInterrupt", reason="cancelled"
        )
    except Exception as error:
        report.update(
            status="watch_test_failed",
            error_type=type(error).__name__,
            reason="watch_trial_stopped",
        )
    finally:
        if backend is not None:
            report["browser_closed"] = backend.browser_closed
            if not backend.browser_closed and report["status"] == "watch_test_completed":
                report.update(status="watch_test_failed", reason="owned_browser_not_closed")
        report["report_path"] = str(report_path)
        write_report(report_path, report)
    return report
