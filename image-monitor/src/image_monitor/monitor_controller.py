"""One background discovery worker controlled by a local status interface.

The application holds the separate monitor-purpose lease for its whole life.
Every scan still takes the existing shared scan lease in run_watch_trial. No
SQLite connection or Playwright object crosses into the HTTP/UI thread.
"""

import math
import re
import shutil
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from image_monitor.artifact_files import _plain_path
from image_monitor.monitor_settings import (
    load_monitor_settings,
    save_monitor_settings,
    validate_interval,
)
from image_monitor.queue import QueueError, QueueStore
from image_monitor.watch_planner import next_poll_at
from image_monitor.watch_runtime import (
    _control,
    _eligibility,
    _stamp,
    _stored_time,
    run_watch_trial,
)
from image_monitor.watch_store import WatchScope, WatchStore

MONITOR_SCOPE = WatchScope("목록 감시", "normal", "comic_new6", "ai", "search_subject_memo")
MIN_FREE_BYTES = 256 * 1024 * 1024
BUSY_BACKOFF_SECONDS = 15
_GAP_REASONS = {
    "excluded_rows_unverified",
    "order_unverified",
    "historical_cursor_unverified",
    "pagination_ambiguous",
    "max_pages",
    "pagination_missing",
    "overlap_incomplete",
    "empty_baseline_requires_end",
    "anchor_not_reached",
    "pagination_cycle",
    "pagination_unverified",
    "list_profile_unverified_or_incomplete",
    "list_transport_or_inspection_failure",
    "requested_stop",
}
_REPORT_STATUSES = {
    "watch_test_completed",
    "watch_waiting",
    "watch_busy",
    "watch_test_failed",
    "watch_test_partial",
    "watch_test_cancelled",
}


def _safe_error_type(value):
    return (
        value
        if isinstance(value, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}", value)
        else None
    )


class _Clock:
    def now(self):
        return datetime.now(UTC)


class MonitorController:
    """Start stopped and record only newly observed list candidates.

    This new watch scope leaves the earlier trial's baseline and candidates
    intact. Its first valid scan creates a new-only baseline. Missing coverage
    later pauses for review instead of resetting that baseline.

    Tests may inject clock.now() and clock.wait_for(event, seconds). The latter
    advances a controlled clock without real minute-long waits.
    """

    def __init__(self, work_root: Path, *, run_cycle=run_watch_trial, clock=None):
        self.work_root = _plain_path(Path(work_root).absolute()).resolve()
        if str(self.work_root).startswith("\\\\"):
            raise QueueError("A local monitor work root is required")
        self.work_root.mkdir(parents=True, exist_ok=True)
        self.database = _plain_path(self.work_root / "watch.sqlite")
        self._clock = clock or _Clock()
        _stamp(self._clock.now())
        self._run_cycle = run_cycle
        settings = load_monitor_settings(self.work_root)
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._pause = threading.Event()
        self._stop = threading.Event()
        self._thread = None
        self._extra_due = None
        self._last_finished = None
        self._seen_database = self.database.exists()
        self._state = {
            "scope_label": "만화 · ai · 제목+내용",
            "phase": "stopped",
            "browser": "chrome",
            "interval_seconds": settings["interval_seconds"],
            "completed_cycles": 0,
            "candidate_count": 0,
            "current_cycle_new": 0,
            "new_candidates": 0,
            "baseline_initialized": False,
            "last_scan_at": None,
            "next_eligible_at": None,
            "remaining_seconds": 0,
            "last_scan_status": None,
            "gap_reason": None,
            "reason": None,
            "error_type": None,
            "browser_closed": True,
            "settings_editable": True,
        }
        try:
            self._read_source()
        except Exception as error:
            self._set(
                phase="needs_review",
                reason="stored_monitor_data_invalid",
                error_type=type(error).__name__,
            )

    def _set(self, **values):
        with self._lock:
            self._state.update(values)

    def status(self):
        with self._lock:
            result = self._state.copy()
            result["settings_editable"] = result["phase"] == "stopped" and not self.is_alive()
            due = result["next_eligible_at"]
            result["remaining_seconds"] = (
                max(0, math.ceil((_stored_time(due) - self._clock.now()).total_seconds()))
                if due is not None
                else 0
            )
            return result

    def is_alive(self):
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def wait_stopped(self, timeout=None):
        with self._lock:
            thread = self._thread
        if thread is None:
            return True
        if thread is threading.current_thread():
            return False
        thread.join(timeout)
        return not thread.is_alive()

    def configure(self, interval_seconds):
        interval = validate_interval(interval_seconds)
        with self._lock:
            if self.is_alive() or self._state["phase"] != "stopped":
                raise QueueError("Stop the monitor before changing its interval")
            save_monitor_settings(self.work_root, interval)
            self._state["interval_seconds"] = interval
            return self.status()

    def start(self):
        with self._lock:
            if self.is_alive():
                if self._pause.is_set() and not self._stop.is_set():
                    self._pause.clear()
                    self._wake.set()
                    self._state.update(phase="starting", reason=None)
                return self.status()
            if self._state["phase"] == "needs_review":
                raise QueueError("The monitor requires review before another start")
            self._stop.clear()
            self._pause.clear()
            self._wake.clear()
            self._state.update(phase="starting", reason=None, error_type=None)
            self._thread = threading.Thread(
                target=self._work, name="image-monitor-discovery", daemon=True
            )
            self._thread.start()
            return self.status()

    def pause(self):
        with self._lock:
            if self.is_alive() and not self._stop.is_set():
                self._pause.set()
                self._wake.set()
                self._state["phase"] = "pausing"
            return self.status()

    def stop(self):
        with self._lock:
            if self.is_alive():
                self._stop.set()
                self._wake.set()
                self._state["phase"] = "stopping"
            elif self._state["browser_closed"] is True:
                self._state["phase"] = "stopped"
            return self.status()

    def _requested_stop(self):
        return self._stop.is_set() or self._pause.is_set()

    def _wait(self, seconds):
        wait_for = getattr(self._clock, "wait_for", None)
        if wait_for is None:
            self._wake.wait(seconds)
        else:
            wait_for(self._wake, seconds)
        self._wake.clear()

    def _read_source(self):
        now = self._clock.now()
        _stamp(now)
        if not self.database.exists():
            if self._seen_database:
                raise QueueError("The existing monitor database disappeared")
            return "ready", now
        _plain_path(self.database)
        self._seen_database = True
        with QueueStore(self.database, read_only=True) as queue:
            if queue.summary()["posts"] or queue.summary()["jobs"]:
                raise QueueError("The discovery monitor requires its separate watch database")
            state = WatchStore(queue).get_state(MONITOR_SCOPE)
            eligibility, due = _eligibility(queue, state, now)
            control = _control(state)
            finished = control.get("finished_at")
            if finished is not None:
                self._last_finished = _stored_time(finished)
                due = (
                    max(
                        due,
                        next_poll_at(
                            self._last_finished, interval_seconds=self._state["interval_seconds"]
                        ),
                    )
                    if due is not None
                    else None
                )
            count = 0
            if queue.schema_version >= 4:
                count = queue.connection.execute(
                    "SELECT COUNT(*) FROM watch_candidates WHERE watch_name=? AND gallery_type=? "
                    "AND gallery_id=? AND keyword=? AND search_type=?",
                    MONITOR_SCOPE.key(),
                ).fetchone()[0]
            latest = state["latest_scan"]
            result = latest["result"] if latest else {}
            self._set(
                candidate_count=count,
                baseline_initialized=state["baseline"] is not None,
                last_scan_at=_stamp(self._last_finished) if finished is not None else None,
                gap_reason=(
                    result.get("gap_reason")
                    if result.get("gap_reason") in _GAP_REASONS
                    else "scan_requires_review"
                    if result.get("gap_reason") is not None
                    else None
                ),
            )
            return eligibility, due

    def _review(self, reason, *, error_type=None):
        self._set(
            phase="needs_review",
            reason=reason,
            error_type=_safe_error_type(error_type),
            next_eligible_at=None,
        )

    def _after_cycle(self, report):
        if not isinstance(report, dict):
            raise QueueError("The monitor cycle did not return a report")
        status = report.get("status")
        if not isinstance(status, str) or status not in _REPORT_STATUSES:
            raise QueueError("The monitor cycle status is invalid")
        persisted = report.get("cycles_completed", 0)
        added = report.get("new_candidates", 0)
        if (
            type(persisted) is not int
            or not 0 <= persisted <= 1
            or type(added) is not int
            or not 0 <= added <= 1000
            or (persisted == 0 and added != 0)
        ):
            raise QueueError("The monitor cycle has invalid discovery counts")
        closed = report.get("browser_closed")
        with self._lock:
            self._state.update(
                last_scan_status=status, browser_closed=closed, current_cycle_new=added
            )
            self._state["new_candidates"] += added
        eligibility, _ = self._read_source()
        if eligibility == "blocked":
            self._review("access_block_requires_review", error_type=report.get("error_type"))
            return False
        if closed is not True:
            self._review("owned_browser_cleanup_unconfirmed", error_type=report.get("error_type"))
            return False
        if status == "watch_busy":
            self._extra_due = self._clock.now() + timedelta(seconds=BUSY_BACKOFF_SECONDS)
            self._set(reason="another_worker_active")
            return True
        due_value = report.get("next_eligible_at_local")
        if due_value is not None:
            self._extra_due = _stored_time(due_value)
        http_status = None
        cycles = report.get("cycles") or []
        if cycles:
            http_status = cycles[-1].get("http_status")
        if status == "watch_test_completed":
            if persisted != 1:
                raise QueueError("The completed monitor cycle has invalid counts")
            if self._extra_due is None and self._last_finished is None:
                raise QueueError("The completed monitor cycle has no durable next time")
            with self._lock:
                self._state["completed_cycles"] += 1
                self._state["reason"] = None
            return True
        if status == "watch_waiting" or http_status in {429, 503}:
            if self._extra_due is None:
                raise QueueError("The waiting monitor cycle has no next time")
            self._set(reason="service_wait" if http_status in {429, 503} else "persisted_cooldown")
            return True
        if status == "watch_test_cancelled" and self._requested_stop():
            return True
        reason = report.get("reason")
        allowed_reasons = {
            "access_block_requires_review",
            "list_profile_unverified_or_incomplete",
            "list_transport_or_inspection_failure",
            "watch_trial_stopped",
            "owned_browser_not_closed",
        }
        self._review(
            reason if reason in allowed_reasons else "scan_requires_review",
            error_type=report.get("error_type"),
        )
        return False

    def _work(self):
        try:
            while not self._stop.is_set():
                if self._pause.is_set():
                    self._set(phase="paused")
                    self._wait(60)
                    continue
                eligibility, due = self._read_source()
                if eligibility == "blocked":
                    self._review("access_block_requires_review")
                    break
                if self._extra_due is not None:
                    due = max(due, self._extra_due)
                self._set(next_eligible_at=_stamp(due))
                remaining = (due - self._clock.now()).total_seconds()
                if remaining > 0:
                    self._set(phase="waiting")
                    self._wait(remaining)
                    continue
                if self._requested_stop():
                    continue
                if shutil.disk_usage(self.work_root).free < MIN_FREE_BYTES:
                    self._review("insufficient_free_space")
                    break
                self._set(phase="scanning", reason=None, browser_closed=None)
                report = self._run_cycle(
                    self.work_root,
                    "chrome",
                    scope=MONITOR_SCOPE,
                    cycles=1,
                    interval_seconds=self._state["interval_seconds"],
                    should_stop=self._requested_stop,
                    clock=self._clock,
                )
                if not self._after_cycle(report):
                    break
        except BaseException as error:
            self._review("monitor_stopped_for_review", error_type=type(error).__name__)
        finally:
            with self._lock:
                if self._state["phase"] != "needs_review":
                    self._state["phase"] = "stopped"
