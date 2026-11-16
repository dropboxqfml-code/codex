"""Bounded, atomic settings for the local discovery monitor."""

import json
import os
import stat
import uuid
from pathlib import Path

from image_monitor.artifact_files import _plain_path, _sync_directory
from image_monitor.queue import QueueError

SETTINGS_NAME = "monitor-settings.json"
MAX_SETTINGS_BYTES = 8192
DEFAULT_INTERVAL_SECONDS = 60


def validate_interval(value):
    if type(value) is not int or not 60 <= value <= 300:
        raise QueueError("The monitor interval must be an integer from 60 to 300 seconds")
    return value


def _settings(value):
    if (
        not isinstance(value, dict)
        or set(value) != {"schema_version", "interval_seconds"}
        or type(value.get("schema_version")) is not int
        or value["schema_version"] != 1
    ):
        raise QueueError("The existing monitor settings format is unknown")
    validate_interval(value["interval_seconds"])
    return value


def _path(work_root):
    root = _plain_path(Path(work_root).absolute())
    if str(root).startswith("\\\\"):
        raise QueueError("A local monitor settings directory is required")
    return _plain_path(root / SETTINGS_NAME)


def _same_file(before, after):
    return (
        os.path.samestat(before, after)
        and before.st_size == after.st_size
        and before.st_mtime_ns == after.st_mtime_ns
    )


def _regular(path):
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or getattr(info, "st_file_attributes", 0) & 0x400
        or info.st_size > MAX_SETTINGS_BYTES
    ):
        raise QueueError("Monitor settings must be a bounded plain file")
    return info


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise QueueError("Monitor settings contain duplicate JSON fields")
        result[key] = value
    return result


def _invalid_constant(_value):
    raise ValueError("Nonfinite settings value")


def _read(path):
    try:
        before = _regular(path)
    except FileNotFoundError:
        return {"schema_version": 1, "interval_seconds": DEFAULT_INTERVAL_SECONDS}, None
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    )
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not _same_file(before, opened):
            raise QueueError("Monitor settings changed while opening them")
        raw = stream.read(MAX_SETTINGS_BYTES + 1)
        after = os.fstat(stream.fileno())
    _plain_path(path)
    if (
        len(raw) > MAX_SETTINGS_BYTES
        or not _same_file(opened, after)
        or not _same_file(after, _regular(path))
    ):
        raise QueueError("Monitor settings changed while reading them")
    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique, parse_constant=_invalid_constant
        )
    except (UnicodeError, ValueError, RecursionError) as error:
        raise QueueError("Monitor settings JSON is invalid") from error
    return _settings(value), after


def load_monitor_settings(work_root: Path) -> dict:
    """Return defaults without creating a settings file when none exists."""
    return _read(_path(work_root))[0]


def save_monitor_settings(work_root: Path, interval_seconds: int) -> dict:
    """Change the known settings file only; never replace unknown existing data."""
    value = {"schema_version": 1, "interval_seconds": validate_interval(interval_seconds)}
    path = _path(work_root)
    _, expected = _read(path)
    data = (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    descriptor = os.open(
        temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        _plain_path(path)
        if expected is None:
            if os.name == "nt":
                os.rename(temporary, path)
            else:
                os.link(temporary, path, follow_symlinks=False)
                temporary.unlink()
        else:
            if not _same_file(expected, _regular(path)):
                raise QueueError("Monitor settings changed before the update")
            os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)
    return value
