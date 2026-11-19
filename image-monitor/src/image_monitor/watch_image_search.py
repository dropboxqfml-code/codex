"""Find a saveable observed body in the latest verified list without rereading the list."""

from pathlib import Path

from image_monitor import PUBLIC_VERSION
from image_monitor.artifact_files import _plain_path
from image_monitor.candidate_browser import HeadlessCandidateBrowser
from image_monitor.candidate_runtime import run_candidate_trial
from image_monitor.candidate_save_policy import classify_stored_candidate_image
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.monitor_batch_runtime import recent_save_exclusions
from image_monitor.native_ui import require_windows
from image_monitor.queue import QueueError, QueueStore
from image_monitor.watch_detail_source import recent_scan_candidates
from image_monitor.watch_lock import WatchRunBusy, watch_run_lock
from image_monitor.watch_runtime import DEFAULT_SCOPE, _Clock, _eligibility
from image_monitor.watch_store import WatchStore

MAX_NEW_DETAILS = 3


def _search_window(queue, state, candidates, excluded, assessed, fresh_posts, report):
    """Classify each attempted post once. A stored eligible body precedes any new navigation."""
    allowed = [candidate for candidate in candidates if candidate["post_id"] not in excluded]
    report["previously_handled"] = len(candidates) - len(allowed)
    pending = None
    details = CandidateDetailStore(queue)
    for candidate in allowed:
        post_id = candidate["post_id"]
        attempt_id = candidate["attempt_id"]
        if attempt_id is None:
            if pending is None:
                pending = post_id
            continue
        if attempt_id in assessed:
            continue
        detail = details.get(attempt_id)
        if detail is None:
            raise QueueError("The stored candidate observation is missing")
        outcome, permit = classify_stored_candidate_image(candidate, state["baseline"], detail)
        assessed.add(attempt_id)
        counts = report["outcome_counts"]
        counts[outcome] = counts.get(outcome, 0) + 1
        if outcome == "save_ready":
            report.update(status="image_candidate_ready", eligible_body_images=permit.image_count)
            return None, {
                "scan_id": state["latest_scan"]["scan_id"],
                "attempt_id": attempt_id,
                "fingerprint": permit.fingerprint,
            }
        if outcome == "no_body_images_observed" and post_id not in fresh_posts:
            report["stored_empty_posts"] += 1
        if outcome == "needs_review" and post_id in fresh_posts:
            report.update(status="image_search_review", reason="detail_evidence_requires_review")
            return None, None
    if pending is None:
        report.update(status="image_search_exhausted", reason="no_remaining_unattempted_candidates")
    elif len(fresh_posts) >= MAX_NEW_DETAILS:
        report.update(status="image_search_limit", reason="fresh_detail_limit")
        pending = None
    return pending, None


def run_watch_image_search(
    watch_root, legacy_root, save_root, *, clock=None, backend_factory=HeadlessCandidateBrowser
):
    """Return a public summary and a private exact save handoff, if one is ready."""
    require_windows()
    clock = clock or _Clock()
    report = {
        "program_version": PUBLIC_VERSION,
        "mode": "recent_candidate_image_search",
        "status": "image_search_failed",
        "reason": None,
        "source_scan": None,
        "new_details_checked": 0,
        "stored_empty_posts": 0,
        "previously_handled": 0,
        "eligible_body_images": 0,
        "outcome_counts": {},
    }
    pinned_scan = None
    assessed = set()
    fresh_posts = set()
    try:
        database = Path(watch_root) / "watch.sqlite"
        if database.anchor.startswith(("//", "\\\\")):
            raise QueueError("Image search requires local watch data")
        while True:
            if not _plain_path(database).is_file():
                report.update(
                    status="image_search_review", reason="existing_watch_database_required"
                )
                break
            with (
                watch_run_lock(database, DEFAULT_SCOPE),
                QueueStore(database, read_only=True) as queue,
            ):
                state = WatchStore(queue).get_state(DEFAULT_SCOPE)
                latest = state["latest_scan"]
                if pinned_scan is not None and (not latest or latest["scan_id"] != pinned_scan):
                    report.update(status="image_search_review", reason="source_scan_changed")
                    break
                if queue.summary()["posts"] or queue.summary()["jobs"]:
                    raise QueueError("Expected a discovery database")
                eligibility, _ = _eligibility(queue, state, clock.now())
                if eligibility == "blocked":
                    report.update(
                        status="image_search_review", reason="access_block_requires_review"
                    )
                    break
                source, candidates = recent_scan_candidates(queue, DEFAULT_SCOPE, state)
                if source is None:
                    report.update(
                        status="image_search_review", reason="verified_recent_scan_required"
                    )
                    break
                if pinned_scan is None:
                    pinned_scan = latest["scan_id"]
                    report["source_scan"] = source
                try:
                    excluded = recent_save_exclusions(watch_root, legacy_root, save_root)
                except QueueError:
                    report.update(
                        status="image_search_review", reason="existing_save_requires_review"
                    )
                    break
                pending, handoff = _search_window(
                    queue, state, candidates, excluded, assessed, fresh_posts, report
                )
            if pending is None:
                return report, handoff

            # The existing worker waits outside the lease and checks both identities
            # under the lease before opening a detail. Never start a separate list scan.
            trial = run_candidate_trial(
                watch_root,
                "chrome",
                max_candidates=1,
                recent_scan_only=True,
                recent_target=(pinned_scan, pending),
                clock=clock,
                backend_factory=backend_factory,
            )
            report["new_details_checked"] += trial["candidates_completed"]
            if trial.get("next_eligible_at_local"):
                report["next_eligible_at_local"] = trial["next_eligible_at_local"]
            status = trial["status"]
            if status == "candidate_test_completed" and trial["browser_closed"] is True:
                if trial["candidates_completed"] != 1 or pending in fresh_posts:
                    raise QueueError("Candidate continuation did not make progress")
                fresh_posts.add(pending)
                continue
            report["status"] = {
                "candidate_waiting": "image_search_waiting",
                "candidate_busy": "image_search_busy",
                "candidate_no_pending": "image_search_busy",
                "candidate_scan_unverified": "image_search_review",
                "candidate_test_partial": "image_search_review",
                "candidate_test_cancelled": "image_search_cancelled",
            }.get(status, "image_search_failed")
            report["reason"] = trial.get("reason")
            break
    except WatchRunBusy:
        report.update(status="image_search_busy", reason="another_scan_owns_this_scope")
    except KeyboardInterrupt:
        report.update(status="image_search_cancelled", reason="cancelled")
    except Exception as error:
        report.update(
            status="image_search_failed", reason="search_stopped", error_type=type(error).__name__
        )
    return report, None
