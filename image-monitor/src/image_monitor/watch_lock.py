"""Process-safe, nonblocking ownership of one list scan's exact watch scope.

The caller holds this lock from its eligibility read through navigation and the
scan commit. Sidecar files are never removed or overwritten: the operating
system owns the lease and releases it if a process exits without cleanup.
"""

import errno
import hashlib
import json
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from image_monitor.queue import QueueError
from image_monitor.watch_store import WatchScope


class WatchRunBusy(QueueError):
    """Another local process or thread owns this watch's scan lease."""


def _lock_path(database: Path, scope: WatchScope, *, purpose=None) -> Path:
    if purpose is not None and (not isinstance(purpose, str) or purpose != "monitor"):
        raise QueueError("Unknown watch lease purpose")
    if not isinstance(scope, WatchScope):
        raise QueueError("scope must be a WatchScope")
    canonical = Path(database).resolve()
    identity_parts = [os.path.normcase(str(canonical)), scope.key()]
    if purpose is not None:
        identity_parts.append(purpose)
    identity = json.dumps(
        identity_parts,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(identity).hexdigest()
    return canonical.parent / f".image-monitor-watch-{digest}.lock"


def _check_regular(path: Path) -> os.stat_result:
    info = path.lstat()
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & reparse:
        raise QueueError("Watch lease sidecar must be a regular file without a reparse point")
    return info


def _acquire(descriptor: int) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        if error.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
            raise WatchRunBusy("Another scan already owns this watch scope") from error
        raise


def _release(descriptor: int) -> None:
    if os.name == "nt":
        import msvcrt

        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_UN)


@contextmanager
def watch_run_lock(database: Path, scope: WatchScope, *, purpose=None) -> Iterator[None]:
    """Own this canonical database/scope until exit; raise if already owned.

    The database's parent directory must exist. Existing sidecar contents are
    left intact, including on Windows where the one-byte lock may extend beyond
    EOF. Sidecars must never be deleted to recover an interrupted process.
    """
    path = _lock_path(database, scope, purpose=purpose)
    try:
        _check_regular(path)
    except FileNotFoundError:
        pass
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        opened = os.fstat(descriptor)
        named = _check_regular(path)
        if not stat.S_ISREG(opened.st_mode) or not os.path.samestat(opened, named):
            raise QueueError("Watch lease sidecar changed while opening it")
        _acquire(descriptor)
        try:
            yield
        finally:
            _release(descriptor)
    finally:
        os.close(descriptor)
