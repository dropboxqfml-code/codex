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
from image_monitor.candidate_save_policy import MONITOR_SCOPE
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


def _snapshot(status, reason=None, *, error_type=None):
    return CatalogSnapshot(
        {
            "status": status,
            "reason": reason,
            "error_type": error_type,
            "files_verified": 0,
            "preview_count": 0,
            "files": [],
        },
        {},
    )


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


def load_saved_catalog(watch_root, save_root, *, should_stop=None) -> CatalogSnapshot:
    """Read only the selected completed monitor save; never collect or repair it.

    Both databases and the selection must already exist. Local verification is
    independent of network cooldowns and access blocks. The standard shared scan
    lease can create its lock sidecar, but no data directories, database, image,
    metadata, selection, or pending marker are created or modified.
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
            with (
                QueueStore(database, read_only=True) as watch_store,
                QueueStore(native_database, read_only=True) as native_store,
            ):
                if watch_store.summary()["posts"] or watch_store.summary()["jobs"]:
                    raise ValueError("Saved-catalog discovery data contains image work")
                permit = select_candidate_save(watch_store, _MONITOR_SCOPE, manifest)
                if permit is None:
                    raise ValueError("The saved monitor selection could not be verified")
                _stop(should_stop)
                summary, proofs = verify_completed_candidate_files(
                    native_store, permit, base=native_base
                )
                if (
                    not isinstance(proofs, list)
                    or not 1 <= len(proofs) <= 2
                    or len(proofs) != permit.image_count
                    or len(summary["saved_files"]) != len(proofs)
                ):
                    raise ValueError("The saved-catalog verifier returned inconsistent files")
                _stop(should_stop)
                images = {}
                files = []
                total_bytes = 0
                for proof in proofs:
                    _stop(should_stop)
                    path = _plain_path(Path(proof["path"]))
                    if (
                        not path.is_absolute()
                        or not path.is_relative_to(native_base / "images")
                        or path.name != proof["saved_filename"]
                    ):
                        raise ValueError("A saved preview proof is outside its owned image root")
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
        return _snapshot("cancelled", "requested_stop")
    except WatchRunBusy:
        return _snapshot("busy", "another_scan_owns_this_scope")
    except _NativeBusy:
        return _snapshot("busy", "native_save_in_progress")
    except Exception as error:
        return _snapshot(
            "needs_review", "saved_catalog_requires_review", error_type=_error_type(error)
        )
