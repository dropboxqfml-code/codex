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
from image_monitor.candidate_runtime import run_candidate_trial
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
MAX_DETAIL_BATCH = 2
_SCOPE_WHERE = "watch_name=? AND gallery_type=? AND gallery_id=? AND keyword=? AND search_type=?"
_TIME_STATUSES = {"unknown", "before_baseline", "at_or_after_baseline"}
_DETAIL_REASONS = {
    "header_unconfirmed",
    "observation_time_unavailable",
    "observation_before_baseline",
    "published_at_missing",
    "published_at_unparseable",
    "publication_time_inconsistent",
    "published_after_observation",
    "published_before_baseline",
    "published_at_or_after_baseline",
    "candidate_unavailable",
    "candidate_deleted",
    "detail_inspection_failed",
    "candidate_identity_or_baseline_invalid",
}
_DETAIL_STATUSES = {
    "candidate_test_completed",
    "candidate_test_partial",
    "candidate_test_failed",
    "candidate_test_cancelled",
    "candidate_waiting",
    "candidate_busy",
    "candidate_no_baseline",
    "candidate_no_pending",
}
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
_SAVED_STATUSES = {"ready", "empty", "busy", "needs_review", "cancelled"}
_SAVED_REASONS = {
    "existing_saved_candidate_required",
    "another_scan_owns_this_scope",
    "native_save_in_progress",
    "pending_save_requires_review",
    "saved_catalog_requires_review",
    "requested_stop",
    "preview_limit",
}
_SAVED_MIMES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "GIF": "image/gif",
    "BMP": "image/bmp",
}
_SAVED_EXTENSIONS = {
    "JPEG": "jpg",
    "PNG": "png",
    "WEBP": "webp",
    "GIF": "gif",
    "BMP": "bmp",
    "TIFF": "tiff",
}
_SAVED_FILE_FIELDS = (
    "saved_filename",
    "detected_format",
    "file_size",
    "width",
    "height",
    "frames",
    "preview_id",
    "preview_available",
    "group_id",
)
_MAX_PREVIEW_BYTES = 16 * 1024 * 1024
_MAX_TOTAL_PREVIEW_BYTES = 32 * 1024 * 1024


def _load_saved_catalog(*args, **kwargs):
    # Import only when a configured local preview is requested. Opening the
    # discovery screen without a save root keeps the earlier startup behavior.
    from image_monitor.saved_catalog import load_saved_catalog

    return load_saved_catalog(*args, **kwargs)


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

    def __init__(
        self,
        work_root: Path,
        *,
        run_cycle=run_watch_trial,
        run_details=run_candidate_trial,
        clock=None,
        save_root=None,
        batch_root=None,
        catalog_loader=_load_saved_catalog,
    ):
        if batch_root is not None and save_root is None:
            raise QueueError("Batch preview requires the legacy save root")
        self.work_root = _plain_path(Path(work_root).absolute()).resolve()
        if str(self.work_root).startswith("\\\\"):
            raise QueueError("A local monitor work root is required")
        self.work_root.mkdir(parents=True, exist_ok=True)
        self.database = _plain_path(self.work_root / "watch.sqlite")
        self._clock = clock or _Clock()
        _stamp(self._clock.now())
        self._run_cycle = run_cycle
        self._run_details = run_details
        self.save_root = Path(save_root) if save_root is not None else None
        self.batch_root = Path(batch_root) if batch_root is not None else None
        self._catalog_loader = catalog_loader
        self._saved_images = {}
        settings = load_monitor_settings(self.work_root)
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._pause = threading.Event()
        self._stop = threading.Event()
        self._thread = None
        self._extra_due = None
        self._last_finished = None
        self._last_detail_finished = None
        self._seen_database = self.database.exists()
        self._state = {
            "scope_label": "만화 · ai · 제목+내용",
            "phase": "stopped",
            "task_kind": "list",
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
            "detail_count": 0,
            "detail_pending_count": 0,
            "detail_completed_count": 0,
            "detail_failed_count": 0,
            "details": [],
            "saved_status": "disabled" if self.save_root is None else "empty",
            "saved_reason": None,
            "saved_error_type": None,
            "saved_files_verified": 0,
            "saved_preview_count": 0,
            "saved_groups_verified": 0,
            "saved_files_omitted": 0,
            "saved_files": [],
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
            result["details"] = [row.copy() for row in result["details"]]
            result["saved_files"] = [row.copy() for row in result["saved_files"]]
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
            if self._state["phase"] == "needs_review":
                raise QueueError("The monitor requires review before another start")
            if self.is_alive():
                if self._state["task_kind"] == "saved":
                    return self.status()
                if self._pause.is_set() and not self._stop.is_set():
                    self._pause.clear()
                    self._wake.set()
                    self._state.update(phase="starting", reason=None)
                return self.status()
            self._stop.clear()
            self._pause.clear()
            self._wake.clear()
            self._state.update(phase="starting", task_kind="list", reason=None, error_type=None)
            self._thread = threading.Thread(
                target=self._work, name="image-monitor-discovery", daemon=True
            )
            self._thread.start()
            return self.status()

    def refresh_saved(self):
        """Refresh local completed files without doing I/O in the caller thread."""
        with self._lock:
            if (
                self.is_alive()
                or self._state["phase"] != "stopped"
                or self._state["browser_closed"] is not True
            ):
                raise QueueError("Stop the monitor before checking saved images")
            if self.save_root is None:
                return self.status()
            # Revoke all previous IDs before starting another bounded snapshot.
            self._saved_images = {}
            self._state.update(
                task_kind="saved",
                phase="verifying_saved",
                saved_status="checking",
                saved_reason=None,
                saved_error_type=None,
                saved_files_verified=0,
                saved_preview_count=0,
                saved_groups_verified=0,
                saved_files_omitted=0,
                saved_files=[],
            )
            self._stop.clear()
            self._pause.clear()
            self._wake.clear()
            self._thread = threading.Thread(
                target=self._work_saved, name="image-monitor-saved-files", daemon=True
            )
            self._thread.start()
            return self.status()

    def saved_image(self, image_id):
        """Return a cached immutable raster only; never reopen a local path."""
        if not isinstance(image_id, str) or not re.fullmatch(r"[0-9a-f]{32}", image_id):
            return None
        with self._lock:
            return self._saved_images.get(image_id)

    @staticmethod
    def _saved_snapshot(snapshot):
        """Project and validate a bounded loader result before publishing it."""
        summary = getattr(snapshot, "summary", None)
        images = getattr(snapshot, "images", None)
        if not isinstance(summary, dict) or not isinstance(images, dict):
            raise QueueError("Saved catalog did not return a snapshot")
        status = summary.get("status")
        reason = summary.get("reason")
        if status not in _SAVED_STATUSES or reason is not None and reason not in _SAVED_REASONS:
            raise QueueError("Saved catalog status is invalid")
        files = summary.get("files")
        verified, preview_count = summary.get("files_verified"), summary.get("preview_count")
        groups = summary.get("groups_verified", 1 if files else 0)
        omitted = summary.get("files_omitted", 0)
        if (
            not isinstance(files, list)
            or not 0 <= len(files) <= 20
            or type(verified) is not int
            or not 0 <= verified <= 2000
            or type(omitted) is not int
            or omitted != verified - len(files)
            or type(groups) is not int
            or not 0 <= groups <= min(1000, verified)
            or verified > 2 * groups
            or type(preview_count) is not int
            or not 0 <= preview_count <= len(files)
            or len(images) != preview_count
            or status == "ready"
            and (not files or not groups)
            or status != "ready"
            and (files or images or verified or preview_count or groups or omitted)
        ):
            raise QueueError("Saved catalog counts are invalid")
        safe_files, expected_ids, names = [], set(), set()
        group_counts = {}
        total = 0
        for row in files:
            if not isinstance(row, dict):
                raise QueueError("Saved catalog file metadata is invalid")
            name, detected = row.get("saved_filename"), row.get("detected_format")
            available, image_id = row.get("preview_available"), row.get("preview_id")
            group_id = row.get("group_id")
            if (
                not isinstance(name, str)
                or not re.fullmatch(r"00[12]\.(?:jpg|png|webp|gif|bmp|tiff)", name)
                or group_id is not None
                and (not isinstance(group_id, str) or not re.fullmatch(r"[0-9a-f]{32}", group_id))
                or (group_id, name) in names
                or detected not in _SAVED_EXTENSIONS
                or not name.endswith("." + _SAVED_EXTENSIONS[detected])
                or type(available) is not bool
                or any(
                    type(row.get(key)) is not int or not 1 <= row[key] <= 2**31 - 1
                    for key in ("file_size", "width", "height", "frames")
                )
            ):
                raise QueueError("Saved catalog file metadata is invalid")
            names.add((group_id, name))
            group_counts[group_id] = group_counts.get(group_id, 0) + 1
            if available:
                if (
                    detected not in _SAVED_MIMES
                    or not isinstance(image_id, str)
                    or not re.fullmatch(r"[0-9a-f]{32}", image_id)
                    or image_id in expected_ids
                ):
                    raise QueueError("Saved catalog preview identity is invalid")
                expected_ids.add(image_id)
                value = images.get(image_id)
                if (
                    not isinstance(value, tuple)
                    or len(value) != 2
                    or value[0] != _SAVED_MIMES.get(detected)
                    or type(value[1]) is not bytes
                    or not 0 < len(value[1]) <= _MAX_PREVIEW_BYTES
                    or len(value[1]) != row["file_size"]
                ):
                    raise QueueError("Saved catalog preview data is invalid")
                total += len(value[1])
            elif image_id is not None:
                raise QueueError("Unavailable previews cannot retain an image identity")
            safe_files.append({key: row[key] for key in _SAVED_FILE_FIELDS if key in row})
        if (
            set(images) != expected_ids
            or total > _MAX_TOTAL_PREVIEW_BYTES
            or len(group_counts) > groups
            or any(count > 2 for count in group_counts.values())
            or None in group_counts
            and (len(group_counts) != 1 or groups != 1)
            or not omitted
            and len(group_counts) != groups
        ):
            raise QueueError("Saved catalog preview cache is invalid")
        return {
            "saved_status": status,
            "saved_reason": reason,
            "saved_error_type": _safe_error_type(summary.get("error_type")),
            "saved_files_verified": verified,
            "saved_preview_count": preview_count,
            "saved_groups_verified": groups,
            "saved_files_omitted": omitted,
            "saved_files": safe_files,
        }, images.copy()

    def _work_saved(self):
        try:
            options = {"should_stop": self._requested_stop}
            if self.batch_root is not None:
                options["batch_root"] = self.batch_root
            snapshot = self._catalog_loader(self.work_root, self.save_root, **options)
            state, images = self._saved_snapshot(snapshot)
            with self._lock:
                if self._requested_stop():
                    self._state.update(saved_status="cancelled", saved_reason="requested_stop")
                else:
                    self._saved_images = images
                    self._state.update(state)
        except BaseException as error:
            with self._lock:
                self._saved_images = {}
                self._state.update(
                    saved_status="cancelled" if self._requested_stop() else "needs_review",
                    saved_reason="requested_stop"
                    if self._requested_stop()
                    else "saved_catalog_requires_review",
                    saved_error_type=_safe_error_type(type(error).__name__),
                )
        finally:
            with self._lock:
                if self._state["phase"] != "needs_review":
                    self._state["phase"] = "stopped"

    def inspect_candidates(self):
        """Inspect an existing, bounded batch without starting list discovery."""
        with self._lock:
            if (
                self.is_alive()
                or self._state["phase"] != "stopped"
                or self._state["browser_closed"] is not True
            ):
                raise QueueError("Stop the monitor before inspecting existing candidates")
            self._state.update(task_kind="details", reason=None, error_type=None)
            if not self._state["baseline_initialized"]:
                self._state["reason"] = "existing_baseline_required"
                return self.status()
            if self._state["detail_pending_count"] == 0:
                self._state["reason"] = "no_unattempted_candidates"
                return self.status()
            self._stop.clear()
            self._pause.clear()
            self._wake.clear()
            self._state["phase"] = "starting"
            self._thread = threading.Thread(
                target=self._work_details, name="image-monitor-details", daemon=True
            )
            self._thread.start()
            return self.status()

    def pause(self):
        with self._lock:
            if self.is_alive() and not self._stop.is_set():
                self._pause.set()
                self._wake.set()
                if self._state["phase"] != "needs_review":
                    self._state["phase"] = "pausing"
            return self.status()

    def stop(self):
        with self._lock:
            if self.is_alive():
                self._stop.set()
                self._wake.set()
                if self._state["phase"] != "needs_review":
                    self._state["phase"] = "stopping"
            elif self._state["browser_closed"] is True and self._state["phase"] != "needs_review":
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

    def _read_details(self, queue, candidate_count):
        """Read bounded, anonymous metadata; never retain a private DOM result."""
        if queue.schema_version < 5:
            return {
                "detail_count": 0,
                "detail_pending_count": candidate_count,
                "detail_completed_count": 0,
                "detail_failed_count": 0,
                "details": [],
            }
        totals = queue.connection.execute(
            "SELECT COUNT(*),COALESCE(SUM(status='completed'),0),"
            "COALESCE(SUM(status IN ('failed','started')),0) FROM candidate_details WHERE "
            + _SCOPE_WHERE,
            MONITOR_SCOPE.key(),
        ).fetchone()
        pending = queue.connection.execute(
            "SELECT COUNT(*) FROM watch_candidates c WHERE "
            "c.watch_name=? AND c.gallery_type=? AND c.gallery_id=? AND c.keyword=? "
            "AND c.search_type=? AND NOT EXISTS (SELECT 1 FROM candidate_details d WHERE "
            "d.watch_name=c.watch_name AND d.gallery_type=c.gallery_type AND "
            "d.gallery_id=c.gallery_id AND d.keyword=c.keyword AND "
            "d.search_type=c.search_type AND d.post_id=c.post_id)",
            MONITOR_SCOPE.key(),
        ).fetchone()[0]
        # JSON paths select only small scalar values, not the multi-megabyte snapshot.
        rows = queue.connection.execute(
            "SELECT status,json_extract(result_json,'$.classification.time_status'),"
            "json_extract(result_json,'$.classification.reason'),"
            "json_extract(result_json,'$.private_observation.snapshot.image_counts.included_unique'),"
            "json_extract(result_json,'$.private_observation.snapshot.image_counts.pending'),"
            "json_extract(result_json,'$.private_observation.http_status') "
            "FROM candidate_details WHERE "
            + _SCOPE_WHERE
            + " ORDER BY started_at DESC,attempt_id DESC LIMIT 10",
            MONITOR_SCOPE.key(),
        ).fetchall()
        details = []
        for index, row in enumerate(reversed(rows), start=max(1, totals[0] - len(rows) + 1)):
            status, time_status, reason, image_count, pending_images, http_status = row
            if status not in {"started", "completed", "failed"}:
                raise QueueError("Stored detail status is invalid")
            details.append(
                {
                    "order": index,
                    "status": status,
                    "time_status": time_status if time_status in _TIME_STATUSES else "unknown",
                    "reason": (
                        "candidate_deleted"
                        if http_status in {404, 410}
                        else reason
                        if reason in _DETAIL_REASONS
                        else None
                    ),
                    "image_count": (
                        image_count
                        if type(image_count) is int and 0 <= image_count <= 1000
                        else None
                    ),
                    "pending_images": (
                        pending_images
                        if type(pending_images) is int and 0 <= pending_images <= 1000
                        else None
                    ),
                }
            )
        finished = queue.connection.execute(
            "SELECT json_extract(result_json,'$.control.finished_at') FROM candidate_details WHERE "
            + _SCOPE_WHERE
            + " AND json_extract(result_json,'$.control.finished_at') IS NOT NULL "
            "ORDER BY julianday(json_extract(result_json,'$.control.finished_at')) DESC LIMIT 1",
            MONITOR_SCOPE.key(),
        ).fetchone()
        if finished is not None:
            self._last_detail_finished = _stored_time(finished[0])
        return {
            "detail_count": totals[0],
            "detail_pending_count": pending,
            "detail_completed_count": totals[1],
            "detail_failed_count": totals[2],
            "details": details,
        }

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
            detail_status = self._read_details(queue, count)
            if self._last_detail_finished is not None and due is not None:
                due = max(
                    due,
                    next_poll_at(
                        self._last_detail_finished, interval_seconds=self._state["interval_seconds"]
                    ),
                )
            self._set(
                **detail_status,
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

    def _after_detail(self, report):
        if not isinstance(report, dict) or report.get("status") not in _DETAIL_STATUSES:
            raise QueueError("The detail inspection did not return a valid report")
        status = report["status"]
        processed = report.get("candidates_completed", 0)
        if type(processed) is not int or not 0 <= processed <= 1:
            raise QueueError("The detail inspection has invalid counts")
        self._set(browser_closed=report.get("browser_closed"))
        eligibility, _ = self._read_source()
        summaries = report.get("details") or []
        if not isinstance(summaries, list) or len(summaries) > 1:
            raise QueueError("The detail inspection has invalid summaries")
        if (processed == 1 and (len(summaries) != 1 or not isinstance(summaries[0], dict))) or (
            processed == 0 and summaries
        ):
            raise QueueError("The detail inspection summaries do not match its counts")
        if (
            eligibility == "blocked"
            or report.get("reason") == "access_block_requires_review"
            or any(
                isinstance(row, dict) and row.get("http_status") in {401, 403} for row in summaries
            )
        ):
            self._review("access_block_requires_review", error_type=report.get("error_type"))
            return False, processed
        if report.get("browser_closed") is not True:
            self._review("owned_browser_cleanup_unconfirmed", error_type=report.get("error_type"))
            return False, processed
        if status == "candidate_busy":
            self._extra_due = self._clock.now() + timedelta(seconds=BUSY_BACKOFF_SECONDS)
            self._set(reason="another_worker_active", next_eligible_at=_stamp(self._extra_due))
            return True, processed
        due = report.get("next_eligible_at_local")
        if due is not None:
            self._extra_due = _stored_time(due)
            self._set(next_eligible_at=_stamp(self._extra_due))
        if processed:
            summary = summaries[0]
            http_status = summary.get("http_status")
            if http_status in {429, 503}:
                if due is None:
                    raise QueueError("The deferred detail inspection has no next time")
                self._set(reason="service_retry_after")
                return False, processed
            if http_status not in {404, 410} and not (
                summary.get("status") == "observed"
                and type(http_status) is int
                and 200 <= http_status < 400
                and summary.get("time_status") in {"before_baseline", "at_or_after_baseline"}
            ):
                self._review("detail_requires_review", error_type=report.get("error_type"))
                return False, processed
        if status == "candidate_no_pending":
            self._set(reason="no_unattempted_candidates")
            return False, processed
        if status == "candidate_no_baseline":
            self._review("existing_baseline_required")
            return False, processed
        if status == "candidate_waiting":
            if due is None:
                raise QueueError("The waiting detail inspection has no next time")
            self._set(reason="persisted_cooldown")
            return True, processed
        if status == "candidate_test_completed":
            if processed != 1 or due is None:
                raise QueueError("The completed detail inspection has invalid evidence")
            self._set(reason=None)
            return True, processed
        if status == "candidate_test_cancelled" and self._requested_stop():
            return True, processed
        self._review("detail_requires_review", error_type=report.get("error_type"))
        return False, processed

    def _work_details(self):
        processed = 0
        try:
            while processed < MAX_DETAIL_BATCH and not self._stop.is_set():
                if self._pause.is_set():
                    self._set(phase="paused")
                    self._wait(60)
                    continue
                eligibility, due = self._read_source()
                if eligibility == "blocked":
                    self._review("access_block_requires_review")
                    break
                if not self._state["baseline_initialized"]:
                    self._review("existing_baseline_required")
                    break
                if self._state["detail_pending_count"] == 0:
                    self._set(reason="no_unattempted_candidates")
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
                self._set(phase="inspecting", reason=None, browser_closed=None)
                report = self._run_details(
                    self.work_root,
                    "chrome",
                    scope=MONITOR_SCOPE,
                    max_candidates=1,
                    interval_seconds=self._state["interval_seconds"],
                    should_stop=self._requested_stop,
                    clock=self._clock,
                )
                keep_going, count = self._after_detail(report)
                processed += count
                if not keep_going:
                    break
        except BaseException as error:
            self._review("detail_stopped_for_review", error_type=type(error).__name__)
        finally:
            with self._lock:
                if self._state["phase"] != "needs_review":
                    self._state["phase"] = "stopped"

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
