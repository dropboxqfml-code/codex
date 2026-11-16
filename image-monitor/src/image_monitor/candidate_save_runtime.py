"""Save one pinned, previously inspected candidate through the native worker."""

import uuid
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from image_monitor.artifact_files import _plain_path
from image_monitor.candidate_save_selection import (
    select_candidate_save,
    write_selection_control,
)
from image_monitor.native_probe import write_report
from image_monitor.native_ui import NativeUIError, require_windows
from image_monitor.post_worker import run_post_save
from image_monitor.queue import QueueError, QueueStore
from image_monitor.retry import retry_after
from image_monitor.watch_lock import WatchRunBusy, watch_run_lock
from image_monitor.watch_planner import next_poll_at
from image_monitor.watch_runtime import DEFAULT_SCOPE, SERVICE_SCOPE, _eligibility, _stamp
from image_monitor.watch_store import WatchStore


class _Clock:
    def now(self):
        return datetime.now(UTC)


class _NavigationObserver:
    def __init__(self, queue, manifest, clock):
        self.queue = queue
        self.manifest = manifest
        self.clock = clock
        self.http_status = None
        self.next_at = None
        self.blocked = False

    def before(self):
        state = WatchStore(self.queue).get_state(DEFAULT_SCOPE)
        eligibility, due = _eligibility(self.queue, state, self.clock.now())
        if eligibility != "ready":
            raise NativeUIError("Candidate navigation requires service eligibility")
        started = self.clock.now()
        self.next_at = next_poll_at(started)
        self.queue.defer_service(SERVICE_SCOPE, self.next_at)
        write_selection_control(
            self.manifest,
            {
                "blocked": False,
                "in_flight": True,
                "started_at": _stamp(started),
                "next_eligible_at": _stamp(self.next_at),
                "http_status": None,
            },
        )

    def after(self, response, error):
        finished = self.clock.now()
        self.next_at = next_poll_at(finished)
        # Persist the minimum finish-based wait before reading optional headers.
        self.queue.defer_service(SERVICE_SCOPE, self.next_at)
        self.http_status = response.status if response is not None else None
        self.blocked = self.http_status in {401, 403}
        observed_retry_after = None
        if response is not None and self.http_status in {429, 503}:
            try:
                value = response.header_value("retry-after")
            except Exception:
                value = None
            if isinstance(value, str):
                observed_retry_after = value[:256]
                try:
                    server_due = retry_after(observed_retry_after, finished)
                except ValueError:
                    server_due = None
                if server_due is not None:
                    self.next_at = max(self.next_at, server_due)
        self.queue.defer_service(SERVICE_SCOPE, self.next_at)
        write_selection_control(
            self.manifest,
            {
                "blocked": self.blocked,
                "in_flight": False,
                "finished_at": _stamp(finished),
                "next_eligible_at": _stamp(self.next_at),
                "http_status": self.http_status,
                "retry_after": observed_retry_after,
                "error_type": type(error).__name__ if error is not None else None,
            },
        )


def _public_file(item):
    return {
        key: item[key]
        for key in (
            "saved_filename",
            "detected_format",
            "file_size",
            "width",
            "height",
            "frames",
        )
        if key in item
    }


def share_candidate_save_report(report):
    fields = (
        "schema_version",
        "mode",
        "status",
        "browser",
        "browser_version",
        "last_stage",
        "error_type",
        "reason",
        "browser_closed",
        "shared_pending_retained",
        "job_counts",
        "image_count",
        "http_status",
        "next_eligible_at_local",
        "native_stage",
        "native_file_type",
        "native_suggested_suffix",
        "focus_at_failure",
        "focus_at_pause",
        "focus_pauses",
        "recovery",
    )
    public = {key: report[key] for key in fields if key in report}
    public["saved_files"] = [_public_file(item) for item in report.get("saved_files", [])]
    return public


def run_candidate_save_trial(
    watch_root: Path,
    work_root: Path,
    browser="chrome",
    *,
    clock=None,
    save_runner=run_post_save,
):
    require_windows()
    if browser != "chrome":
        raise NativeUIError("Candidate native saving is verified for Chrome only")
    clock = clock or _Clock()
    _stamp(clock.now())
    watch_base = Path(watch_root).resolve()
    output_base = Path(work_root).resolve()
    if any(str(root).startswith("\\\\") for root in (watch_base, output_base)):
        raise NativeUIError("Local candidate save and discovery roots are required")
    if (
        watch_base == output_base
        or watch_base.is_relative_to(output_base)
        or output_base.is_relative_to(watch_base)
    ):
        raise NativeUIError("Candidate saving requires a separate output work root")
    _plain_path(watch_base)
    _plain_path(output_base)
    database = _plain_path(watch_base / "watch.sqlite")
    manifest = _plain_path(watch_base / "candidate-save-selection.json")
    run_directory = output_base / "candidate-save-runs" / uuid.uuid4().hex
    run_directory.mkdir(parents=True)
    report_path = run_directory / "report.json"
    report = {
        "schema_version": 1,
        "mode": "reviewed_candidate_native_context_menu",
        "status": "candidate_save_failed",
        "browser": browser,
        "browser_closed": True,
        "shared_pending_retained": False,
        "last_stage": "candidate_selection",
        "error_type": None,
        "saved_files": [],
    }
    observer = None
    try:
        if not database.is_file():
            report.update(
                status="candidate_save_no_candidate", reason="existing_candidate_details_required"
            )
        else:
            with watch_run_lock(database, DEFAULT_SCOPE), QueueStore(database) as queue:
                if queue.summary()["posts"] or queue.summary()["jobs"]:
                    raise QueueError("Image jobs must remain separate from the discovery database")
                state = WatchStore(queue).get_state(DEFAULT_SCOPE)
                eligibility, due = _eligibility(queue, state, clock.now())
                if eligibility == "blocked":
                    report.update(reason="access_block_requires_review", last_stage="blocked")
                elif eligibility == "waiting":
                    report.update(status="candidate_save_waiting", reason="persisted_cooldown")
                    report["next_eligible_at_local"] = due.astimezone(
                        ZoneInfo("Asia/Seoul")
                    ).isoformat()
                else:
                    permit = select_candidate_save(queue, DEFAULT_SCOPE, manifest)
                    if permit is None:
                        report.update(
                            status="candidate_save_no_candidate",
                            reason="no_reviewed_image_candidate",
                        )
                    else:
                        observer = _NavigationObserver(queue, manifest, clock)
                        report["image_count"] = permit.image_count
                        report["last_stage"] = "native_post_worker"
                        # The worker may reject an existing pending save before
                        # returning a report. Its browser/marker state is then unknown.
                        report["browser_closed"] = None
                        report["shared_pending_retained"] = None
                        worker = save_runner(
                            output_base,
                            browser,
                            permit.post_url,
                            candidate_permit=permit,
                            navigation_observer=observer,
                        )
                        report.update(worker)
                        report["mode"] = "reviewed_candidate_native_context_menu"
                        report["status"] = (
                            "candidate_save_completed"
                            if worker.get("status") == "post_completed"
                            else "candidate_save_cancelled"
                            if worker.get("error_type") == "KeyboardInterrupt"
                            else "candidate_save_manual_review"
                        )
                        report["worker_report_path"] = worker.get("report_path")
                        if observer.next_at is not None:
                            report["next_eligible_at_local"] = observer.next_at.astimezone(
                                ZoneInfo("Asia/Seoul")
                            ).isoformat()
                        report["http_status"] = observer.http_status
                        if observer.http_status in {429, 503}:
                            report.update(
                                status="candidate_save_waiting", reason="service_retry_after"
                            )
                        elif observer.blocked:
                            report.update(
                                status="candidate_save_failed",
                                reason="access_block_requires_review",
                            )
                        elif observer.http_status in {404, 410}:
                            report.update(
                                status="candidate_save_manual_review",
                                reason="selected_candidate_unavailable",
                            )
                if queue.summary()["posts"] or queue.summary()["jobs"]:
                    raise QueueError("Native saving unexpectedly changed the discovery image queue")
    except WatchRunBusy:
        report.update(status="candidate_save_busy", reason="another_scan_owns_this_scope")
    except KeyboardInterrupt:
        report.update(
            status="candidate_save_cancelled", error_type="KeyboardInterrupt", reason="cancelled"
        )
    except Exception as error:
        report.update(
            status="candidate_save_failed",
            error_type=type(error).__name__,
            reason="candidate_save_stopped",
        )
    finally:
        report["report_path"] = str(report_path)
        write_report(report_path, report)
    return report
