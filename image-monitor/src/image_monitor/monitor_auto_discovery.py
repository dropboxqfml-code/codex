"""One eligible Chrome list scan for the automatic monitor."""

import sqlite3
from pathlib import Path

from image_monitor.artifact_files import _plain_path
from image_monitor.monitor_clock import stop_requested
from image_monitor.monitor_date_report import verified_date_cell_checks
from image_monitor.monitor_gap_report import gap_route_details, search_window_start_visits
from image_monitor.monitor_gap_store import load_bookmark
from image_monitor.monitor_list_attempt import uncommitted_list_review
from image_monitor.monitor_list_review import current_list_review
from image_monitor.native_ui import NativeUIError
from image_monitor.queue import QueueError, QueueStore
from image_monitor.watch_detail_source import recent_scan_candidates, scan_plan_candidates
from image_monitor.watch_gap_recovery import gap_next_url
from image_monitor.watch_history import historical_route_details, plan_historical_scan
from image_monitor.watch_lock import WatchRunBusy, watch_list_lock
from image_monitor.watch_planner import next_poll_at, plan_scan
from image_monitor.watch_runtime import (
    DEFAULT_SCOPE,
    HEAD_OVERLAP_SCHEMA,
    _control,
    _cycle_summary,
    _eligibility,
    _matched_documents,
    _observed_page_chain,
    _plan_observation,
    _stamp,
    _stored_time,
    confirmed_monitor_scan,
    matches_partial_coverage_scan,
    monitor_scan_policy,
    run_watch_trial,
    verified_recent_plan,
)
from image_monitor.watch_store import MONITOR_SCOPE, WatchStore

_EMPTY = {"generation": 0, "baseline": None, "checkpoint": None, "latest_scan": None}


def _result(status, reason, *, due=None, closed=None, added=0):
    return {
        "status": status,
        "reason": reason,
        "new_candidates": added,
        "next_eligible_at": _stamp(due) if due is not None else None,
        "browser_closed": closed,
    }


class _ScanReview(QueueError):
    """The monitor could not verify this part of the saved list scan."""


def _review(stage, closed, evidence=None):
    result = _result("review", "list_scan_requires_review", closed=closed)
    result["review"] = evidence or {"stage": stage}
    return result


def _source(queue, now, interval):
    summary = queue.summary()
    if summary["posts"] or summary["jobs"]:
        raise QueueError("List discovery requires a dedicated database")
    state = WatchStore(queue).get_state(MONITOR_SCOPE)
    eligibility, due = _eligibility(queue, state, now)
    if eligibility == "blocked":
        return state, eligibility, None
    finished = _control(state).get("finished_at")
    if finished is not None:
        due = max(due, next_poll_at(_stored_time(finished), interval))
    if queue.schema_version >= 5:
        last_detail = queue.connection.execute(
            "SELECT MAX(finished_at) FROM candidate_details WHERE watch_name=? AND gallery_type=? "
            "AND gallery_id=? AND keyword=? AND search_type=?",
            MONITOR_SCOPE.key(),
        ).fetchone()[0]
        if last_detail is not None:
            due = max(due, next_poll_at(_stored_time(last_detail), interval))
    return state, "waiting" if due > now else "ready", due


def _completed_scan(queue, before, after, raw, page_limit, historical_source):
    """Replay a complete scan from the state observed before launching Chrome."""
    latest = after["latest_scan"]
    record = latest["result"]
    observed = record["private_observation"]
    pages = observed["pages"]
    visits = observed["navigation"]
    control = _control(after)
    if (
        observed.get("status") != "observed"
        or control.get("transport_status") != "observed"
        or control.get("http_status") != observed.get("http_status")
        or len(visits) != len(pages)
        or observed.get("http_status") != visits[-1]["http_status"]
        or any(
            type(v["http_status"]) is not int
            or not 200 <= v["http_status"] < 300
            or p["url"] != v["url"]
            for p, v in zip(pages, visits, strict=True)
        )
    ):
        raise _ScanReview("transport_check")
    observed_at = _stored_time(latest["observed_at"])
    if "gap_recovery" in record or observed.get("gap_seed_route") is True:
        if "gap_recovery" in record and not (historical_source and "frontier" in historical_source):
            raise _ScanReview("route_check")
        plan = _plan_observation(
            MONITOR_SCOPE,
            before,
            observed,
            observed_at,
            page_limit if page_limit > 2 else None,
            historical_source,
            allow_seed_crossing=True,
        )
        if plan != verified_recent_plan(queue, MONITOR_SCOPE, after):
            raise _ScanReview("planner_check")
    elif "historical_follow_up" in record:
        plan = plan_historical_scan(
            MONITOR_SCOPE,
            before,
            pages,
            observed_at,
            historical_source,
            allow_head_overlap=control.get("historical_route_schema") == HEAD_OVERLAP_SCHEMA,
        )
        if plan != verified_recent_plan(queue, MONITOR_SCOPE, after):
            raise _ScanReview("planner_check")
    else:
        plan = plan_scan(MONITOR_SCOPE, before, pages, observed_at, allow_verified_live=True)
    matches, _ = scan_plan_candidates(queue, MONITOR_SCOPE, after, plan)
    if matches is None:
        raise _ScanReview("candidate_check")
    added = matches["new_candidates"]
    stored_plan = {k: v for k, v in record.items() if k not in ("private_observation", "control")}
    summary = _cycle_summary(
        observed,
        plan,
        {"generation": after["generation"], "candidates_added": added},
        follow_up_page_limit=page_limit if page_limit > 2 else None,
    )
    gap = queue.connection.execute(
        "SELECT 1 FROM watch_gaps WHERE scan_id=?", (latest["scan_id"],)
    ).fetchone()
    if (
        not plan["complete"]
        or len(plan["scan_result"]["pages"]) != len(pages)
        or gap is not None
        or plan["checkpoint"] != latest["checkpoint"]
        or after["checkpoint"] != latest["checkpoint"]
        or after["updated_at"] != latest["observed_at"]
        or after["baseline"] != (plan["baseline"] or before["baseline"])
        or stored_plan != plan["scan_result"]
        or raw.get("cycles") != [summary]
        or raw.get("new_candidates") != added
        or (plan["baseline"] is not None and added != 0)
    ):
        raise _ScanReview("scan_record")
    return "baseline" if plan["baseline"] is not None else "complete", added


def _verified_scan(database, queue, before, after, raw, page_limit, historical_source):
    latest = after["latest_scan"]
    if (
        latest is None
        or after["generation"] != before["generation"] + 1
        or latest["generation"] != after["generation"]
        or raw.get("cycles_requested") != 1
        or raw.get("cycles_completed") != 1
        or raw.get("browser") != "chrome"
        or not confirmed_monitor_scan(database, latest, expected_report=raw)
    ):
        raise _ScanReview("receipt_check")
    control = _control(after)
    record = latest["result"]
    if (isinstance(historical_source, dict) and "frontier" in historical_source) != (
        "gap_recovery" in record
    ):
        raise _ScanReview("route_check")
    observation = record["private_observation"]
    if page_limit > 2:
        recorded = control.get("follow_up_page_limit")
        if type(recorded) is not int or recorded != page_limit:
            raise _ScanReview("route_check")
        if not _observed_page_chain(observation, page_limit):
            raise _ScanReview("transport_check")
    elif "follow_up_page_limit" in control:
        raise _ScanReview("route_check")
    if not 1 <= len(observation["pages"]) <= page_limit:
        raise _ScanReview("route_check")
    if "historical_follow_up" in latest["result"]:
        marker = latest["result"]["historical_follow_up"]
        if (
            historical_source is None
            or not isinstance(marker, dict)
            or marker.get("source_scan_id") != historical_source["source_scan_id"]
            or marker.get("boundary_page") != historical_source["boundary_page"]
        ):
            raise _ScanReview("route_check")
    if latest["complete"]:
        return _completed_scan(queue, before, after, raw, page_limit, historical_source)
    if (
        before["baseline"] is not None
        and after["baseline"] == before["baseline"]
        and after["checkpoint"] == before["checkpoint"]
        and raw.get("recent_pages_verified") is True
        and matches_partial_coverage_scan(queue, MONITOR_SCOPE, after, raw)
    ):
        matches, _ = recent_scan_candidates(queue, MONITOR_SCOPE, after)
        if matches is not None and matches["new_candidates"] == raw["new_candidates"]:
            return "partial", matches["new_candidates"]
        raise _ScanReview("candidate_check")
    raise _ScanReview("partial_check")


def _can_retry_inspection(queue, before, after, evidence, bookmark):
    """Only a timed-out read of the proven bookmark's successor gets one later list check."""
    if not evidence or not isinstance(bookmark, dict) or "frontier" not in bookmark:
        return False
    failure = evidence.get("inspection_failure", {})
    if not (
        evidence.get("evidence") == "committed_scan"
        and evidence.get("error_type") == "DCSnapshotError"
        and evidence.get("failed_visit") == 4
        and evidence.get("failed_page") == failure.get("page")
        and failure.get("stage") == "dom_read"
        and failure.get("reason") == "dom_budget_exceeded"
        and failure.get("visit") == 4
    ):
        return False
    # The preceding committed observation survives a process restart. An explicit
    # restart can check the site, but another consecutive timeout earns no extra turn.
    prior = before["latest_scan"]["result"]["private_observation"]
    prior_failure = prior.get("inspection_failure") or {}
    if (
        prior.get("status") == "inspection_error"
        and prior_failure.get("reason") == "dom_budget_exceeded"
    ):
        return False
    latest = after["latest_scan"]
    observed = latest["result"]["private_observation"]
    pages, visits = observed["pages"], observed["navigation"]
    if not (
        observed.get("gap_frontier_requested") is True
        and len(pages) == 3
        and len(visits) == 4
        and all(p.get("layout_status") == "site_verified" for p in pages)
        and _matched_documents(pages, visits[:3], follow_up=True)
        and 200 <= visits[3]["http_status"] < 300
        and all(visit.get("retry_after") is None for visit in visits)
        and observed.get("retry_after") is None
        and before["checkpoint"] == after["checkpoint"]
    ):
        return False
    at = _stored_time(latest["observed_at"])
    if any(
        gap_next_url(MONITOR_SCOPE, before, pages[:n], at, bookmark) != visits[n]["url"]
        for n in (2, 3)
    ):
        return False
    return load_bookmark(queue, after) == bookmark


def run_auto_discovery(
    watch_root,
    *,
    interval_seconds,
    clock,
    should_stop=None,
    run_cycle=run_watch_trial,
    recover_long_gaps=True,
):
    """Check durable eligibility, run one scan, and verify the exact saved result."""
    closed = None
    stage = "preflight"
    try:
        if stop_requested(should_stop):
            return _result("cancelled", "requested_stop")
        if type(interval_seconds) is not int or not 60 <= interval_seconds <= 300:
            raise ValueError("Invalid list interval")
        _stamp(clock.now())
        base = _plain_path(Path(watch_root))
        if base.drive.startswith("\\\\"):
            raise ValueError("The monitor requires a local state directory")
        base.mkdir(parents=True, exist_ok=True)
        database = _plain_path(base / "watch.sqlite")
        with watch_list_lock(database, DEFAULT_SCOPE):
            before = _EMPTY
            page_limit = 1
            historical_source = None
            if database.exists():
                stage = "baseline_check"
                with QueueStore(database, read_only=True) as queue:
                    before, status, due = _source(queue, clock.now(), interval_seconds)
                    if status == "blocked":
                        return _result("blocked", "access_block_requires_review")
                    if status == "waiting":
                        return _result("waiting", "persisted_cooldown", due=due)
                    stage = "cursor_check"
                    page_limit, historical_source = monitor_scan_policy(
                        database, queue, before, recover_long_gaps=recover_long_gaps
                    )
        stage = "browser_scan"
        raw = run_cycle(
            base,
            "chrome",
            cycles=1,
            interval_seconds=interval_seconds,
            clock=clock,
            scope=MONITOR_SCOPE,
            should_stop=should_stop,
            follow_up_gaps=True,
            recover_long_gaps=recover_long_gaps,
        )
        closed = raw.get("browser_closed") if type(raw.get("browser_closed")) is bool else None
        if closed is not True:
            return _result("review", "owned_browser_cleanup_unconfirmed", closed=closed) | {
                "review": {"stage": "browser_close"}
            }
        status = raw.get("status")
        if status == "watch_busy":
            return _result("busy", "another_worker_active", closed=closed)
        if status == "watch_test_cancelled":
            return _result("cancelled", "requested_stop", closed=closed)
        stage = "watch_result" if status == "watch_test_failed" else "queue_check"
        with (
            watch_list_lock(database, DEFAULT_SCOPE),
            QueueStore(database, read_only=True) as queue,
        ):
            after, eligibility, due = _source(queue, clock.now(), interval_seconds)
            if eligibility == "blocked":
                return _result("blocked", "access_block_requires_review", closed=closed)
            if status == "watch_waiting" and eligibility == "waiting":
                return _result("waiting", "persisted_cooldown", due=due, closed=closed)
            if status == "watch_test_failed":
                if (
                    eligibility == "waiting"
                    and after["generation"] == before["generation"] + 1
                    and _control(after).get("http_status") in (429, 503)
                    and raw.get("cycles_completed") == 1
                    and raw["cycles"][0]["generation"] == after["generation"]
                    and raw["cycles"][0]["http_status"] == _control(after)["http_status"]
                ):
                    return _result("waiting", "service_wait", due=due, closed=closed)
                if raw.get("cycles_completed") == 0:
                    evidence = uncommitted_list_review(
                        database, before, after, raw, run_cycle=run_cycle
                    )
                else:
                    evidence = current_list_review(database, queue, before, after, raw, stage=stage)
                    if eligibility == "waiting" and _can_retry_inspection(
                        queue, before, after, evidence, historical_source
                    ):
                        return _result("waiting", "inspection_retry_due", due=due, closed=True) | {
                            "review": evidence
                        }
                return _review(stage, closed, evidence)
            stage = "scan_record"
            try:
                kind, added = _verified_scan(
                    database, queue, before, after, raw, page_limit, historical_source
                )
            except _ScanReview as exc:
                stage = str(exc)
                evidence = current_list_review(database, queue, before, after, raw, stage=stage)
                # A genuine partial report can document a layout failure without
                # authorizing coverage. Distinguish it from a missing final report.
                if (
                    stage == "receipt_check"
                    and evidence
                    and evidence.get("watch_status") == "watch_test_partial"
                    and raw.get("recent_pages_verified") is not True
                    and "closed_monitor_scan" not in raw
                ):
                    evidence["stage"] = "partial_check"
                return _review(stage, closed, evidence)
            latest = after["latest_scan"]
            record = latest["result"]
            numbers = [page["page"] for page in record["private_observation"]["pages"]]
            result = _result(kind, raw.get("reason"), due=due, closed=closed, added=added)
            result.update(
                page_limit=page_limit, pages_checked=len(numbers), visited_page_numbers=numbers
            )
            if checks := verified_date_cell_checks(record["private_observation"]["pages"]):
                result["date_cell_checks"] = checks
            starts = search_window_start_visits(record)
            if starts:
                result["search_window_start_visits"] = starts
            if "gap_recovery" in record:
                result.update(gap_route_details(record))
                return result
            result.update(
                historical_route_details(
                    before,
                    latest,
                    historical_source,
                    allow_head_overlap=record["control"].get("historical_route_schema")
                    == HEAD_OVERLAP_SCHEMA,
                )
            )
            return result
    except WatchRunBusy:
        return _result("busy", "another_worker_active", closed=closed)
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        AttributeError,
        sqlite3.Error,
        NativeUIError,
    ):
        return _review(stage, closed)
