"""Find one image-bearing recent post and hand its exact observation to native saving."""

from image_monitor import PUBLIC_VERSION
from image_monitor.monitor_batch_runtime import run_recent_save, share_batch_report
from image_monitor.monitor_save_ledger import _roots
from image_monitor.native_ui import NativeUIError
from image_monitor.post_worker import run_post_save
from image_monitor.watch_image_search import run_watch_image_search
from image_monitor.watch_runtime import _Clock, _stored_time


def _save_status(save, expected_images):
    status = save["status"]
    if status == "monitor_batch_completed":
        if (
            save["tasks_completed"] == save["tasks_started"] == 1
            and save.get("saved_file_count") == expected_images
            and expected_images > 0
            and save.get("browser_closed") is True
            and save.get("shared_pending_retained") is False
        ):
            return "watch_images_saved"
        if save.get("reason") == "candidate_unavailable":
            return "watch_images_unavailable"
    if status == "monitor_batch_no_candidates":
        if save.get("reason") == "selected_candidate_already_completed":
            return "watch_images_already_saved"
        if save.get("reason") == "candidate_unavailable":
            return "watch_images_unavailable"
        return "watch_images_no_candidate"
    return {
        "monitor_batch_waiting": "watch_images_waiting",
        "monitor_batch_busy": "watch_images_busy",
        "monitor_batch_cancelled": "watch_images_cancelled",
    }.get(status, "watch_images_review")


def run_watch_images(
    watch_root, legacy_root, work_root, browser="chrome", *, clock=None, save_runner=run_post_save
):
    if browser != "chrome":
        raise NativeUIError("Recent-post native saving requires Chrome")
    roots = _roots(watch_root, legacy_root, work_root)
    clock = clock or _Clock()
    report = {
        "program_version": PUBLIC_VERSION,
        "status": "watch_images_review",
        "search": None,
        "save": None,
    }
    try:
        search, handoff = run_watch_image_search(*roots, clock=clock)
        report["search"] = search
        if search["status"] != "image_candidate_ready":
            report["status"] = search["status"]
            return report
        if handoff is None:
            return report

        save = run_recent_save(*roots, handoff, clock=clock, save_runner=save_runner)
        if (
            save["status"] == "monitor_batch_waiting"
            and save.get("reason") == "persisted_cooldown"
            and save["tasks_started"] == 0
        ):
            # An immediately preceding detail request normally leaves one minute.
            # The saver has released its leases and must validate the same handoff again.
            remaining = (_stored_time(save["next_eligible_at_local"]) - clock.now()).total_seconds()
            if remaining <= 60:
                clock.wait(max(0, remaining))
                save = run_recent_save(*roots, handoff, clock=clock, save_runner=save_runner)
        report["save"] = share_batch_report(save)
        report["status"] = _save_status(report["save"], search["eligible_body_images"])
    except KeyboardInterrupt:
        report.update(status="watch_images_cancelled", error_type="KeyboardInterrupt")
    except Exception as error:
        report.update(status="watch_images_review", error_type=type(error).__name__)
    return report


def watch_images_exit_code(report):
    status = report["status"]
    if status in {"watch_images_cancelled", "image_search_cancelled"}:
        return 130
    if status in {
        "watch_images_saved",
        "watch_images_already_saved",
        "watch_images_unavailable",
        "watch_images_no_candidate",
        "watch_images_waiting",
        "watch_images_busy",
        "image_search_exhausted",
        "image_search_limit",
        "image_search_waiting",
        "image_search_busy",
    }:
        return 0
    return 2
