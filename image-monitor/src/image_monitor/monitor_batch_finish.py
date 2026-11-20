"""Reconcile one completed batch attempt without repeating native input.

The ledger may record completion only after its frozen source, local files and
browser identity are reverified. Existing native queues, images and metadata
remain read-only. This command never makes an attempted task runnable again.
"""

import re
import stat
import uuid
from datetime import UTC, datetime
from pathlib import Path

from image_monitor.artifact_files import _plain_path
from image_monitor.candidate_finish import (
    _paths,
    finish_completed_candidate,
    read_completed_report,
    verify_completed_candidate_files,
)
from image_monitor.candidate_save_policy import MAX_MONITOR_SAVE_IMAGES, MAX_SAVE_IMAGES
from image_monitor.completed_browser_close import close_completed_browser
from image_monitor.monitor_save_ledger import (
    LEDGER_NAME,
    RECENT_LEDGER_NAME,
    LedgerStore,
    task_native_base,
)
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
from image_monitor.watch_store import MONITOR_SCOPE, WatchScope

_UNFINISHED = {"started", "needs_review"}
_BINDING_FIELDS = (
    "task_id",
    "post_id",
    "post_url",
    "first_scan_id",
    "detail_attempt_id",
    "permit_fingerprint",
    "output_kind",
    "relative_root",
    "native_session",
)
_FILE_FIELDS = ("saved_filename", "detected_format", "file_size", "width", "height", "frames")


def _require(value, message):
    if not value:
        raise NativeUIError(message)


def _roots(*values):
    roots = tuple(_plain_path(Path(value).absolute()).resolve() for value in values)
    for index, left in enumerate(roots):
        _require(not str(left).startswith(("\\\\", "//")), "Local batch finish roots are required")
        _require(not left.exists() or left.is_dir(), "Batch finish roots must be directories")
        for right in roots[index + 1 :]:
            _require(
                left != right and not left.is_relative_to(right) and not right.is_relative_to(left),
                "Discovery, legacy and batch roots must be separate",
            )
    return roots


def _regular(path):
    path = _plain_path(path)
    _require(stat.S_ISREG(path.lstat().st_mode), "Existing batch records are required")
    return path


def _permit(watch, ledger, original):
    from image_monitor.monitor_batch_runtime import reconstruct_permit

    latest = ledger.get_task(original["task_id"])
    _require(
        isinstance(latest, dict)
        and latest["status"] in _UNFINISHED
        and all(latest.get(key) == original.get(key) for key in _BINDING_FIELDS),
        "The attempted batch binding changed during verification",
    )
    return reconstruct_permit(watch, latest, WatchScope(*ledger.scope))


def _record_verified(report, verified):
    report.update(verified)
    report["files_verified"] = len(verified["saved_files"])


def _completed_result(verified):
    return {"verification": verified, "reconciled_without_native_input": True}


def _browser_absent(is_running, identity):
    running = is_running(identity)
    _require(type(running) is bool, "The recorded browser state is not confirmed")
    return not running


def _confirmed_absence(is_running, identity, report, message):
    report["browser_closed"] = None
    absent = _browser_absent(is_running, identity)
    report["browser_closed"] = absent
    _require(absent, message)


def _pending_task(tasks, pending, batch_root, legacy_root):
    directory = pending.get("run_directory") if isinstance(pending, dict) else None
    _require(isinstance(directory, str), "The pending batch identity is incomplete")
    run_name = Path(directory).name
    _require(re.fullmatch(r"[0-9a-f]{32}", run_name), "The pending batch run is invalid")
    matching = [
        task
        for task in tasks
        if directory == str(task_native_base(task, batch_root, legacy_root) / "runs" / run_name)
    ]
    _require(len(matching) == 1, "The pending save does not identify one unfinished batch task")
    return matching[0]


def _finish_pending(
    watch,
    ledger,
    task,
    state,
    pending,
    batch_root,
    legacy_root,
    report,
    report_path,
    is_running,
    close_owned,
):
    base = task_native_base(task, batch_root, legacy_root)
    native_database = _regular(base / "queue.sqlite")
    report["last_stage"] = "completed_report_check"
    permit = _permit(watch, ledger, task)
    previous = read_completed_report(base, pending, permit=permit)
    report["last_stage"] = "local_file_verification"
    with QueueStore(native_database, read_only=True) as native:
        verified = finish_completed_candidate(
            native, permit, base=base, pending=pending, report=previous
        )
    _record_verified(report, verified)
    if not _browser_absent(is_running, pending):
        report.update(browser_closed=False, close_attempted=True, last_stage="owned_browser_close")
        close_owned(pending)
        _require(_browser_absent(is_running, pending), "The previous batch browser remains active")
    report["browser_closed"] = True
    report.update(last_stage="final_local_file_verification", files_verified=0, saved_files=[])
    permit = _permit(watch, ledger, task)
    latest_report = read_completed_report(base, pending, permit=permit)
    _require(latest_report == previous, "The completed batch report changed during shutdown")
    with QueueStore(native_database, read_only=True) as native:
        verified = finish_completed_candidate(
            native, permit, base=base, pending=pending, report=latest_report
        )
    _record_verified(report, verified)
    _confirmed_absence(is_running, pending, report, "The recorded batch profile became active")
    _require(state.read() == pending, "The pending save changed during batch verification")
    report["last_stage"] = "clear_completed_pending"
    write_report(report_path, report)
    state.finish(pending)
    # Preserve this fact even if a later ledger commit fails. A subsequent local
    # reconciliation still requires the recorded identity and completed files.
    report["shared_pending_retained"] = False
    ledger.reconcile_completed(
        task["task_id"], result=_completed_result(verified), now=datetime.now(UTC)
    )


def _finish_without_pending(
    watch, ledger, task, state, batch_root, legacy_root, report, is_running
):
    identity = task["control"].get("browser_identity")
    _require(isinstance(identity, dict), "The attempted batch has no recorded browser identity")
    base = task_native_base(task, batch_root, legacy_root)
    # The identity came from the worker's actual PendingSave record. Validate its
    # exact root/run/profile before probing; never fabricate a replacement marker.
    _paths(base, identity)
    _confirmed_absence(is_running, identity, report, "The recorded batch browser remains active")
    native_database = _regular(base / "queue.sqlite")
    permit = _permit(watch, ledger, task)
    report["last_stage"] = "local_file_verification"
    with QueueStore(native_database, read_only=True) as native:
        verified, _proofs = verify_completed_candidate_files(native, permit, base=base)
    _record_verified(report, verified)
    # Re-read immutable source evidence after the file checks, and require both
    # browser absence and marker absence immediately before recording completion.
    _permit(watch, ledger, task)
    _confirmed_absence(is_running, identity, report, "The recorded batch profile became active")
    current = state.read()
    report["shared_pending_retained"] = current is not None
    _require(current is None, "A pending save appeared during local batch verification")
    report["browser_closed"] = True
    ledger.reconcile_completed(
        task["task_id"], result=_completed_result(verified), now=datetime.now(UTC)
    )


def share_batch_finish_report(report):
    fields = (
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
        "tasks_completed",
        "job_counts",
    )
    public = {key: report[key] for key in fields if key in report}
    limit = (
        MAX_MONITOR_SAVE_IMAGES
        if report.get("mode") == "completed_monitor_batch_local_finish"
        else MAX_SAVE_IMAGES
    )
    public["saved_files"] = [
        {key: item[key] for key in _FILE_FIELDS if key in item}
        for item in report.get("saved_files", [])[:limit]
        if isinstance(item, dict)
    ]
    return public


def run_monitor_batch_finish(
    watch_root: Path,
    legacy_root: Path,
    batch_root: Path,
    *,
    is_running=browser_still_running,
    close_owned=close_completed_browser,
    recent=False,
):
    require_windows()
    scope = DEFAULT_SCOPE if recent else MONITOR_SCOPE
    watch_base, legacy_base, batch_base = _roots(watch_root, legacy_root, batch_root)
    database = _plain_path(watch_base / "watch.sqlite")
    ledger_path = _plain_path(watch_base / (RECENT_LEDGER_NAME if recent else LEDGER_NAME))
    run_directory = batch_base / "batch-finish-runs" / uuid.uuid4().hex
    run_directory.mkdir(parents=True)
    report_path = run_directory / "report.json"
    report = {
        "schema_version": 1,
        "mode": "recent_candidate_local_finish"
        if recent
        else "completed_monitor_batch_local_finish",
        "status": "batch_finish_manual_review",
        "last_stage": "pending_check",
        "error_type": None,
        "browser_closed": None,
        "shared_pending_retained": None,
        "close_attempted": False,
        "files_preserved": True,
        "metadata_preserved": True,
        "files_verified": 0,
        "tasks_completed": 0,
        "saved_files": [],
    }
    try:
        # A missing ledger is an inert finish, never an invitation to create new
        # planning state. Read the session marker under the native owner lock.
        if not ledger_path.exists():
            with NativeSaveLock():
                pending = PendingSave(shared_state_path()).read()
                report["shared_pending_retained"] = pending is not None
                _require(pending is None, "The unresolved save has no existing batch ledger")
                report.update(
                    status="batch_finish_no_pending",
                    reason="no_unfinished_batch_tasks",
                    last_stage="complete",
                )
        else:
            _regular(database)
            _regular(ledger_path)
            with (
                watch_run_lock(database, DEFAULT_SCOPE),
                NativeSaveLock(),
                QueueStore(database, read_only=True) as watch,
                LedgerStore(
                    ledger_path,
                    watch_root=watch_base,
                    legacy_root=legacy_base,
                    batch_root=batch_base,
                    create=False,
                    scope=scope.key(),
                ) as ledger,
            ):
                tasks = [task for task in ledger.list_tasks() if task["status"] in _UNFINISHED]
                if tasks:
                    _require(len(tasks) == 1, "Unfinished batch work is not unambiguous")
                    current_session = session_id()
                    _require(
                        type(current_session) is int
                        and 0 <= current_session <= 2**32 - 1
                        and tasks[0]["native_session"] == current_session,
                        "The unfinished batch belongs to another Windows session",
                    )
                state = PendingSave(shared_state_path())
                pending = state.read()
                report["shared_pending_retained"] = pending is not None
                _require(
                    not watch.summary()["posts"] and not watch.summary()["jobs"],
                    "Batch finish requires separate discovery records",
                )
                if not tasks:
                    _require(pending is None, "The unresolved save is not an unfinished batch task")
                    report.update(
                        status="batch_finish_no_pending",
                        reason="no_unfinished_batch_tasks",
                        last_stage="complete",
                    )
                else:
                    if pending is not None:
                        task = _pending_task(tasks, pending, batch_base, legacy_base)
                        _finish_pending(
                            watch,
                            ledger,
                            task,
                            state,
                            pending,
                            batch_base,
                            legacy_base,
                            report,
                            report_path,
                            is_running,
                            close_owned,
                        )
                    else:
                        _finish_without_pending(
                            watch,
                            ledger,
                            tasks[0],
                            state,
                            batch_base,
                            legacy_base,
                            report,
                            is_running,
                        )
                    report.update(
                        status="batch_finish_completed",
                        reason="completed_files_reverified_and_batch_resolved",
                        last_stage="complete",
                        tasks_completed=1,
                    )
    except WatchRunBusy:
        report.update(status="batch_finish_busy", reason="another_scan_owns_this_scope")
    except KeyboardInterrupt:
        report.update(
            status="batch_finish_cancelled", error_type="KeyboardInterrupt", reason="cancelled"
        )
    except Exception as error:
        name = type(error).__name__
        report.update(
            error_type=name if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}", name) else None,
            reason="completed_batch_requires_review",
        )
    finally:
        report["report_path"] = str(report_path)
        write_report(report_path, report)
    return report
