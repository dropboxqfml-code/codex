"""Inspect at most two persisted list candidates; never create image work."""

import time
import uuid
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

from image_monitor.artifact_files import _plain_path
from image_monitor.candidate_browser import HeadlessCandidateBrowser
from image_monitor.candidate_policy import CandidatePolicyError, classify_candidate_detail
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.dcinside import HEADER_FIELD_COUNTS, validate_post_url
from image_monitor.native_probe import write_report
from image_monitor.native_ui import NativeUIError, require_windows
from image_monitor.queue import QueueError, QueueStore
from image_monitor.retry import retry_after
from image_monitor.watch_lock import WatchRunBusy, watch_run_lock
from image_monitor.watch_planner import next_poll_at
from image_monitor.watch_runtime import (
    DEFAULT_SCOPE,
    PARTIAL_COVERAGE_GAPS,
    SERVICE_SCOPE,
    _Clock,
    _eligibility,
    _stamp,
    _stored_time,
)
from image_monitor.watch_store import WatchScope, WatchStore

_MONITOR_SCOPE = WatchScope("목록 감시", "normal", "comic_new6", "ai", "search_subject_memo")


class _RequestedStop(Exception):
    """Finish a requested stop after committing any completed observation."""


def _safe_count(value):
    return value if type(value) is int and 0 <= value <= 1000 else None


def _detail_summary(outcome, classification, *, order):
    snapshot = outcome.get("snapshot") or {}
    evidence = snapshot.get("profile_evidence") or {}
    diagnostics = snapshot.get("diagnostics") or outcome.get("diagnostics") or {}
    fields = evidence.get("header_field_counts") or {}
    counts = snapshot.get("image_counts") or {}
    matching = Counter(
        image.get("original_filename_match_status", "unknown")
        for image in snapshot.get("images", [])
    )
    return {
        "order": order,
        "status": outcome["status"],
        "http_status": outcome.get("http_status"),
        "error_type": outcome.get("error_type"),
        "error_code": outcome.get("error_code"),
        "navigation_attempts": outcome.get("navigation_attempts", 1),
        "time_status": classification["time_status"],
        "reason": classification["reason"],
        "header_observed": classification["header_observed"],
        "layout_status": classification["layout_status"],
        "save_approved": False,
        "queue_eligible": False,
        "header_count": _safe_count(evidence.get("header_count")),
        "header_field_counts": {key: _safe_count(fields.get(key)) for key in HEADER_FIELD_COUNTS},
        "body_count": _safe_count((diagnostics.get("counts") or {}).get(".write_div")),
        "title_present": isinstance(snapshot.get("title"), str) and bool(snapshot["title"].strip()),
        "author_present": isinstance(snapshot.get("nickname"), str)
        and bool(snapshot["nickname"].strip()),
        "published_at_parsed": classification["published_at"] is not None,
        "image_counts": {
            key: _safe_count(counts.get(key))
            for key in ("body_occurrences", "included_unique", "excluded", "pending")
        },
        "attachment_count": len(snapshot.get("attachment_inventory", [])),
        "attachment_matching_counts": {
            key: matching[key]
            for key in ("matched", "ambiguous", "unavailable", "not_applicable", "unknown")
            if matching[key]
        },
    }


def _unknown(reason):
    return {
        "time_status": "unknown",
        "reason": reason,
        "header_observed": False,
        "published_at": None,
        "layout_status": "unverified",
        "save_approved": False,
        "queue_eligible": False,
    }


def _deadline(report, due):
    report["next_eligible_at_local"] = due.astimezone(ZoneInfo("Asia/Seoul")).isoformat()


def share_candidate_report(report):
    """Share bounded structure and result counts, keeping each post identity private."""
    allowed = (
        "schema_version",
        "status",
        "mode",
        "inspection_only",
        "images_saved",
        "image_jobs_created",
        "browser",
        "browser_version",
        "browser_closed",
        "last_stage",
        "error_type",
        "reason",
        "candidates_selected",
        "candidates_completed",
        "interval_seconds",
        "details",
        "time_status_counts",
        "next_eligible_at_local",
    )
    return {key: report[key] for key in allowed if key in report}


def run_candidate_trial(
    work_root: Path,
    browser="chrome",
    *,
    max_candidates=2,
    interval_seconds=60,
    backend_factory=HeadlessCandidateBrowser,
    clock=None,
    scope=DEFAULT_SCOPE,
    should_stop=None,
    expected_scan_id=None,
):
    require_windows()
    if browser not in {"chrome", "edge"}:
        raise NativeUIError("Choose a supported candidate inspection browser")
    if type(max_candidates) is not int or not 1 <= max_candidates <= 2:
        raise NativeUIError("Choose one or two candidate inspections")
    if type(interval_seconds) is not int or not 60 <= interval_seconds <= 300:
        raise NativeUIError("The candidate interval must be an integer from 60 to 300 seconds")
    if not isinstance(scope, WatchScope) or scope not in (DEFAULT_SCOPE, _MONITOR_SCOPE):
        raise NativeUIError("Candidate inspection requires an existing reviewed watch scope")
    if should_stop is not None and not callable(should_stop):
        raise NativeUIError("The candidate stop condition must be callable")
    clock = clock or _Clock()
    _stamp(clock.now())
    base = Path(work_root).resolve()
    if str(base).startswith("\\\\"):
        raise NativeUIError("A local candidate state directory is required")
    _plain_path(base)
    database = _plain_path(base / "watch.sqlite")
    run_directory = base / "candidate-runs" / uuid.uuid4().hex
    run_directory.mkdir(parents=True)
    report_path = run_directory / "report.json"
    report = {
        "schema_version": 1,
        "status": "candidate_test_failed",
        "mode": "bounded_candidate_detail_inspection",
        "inspection_only": True,
        "images_saved": False,
        "image_jobs_created": 0,
        "browser": browser,
        "browser_closed": True,
        "last_stage": "eligibility_check",
        "error_type": None,
        "candidates_selected": 0,
        "candidates_completed": 0,
        "interval_seconds": interval_seconds,
        "details": [],
        "time_status_counts": {},
    }
    backend = None
    try:

        def stopped():
            if should_stop is None:
                return False
            value = should_stop()
            if type(value) is not bool:
                raise QueueError("The candidate stop condition must return a boolean")
            return value

        def stop_if_requested():
            if stopped():
                raise _RequestedStop

        def wait_until(due):
            if should_stop is None:
                clock.wait(max(0, (due - clock.now()).total_seconds()))
                return
            while (remaining := (due - clock.now()).total_seconds()) > 0:
                stop_if_requested()
                wait = getattr(clock, "wait", time.sleep)
                wait(min(remaining, 0.1))
            stop_if_requested()

        if not database.is_file():
            report.update(status="candidate_no_baseline", reason="existing_watch_database_required")
        else:
            # All reviewed scopes share this scan lease with discovery and saving.
            with watch_run_lock(database, DEFAULT_SCOPE), QueueStore(database) as queue:
                state = WatchStore(queue).get_state(scope)
                if expected_scan_id is not None:
                    # The monitor validated this particular partial scan before its
                    # cooldown. Bind the decision again under the shared navigation lease.
                    latest = state["latest_scan"]
                    if latest is None or (
                        latest["scan_id"] != expected_scan_id
                        or latest["complete"]
                        or latest["gap_reason"] not in PARTIAL_COVERAGE_GAPS
                    ):
                        raise QueueError("List coverage changed before candidate inspection")
                if queue.summary()["posts"] or queue.summary()["jobs"]:
                    raise QueueError("Candidate inspection requires the separate watch database")
                baseline = state["baseline"]
                if baseline is None:
                    report.update(
                        status="candidate_no_baseline", reason="existing_baseline_required"
                    )
                else:
                    eligibility, due = _eligibility(queue, state, clock.now())
                    store = CandidateDetailStore(queue)
                    if eligibility == "blocked":
                        report.update(reason="access_block_requires_review", last_stage="blocked")
                    elif stopped():
                        raise _RequestedStop
                    elif eligibility == "waiting":
                        report.update(status="candidate_waiting", reason="persisted_cooldown")
                        _deadline(report, due)
                    else:
                        batch = store.list_pending(scope, limit=max_candidates)
                        report["candidates_selected"] = len(batch)
                        if not batch:
                            report.update(
                                status="candidate_no_pending", reason="no_unattempted_candidates"
                            )
                        else:
                            # Validate every frozen identity before opening any browser.
                            for candidate in batch:
                                target = validate_post_url(candidate["post_url"])
                                if (
                                    any(
                                        target[key] != candidate[key]
                                        for key in ("gallery_type", "gallery_id", "post_id")
                                    )
                                    or target["canonical_url"] != candidate["post_url"]
                                ):
                                    raise QueueError(
                                        "Candidate identity does not match its stored URL"
                                    )
                            stop_if_requested()
                            backend = backend_factory(browser, now=clock.now)
                            with backend:
                                report["browser_closed"] = False
                                report["browser_version"] = backend.browser_version
                                for index, candidate in enumerate(batch):
                                    state = WatchStore(queue).get_state(scope)
                                    eligibility, due = _eligibility(queue, state, clock.now())
                                    if eligibility == "blocked":
                                        report.update(
                                            reason="access_block_requires_review",
                                            last_stage="blocked",
                                        )
                                        break
                                    stop_if_requested()
                                    if eligibility == "waiting":
                                        remaining = (due - clock.now()).total_seconds()
                                        _deadline(report, due)
                                        if index == 0 or remaining > interval_seconds:
                                            report.update(
                                                status="candidate_waiting",
                                                reason="persisted_cooldown",
                                            )
                                            break
                                        report["last_stage"] = "waiting_between_candidates"
                                        write_report(report_path, report)
                                        wait_until(due)
                                        eligibility, due = _eligibility(
                                            queue, WatchStore(queue).get_state(scope), clock.now()
                                        )
                                        if eligibility == "blocked":
                                            report.update(
                                                reason="access_block_requires_review",
                                                last_stage="blocked",
                                            )
                                            break
                                        if eligibility != "ready":
                                            report.update(
                                                status="candidate_waiting",
                                                reason="cooldown_not_elapsed",
                                            )
                                            break
                                    stop_if_requested()
                                    observed_at = clock.now()
                                    attempt = store.start(
                                        scope,
                                        candidate["post_id"],
                                        expected_first_scan_id=candidate["first_scan_id"],
                                        baseline_observed_at=_stored_time(baseline["observed_at"]),
                                        started_at=observed_at,
                                    )
                                    report["last_stage"] = "candidate_observation"
                                    queue.defer_service(
                                        SERVICE_SCOPE,
                                        next_poll_at(
                                            observed_at, interval_seconds=interval_seconds
                                        ),
                                    )
                                    try:
                                        outcome = backend.inspect(candidate, observed_at)
                                    finally:
                                        finished_at = clock.now()
                                        next_at = next_poll_at(
                                            finished_at, interval_seconds=interval_seconds
                                        )
                                        queue.defer_service(SERVICE_SCOPE, next_at)
                                    http_status = outcome.get("http_status")
                                    blocked = http_status in {401, 403}
                                    deleted = http_status in {404, 410}
                                    if http_status in {429, 503}:
                                        try:
                                            server_due = retry_after(
                                                outcome.get("retry_after"), finished_at
                                            )
                                        except ValueError:
                                            server_due = None
                                        if server_due is not None:
                                            next_at = max(next_at, server_due)
                                        queue.defer_service(SERVICE_SCOPE, next_at)
                                    classification = _unknown(
                                        "candidate_unavailable"
                                        if deleted
                                        else "detail_inspection_failed"
                                    )
                                    observed = outcome["status"] == "observed"
                                    if observed:
                                        try:
                                            classification = classify_candidate_detail(
                                                candidate, baseline, outcome["snapshot"]
                                            )
                                        except CandidatePolicyError:
                                            classification = _unknown(
                                                "candidate_identity_or_baseline_invalid"
                                            )
                                    result = {
                                        "classification": classification,
                                        "private_observation": outcome,
                                        "control": {
                                            "blocked": blocked,
                                            "finished_at": _stamp(finished_at),
                                            "next_eligible_at": _stamp(next_at),
                                            "interval_seconds": interval_seconds,
                                            "http_status": http_status,
                                        },
                                    }
                                    store.finish(
                                        attempt["attempt_id"],
                                        finished_at=finished_at,
                                        result=result,
                                        status="completed" if observed or deleted else "failed",
                                    )
                                    summary = _detail_summary(
                                        outcome, classification, order=index + 1
                                    )
                                    report["details"].append(summary)
                                    report["candidates_completed"] += 1
                                    report["time_status_counts"] = dict(
                                        Counter(item["time_status"] for item in report["details"])
                                    )
                                    _deadline(report, next_at)
                                    write_report(report_path, report)
                                    if blocked:
                                        report.update(
                                            reason="access_block_requires_review",
                                            last_stage="blocked",
                                        )
                                        break
                                    stop_if_requested()
                                    if http_status in {429, 503}:
                                        report.update(
                                            status="candidate_waiting", reason="service_retry_after"
                                        )
                                        break
                                    if not observed and not deleted:
                                        report.update(
                                            reason="detail_inspection_failed",
                                            error_type=outcome.get("error_type"),
                                        )
                                        break
                                    if classification["time_status"] == "unknown" and not deleted:
                                        report.update(
                                            status="candidate_test_partial",
                                            reason=classification["reason"],
                                        )
                                        break
                                    if index + 1 == len(batch):
                                        report.update(
                                            status="candidate_test_completed", last_stage="complete"
                                        )
                if queue.summary()["posts"] or queue.summary()["jobs"]:
                    raise QueueError("Candidate inspection unexpectedly created image work")
    except _RequestedStop:
        report.update(status="candidate_test_cancelled", error_type=None, reason="requested_stop")
    except WatchRunBusy:
        report.update(status="candidate_busy", reason="another_scan_owns_this_scope")
    except KeyboardInterrupt:
        report.update(
            status="candidate_test_cancelled", error_type="KeyboardInterrupt", reason="cancelled"
        )
    except Exception as error:
        report.update(
            status="candidate_test_failed",
            error_type=type(error).__name__,
            reason="candidate_trial_stopped",
        )
    finally:
        if backend is not None:
            report["browser_closed"] = backend.browser_closed
            if not backend.browser_closed and report["status"] == "candidate_test_completed":
                report.update(status="candidate_test_failed", reason="owned_browser_not_closed")
        report["report_path"] = str(report_path)
        write_report(report_path, report)
    return report
