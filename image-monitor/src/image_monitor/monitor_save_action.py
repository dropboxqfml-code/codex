"""Run one user-requested native save in an owned child process."""

import json
import os
import sys
import threading
from pathlib import Path

from image_monitor.monitor_finish_action import (
    _integer,
    _reject_number,
    _requested,
    _run_child,
    _StoppedBeforeLaunch,
    _unique_object,
)

_STATUS_CODES = {
    "monitor_batch_completed": 0,
    "monitor_batch_waiting": 0,
    "monitor_batch_busy": 0,
    "monitor_batch_no_candidates": 0,
    "monitor_batch_manual_review": 2,
    "monitor_batch_cancelled": 130,
}
_STATUS_REASONS = {
    "monitor_batch_completed": {None, "candidate_unavailable"},
    "monitor_batch_waiting": {"persisted_cooldown", "cooldown_not_elapsed"},
    "monitor_batch_busy": {"another_scan_owns_this_scope"},
    "monitor_batch_no_candidates": {
        "existing_watch_required",
        "existing_baseline_required",
        "no_unsaved_reviewed_candidates",
    },
    "monitor_batch_manual_review": {
        "unfinished_batch_requires_reconcile",
        "unfinished_legacy_requires_review",
        "access_block_requires_review",
        "native_batch_task_requires_review",
        "service_retry_after",
        "selected_candidate_unavailable",
        "batch_requires_review",
        "save_action_failed",
    },
    "monitor_batch_cancelled": {
        "cancelled",
        "requested_stop",
        "native_batch_task_requires_review",
        "access_block_requires_review",
        "service_retry_after",
        "selected_candidate_unavailable",
    },
}
SAVE_ACTION_STATUSES = frozenset(_STATUS_CODES)
SAVE_ACTION_REASONS = frozenset.union(*(frozenset(v) for v in _STATUS_REASONS.values())) - {None}
_FIELDS = {
    "status",
    "reason",
    "tasks_started",
    "tasks_completed",
    "files_verified",
    "browser_closed",
}
_START = b"save-one\n"


def _fallback(*, cancelled=False):
    return {
        "status": "monitor_batch_cancelled" if cancelled else "monitor_batch_manual_review",
        "reason": "requested_stop" if cancelled else "save_action_failed",
        "tasks_started": 0,
        "tasks_completed": 0,
        "files_verified": 0,
        "browser_closed": True if cancelled else None,
    }


def validate_save_result(report):
    """Validate the bounded dashboard protocol without importing the native runtime."""
    if not isinstance(report, dict) or set(report) != _FIELDS:
        raise ValueError("Invalid dashboard save report fields")
    status, reason = report["status"], report["reason"]
    started, completed = report["tasks_started"], report["tasks_completed"]
    files, closed = report["files_verified"], report["browser_closed"]
    if (
        not isinstance(status, str)
        or status not in _STATUS_CODES
        or not (reason is None or isinstance(reason, str))
        or reason not in _STATUS_REASONS[status]
        or not _integer(started, 0, 1)
        or not _integer(completed, 0, started)
        or not _integer(files, 0, 2)
        or (closed is not None and type(closed) is not bool)
    ):
        raise ValueError("Invalid dashboard save report values")
    if status == "monitor_batch_completed":
        saved = reason is None
        if closed is not True or started != 1 or completed != int(saved) or (files > 0) != saved:
            raise ValueError("Incomplete dashboard save evidence")
    elif completed or files:
        raise ValueError("Unexpected completed dashboard save")
    if status in {"monitor_batch_waiting", "monitor_batch_busy", "monitor_batch_no_candidates"} or (
        status == "monitor_batch_cancelled" and reason == "requested_stop"
    ):
        if started or closed is not True:
            raise ValueError("Unexpected active dashboard save")
    return report


def _single_result(batch):
    if (
        batch.get("mode") != "bounded_monitor_candidate_native_batch"
        or not _integer(batch.get("schema_version"), 1, 1)
        or not _integer(batch.get("max_tasks"), 1, 1)
        or not isinstance(batch.get("saved_files"), list)
    ):
        raise ValueError("Expected a one-post batch result")
    if batch["status"] == "monitor_batch_completed" and (
        batch.get("last_stage") != "complete" or batch.get("shared_pending_retained") is not False
    ):
        raise ValueError("Unconfirmed single-post completion")
    return validate_save_result(
        {
            "status": batch["status"],
            "reason": batch.get("reason"),
            "tasks_started": batch["tasks_started"],
            "tasks_completed": batch["tasks_completed"],
            "files_verified": len(batch["saved_files"]),
            "browser_closed": batch["browser_closed"],
        }
    )


def save_exit_code(report):
    return _STATUS_CODES[report["status"]]


def _watch_parent(stream):
    """Authorize only after the parent opens the pipe and sends the launch line.

    EOF, data after the launch line or a broken pipe requests a cooperative
    stop. The reader uses the raw descriptor and never touches SQLite or UI.
    """
    if stream.isatty() or stream.readline(len(_START)) != _START:
        raise _StoppedBeforeLaunch
    stopped = threading.Event()
    fd = stream.fileno()

    def read():
        try:
            os.read(fd, 1)
        except OSError:
            pass
        finally:
            stopped.set()

    threading.Thread(target=read, name="dashboard-save-stop", daemon=True).start()
    return stopped.is_set


def run_dashboard_child(watch_root, legacy_root, batch_root, *, stream):
    try:
        should_stop = _watch_parent(stream)
        if should_stop():
            raise _StoppedBeforeLaunch
        from image_monitor.monitor_batch_runtime import run_monitor_batch

        report = run_monitor_batch(
            watch_root, legacy_root, batch_root, max_tasks=1, should_stop=should_stop
        )
        return _single_result(report)
    except _StoppedBeforeLaunch:
        return _fallback(cancelled=True)
    except Exception:
        return _fallback()


def run_dashboard_save(watch_root, legacy_root, batch_root, *, should_stop=None):
    """Request one native attempt, preserving the settled outcome after a stop."""
    if _requested(should_stop):
        return _fallback(cancelled=True)
    try:
        args = [sys.executable, "-m", "image_monitor", "monitor-save-one"]
        for flag, root in (
            ("--watch-root", watch_root),
            ("--legacy-root", legacy_root),
            ("--work-root", batch_root),
        ):
            args.extend((flag, str(Path(root).absolute())))
        code, raw, failed, _ = _run_child(args, should_stop, start_line=_START)
        if failed or len(raw) > 1024:
            return _fallback()
        report = validate_save_result(
            json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_unique_object,
                parse_float=_reject_number,
                parse_constant=_reject_number,
            )
        )
        if type(code) is not int or save_exit_code(report) != code:
            return _fallback()
        return report
    except _StoppedBeforeLaunch:
        return _fallback(cancelled=True)
    except Exception:
        return _fallback()
