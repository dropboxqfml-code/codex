"""Bounded live list-discovery trial; never starts native saving or image work."""

import time
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from image_monitor import PUBLIC_VERSION
from image_monitor.artifact_files import _plain_path
from image_monitor.native_probe import write_report
from image_monitor.native_ui import NativeUIError, require_windows
from image_monitor.queue import QueueError, QueueStore
from image_monitor.retry import retry_after
from image_monitor.search_list import build_list_url
from image_monitor.watch_browser import HeadlessWatchBrowser
from image_monitor.watch_diagnosis import diagnose_list_page
from image_monitor.watch_lock import WatchRunBusy, watch_run_lock
from image_monitor.watch_planner import (
    WatchPlanError,
    next_poll_at,
    plan_scan,
    plan_verified_page_prefix,
)
from image_monitor.watch_store import WatchScope, WatchStore

SERVICE_SCOPE = "dcinside"
PARTIAL_COVERAGE_GAPS = frozenset({"anchor_not_reached", "overlap_incomplete"})
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


def _cycle_summary(outcome, plan, persisted):
    pages = outcome.get("pages", [])
    exclusions = [row for page in pages for row in page.get("excluded_rows", [])]
    return {
        "generation": persisted["generation"],
        "status": outcome["status"],
        "http_status": outcome.get("http_status"),
        "navigation_attempts": len(outcome.get("navigation", [])),
        "page_count": len(pages),
        "page_statuses": [page.get("status") for page in pages],
        "layout_statuses": [page.get("layout_status") for page in pages],
        "page_checks": [diagnose_list_page(page, index) for index, page in enumerate(pages, 1)],
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


def _observed_page_pair(outcome):
    """Both snapshots must correspond to actual successful document navigations."""
    pages = outcome.get("pages", [])
    visits = outcome.get("navigation", [])
    if (
        outcome.get("status") != "observed"
        or not isinstance(pages, list)
        or len(pages) != 2
        or not isinstance(visits, list)
        or len(visits) != 2
    ):
        return False
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
        ):
            return False
    return outcome.get("http_status") == visits[-1]["http_status"]


def matches_partial_coverage_scan(queue, scope, state, report):
    """Verify one incomplete two-page observation against its durable gap and planner evidence."""
    latest = state["latest_scan"]
    if not (
        latest
        and latest["complete"] is False
        and latest["gap_reason"] in PARTIAL_COVERAGE_GAPS
        and latest["gap_reason"] == report.get("reason")
        and report.get("cycles_completed") == 1
        and report.get("browser_closed") is True
        and report.get("error_type") is None
    ):
        return False
    result = latest["result"]
    observed = result.get("private_observation", {})
    control = _control(state)
    if (
        not _observed_page_pair(observed)
        or control.get("transport_status") != "observed"
        or control.get("blocked") is not False
        or control.get("http_status") != observed.get("http_status")
    ):
        return False
    pages = observed["pages"]
    # Partial coverage leaves the state checkpoint at the original complete scan.
    # Reuse the planner to validate exact links, descending identities and safe
    # exclusions and to reproduce the saved observations for this checkpoint.
    scan_time = _stored_time(result["observed_at"])
    if scan_time != _stored_time(latest["observed_at"]):
        return False
    try:
        planned = plan_scan(scope, state, pages, scan_time, allow_verified_live=True)
    except WatchPlanError:
        return False
    if (
        planned["gap_reason"] != latest["gap_reason"]
        or planned["checkpoint"] != latest["checkpoint"]
        or planned["scan_result"]
        != {k: v for k, v in result.items() if k not in ("control", "private_observation")}
    ):
        return False
    gap = queue.connection.execute(
        "SELECT reason, generation, observed_at FROM watch_gaps WHERE scan_id=? "
        "AND watch_name=? AND gallery_type=? AND gallery_id=? AND keyword=? AND search_type=?",
        (latest["scan_id"], *scope.key()),
    ).fetchone()
    if gap is None or tuple(gap) != (
        latest["gap_reason"],
        state["generation"],
        latest["observed_at"],
    ):
        return False
    added = queue.connection.execute(
        "SELECT COUNT(*) FROM watch_candidates WHERE first_scan_id=?", (latest["scan_id"],)
    ).fetchone()[0]
    summary = _cycle_summary(
        observed, planned, {"generation": state["generation"], "candidates_added": added}
    )
    return (
        report.get("cycles") == [summary]
        and report.get("new_candidates") == added
        and _stored_time(report.get("next_eligible_at_local"))
        == _stored_time(control["next_eligible_at"])
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
                                max_pages=1 if state["baseline"] is None else 2,
                            )
                        finally:
                            finished_at = clock.now()
                            queue.defer_service(
                                SERVICE_SCOPE,
                                next_poll_at(finished_at, interval_seconds=interval_seconds),
                            )
                        pages = outcome.get("pages", [])
                        reason = None
                        try:
                            plan = plan_scan(
                                scope, state, pages, observed_at, allow_verified_live=True
                            )
                        except WatchPlanError as error:
                            reason = "list_profile_unverified_or_incomplete"
                            plan = None
                            if error.issue == "snapshot_layout" and _observed_page_pair(outcome):
                                plan = plan_verified_page_prefix(scope, state, pages, observed_at)
                            if plan is None:
                                plan = _empty_plan(state, observed_at, reason, scope)
                            plan["scan_result"]["planner_issue"] = error.issue
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
                        plan["scan_result"]["private_observation"] = outcome
                        report["last_stage"] = "persist_scan"
                        persisted = store.persist_scan(scope, **plan)
                        summary = _cycle_summary(outcome, plan, persisted)
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
