"""Find one unclaimed monitor post, checking at most three new bodies per collection."""

from image_monitor.artifact_files import _plain_path
from image_monitor.candidate_runtime import run_candidate_trial
from image_monitor.candidate_save_policy import classify_stored_candidate_image
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.monitor_batch_runtime import _candidate, reconstruct_permit
from image_monitor.monitor_operations import load_monitor_operations
from image_monitor.monitor_save_ledger import (
    LEDGER_NAME,
    MAX_TASKS,
    LedgerStore,
    _roots,
    other_monitor_save_claims,
)
from image_monitor.monitor_settings import load_monitor_settings
from image_monitor.monitor_setup_retry import verify_setup_retry
from image_monitor.native_ui import NativeSaveLock
from image_monitor.queue import QueueError, QueueStore
from image_monitor.watch_image_search import MAX_NEW_DETAILS
from image_monitor.watch_lock import WatchRunBusy, watch_run_lock
from image_monitor.watch_planner import next_poll_at
from image_monitor.watch_runtime import (
    DEFAULT_SCOPE,
    _Clock,
    _control,
    _eligibility,
    _stamp,
    _stored_time,
)
from image_monitor.watch_store import MONITOR_SCOPE, WatchStore


def _handoff(permit):
    return {
        "post_id": permit.reference_snapshot["post_id"],
        "attempt_id": permit.detail_attempt_id,
        "fingerprint": permit.fingerprint,
    }


def _choice(queue, state, roots, details, assessed, fresh_posts, report, *, setup_retry):
    watch, legacy, batch = roots
    claimed = other_monitor_save_claims(watch / "watch.sqlite")
    ledger_path = _plain_path(watch / LEDGER_NAME)
    if ledger_path.exists():
        with LedgerStore(
            ledger_path, watch_root=watch, legacy_root=legacy, batch_root=batch, read_only=True
        ) as ledger:
            tasks = ledger.list_tasks()
            unfinished = [t for t in tasks if t["status"] in {"started", "needs_review"}]
            if setup_retry or unfinished:
                if not setup_retry or len(unfinished) != 1 or unfinished[0]["post_id"] in claimed:
                    raise QueueError("An unfinished monitor save requires review")
                task = unfinished[0]
                permit = reconstruct_permit(queue, task)
                with NativeSaveLock():
                    prior_run, prior_reason = verify_setup_retry(ledger, task, permit)
                report["eligible_body_images"] = permit.image_count
                report["previous_completion_setup_reason"] = prior_reason
                return _handoff(permit) | {
                    "retry_task_id": task["task_id"],
                    "prior_run": prior_run,
                }, None
            for task in tasks:
                if task["status"] == "planned" and task["post_id"] not in claimed:
                    permit = reconstruct_permit(queue, task)
                    report["eligible_body_images"] = permit.image_count
                    return _handoff(permit), None
                claimed.add(task["post_id"])
    elif setup_retry:
        raise QueueError("The prior monitor save ledger disappeared")
    for detail in details:
        attempt = detail["attempt_id"]
        if detail["status"] != "completed" or detail["post_id"] in claimed:
            continue
        if attempt in assessed and assessed[attempt] != "save_ready":
            continue
        candidate = _candidate(queue, detail["post_id"])
        outcome, permit = classify_stored_candidate_image(candidate, state["baseline"], detail)
        if attempt not in assessed:
            assessed[attempt] = outcome
            counts = report["outcome_counts"]
            counts[outcome] = counts.get(outcome, 0) + 1
            if outcome == "needs_review" and detail["post_id"] in fresh_posts:
                raise QueueError("Stored body evidence requires review")
        if permit is not None:
            report["eligible_body_images"] = permit.image_count
            return _handoff(permit), None
    pending = CandidateDetailStore(queue).list_pending(
        MONITOR_SCOPE, limit=1, exclude_posts=claimed
    )
    if pending:
        return None, (pending[0]["first_scan_id"], pending[0]["post_id"])
    return None, None


def search_monitor_candidates(
    watch_root, legacy_root, batch_root, *, clock=None, detail_runner=run_candidate_trial
):
    """Return an anonymous summary and a private, exact handoff for one native save."""
    clock = clock or _Clock()
    report = {
        "status": "review",
        "reason": None,
        "new_details_checked": 0,
        "eligible_body_images": 0,
        "outcome_counts": {},
        "next_eligible_at": None,
        "browser_closed": True,
    }
    assessed = {}
    waited_for = None
    fresh_posts = set()
    setup_retry = False
    try:
        roots = _roots(watch_root, legacy_root, batch_root)
        watch = roots[0]
        database = _plain_path(watch / "watch.sqlite")
        interval = load_monitor_settings(watch)["interval_seconds"]
        while True:
            ops = load_monitor_operations(*roots, now=clock.now())
            if ops["status"] in {"busy", "cancelled"}:
                report.update(status=ops["status"], reason=ops["reason"])
                break
            # The dashboard marks out-of-range bodies for review. The collection's
            # classifier can verify these observations and skip them individually.
            setup_retry = (
                ops["status"] == "needs_review" and ops["reason"] == "save_requires_review"
            )
            if (
                ops["status"] == "needs_review"
                and ops["reason"] != "candidate_detail_requires_review"
                and not setup_retry
            ):
                report["reason"] = ops["reason"]
                break
            if not database.is_file():
                report.update(status="no_candidates", reason="existing_watch_required")
                break
            with (
                watch_run_lock(database, DEFAULT_SCOPE),
                QueueStore(database, read_only=True) as queue,
            ):
                state = WatchStore(queue).get_state(MONITOR_SCOPE)
                if state["baseline"] is None:
                    report.update(status="no_candidates", reason="existing_baseline_required")
                    break
                now = clock.now()
                eligibility, due = _eligibility(queue, state, now)
                if eligibility == "blocked":
                    report["reason"] = "service_access_blocked"
                    break
                details = CandidateDetailStore(queue).list_details(MONITOR_SCOPE, limit=MAX_TASKS)
                if not fresh_posts.issubset(
                    {d["post_id"] for d in details if d["status"] == "completed"}
                ):
                    raise QueueError("Expected a durable completed body observation")
                handoff, pending = _choice(
                    queue,
                    state,
                    roots,
                    details,
                    assessed,
                    fresh_posts,
                    report,
                    setup_retry=setup_retry,
                )
                if handoff is None and pending is None:
                    report.update(
                        status="no_candidates", reason="no_remaining_unattempted_candidates"
                    )
                    break
                if handoff is None and len(fresh_posts) >= MAX_NEW_DETAILS:
                    report.update(status="limit", reason="fresh_detail_limit")
                    break
                if ops["wait_until"] is not None:
                    due = max(due, _stored_time(ops["wait_until"]))
                finished = [
                    _control(state).get("finished_at"),
                    *(d["finished_at"] for d in details),
                ]
                for value in filter(None, finished):
                    due = max(due, next_poll_at(_stored_time(value), interval_seconds=interval))
                wait = (due - now).total_seconds()
                choice = handoff or pending
            if waited_for is not None and waited_for != choice:
                report.update(status="busy", reason="monitor_candidate_changed")
                break
            if wait > 0:
                report["next_eligible_at"] = _stamp(due)
                if wait > 60 or waited_for is not None:
                    report.update(status="waiting", reason="persisted_cooldown")
                    break
                waited_for = choice
                clock.wait(wait)
                continue
            waited_for = None
            report["next_eligible_at"] = None
            if handoff is not None:
                report.update(
                    status="ready",
                    reason="completion_setup_retry_ready" if setup_retry else "save_ready",
                )
                return report, handoff
            report["browser_closed"] = None
            trial = detail_runner(
                watch,
                "chrome",
                max_candidates=1,
                scope=MONITOR_SCOPE,
                interval_seconds=interval,
                monitor_target=pending,
                clock=clock,
            )
            closed = trial.get("browser_closed")
            report["browser_closed"] = closed if type(closed) is bool else None
            checked = trial.get("candidates_completed")
            if type(checked) is not int or not 0 <= checked <= 1:
                raise QueueError("A bounded detail worker returned invalid counts")
            report["new_details_checked"] += checked
            if report["browser_closed"] is not True:
                report["reason"] = "owned_browser_cleanup_unconfirmed"
                break
            status = trial["status"]
            if status == "candidate_test_completed":
                if checked != 1 or pending[1] in fresh_posts:
                    raise QueueError("Expected one new body observation")
                fresh_posts.add(pending[1])
                continue
            report["status"] = {
                "candidate_waiting": "waiting",
                "candidate_busy": "busy",
                "candidate_no_pending": "busy",
                "candidate_test_cancelled": "cancelled",
            }.get(status, "review")
            reason = trial.get("reason")
            report["reason"] = (
                reason
                if reason
                in {
                    "service_retry_after",
                    "persisted_cooldown",
                    "monitor_candidate_changed",
                    "another_scan_owns_this_scope",
                    "cancelled",
                    "requested_stop",
                    "access_block_requires_review",
                }
                else "detail_requires_review"
            )
            if trial.get("next_eligible_at_local"):
                report["next_eligible_at"] = _stamp(_stored_time(trial["next_eligible_at_local"]))
            break
    except WatchRunBusy:
        report.update(status="busy", reason="another_scan_owns_this_scope")
    except KeyboardInterrupt:
        report.update(status="cancelled", reason="requested_stop")
    except Exception:
        report.update(
            status="review",
            reason="setup_retry_evidence_unconfirmed"
            if setup_retry
            else "monitor_evidence_requires_review",
        )
    return report, None
