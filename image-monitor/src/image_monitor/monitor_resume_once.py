"""Run one outstanding monitor detail inspection and return its shareable result."""

import stat
import time
from pathlib import Path

from image_monitor import PUBLIC_VERSION
from image_monitor.artifact_files import _plain_path
from image_monitor.candidate_runtime import run_candidate_trial
from image_monitor.monitor_controller import MonitorController, _detail_fields
from image_monitor.watch_lock import WatchRunBusy, watch_run_lock
from image_monitor.watch_runtime import _stamp, _stored_time
from image_monitor.watch_store import MONITOR_SCOPE

_STATUSES = {
    "completed": "monitor_resume_completed",
    "no_slot": "monitor_resume_no_slot",
    "waiting": "monitor_resume_waiting",
    "busy": "monitor_resume_busy",
    "cancelled": "monitor_resume_cancelled",
    "needs_review": "monitor_resume_review",
}
_REASONS = {
    "access_block_requires_review",
    "another_worker_active",
    "detail_requires_review",
    "detail_stopped_for_review",
    "existing_baseline_required",
    "insufficient_free_space",
    "no_verified_detail_slot",
    "owned_browser_cleanup_unconfirmed",
    "persisted_cooldown",
    "requested_stop",
    "resume_slot_changed",
    "scan_requires_review",
    "service_retry_after",
    "stored_monitor_data_invalid",
}


def _count(value):
    return value if type(value) is int and value >= 0 else 0


def _list_disabled(*args, **kwargs):
    raise RuntimeError("List scans are disabled in single-detail mode")


def _report(state=None, *, status=None, reason=None):
    state = state or {}
    closed = state.get("browser_closed", True)
    checked = _count(state.get("auto_details_checked"))
    resumed = state.get("resumed_detail_slot") is True
    detail = state.get("resume_once_detail")
    if detail is not None:
        http = detail.get("http_status")
        http = http if type(http) is int and 100 <= http <= 599 else None
        detail = {
            "http_status": http,
            **_detail_fields(
                http,
                detail.get("time_status"),
                detail.get("reason"),
                detail.get("image_count"),
                detail.get("pending_images"),
            ),
        }
    if status is None:
        status = _STATUSES.get(state.get("resume_once_status"), "monitor_resume_review")
        raw_reason = state.get("reason")
        reason = raw_reason if raw_reason in _REASONS else None
    if closed is not True and status != "monitor_resume_review":
        status, reason = "monitor_resume_review", "owned_browser_cleanup_unconfirmed"
    if status == "monitor_resume_completed":
        http = detail and detail["http_status"]
        if (
            checked != 1
            or not resumed
            or http is None
            or not (200 <= http < 400 or http in {404, 410})
        ):
            status, reason = "monitor_resume_review", "detail_requires_review"
        elif http in {404, 410}:
            status = "monitor_resume_unavailable"
    if status == "monitor_resume_review" and reason is None:
        reason = "resume_requires_review"
    backlog_known = "detail_pending_count" in state and reason != "stored_monitor_data_invalid"
    due = state.get("next_eligible_at")
    return {
        "schema_version": 1,
        "program_version": PUBLIC_VERSION,
        "mode": "bounded_monitor_resume",
        "status": status,
        "reason": reason,
        "details_checked": checked,
        "detail_responses_received": int(detail is not None and detail["http_status"] is not None),
        "detail": detail,
        "resumed_detail_slot": resumed,
        "resume_detail_pending": state.get("resume_detail_pending") is True
        if backlog_known
        else None,
        "detail_pending_count": _count(state["detail_pending_count"]) if backlog_known else None,
        "next_eligible_at": _stamp(_stored_time(due)) if due is not None else None,
        "remaining_seconds": _count(state.get("remaining_seconds")),
        "native_save_tasks_started": _count(state.get("operations_save_tasks_started")),
        "worker_stopped": True,
        "browser_closed": closed if type(closed) is bool else None,
    }


def _run(controller):
    interrupted = False
    owns_worker = True
    try:
        state = controller.resume_once()
        if state["resume_once_status"] == "busy":
            owns_worker = False
            return _report(status="monitor_resume_busy", reason="another_worker_active")
        # Sleep outside Thread.join so Ctrl+C on Windows cannot interrupt thread bookkeeping.
        while controller.is_alive():
            time.sleep(0.1)
    except KeyboardInterrupt:
        interrupted = True
    finally:
        while owns_worker and controller.is_alive():
            try:
                controller.stop()
                time.sleep(0.1)
            except KeyboardInterrupt:
                interrupted = True
    state = controller.status()
    if (
        interrupted
        and state["resume_once_status"] != "needs_review"
        and state["resume_once_detail"] is None
    ):
        return _report(state, status="monitor_resume_cancelled", reason="requested_stop")
    return _report(state)


def run_monitor_resume_once(work_root: Path, *, clock=None, run_details=run_candidate_trial):
    """Resume the verified slot under the same process lease as the desktop monitor."""
    try:
        base = Path(work_root).absolute()
        if str(work_root).startswith(("//", "\\\\")) or str(base).startswith(("//", "\\\\")):
            return _report(status="monitor_resume_review", reason="local_work_root_required")
        database = _plain_path(base / "watch.sqlite")
        try:
            info = database.lstat()
        except FileNotFoundError:
            return _report(
                status="monitor_resume_no_slot", reason="existing_watch_database_required"
            )
        if not stat.S_ISREG(info.st_mode):
            return _report(status="monitor_resume_review", reason="stored_monitor_data_invalid")
        with watch_run_lock(database, MONITOR_SCOPE, purpose="monitor"):
            controller = MonitorController(
                base, clock=clock, run_cycle=_list_disabled, run_details=run_details
            )
            try:
                return _run(controller)
            except Exception:
                return _report(
                    {"browser_closed": None},
                    status="monitor_resume_review",
                    reason="resume_requires_review",
                )
    except WatchRunBusy:
        return _report(status="monitor_resume_busy", reason="another_monitor_is_open")
    except KeyboardInterrupt:
        return _report(status="monitor_resume_cancelled", reason="requested_stop")
    except Exception:
        return _report(status="monitor_resume_review", reason="resume_requires_review")


def monitor_resume_once_exit_code(report):
    if report.get("status") == "monitor_resume_cancelled":
        return 130
    if report.get("status") in {
        "monitor_resume_completed",
        "monitor_resume_unavailable",
        "monitor_resume_no_slot",
        "monitor_resume_waiting",
        "monitor_resume_busy",
    }:
        return 0
    return 2
