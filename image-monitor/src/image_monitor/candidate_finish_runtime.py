"""Reconcile a completed candidate save without re-downloading its images."""

import uuid
from pathlib import Path

from image_monitor.artifact_files import _plain_path
from image_monitor.candidate_finish import finish_completed_candidate, read_completed_report
from image_monitor.candidate_save_selection import read_selection, select_candidate_save
from image_monitor.completed_browser_close import close_completed_browser
from image_monitor.native_probe import write_report
from image_monitor.native_state import (
    PendingSave,
    browser_still_running,
    session_id,
    shared_state_path,
)
from image_monitor.native_ui import NativeSaveLock, NativeUIError, require_windows
from image_monitor.queue import QueueStore
from image_monitor.watch_lock import WatchRunBusy, watch_run_lock
from image_monitor.watch_runtime import DEFAULT_SCOPE


def share_candidate_finish_report(report):
    allowed = (
        "schema_version",
        "mode",
        "status",
        "last_stage",
        "error_type",
        "reason",
        "browser_closed",
        "shared_pending_retained",
        "close_attempted",
        "files_preserved",
        "metadata_preserved",
        "files_verified",
        "job_counts",
        "saved_files",
        "output_directory",
        "shutdown",
    )
    return {key: report[key] for key in allowed if key in report}


def run_candidate_finish_trial(
    watch_root: Path,
    work_root: Path,
    *,
    is_running=browser_still_running,
    close_owned=close_completed_browser,
):
    require_windows()
    watch_base = _plain_path(Path(watch_root).absolute()).resolve()
    output_base = _plain_path(Path(work_root).absolute()).resolve()
    if any(str(root).startswith("\\\\") for root in (watch_base, output_base)):
        raise NativeUIError("Local candidate finish roots are required")
    if (
        watch_base == output_base
        or watch_base.is_relative_to(output_base)
        or output_base.is_relative_to(watch_base)
    ):
        raise NativeUIError("Candidate finish requires separate discovery and output roots")
    native_base = output_base / f"session-{session_id()}"
    database = _plain_path(watch_base / "watch.sqlite")
    native_database = _plain_path(native_base / "queue.sqlite")
    manifest = _plain_path(watch_base / "candidate-save-selection.json")
    run_directory = output_base / "candidate-finish-runs" / uuid.uuid4().hex
    run_directory.mkdir(parents=True)
    report_path = run_directory / "report.json"
    report = {
        "schema_version": 1,
        "mode": "completed_candidate_local_finish",
        "status": "candidate_finish_manual_review",
        "last_stage": "pending_check",
        "error_type": None,
        "browser_closed": None,
        "shared_pending_retained": None,
        "close_attempted": False,
        "files_preserved": True,
        "metadata_preserved": True,
        "files_verified": 0,
        "saved_files": [],
    }
    pending = None
    try:
        with watch_run_lock(database, DEFAULT_SCOPE), NativeSaveLock():
            state = PendingSave(shared_state_path())
            pending = state.read()
            if pending is None:
                report.update(
                    status="candidate_finish_no_pending",
                    reason="no_pending_save",
                    shared_pending_retained=False,
                    last_stage="complete",
                )
            else:
                report["shared_pending_retained"] = True
                if (
                    not database.is_file()
                    or not native_database.is_file()
                    or read_selection(manifest) is None
                ):
                    raise NativeUIError(
                        "Existing candidate selection and save records are required"
                    )
                report["last_stage"] = "completed_report_check"
                previous = read_completed_report(native_base, pending)
                with QueueStore(database, read_only=True) as watch_store:
                    permit = select_candidate_save(watch_store, DEFAULT_SCOPE, manifest)
                if permit is None:
                    raise NativeUIError("The original saved candidate could not be verified")
                report["last_stage"] = "local_file_verification"
                with QueueStore(native_database, read_only=True) as native_store:
                    verified = finish_completed_candidate(
                        native_store,
                        permit,
                        base=native_base,
                        pending=pending,
                        report=previous,
                    )
                report.update(verified)
                report["files_verified"] = len(verified["saved_files"])
                report["output_directory"] = str(native_base / "images")
                running = is_running(pending)
                if type(running) is not bool:
                    raise NativeUIError("The previous browser state is not confirmed")
                if running:
                    report.update(
                        browser_closed=False, close_attempted=True, last_stage="owned_browser_close"
                    )
                    close_owned(pending)
                    running = is_running(pending)
                    if type(running) is not bool:
                        raise NativeUIError("The previous browser state is not confirmed")
                if running:
                    report.update(reason="previous_browser_still_active", browser_closed=False)
                else:
                    report["browser_closed"] = True
                    # Closing can take tens of seconds. Confirm that no file,
                    # metadata or immutable source changed during that interval.
                    report.update(
                        last_stage="final_local_file_verification",
                        files_verified=0,
                        saved_files=[],
                    )
                    latest_report = read_completed_report(native_base, pending)
                    if latest_report != previous:
                        raise NativeUIError("The completed save report changed during shutdown")
                    with QueueStore(native_database, read_only=True) as native_store:
                        verified = finish_completed_candidate(
                            native_store,
                            permit,
                            base=native_base,
                            pending=pending,
                            report=latest_report,
                        )
                    report.update(verified)
                    report["files_verified"] = len(verified["saved_files"])
                    report["last_stage"] = "clear_completed_pending"
                    if state.read() != pending:
                        raise NativeUIError("The pending save changed during file verification")
                    write_report(report_path, report)
                    state.finish(pending)
                    report.update(
                        status="candidate_finish_completed",
                        last_stage="complete",
                        shared_pending_retained=False,
                        reason="completed_files_reverified_and_pending_cleared",
                    )
    except WatchRunBusy:
        report.update(status="candidate_finish_busy", reason="another_scan_owns_this_scope")
    except KeyboardInterrupt:
        report.update(
            status="candidate_finish_cancelled", error_type="KeyboardInterrupt", reason="cancelled"
        )
    except Exception as error:
        report.update(error_type=type(error).__name__, reason="completed_candidate_requires_review")
        diagnostics = getattr(error, "shutdown_diagnostics", None)
        if isinstance(diagnostics, dict):
            report["shutdown"] = diagnostics
    finally:
        report["report_path"] = str(report_path)
        write_report(report_path, report)
    return report
