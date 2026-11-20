"""Serial Chrome discovery and native image collection under the dashboard lease."""

from copy import deepcopy
from datetime import timedelta

from image_monitor import PUBLIC_VERSION
from image_monitor.artifact_files import _plain_path
from image_monitor.monitor_auto_discovery import run_auto_discovery
from image_monitor.monitor_clock import stop_requested, wait_until
from image_monitor.monitor_collect import collect_session_turn
from image_monitor.monitor_save_ledger import _roots
from image_monitor.monitor_settings import load_monitor_settings
from image_monitor.watch_lock import WatchRunBusy, watch_run_lock
from image_monitor.watch_runtime import _Clock, _stamp, _stored_time
from image_monitor.watch_store import MONITOR_SCOPE

_FINISHED_COLLECTIONS = {
    "monitor_collect_no_candidates",
    "monitor_collect_limit",
    "monitor_collect_unavailable",
    "monitor_collect_already_handled",
    "monitor_collect_saved",
}


def _finish(report, status, reason):
    report.update(status="auto_monitor_" + status, reason=reason)
    return report


def _progress(report, phase, on_progress):
    report.update(phase=phase)
    if on_progress is not None:
        on_progress(deepcopy(report))


def _count(result, key, maximum=None):
    value = result[key]
    if type(value) is not int or value < 0 or (maximum is not None and value > maximum):
        raise ValueError("Invalid monitor turn count")
    return value


def _record_collection(report, turn):
    # Both adapters return public, bounded reports. Keep only the last outcome
    # and last verified files; a multi-day session never accumulates a history.
    last = {key: turn[key] for key in ("status", "reason")}
    if turn.get("setup_retry_started"):
        last["setup_retry_started"] = True
    if turn.get("save") is not None:
        for key in ("worker_last_stage", "native_stage", "error_type", "completion_setup_reason"):
            if turn["save"].get(key) is not None:
                last[key] = turn["save"][key]
    report["last_collection"] = last
    report["new_details_checked"] += _count(turn, "new_details_checked", 1)
    started = turn["native_save_tasks_started"]
    if started is None:
        # A writer may have started without returning a complete worker receipt.
        report["native_save_tasks_started"] = None
    elif report["native_save_tasks_started"] is not None:
        report["native_save_tasks_started"] += _count(turn, "native_save_tasks_started", 1)
    count = _count(turn, "files_verified", 2)
    if turn["status"] == "monitor_collect_saved":
        if not (
            turn["browser_closed"] is True
            and started == 1
            and count >= 1
            and count == len(turn["saved_files"])
        ):
            raise ValueError("Missing verified collection result")
        report["posts_saved"] += 1
        report["files_verified"] += count
        report["last_saved_files"] = deepcopy(turn["saved_files"])
    elif count:
        raise ValueError("Unconfirmed collection returned verified files")


def _session(roots, report, *, clock, should_stop, on_progress, scan_runner, collect_runner):
    interval = load_monitor_settings(roots[0])["interval_seconds"]
    report["interval_seconds"] = interval
    list_interval = timedelta(seconds=interval)
    list_due = None
    due = None
    phase = "scanning"
    retried_wait = False
    while True:
        if stop_requested(should_stop):
            return _finish(report, "stopped", "requested_stop")
        if due is not None:
            report["next_eligible_at"] = _stamp(due)
            if due > clock.now():
                _progress(report, "waiting", on_progress)
                if stop_requested(should_stop):
                    return _finish(report, "stopped", "requested_stop")
                if report["max_cycles"] is not None and due > clock.now() + list_interval:
                    return _finish(report, "waiting", "persisted_cooldown")
                if not wait_until(clock, due, should_stop):
                    return _finish(report, "stopped", "requested_stop")
            due = None

        _progress(report, phase, on_progress)
        if stop_requested(should_stop):
            return _finish(report, "stopped", "requested_stop")
        report.update(next_eligible_at=None, browser_closed=None)
        turn_started_at = clock.now()
        if phase == "scanning":
            turn = scan_runner(
                roots[0], clock=clock, interval_seconds=interval, should_stop=should_stop
            )
        else:
            turn = collect_runner(*roots, clock=clock, should_stop=should_stop)
        status = turn["status"]
        reason = turn["reason"]
        closed = turn["browser_closed"]
        report["browser_closed"] = closed
        due = _stored_time(turn["next_eligible_at"]) if turn["next_eligible_at"] else None
        report["next_eligible_at"] = _stamp(due) if due is not None else None
        if phase == "scanning":
            report["last_list"] = {"status": status, "reason": reason}
        else:
            _record_collection(report, turn)

        if status in {"cancelled", "monitor_collect_cancelled"}:
            if closed is False or (phase == "collecting" and closed is not True):
                return _finish(report, "review", "owned_browser_cleanup_unconfirmed")
            end = "stopped" if stop_requested(should_stop) else "cancelled"
            return _finish(report, end, "requested_stop")
        if status in {"busy", "monitor_collect_busy"}:
            return _finish(report, "busy", reason)
        if status == "blocked" or reason in {
            "service_access_blocked",
            "access_block_requires_review",
        }:
            return _finish(report, "blocked", reason)
        if phase == "collecting" and turn["native_save_tasks_started"] is None:
            return _finish(report, "review", reason or "native_save_attempt_unconfirmed")
        if status in {"waiting", "monitor_collect_waiting"}:
            if closed is False or (phase == "collecting" and closed is not True):
                return _finish(report, "review", "owned_browser_cleanup_unconfirmed")
            # Check against the start of the turn, so a deadline that expires
            # while this call finishes can be retried without a stale-deadline spin.
            if due is None or due <= turn_started_at:
                return _finish(report, "review", "invalid_wait_deadline")
            if phase == "scanning" or (
                turn["new_details_checked"] == 0 and turn["native_save_tasks_started"] == 0
            ):
                # One bounded trial can wait through an ordinary cooldown. A
                # continuing rate limit or moving deadline gets a result now.
                if report["max_cycles"] is not None and (retried_wait or reason == "service_wait"):
                    return _finish(report, "waiting", reason)
                retried_wait = True
                continue
            # A detail/navigation attempt already spent this list's budget.
            # Its candidate is durable and can be considered after the next scan.
        elif phase == "scanning" and status in {"complete", "partial", "baseline"}:
            if closed is not True:
                return _finish(report, "review", "owned_browser_cleanup_unconfirmed")
            report["list_checks"] += 1
            report["partial_list_checks"] += int(status == "partial")
            report["new_candidates"] += _count(turn, "new_candidates")
            list_due = max(clock.now() + list_interval, due or clock.now())
            report["next_eligible_at"] = _stamp(list_due)
            if status != "baseline":
                phase = "collecting"
                retried_wait = False
                due = None  # The collector checks its own shared service deadline.
                continue
        elif phase != "collecting" or status not in _FINISHED_COLLECTIONS or closed is not True:
            return _finish(report, "review", reason or "automatic_turn_requires_review")

        report["cycles_completed"] += 1
        phase = "scanning"
        retried_wait = False
        due = max(list_due, due) if due is not None else list_due
        report["next_eligible_at"] = _stamp(due)
        if stop_requested(should_stop):
            return _finish(report, "stopped", "requested_stop")
        if report["cycles_completed"] == report["max_cycles"]:
            return _finish(report, "completed", "cycle_limit_reached")


def run_auto_monitor(
    watch_root,
    legacy_root,
    work_root,
    *,
    max_cycles=None,
    clock=None,
    should_stop=None,
    on_progress=None,
    scan_runner=run_auto_discovery,
    collect_runner=collect_session_turn,
):
    """Alternate list checks and bounded collection turns until stopped or the limit is reached."""
    report = {
        "schema_version": 1,
        "program_version": PUBLIC_VERSION,
        "mode": "automatic_monitor_session",
        "status": "auto_monitor_running",
        "phase": "starting",
        "reason": None,
        "max_cycles": max_cycles,
        "interval_seconds": None,
        "cycles_completed": 0,
        "list_checks": 0,
        "partial_list_checks": 0,
        "new_candidates": 0,
        "new_details_checked": 0,
        "native_save_tasks_started": 0,
        "posts_saved": 0,
        "files_verified": 0,
        "last_saved_files": [],
        "last_list": None,
        "last_collection": None,
        "next_eligible_at": None,
        "browser_closed": None,
    }
    try:
        if max_cycles is not None and (type(max_cycles) is not int or max_cycles < 1):
            return _finish(report, "review", "invalid_cycle_limit")
        _progress(report, "starting", on_progress)
        if stop_requested(should_stop):
            return _finish(report, "stopped", "requested_stop")
        roots = _roots(watch_root, legacy_root, work_root)
        roots[0].mkdir(parents=True, exist_ok=True)
        database = _plain_path(roots[0] / "watch.sqlite")
        with watch_run_lock(database, MONITOR_SCOPE, purpose="monitor"):
            return _session(
                roots,
                report,
                clock=clock or _Clock(),
                should_stop=should_stop,
                on_progress=on_progress,
                scan_runner=scan_runner,
                collect_runner=collect_runner,
            )
    except WatchRunBusy:
        return _finish(report, "busy", "another_monitor_is_open")
    except KeyboardInterrupt:
        return _finish(report, "cancelled", "requested_stop")
    except Exception:
        return _finish(report, "review", "automatic_session_requires_review")


def auto_monitor_exit_code(report):
    if report["status"] == "auto_monitor_cancelled":
        return 130
    if report["status"] in {
        "auto_monitor_completed",
        "auto_monitor_stopped",
        "auto_monitor_waiting",
        "auto_monitor_busy",
    }:
        return 0
    return 2
