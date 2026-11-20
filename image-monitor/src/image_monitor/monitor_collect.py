"""Inspect up to three queued monitor posts and automatically save one verified body."""

from image_monitor import PUBLIC_VERSION
from image_monitor.artifact_files import _plain_path
from image_monitor.candidate_runtime import run_candidate_trial
from image_monitor.monitor_auto_selection import search_monitor_candidates
from image_monitor.monitor_batch_runtime import run_monitor_batch, share_batch_report
from image_monitor.monitor_save_ledger import _roots
from image_monitor.post_worker import run_post_save
from image_monitor.watch_lock import WatchRunBusy, watch_run_lock
from image_monitor.watch_runtime import _Clock, _stamp, _stored_time
from image_monitor.watch_store import MONITOR_SCOPE


def _save_status(save, expected_images):
    status = save["status"]
    if status == "monitor_batch_completed" and save["browser_closed"] is True:
        if (
            save["reason"] is None
            and save["tasks_started"] == save["tasks_completed"] == 1
            and 1 <= expected_images <= 2
            and len(save["saved_files"]) == expected_images
            and save["shared_pending_retained"] is False
            and save["last_stage"] == "complete"
        ):
            return "monitor_collect_saved"
        if save["reason"] == "candidate_unavailable" and save["shared_pending_retained"] is False:
            return "monitor_collect_unavailable"
    if status == "monitor_batch_no_candidates":
        if save["reason"] in {
            "selected_candidate_already_claimed",
            "selected_candidate_already_completed",
        }:
            return "monitor_collect_already_handled"
        if save["reason"] == "candidate_unavailable":
            return "monitor_collect_unavailable"
    return {
        "monitor_batch_waiting": "monitor_collect_waiting",
        "monitor_batch_busy": "monitor_collect_busy",
        "monitor_batch_cancelled": "monitor_collect_cancelled",
    }.get(status, "monitor_collect_review")


def _collect(report, roots, clock, detail_runner, save_runner):
    report["browser_closed"] = None
    search, target = search_monitor_candidates(*roots, clock=clock, detail_runner=detail_runner)
    report.update(
        search=search,
        reason=search["reason"],
        new_details_checked=search["new_details_checked"],
        next_eligible_at=search["next_eligible_at"],
        browser_closed=search["browser_closed"],
    )
    if search["browser_closed"] is not True:
        report.update(reason="detail_browser_cleanup_unconfirmed")
        return
    if search["status"] != "ready":
        if search["status"] in {"no_candidates", "limit", "waiting", "busy", "review", "cancelled"}:
            report["status"] = "monitor_collect_" + search["status"]
        return
    if target is None or not 1 <= search["eligible_body_images"] <= 2:
        report.update(reason="verified_candidate_required")
        return

    # An independent pilot can impose a new wait after selection. Re-enter the
    # batch with the original immutable binding; never substitute another post.
    for attempt in range(2):
        report.update(
            native_save_tasks_started=None, worker_images_completed=None, browser_closed=None
        )
        save = run_monitor_batch(
            *roots, max_tasks=1, monitor_handoff=target, clock=clock, save_runner=save_runner
        )
        report.update(
            native_save_tasks_started=save["tasks_started"],
            worker_images_completed=save["worker_images_completed"],
            browser_closed=save["browser_closed"],
        )
        if (
            attempt
            or save["status"] != "monitor_batch_waiting"
            or save.get("reason") != "persisted_cooldown"
            or save["tasks_started"]
        ):
            break
        due = _stored_time(save["next_eligible_at_local"])
        report["next_eligible_at"] = _stamp(due)
        remaining = (due - clock.now()).total_seconds()
        if remaining > 60:
            break
        clock.wait(max(0, remaining))

    public = share_batch_report(save)
    status = _save_status(public, search["eligible_body_images"])
    files = public["saved_files"] if status == "monitor_collect_saved" else []
    due = public.get("next_eligible_at_local")
    report.update(
        save=public,
        status=status,
        reason=public.get("reason"),
        native_save_tasks_started=public["tasks_started"],
        files_verified=len(files),
        saved_files=files,
        next_eligible_at=_stamp(_stored_time(due)) if due else None,
        browser_closed=public["browser_closed"],
    )


def run_monitor_collect(
    watch_root,
    legacy_root,
    work_root,
    *,
    clock=None,
    detail_runner=run_candidate_trial,
    save_runner=run_post_save,
):
    """Use the desktop monitor lease across selection, waiting, saving, and verification."""
    report = {
        "schema_version": 1,
        "program_version": PUBLIC_VERSION,
        "mode": "bounded_automatic_monitor_collection",
        "status": "monitor_collect_review",
        "reason": None,
        "new_details_checked": 0,
        "native_save_tasks_started": 0,
        "worker_images_completed": 0,
        "files_verified": 0,
        "saved_files": [],
        "next_eligible_at": None,
        "browser_closed": True,
        "search": None,
        "save": None,
    }
    try:
        roots = _roots(watch_root, legacy_root, work_root)
        database = _plain_path(roots[0] / "watch.sqlite")
        if not database.exists():
            report.update(
                status="monitor_collect_no_candidates", reason="existing_watch_database_required"
            )
        elif not database.is_file():
            report.update(reason="stored_monitor_data_invalid")
        else:
            with watch_run_lock(database, MONITOR_SCOPE, purpose="monitor"):
                _collect(report, roots, clock or _Clock(), detail_runner, save_runner)
    except WatchRunBusy:
        report.update(status="monitor_collect_busy", reason="another_monitor_is_open")
    except KeyboardInterrupt:
        report.update(status="monitor_collect_cancelled", reason="requested_stop")
    except Exception:
        report.update(reason="collection_requires_review")
    return report


def monitor_collect_exit_code(report):
    if report["status"] == "monitor_collect_cancelled":
        return 130
    if report["status"] in {
        "monitor_collect_saved",
        "monitor_collect_no_candidates",
        "monitor_collect_limit",
        "monitor_collect_unavailable",
        "monitor_collect_waiting",
        "monitor_collect_busy",
        "monitor_collect_already_handled",
    }:
        return 0
    return 2
