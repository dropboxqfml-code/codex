"""Schedule headless list discovery and a single native writer under the monitor lease."""

from contextlib import contextmanager
from copy import deepcopy
from datetime import timedelta
from threading import Event, Thread

from image_monitor import PUBLIC_VERSION
from image_monitor.artifact_files import _plain_path
from image_monitor.candidate_save_policy import MAX_MONITOR_SAVE_IMAGES
from image_monitor.monitor_auto_discovery import run_auto_discovery
from image_monitor.monitor_clock import stop_requested, wait_until
from image_monitor.monitor_collect import collect_session_turn, list_checks_during_save
from image_monitor.monitor_date_report import public_date_cell_checks
from image_monitor.monitor_gap_report import checked_gap_route, checked_window_starts
from image_monitor.monitor_list_history import previous_list_checks
from image_monitor.monitor_list_review import previous_list_review, public_list_review
from image_monitor.monitor_save_ledger import _root, _roots
from image_monitor.monitor_settings import MAX_CATCH_UP_SCANS, load_monitor_settings
from image_monitor.monitor_setup_retry import FOREGROUND_RETRY_REASON, PARTIAL_RETRY_REASON
from image_monitor.post_worker import share_setup_diagnostics
from image_monitor.queue import QueueStore
from image_monitor.watch_history import (
    HEAD_JOIN_METHODS,
    HISTORICAL_ROUTE_REASONS,
    MAX_HISTORICAL_PAGE,
)
from image_monitor.watch_lock import WatchRunBusy, watch_list_lock, watch_run_lock
from image_monitor.watch_runtime import DEFAULT_SCOPE, _Clock, _stamp, _stored_time
from image_monitor.watch_store import MAX_MONITOR_SCAN_PAGES, MONITOR_SCOPE, WatchStore

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


def _record_list_pages(report, turn, *, during_native_save=False):
    limit = _count(turn, "page_limit", MAX_MONITOR_SCAN_PAGES)
    count = _count(turn, "pages_checked", limit)
    numbers = turn["visited_page_numbers"]
    if (
        not isinstance(numbers, list)
        or not count
        or len(numbers) != count
        or any(type(n) is not int or n < 1 for n in numbers)
        or (limit == 1) != (turn["status"] == "baseline")
    ):
        raise ValueError("Invalid verified list page numbers")
    last = report["last_list"]
    expected = list(range(1, count + 1))
    historical = "historical_status" in turn or "historical_boundary_page" in turn
    if historical and ("recovery_status" in turn or "search_window_start_visits" in turn):
        raise ValueError("Conflicting list routing evidence")
    if "recovery_status" in turn:
        last.update(checked_gap_route(turn, numbers, limit))
        expected = numbers
    elif "search_window_start_visits" in turn:
        last.update(checked_window_starts(turn, numbers, limit))
        expected = numbers
    elif historical:
        boundary = turn["historical_boundary_page"]
        status = turn["historical_status"]
        if (
            limit != MAX_MONITOR_SCAN_PAGES
            or type(boundary) is not int
            or not 4 <= boundary < MAX_HISTORICAL_PAGE
            or status not in ("extended", "boundary_changed", "recent_pages_only")
        ):
            raise ValueError("Invalid historical list boundary")
        if status != "recent_pages_only":
            if count not in (3, 4):
                raise ValueError("Missing historical list pages")
            expected = [1, 2, boundary, boundary + 1][:count]
    if numbers != expected:
        raise ValueError("Unexpected verified list page sequence")
    last.update(pages_checked=count, page_limit=limit, visited_page_numbers=numbers.copy())
    recovery_trial = report.get("mode") == "list_recovery_test"
    if report.get("mode") == "automatic_monitor_session" and report.get("max_cycles") == 2:
        last["during_native_save"] = during_native_save
        last["new_candidates"] = _count(turn, "new_candidates")
    elif recovery_trial and report.get("max_cycles") in (2, MAX_CATCH_UP_SCANS):
        last["new_candidates"] = _count(turn, "new_candidates")
    if checks := public_date_cell_checks(turn.get("date_cell_checks"), numbers):
        last["date_cell_checks"] = checks
    if "historical_status" in turn:
        last.update(historical_boundary_page=boundary, historical_status=status)
        reason = turn.get("historical_reason")
        if isinstance(reason, str) and reason in HISTORICAL_ROUTE_REASONS[status]:
            last["historical_reason"] = reason
            join = turn.get("head_join")
            if (
                status != "recent_pages_only"
                and isinstance(join, str)
                and join in HEAD_JOIN_METHODS
            ):
                last["head_join"] = join
    history_limit = (
        MAX_CATCH_UP_SCANS if recovery_trial and report["max_cycles"] == MAX_CATCH_UP_SCANS else 2
    )
    report["recent_list_checks"] = [*report["recent_list_checks"], last.copy()][-history_limit:]
    if limit > 2:
        report["gap_followup_checks"] += 1
        report["gap_followups_completed"] += int(turn["status"] == "complete")


def _record_collection(report, turn):
    last = {key: turn[key] for key in ("status", "reason")}
    search = turn.get("search")
    if isinstance(search, dict) and search.get("previous_failure_reason") in (
        FOREGROUND_RETRY_REASON,
        PARTIAL_RETRY_REASON,
    ):
        last["previous_failure_reason"] = search["previous_failure_reason"]
    if turn.get("setup_retry_started"):
        last["setup_retry_started"] = True
    if turn.get("partial_retry_started") is True:
        last["partial_retry_started"] = True
        last["previously_verified_files"] = _count(
            turn, "previously_verified_files", MAX_MONITOR_SAVE_IMAGES - 1
        )
    if turn.get("save") is not None:
        for key in ("worker_last_stage", "native_stage", "error_type"):
            if turn["save"].get(key) is not None:
                last[key] = turn["save"][key]
        focus = turn["save"].get("focus_at_failure")
        if last.get("worker_last_stage") in (
            "automatic_foreground_check",
            "pre_input_check",
        ) and isinstance(focus, dict):
            flags = {
                key: focus[key]
                for key in (
                    "target_exists",
                    "target_foreground",
                    "belongs_to_target",
                    "foreground_identified",
                )
                if type(focus.get(key)) is bool
            }
            if flags:
                last["focus_at_failure"] = flags
        last.update(share_setup_diagnostics(turn["save"], stage_key="worker_last_stage"))
    report["last_collection"] = last
    report["new_details_checked"] += _count(turn, "new_details_checked", 1)
    started = turn["native_save_tasks_started"]
    if started is None:
        # A writer may have started without returning a complete worker receipt.
        report["native_save_tasks_started"] = None
    elif report["native_save_tasks_started"] is not None:
        report["native_save_tasks_started"] += _count(turn, "native_save_tasks_started", 1)
    count = _count(turn, "files_verified", MAX_MONITOR_SAVE_IMAGES)
    new_count = 0
    if turn["status"] == "monitor_collect_saved":
        if not (
            turn["browser_closed"] is True
            and started == 1
            and count >= 1
            and count == len(turn["saved_files"])
        ):
            raise ValueError("Missing verified collection result")
        previous = 0
        new_count = count
        if last.get("partial_retry_started"):
            previous = last["previously_verified_files"]
            new_count = _count(turn, "newly_saved_files", MAX_MONITOR_SAVE_IMAGES - 1)
            if not (
                0 < new_count < count
                and previous + new_count == count
                and not last.get("setup_retry_started")
                and last.get("previous_failure_reason") == PARTIAL_RETRY_REASON
            ):
                raise ValueError("Invalid verified partial-retry result")
            last["newly_saved_files"] = new_count
        elif last.get("previous_failure_reason") == PARTIAL_RETRY_REASON or (
            "previously_verified_files" in turn or "newly_saved_files" in turn
        ):
            raise ValueError("Unexpected partial counts for an ordinary collection")
        report["posts_saved"] += 1
        report["files_verified"] += count
        report["previously_verified_files"] += previous
        report["newly_saved_files"] += new_count
        report["last_saved_files"] = deepcopy(turn["saved_files"])
    elif count:
        raise ValueError("Unconfirmed collection returned verified files")
    if "recent_collection_attempts" in report:
        attempts = report["recent_collection_attempts"]
        attempts.append(
            {
                "status": last["status"],
                "reason": last["reason"],
                "new_details_checked": turn["new_details_checked"],
                "newly_saved_files": new_count,
            }
        )
        del attempts[:-2]


def _verified_list(report, turn, finished, interval, *, during_native_save=False):
    report["last_list"] = {"status": turn["status"], "reason": turn["reason"]}
    _record_list_pages(report, turn, during_native_save=during_native_save)
    report["list_checks"] += 1
    report["partial_list_checks"] += int(turn["status"] == "partial")
    report["new_candidates"] += _count(turn, "new_candidates")
    due = finished + interval
    if turn["next_eligible_at"]:
        due = max(due, _stored_time(turn["next_eligible_at"]))
    return due


def _record_inspection_retry(report, turn):
    if turn.get("reason") == "inspection_retry_due" and (
        review := public_list_review(turn.get("review"))
    ):
        report["inspection_retries_scheduled"] += 1
        report["last_inspection_retry"] = review


class _NativeSaveLists:
    """During a local save, keep at most one pending collection from the newest list."""

    def __init__(self, root, report, clock, should_stop, scan_runner, interval, due, on_progress):
        self.root, self.report, self.clock = root, report, clock
        self.should_stop, self.scan_runner = should_stop, scan_runner
        self.interval, self.due = interval, due
        self.checked = 0
        self.terminal = None
        self.on_progress = on_progress

    @contextmanager
    def window(self, lease, native_due):
        end = Event()

        def watch():
            try:
                self.due = max(native_due, self.due)
                with lease.borrow_for_list():
                    while not end.is_set() and not stop_requested(self.should_stop):
                        remaining = (self.due - self.clock.now()).total_seconds()
                        if remaining > 0:
                            # A short save wakes this thread as soon as its browser closes.
                            end.wait(min(remaining, 0.5))
                            continue
                        started = self.clock.now()
                        if self.terminal:
                            _record_inspection_retry(self.report, self.terminal[0])
                            self.terminal = None
                        turn = self.scan_runner(
                            self.root,
                            clock=self.clock,
                            interval_seconds=self.report["interval_seconds"],
                            should_stop=self.should_stop,
                        )
                        if (
                            turn["status"] not in {"complete", "partial"}
                            or turn["browser_closed"] is not True
                        ):
                            self.terminal = turn, started
                            if (
                                turn["status"] == "waiting"
                                and turn["browser_closed"] is not False
                                and self.report["max_cycles"] is None
                                and turn["next_eligible_at"]
                            ):
                                due = _stored_time(turn["next_eligible_at"])
                                if due > started:
                                    # If the save ends first, hand the wait back to the
                                    # owner. A longer save can resume here once eligible.
                                    self.due = due
                                    continue
                            break
                        self.terminal = None
                        self.due = _verified_list(
                            self.report,
                            turn,
                            self.clock.now(),
                            self.interval,
                            during_native_save=True,
                        )
                        if self.checked:
                            # Its candidates are durable. The newest scan gets the next writer turn.
                            self.report["cycles_completed"] += 1
                        self.checked += 1
                        self.report["list_checks_during_save"] += 1
                        if self.on_progress is not None:
                            self.on_progress(
                                deepcopy(self.report) | {"phase": "scanned_during_save"}
                            )
                        if self.report["list_checks"] == self.report["max_cycles"]:
                            break
            except Exception:
                self.terminal = (
                    {
                        "status": "review",
                        "reason": "concurrent_list_check_unconfirmed",
                        "browser_closed": None,
                        "next_eligible_at": None,
                    },
                    self.clock.now(),
                )

        thread = Thread(target=watch, name="image-monitor-headless-list")
        thread.start()
        try:
            yield
        finally:
            end.set()
            thread.join()


def _catch_up_pause(checks):
    """A new segment may reset depth. A verified bookmark successor must move it forward."""
    current = checks[-1]
    previous = checks[-2] if len(checks) >= 2 else None
    status = current.get("recovery_status")
    if current["pages_checked"] != MAX_MONITOR_SCAN_PAGES:
        return "recovery_followup_deferred"
    if current.get("recovery_route") == "recent" and status in {"segment_queued", "head_rejoined"}:
        if previous and previous.get("recovery_route") == "recent":
            return "recovery_progress_stalled"
        return None
    if current.get("recovery_route") != "bookmark" or status not in {
        "advanced",
        "frontier_relocated",
        "overlap_pending",
        "segment_rejoined",
    }:
        return "recovery_followup_deferred"
    if (
        status != "segment_rejoined"
        and previous
        and current["recovery_depth"] <= previous["recovery_depth"]
    ):
        return "recovery_progress_stalled"
    return None


def _session(roots, report, *, clock, should_stop, on_progress, scan_runner, collect_runner):
    interval = load_monitor_settings(roots[0])["interval_seconds"]
    report["interval_seconds"] = interval
    list_interval = timedelta(seconds=interval)
    follow_gap = report["mode"] == "list_recovery_test" and report["max_cycles"] in (
        2,
        MAX_CATCH_UP_SCANS,
    )
    catch_up = follow_gap and report["max_cycles"] == MAX_CATCH_UP_SCANS
    list_attempts = 0
    list_due = None
    due = None
    phase = "scanning"
    retried_wait = False
    inspection_retry_pending = False
    pending_scan = None
    order_retry_pending = False
    while True:
        if pending_scan is None and stop_requested(should_stop):
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
        if pending_scan is None and stop_requested(should_stop):
            return _finish(report, "stopped", "requested_stop")
        report.update(next_eligible_at=None, browser_closed=None)
        turn_started_at = clock.now()
        overlap = None
        if pending_scan is not None:
            turn, turn_started_at = pending_scan
            pending_scan = None
        elif phase == "scanning":
            turn = scan_runner(
                roots[0], clock=clock, interval_seconds=interval, should_stop=should_stop
            )
        else:
            if report["list_checks"] != report["max_cycles"]:
                overlap = _NativeSaveLists(
                    roots[0],
                    report,
                    clock,
                    should_stop,
                    scan_runner,
                    list_interval,
                    list_due,
                    on_progress,
                )
            with list_checks_during_save(overlap.window if overlap else None):
                turn = collect_runner(*roots, clock=clock, should_stop=should_stop)
        status = turn["status"]
        reason = turn["reason"]
        closed = turn["browser_closed"]
        report["browser_closed"] = closed
        due = _stored_time(turn["next_eligible_at"]) if turn["next_eligible_at"] else None
        report["next_eligible_at"] = _stamp(due) if due is not None else None
        if phase == "scanning":
            if follow_gap and (
                status in {"complete", "partial", "baseline"} or reason == "inspection_retry_due"
            ):
                list_attempts += 1
            report["last_list"] = {"status": status, "reason": reason}
            if status in {"review", "waiting"} and (
                review := public_list_review(turn.get("review"))
            ):
                report["last_list"]["review"] = review
                if (
                    status == "review"
                    and reason == "list_scan_requires_review"
                    and report["mode"] == "automatic_monitor_session"
                    and closed is True
                    and review.get("order_check")
                    and turn.get("order_recheck_at")
                    and not order_retry_pending
                ):
                    due = _stored_time(turn["order_recheck_at"])
                    if due > turn_started_at:
                        order_retry_pending = True
                        report["order_retries_scheduled"] += 1
                        report["last_order_retry"] = review
                        report["last_list"].update(status="waiting", reason="order_retry_due")
                        continue
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
            if phase == "scanning" and reason == "inspection_retry_due":
                if follow_gap and list_attempts >= report["max_cycles"]:
                    return _finish(report, "waiting", reason)
                if inspection_retry_pending:
                    report["last_list"].update(status="review", reason="list_scan_requires_review")
                    report["next_eligible_at"] = None
                    return _finish(report, "review", "list_scan_requires_review")
                inspection_retry_pending = True
                _record_inspection_retry(report, turn)
            if phase == "scanning" or (
                turn["new_details_checked"] == 0 and turn["native_save_tasks_started"] == 0
            ):
                # One bounded trial can wait through an ordinary cooldown. A
                # continuing rate limit or moving deadline gets a result now.
                if report["max_cycles"] is not None and (
                    reason == "service_wait" or (retried_wait and reason != "inspection_retry_due")
                ):
                    return _finish(report, "waiting", reason)
                retried_wait = True
                continue
            # A detail/navigation attempt already spent this list's budget.
            # Its candidate is durable and can be considered after the next scan.
        elif phase == "scanning" and status in {"complete", "partial", "baseline"}:
            inspection_retry_pending = False
            order_retry_pending = False
            if closed is not True:
                return _finish(report, "review", "owned_browser_cleanup_unconfirmed")
            try:
                list_due = _verified_list(report, turn, clock.now(), list_interval)
            except (ValueError, KeyError, TypeError):
                return _finish(report, "review", "invalid_list_page_count")
            report["next_eligible_at"] = _stamp(list_due)
            if status != "baseline" and report["mode"] == "automatic_monitor_session":
                phase = "collecting"
                retried_wait = False
                due = None  # The collector checks its own shared service deadline.
                continue
        elif phase != "collecting" or status not in _FINISHED_COLLECTIONS or closed is not True:
            return _finish(report, "review", reason or "automatic_turn_requires_review")

        report["cycles_completed"] += 1
        phase = "scanning"
        retried_wait = False
        if overlap is not None:
            if overlap.checked:
                list_due = overlap.due
                # Only the latest completed list can start a collection now.
                phase = "collecting"
                due = None
            if overlap.terminal is not None:
                report["cycles_completed"] += int(bool(overlap.checked))
                phase = "scanning"
                pending_scan = overlap.terminal
                due = None
                continue
            if overlap.checked:
                continue
        due = max(list_due, due) if due is not None else list_due
        report["next_eligible_at"] = _stamp(due)
        if stop_requested(should_stop):
            return _finish(report, "stopped", "requested_stop")
        if follow_gap:
            if status == "complete":
                return _finish(report, "completed", "list_coverage_confirmed")
            if catch_up and (pause := _catch_up_pause(report["recent_list_checks"])):
                return _finish(report, "completed", pause)
            if list_attempts >= report["max_cycles"]:
                return _finish(report, "completed", "cycle_limit_reached")
            if not catch_up and report["last_list"].get("recovery_status") not in {
                "head_rejoined",
                "frontier_relocated",
                "segment_rejoined",
                "segment_queued",
                "advanced",
                "overlap_pending",
            }:
                return _finish(report, "completed", "recovery_followup_deferred")
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
    list_only=False,
):
    """Alternate list checks and bounded collection turns until stopped or the limit is reached."""
    report = {
        "schema_version": 1,
        "program_version": PUBLIC_VERSION,
        "mode": "list_recovery_test" if list_only else "automatic_monitor_session",
        "status": "auto_monitor_running",
        "phase": "starting",
        "reason": None,
        "max_cycles": max_cycles,
        "interval_seconds": None,
        "cycles_completed": 0,
        "list_checks": 0,
        "list_checks_during_save": 0,
        "inspection_retries_scheduled": 0,
        "order_retries_scheduled": 0,
        "partial_list_checks": 0,
        "gap_followup_checks": 0,
        "gap_followups_completed": 0,
        "new_candidates": 0,
        "new_details_checked": 0,
        "native_save_tasks_started": 0,
        "posts_saved": 0,
        "files_verified": 0,
        "previously_verified_files": 0,
        "newly_saved_files": 0,
        "last_saved_files": [],
        "last_list": None,
        "previous_list_checks": [],
        "recent_list_checks": [],
        "last_collection": None,
        "next_eligible_at": None,
        "browser_closed": None,
    }
    try:
        if max_cycles is not None and (type(max_cycles) is not int or max_cycles < 1):
            return _finish(report, "review", "invalid_cycle_limit")
        if not list_only and max_cycles == 2:
            report["recent_collection_attempts"] = []
        _progress(report, "starting", on_progress)
        if stop_requested(should_stop):
            return _finish(report, "stopped", "requested_stop")
        if list_only:
            if max_cycles not in (1, 2, MAX_CATCH_UP_SCANS):
                return _finish(report, "review", "invalid_cycle_limit")
            roots = (_root(watch_root),)
        else:
            roots = _roots(watch_root, legacy_root, work_root)
            roots[0].mkdir(parents=True, exist_ok=True)
        database = _plain_path(roots[0] / "watch.sqlite")
        if list_only and not database.is_file():
            return _finish(report, "review", "watch_database_missing")
        with watch_run_lock(database, MONITOR_SCOPE, purpose="monitor"):
            if list_only:
                with (
                    watch_list_lock(database, DEFAULT_SCOPE),
                    QueueStore(database, read_only=True) as queue,
                ):
                    if WatchStore(queue).get_state(MONITOR_SCOPE)["baseline"] is None:
                        return _finish(report, "review", "no_saved_baseline")
            report["previous_list_checks"] = previous_list_checks(roots[0])
            if review := previous_list_review(roots[0]):
                report["previous_list_review"] = review
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
