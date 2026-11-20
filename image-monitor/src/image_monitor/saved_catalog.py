"""Verify a frozen monitor save and cache its original local image bytes.

Only the background caller performs file or SQLite work. The HTTP layer receives
opaque IDs and immutable byte buffers; it never opens a caller-supplied path.
"""

import hashlib
import os
import re
import stat
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from image_monitor.artifact_files import _plain_path
from image_monitor.candidate_finish import verify_completed_candidate_files
from image_monitor.candidate_save_policy import MAX_MONITOR_SAVE_IMAGES, MONITOR_SCOPE
from image_monitor.candidate_save_selection import (
    MONITOR_MANIFEST_NAME,
    read_selection,
    select_candidate_save,
)
from image_monitor.native_state import PendingSave, session_id, shared_state_path
from image_monitor.native_ui import NativeSaveLock, NativeUIError
from image_monitor.queue import QueueStore
from image_monitor.watch_lock import WatchRunBusy, watch_run_lock
from image_monitor.watch_runtime import DEFAULT_SCOPE
from image_monitor.watch_store import WatchScope

MAX_PREVIEW_BYTES = 16 * 1024 * 1024
MAX_TOTAL_PREVIEW_BYTES = 32 * 1024 * 1024
MAX_PENDING_BYTES = 64 * 1024
MAX_CATALOG_FILES = 20
PREVIEW_CONTENT_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "GIF": "image/gif",
    "BMP": "image/bmp",
}
_FILE_FIELDS = ("saved_filename", "detected_format", "file_size", "width", "height", "frames")
_MONITOR_SCOPE = WatchScope(*MONITOR_SCOPE)


@dataclass(frozen=True)
class CatalogSnapshot:
    """Separate bounded public metadata from the private, immutable byte cache."""

    summary: dict
    images: dict[str, tuple[str, bytes]]


class _Cancelled(Exception):
    pass


class _NativeBusy(Exception):
    pass


def _snapshot(status, reason=None, *, error_type=None, grouped=False):
    summary = {
        "status": status,
        "reason": reason,
        "error_type": error_type,
        "files_verified": 0,
        "preview_count": 0,
        "files": [],
    }
    if grouped:
        summary.update(groups_verified=0, files_omitted=0)
    return CatalogSnapshot(summary, {})


def _error_type(error):
    name = type(error).__name__
    return name if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}", name) else None


def _stop(should_stop):
    if should_stop is not None:
        value = should_stop()
        if type(value) is not bool:
            raise ValueError("The saved-catalog stop condition must return a boolean")
        if value:
            raise _Cancelled


def _root(value):
    path = _plain_path(Path(value).absolute())
    if str(path).startswith(("\\\\", "//")):
        raise ValueError("A local saved-catalog root is required")
    return path.resolve()


def _existing(path, *, directory=False):
    """Missing records are an empty catalog; a foreign file type is an error."""
    path = _plain_path(path)
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise ValueError("Saved-catalog data must use plain directories and files")
    return True


def _same_file(before, after):
    # On Windows path/descriptor ctime values have different meanings. Compare
    # ctime only between two descriptor stats, as local image verification does.
    return (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_size,
        before.st_mtime_ns,
    ) == (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_size,
        after.st_mtime_ns,
    )


def _read_preview(proof):
    """Cache exactly the verified bytes, rejecting replacement or changing files."""
    path = _plain_path(Path(proof["path"]))
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size != proof["file_size"]:
        raise ValueError("A verified saved image changed before preview loading")
    if not 0 < before.st_size <= MAX_PREVIEW_BYTES:
        raise ValueError("The saved image exceeds the preview buffer limit")
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0),
    )
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or not _same_file(before, opened):
            raise ValueError("The saved image changed while opening its preview")
        data = stream.read(MAX_PREVIEW_BYTES + 1)
        finished = os.fstat(stream.fileno())
    after = _plain_path(path).lstat()
    if (
        len(data) != proof["file_size"]
        or len(data) > MAX_PREVIEW_BYTES
        or not _same_file(opened, finished)
        or opened.st_ctime_ns != finished.st_ctime_ns
        or not _same_file(finished, after)
        or hashlib.sha256(data).hexdigest() != proof["sha256"]
    ):
        raise ValueError("The saved preview bytes no longer match their verified artifact")
    return data


@contextmanager
def _native_lock():
    owner = NativeSaveLock()
    try:
        owner.__enter__()
    except NativeUIError as error:
        raise _NativeBusy from error
    try:
        yield
    finally:
        owner.__exit__(None, None, None)


def _pending_state():
    path = _plain_path(shared_state_path())
    if _existing(path):
        if path.stat().st_size > MAX_PENDING_BYTES:
            raise ValueError("Saved-catalog pending state exceeds its metadata limit")
    return PendingSave(path).read()


def _task_directories(batch_root):
    """Check the bounded registry boundary without discovering images by scanning."""
    from image_monitor.monitor_save_ledger import MAX_TASKS

    directory = _plain_path(batch_root / "tasks")
    if not _existing(directory, directory=True):
        return set()
    identifiers = set()
    for index, child in enumerate(directory.iterdir()):
        if index >= MAX_TASKS:
            raise ValueError("The saved batch task range exceeds its metadata limit")
        if not re.fullmatch(r"[0-9a-f]{32}", child.name) or not _existing(child, directory=True):
            raise ValueError("The saved batch contains an unknown task directory")
        identifiers.add(child.name)
    return identifiers


def _check_native_children(root, sessions, *, legacy=False):
    """Refuse native output which has no frozen registry binding."""
    from image_monitor.monitor_save_ledger import MAX_TASKS

    if not _existing(root, directory=True):
        return
    expected = {f"session-{value}" for value in sessions}
    for index, child in enumerate(root.iterdir()):
        if index >= MAX_TASKS:
            raise ValueError("The saved native output range exceeds its metadata limit")
        child = _plain_path(child)
        if child.name in expected and _existing(child, directory=True):
            continue
        if (
            legacy
            and not child.name.startswith("session-")
            and child.name not in {"queue.sqlite", "images", "runs"}
        ):
            continue
        raise ValueError("Saved native output has no frozen registry binding")


def valid_monitor_filename(name):
    return (
        isinstance(name, str)
        and re.fullmatch(r"[0-9]{3}\.(?:jpg|png|webp|gif|bmp|tiff)", name) is not None
        and 1 <= int(name[:3]) <= MAX_MONITOR_SAVE_IMAGES
    )


def _verify_source(native_base, permit, should_stop):
    """Return private proofs only after checking one exact frozen native root."""
    native_base = _plain_path(native_base)
    database = _plain_path(native_base / "queue.sqlite")
    if not all(
        (
            _existing(native_base, directory=True),
            _existing(native_base / "images", directory=True),
            _existing(database),
        )
    ):
        raise ValueError("A completed saved source is missing its native records")
    _stop(should_stop)
    with QueueStore(database, read_only=True) as store:
        summary, proofs = verify_completed_candidate_files(store, permit, base=native_base)
    if (
        not isinstance(proofs, list)
        or not 1 <= len(proofs) <= MAX_MONITOR_SAVE_IMAGES
        or len(proofs) != permit.image_count
        or not isinstance(summary.get("saved_files"), list)
        or len(summary["saved_files"]) != len(proofs)
    ):
        raise ValueError("The saved-catalog verifier returned inconsistent files")
    slots = set()
    for proof in proofs:
        _stop(should_stop)
        path = _plain_path(Path(proof["path"]))
        name = proof["saved_filename"]
        if (
            not path.is_absolute()
            or not path.is_relative_to(native_base / "images")
            or path.name != name
            or not valid_monitor_filename(name)
            or int(name[:3]) > permit.image_count
            or name[:3] in slots
        ):
            raise ValueError("A saved preview proof is outside its owned image root")
        slots.add(name[:3])
    return proofs


def _legacy_source(watch_store, watch_base, output_base, should_stop):
    """Allow an unregistered legacy save only before any batch registry/output."""
    manifest = _plain_path(watch_base / MONITOR_MANIFEST_NAME)
    native_base = _plain_path(output_base / f"session-{session_id()}")
    if not all(
        (
            _existing(manifest),
            _existing(output_base, directory=True),
            _existing(native_base, directory=True),
            _existing(native_base / "images", directory=True),
            _existing(native_base / "queue.sqlite"),
        )
    ):
        return []
    if read_selection(manifest) is None:
        return []
    permit = select_candidate_save(watch_store, _MONITOR_SCOPE, manifest)
    if permit is None:
        raise ValueError("The saved monitor selection could not be verified")
    return [(native_base, _verify_source(native_base, permit, should_stop))]


def _grouped_snapshot(sources, should_stop):
    """Publish a bounded first page only after every source has been verified."""
    files, images, groups = [], {}, set()
    total_bytes = 0
    verified = sum(len(proofs) for _base, proofs in sources)
    for _base, proofs in sources:
        _stop(should_stop)
        group_id = uuid.uuid4().hex
        if group_id in groups or group_id in images:
            raise ValueError("Saved group identities collided")
        groups.add(group_id)
        for proof in proofs:
            _stop(should_stop)
            if len(files) >= MAX_CATALOG_FILES:
                continue
            item = {key: proof[key] for key in _FILE_FIELDS}
            item.update(group_id=group_id, preview_id=None, preview_available=False)
            content_type = PREVIEW_CONTENT_TYPES.get(proof["detected_format"])
            size = proof["file_size"]
            if (
                content_type is not None
                and type(size) is int
                and 0 < size <= MAX_PREVIEW_BYTES
                and total_bytes + size <= MAX_TOTAL_PREVIEW_BYTES
            ):
                data = _read_preview(proof)
                opaque_id = uuid.uuid4().hex
                if opaque_id in images or opaque_id in groups:
                    raise ValueError("Saved preview identities collided")
                images[opaque_id] = (content_type, data)
                item.update(preview_id=opaque_id, preview_available=True)
                total_bytes += len(data)
            files.append(item)
    _stop(should_stop)
    if _pending_state() is not None:
        raise ValueError("Native-save state changed during local verification")
    if not files:
        return _snapshot("empty", "existing_saved_candidate_required", grouped=True)
    omitted = verified - len(files)
    return CatalogSnapshot(
        {
            "status": "ready",
            "reason": "preview_limit" if omitted or len(images) != len(files) else None,
            "error_type": None,
            "files_verified": verified,
            "groups_verified": len(sources),
            "files_omitted": omitted,
            "preview_count": len(images),
            "files": files,
        },
        images,
    )


def _load_batch_catalog(watch_base, output_base, batch_base, should_stop):
    from image_monitor.monitor_batch_runtime import reconstruct_permit
    from image_monitor.monitor_save_ledger import (
        LEDGER_NAME,
        LedgerStore,
        task_native_base,
        task_work_root,
    )

    for root in (watch_base, output_base):
        if root == batch_base or root.is_relative_to(batch_base) or batch_base.is_relative_to(root):
            raise ValueError("Saved images require separate discovery, legacy and batch roots")
    # Validate existing configured roots without creating empty output folders.
    _existing(output_base, directory=True)
    _existing(batch_base, directory=True)
    database = _plain_path(watch_base / "watch.sqlite")
    ledger_path = _plain_path(watch_base / LEDGER_NAME)
    if not all((_existing(watch_base, directory=True), _existing(database))):
        if _existing(ledger_path) or _task_directories(batch_base):
            raise ValueError("Existing batch output lost its discovery records")
        return _snapshot("empty", "existing_saved_candidate_required", grouped=True)
    _stop(should_stop)
    with watch_run_lock(database, DEFAULT_SCOPE), _native_lock():
        _stop(should_stop)
        if _pending_state() is not None:
            return _snapshot("busy", "pending_save_requires_review", grouped=True)
        directories = _task_directories(batch_base)
        with QueueStore(database, read_only=True) as watch_store:
            if watch_store.summary()["posts"] or watch_store.summary()["jobs"]:
                raise ValueError("Saved-catalog discovery data contains image work")
            if not _existing(ledger_path):
                if directories:
                    raise ValueError("Existing batch output lost its original save ledger")
                return _grouped_snapshot(
                    _legacy_source(watch_store, watch_base, output_base, should_stop), should_stop
                )
            with LedgerStore(
                ledger_path,
                watch_root=watch_base,
                legacy_root=output_base,
                batch_root=batch_base,
                read_only=True,
                create=False,
            ) as ledger:
                tasks = ledger.list_tasks()
                managed_ids = {t["task_id"] for t in tasks if t["output_kind"] == "managed"}
                if directories - managed_ids:
                    raise ValueError("Existing batch output has no original task binding")
                _check_native_children(
                    output_base,
                    {
                        t["native_session"]
                        for t in tasks
                        if t["output_kind"] == "legacy" and t["native_session"] is not None
                    },
                    legacy=True,
                )
                sources, bases = [], set()
                for task in tasks:
                    _stop(should_stop)
                    if task["output_kind"] == "managed":
                        _check_native_children(
                            _plain_path(task_work_root(task, batch_base, output_base)),
                            set() if task["native_session"] is None else {task["native_session"]},
                        )
                    if task["status"] in {"started", "needs_review"}:
                        raise ValueError("An unfinished batch save requires reconciliation")
                    if task["status"] == "planned":
                        root = _plain_path(task_work_root(task, batch_base, output_base))
                        if _existing(root, directory=True) and any(root.iterdir()):
                            raise ValueError("A planned batch task contains native output")
                        continue
                    if task["status"] == "unavailable":
                        continue
                    permit = reconstruct_permit(watch_store, task)
                    native_base = _plain_path(task_native_base(task, batch_base, output_base))
                    if native_base in bases:
                        raise ValueError("Completed batch tasks share a native save root")
                    bases.add(native_base)
                    sources.append((native_base, _verify_source(native_base, permit, should_stop)))
                # Registry rows are the only source list, including adopted legacy
                # saves. Never append the standalone legacy selection a second time.
                if ledger.list_tasks() != tasks or _task_directories(batch_base) != directories:
                    raise ValueError("The batch registry changed during local verification")
                return _grouped_snapshot(sources, should_stop)


def load_saved_catalog(
    watch_root, save_root, *, batch_root=None, should_stop=None
) -> CatalogSnapshot:
    """Verify completed local saves without collecting, adopting, or repairing.

    Without a batch root, use the existing selection and current native session.
    With a batch root, the existing validated ledger supplies every frozen native
    session, including adopted legacy saves. Verify all completed sources before
    publishing at most MAX_CATALOG_FILES rows and bounded original-byte buffers.
    Local verification is independent of network cooldowns and access blocks.
    No data directories, databases, images, metadata, selections, or pending
    markers are created or modified; ownership uses the standard lease sidecars.
    SQLite read-only WAL connections may create their WAL/SHM coordination files.
    """
    try:
        if should_stop is not None and not callable(should_stop):
            raise ValueError("The saved-catalog stop condition must be callable")
        _stop(should_stop)
        watch_base, output_base = _root(watch_root), _root(save_root)
        if (
            watch_base == output_base
            or watch_base.is_relative_to(output_base)
            or output_base.is_relative_to(watch_base)
        ):
            raise ValueError("Saved images require a separate output root")
        if batch_root is not None:
            return _load_batch_catalog(watch_base, output_base, _root(batch_root), should_stop)
        database = _plain_path(watch_base / "watch.sqlite")
        manifest = _plain_path(watch_base / MONITOR_MANIFEST_NAME)
        required = (
            _existing(watch_base, directory=True),
            _existing(output_base, directory=True),
            _existing(database),
            _existing(manifest),
        )
        if not all(required):
            return _snapshot("empty", "existing_saved_candidate_required")
        _stop(should_stop)
        with watch_run_lock(database, DEFAULT_SCOPE), _native_lock():
            _stop(should_stop)
            if _pending_state() is not None:
                return _snapshot("busy", "pending_save_requires_review")
            native_base = _plain_path(output_base / f"session-{session_id()}")
            native_database = _plain_path(native_base / "queue.sqlite")
            if not all(
                (
                    _existing(native_base, directory=True),
                    _existing(native_base / "images", directory=True),
                    _existing(native_database),
                )
            ):
                return _snapshot("empty", "existing_saved_candidate_required")
            # This read must succeed before selection: a read-only preview can
            # never freeze a new candidate as a side effect of opening the UI.
            if read_selection(manifest) is None:
                return _snapshot("empty", "existing_saved_candidate_required")
            with QueueStore(database, read_only=True) as watch_store:
                if watch_store.summary()["posts"] or watch_store.summary()["jobs"]:
                    raise ValueError("Saved-catalog discovery data contains image work")
                permit = select_candidate_save(watch_store, _MONITOR_SCOPE, manifest)
                if permit is None:
                    raise ValueError("The saved monitor selection could not be verified")
                proofs = _verify_source(native_base, permit, should_stop)
                _stop(should_stop)
                images = {}
                files = []
                total_bytes = 0
                for proof in proofs:
                    _stop(should_stop)
                    item = {key: proof[key] for key in _FILE_FIELDS}
                    content_type = PREVIEW_CONTENT_TYPES.get(proof["detected_format"])
                    size = proof["file_size"]
                    allowed = (
                        content_type is not None
                        and type(size) is int
                        and 0 < size <= MAX_PREVIEW_BYTES
                        and total_bytes + size <= MAX_TOTAL_PREVIEW_BYTES
                    )
                    item.update(preview_id=None, preview_available=False)
                    if allowed:
                        data = _read_preview(proof)
                        opaque_id = uuid.uuid4().hex
                        if opaque_id in images:
                            raise ValueError("Saved preview identities collided")
                        images[opaque_id] = (content_type, data)
                        item.update(preview_id=opaque_id, preview_available=True)
                        total_bytes += len(data)
                    files.append(item)
                _stop(should_stop)
                if _pending_state() is not None:
                    raise ValueError("Native-save state changed during local verification")
                return CatalogSnapshot(
                    {
                        "status": "ready",
                        "reason": "preview_limit" if len(images) != len(files) else None,
                        "error_type": None,
                        "files_verified": len(files),
                        "preview_count": len(images),
                        "files": files,
                    },
                    images,
                )
    except _Cancelled:
        return _snapshot("cancelled", "requested_stop", grouped=batch_root is not None)
    except WatchRunBusy:
        return _snapshot("busy", "another_scan_owns_this_scope", grouped=batch_root is not None)
    except _NativeBusy:
        return _snapshot("busy", "native_save_in_progress", grouped=batch_root is not None)
    except Exception as error:
        return _snapshot(
            "needs_review",
            "saved_catalog_requires_review",
            error_type=_error_type(error),
            grouped=batch_root is not None,
        )
