"""Recheck the last completed recent-post save using its original local evidence."""

from contextlib import ExitStack, contextmanager
from pathlib import Path

from image_monitor import PUBLIC_VERSION
from image_monitor.artifact_files import _plain_path
from image_monitor.candidate_finish import _same_json, verify_completed_candidate_files
from image_monitor.monitor_batch_runtime import reconstruct_permit
from image_monitor.monitor_save_ledger import (
    RECENT_LEDGER_NAME,
    LedgerStore,
    _roots,
    _stored_stamp,
    task_native_base,
    task_work_root,
)
from image_monitor.queue import QueueStore
from image_monitor.saved_catalog import (
    _check_native_children,
    _existing,
    _native_lock,
    _NativeBusy,
    _pending_state,
    _task_directories,
)
from image_monitor.watch_lock import WatchRunBusy, _lock_path, watch_run_lock
from image_monitor.watch_runtime import DEFAULT_SCOPE


class _UnstableDatabase(Exception):
    pass


def _database_stamp(path):
    if not _existing(path):
        return None
    info = path.stat()
    return info.st_size, info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns


@contextmanager
def _read_mode(path):
    """Read a locked checkpoint without creating SQLite sidecars or overlooking committed WAL."""
    wal, shm, journal = (Path(str(path) + suffix) for suffix in ("-wal", "-shm", "-journal"))
    guarded = (path, wal, journal)
    before = tuple(_database_stamp(item) for item in guarded)
    database, wal_stamp, journal_stamp = before
    if database is None:
        raise FileNotFoundError
    if journal_stamp and journal_stamp[0]:
        raise _UnstableDatabase
    immutable = not wal_stamp or not wal_stamp[0]
    shm_stamp = _database_stamp(shm)
    if not immutable and (not shm_stamp or not shm_stamp[0]):
        raise _UnstableDatabase
    # A live WAL needs ordinary SQLite locking and its already existing shared
    # memory index. Immutable mode is safe only for a stable, checkpointed DB.
    yield immutable
    if tuple(_database_stamp(item) for item in guarded) != before:
        raise _UnstableDatabase


def _report(status, reason=None, files=()):
    return {
        "schema_version": 1,
        "program_version": PUBLIC_VERSION,
        "mode": "recent_saved_image_check",
        "status": status,
        "reason": reason,
        "saved_file_count": len(files),
        "saved_files": list(files),
    }


def check_recent_images(watch_root, legacy_root, work_root):
    """Read the recent-save ledger, rederive the permit and verify its files on disk."""
    reason = "save_history_unreadable"
    try:
        watch, legacy, work = _roots(watch_root, legacy_root, work_root)
        database = watch / "watch.sqlite"
        ledger_path = watch / RECENT_LEDGER_NAME
        if not _existing(database):
            if _existing(ledger_path) or _task_directories(work):
                return _report("watch_images_review", "discovery_database_missing")
            return _report("watch_images_no_saved_files", "no_recent_save_history")

        if not _existing(_lock_path(database, DEFAULT_SCOPE)):
            if _existing(ledger_path) or _task_directories(work):
                return _report("watch_images_review", "recent_save_lease_missing")
            return _report("watch_images_no_saved_files", "no_recent_save_history")
        with watch_run_lock(database, DEFAULT_SCOPE, existing_only=True), ExitStack() as reads:
            directories = _task_directories(work)
            if not _existing(ledger_path):
                if directories:
                    return _report("watch_images_review", "recent_save_ledger_missing")
                return _report("watch_images_no_saved_files", "no_recent_save_history")
            immutable_ledger = reads.enter_context(_read_mode(ledger_path))
            with LedgerStore(
                ledger_path,
                watch_root=watch,
                legacy_root=legacy,
                batch_root=work,
                scope=DEFAULT_SCOPE.key(),
                read_only=True,
                create=False,
                immutable=immutable_ledger,
            ) as ledger:
                tasks = ledger.list_tasks()
            if any(task["output_kind"] != "managed" for task in tasks) or directories - {
                task["task_id"] for task in tasks
            }:
                return _report("watch_images_review", "unexpected_recent_save_binding")
            completed = [task for task in tasks if task["status"] == "completed"]
            if not completed:
                if any(task["status"] in {"started", "needs_review"} for task in tasks):
                    return _report("watch_images_review", "unfinished_recent_save")
                return _report("watch_images_no_saved_files", "no_completed_recent_save")

            # Finish times are instants. SQLite string order can differ for older offsets.
            completed.sort(key=lambda task: _stored_stamp(task["finished_at"]), reverse=True)
            task = completed[0]
            if len(completed) > 1 and _stored_stamp(completed[1]["finished_at"]) == _stored_stamp(
                task["finished_at"]
            ):
                return _report("watch_images_review", "latest_completion_ambiguous")

            with (
                _native_lock(),
                _read_mode(database) as immutable_watch,
                QueueStore(database, read_only=True, immutable=immutable_watch) as queue,
            ):
                if _pending_state() is not None:
                    return _report("watch_images_busy", "pending_native_save")
                reason = "saved_observation_mismatch"
                discovery = queue.summary()
                if discovery["posts"] or discovery["jobs"]:
                    return _report("watch_images_review", "unexpected_discovery_work")
                permit = reconstruct_permit(queue, task, DEFAULT_SCOPE)
                reason = "saved_files_missing_or_changed"
                _check_native_children(task_work_root(task, work, legacy), {task["native_session"]})
                base = task_native_base(task, work, legacy)
                native_db = _plain_path(base / "queue.sqlite")
                with (
                    _read_mode(native_db) as immutable_native,
                    QueueStore(native_db, read_only=True, immutable=immutable_native) as native,
                ):
                    verified, _ = verify_completed_candidate_files(native, permit, base=base)
                # Both alpha.6 completion paths persisted the verification. A local
                # finish after an interruption also recorded how it reconciled the task.
                recorded = task["result"]
                if recorded.get("reconciled_without_native_input") is True:
                    recorded = recorded.get("verification")
                if not _same_json(verified, recorded):
                    return _report("watch_images_review", "saved_completion_record_mismatch")
                return _report("watch_images_verified", files=verified["saved_files"])
    except _UnstableDatabase:
        return _report("watch_images_busy", "local_database_changed_or_in_use")
    except WatchRunBusy:
        return _report("watch_images_busy", "another_scan_owns_this_scope")
    except _NativeBusy:
        return _report("watch_images_busy", "native_save_in_progress")
    except KeyboardInterrupt:
        return _report("watch_images_cancelled", "cancelled")
    except Exception:
        return _report("watch_images_review", reason)


def watch_images_check_exit_code(report):
    if report["status"] == "watch_images_cancelled":
        return 130
    if report["status"] in {
        "watch_images_verified",
        "watch_images_no_saved_files",
        "watch_images_busy",
    }:
        return 0
    return 2
