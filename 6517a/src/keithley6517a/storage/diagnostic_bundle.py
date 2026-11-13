"""Export a bounded, local diagnostic snapshot without opening an instrument."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import stat
import sys
import zipfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from .. import __version__

MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024
MAX_LOG_BYTES = 1024 * 1024
MAX_CONTEXT_BYTES = 1024 * 1024
MAX_STARTUP_ENTRIES = 4096
RUN_FILES = (
    "config.json",
    "metadata.json",
    "run_status.json",
    "events.jsonl",
    "raw_io.jsonl",
    "summary.csv",
    "readings.csv",
    "analysis.txt",
)
DIAGNOSTIC_FILES = ("diagnostic.json", "raw_io.jsonl")
STARTUP_PREFIXES = ("startup-check-", "bundle-verification-", "launcher-error-")


def _absolute(path):
    return Path(os.path.abspath(Path(path).expanduser()))


def _linked(info):
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _checked_stat(path):
    """Check every component before reading; do not follow links or Windows junctions."""
    for component in (*reversed(path.parents), path):
        info = component.lstat()
        if _linked(info):
            raise ValueError("symbolic link or reparse point")
    return info


def _omit(omitted, source, reason, **details):
    omitted.append({"source": str(source), "reason": reason, **details})


def _directory(value, category, omitted):
    if value is None:
        _omit(omitted, category, "not_selected")
        return None
    path = _absolute(value)
    try:
        info = _checked_stat(path)
    except FileNotFoundError:
        _omit(omitted, path, "missing_directory")
    except ValueError:
        _omit(omitted, path, "unsafe_link")
    except OSError as exc:
        _omit(omitted, path, "unreadable_directory", detail=str(exc))
    else:
        if stat.S_ISDIR(info.st_mode):
            return path
        _omit(omitted, path, "not_directory")
    return None


def _startup_reports(directory, omitted):
    """Select one latest report of each kind from the diagnostics root only."""
    latest = {}
    counts = dict.fromkeys(STARTUP_PREFIXES, 0)
    try:
        with os.scandir(directory) as entries:
            for count, entry in enumerate(entries, start=1):
                if count > MAX_STARTUP_ENTRIES:
                    _omit(omitted, directory, "startup_scan_limit", limit=MAX_STARTUP_ENTRIES)
                    return []
                prefix = next(
                    (
                        value
                        for value in STARTUP_PREFIXES
                        if entry.name.startswith(value) and entry.name.endswith(".json")
                    ),
                    None,
                )
                if prefix is None:
                    continue
                path = directory / entry.name
                if not re.fullmatch(r"[A-Za-z0-9_.-]+", entry.name):
                    _omit(omitted, path, "unsafe_report_name")
                    continue
                info = entry.stat(follow_symlinks=False)
                if _linked(info):
                    _omit(omitted, path, "unsafe_link")
                    continue
                if not stat.S_ISREG(info.st_mode):
                    _omit(omitted, path, "not_regular_file")
                    continue
                counts[prefix] += 1
                key = (info.st_mtime_ns, entry.name)
                if prefix not in latest or key > latest[prefix][0]:
                    latest[prefix] = (key, path)
    except OSError as exc:
        _omit(omitted, directory, "startup_scan_error", detail=str(exc))
        return []
    for prefix in STARTUP_PREFIXES:
        if counts[prefix] == 0:
            _omit(omitted, directory / f"{prefix}*.json", "missing_report")
        elif counts[prefix] > 1:
            _omit(
                omitted,
                directory / f"{prefix}*.json",
                "older_reports",
                count=counts[prefix] - 1,
            )
    return [latest[prefix][1] for prefix in STARTUP_PREFIXES if prefix in latest]


def _read_snapshot(path, remaining, omitted):
    try:
        before = _checked_stat(path)
        if not stat.S_ISREG(before.st_mode):
            _omit(omitted, path, "not_regular_file")
            return None
        if before.st_size > MAX_FILE_BYTES:
            _omit(omitted, path, "file_size_limit", bytes=before.st_size, limit=MAX_FILE_BYTES)
            return None
        if before.st_size > remaining:
            _omit(omitted, path, "total_size_limit", bytes=before.st_size, available=remaining)
            return None
        descriptor = os.open(
            path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        )
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            current = _checked_stat(path)
            if (
                not stat.S_ISREG(opened.st_mode)
                or _linked(opened)
                or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino)
            ):
                raise ValueError("source changed before reading")
            content = stream.read(min(MAX_FILE_BYTES, remaining) + 1)
            after = os.fstat(stream.fileno())
        if len(content) != before.st_size or (before.st_dev, before.st_ino, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_mtime_ns,
        ):
            _omit(omitted, path, "source_changed")
            return None
        return content
    except FileNotFoundError:
        _omit(omitted, path, "missing_file")
    except ValueError:
        _omit(omitted, path, "unsafe_or_changed_source")
    except OSError as exc:
        _omit(omitted, path, "read_error", detail=str(exc))
    return None


def export_diagnostic_bundle(
    output,
    *,
    run_directory=None,
    diagnostic_directory=None,
    startup_directory=None,
    log_text="",
    context=None,
):
    """Save a new ZIP of explicitly selected records; originals are never modified.

    ``startup_directory`` is the bundle's diagnostics root, not the simulation
    run directory. Its latest startup report contains the simulation summary.
    Missing, unsafe, changed, or oversized records are listed in manifest.json.
    No recursive folder scans, environment variables, drivers, or network calls
    are used. The caller should export only while acquisition is idle.
    """
    if not isinstance(log_text, str):
        raise ValueError("Diagnostic log must be text")
    if context is not None and not isinstance(context, Mapping):
        raise ValueError("Diagnostic context must be a JSON object")
    # Validate before creating an output, and make an independent JSON snapshot.
    encoded_context = json.dumps(dict(context or {}), ensure_ascii=False, allow_nan=False)
    if len(encoded_context.encode("utf-8")) > MAX_CONTEXT_BYTES:
        raise ValueError("Diagnostic context exceeds its size limit")
    context = json.loads(encoded_context)
    destination = _absolute(output)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"Diagnostic ZIP already exists: {destination}")
    if not stat.S_ISDIR(_checked_stat(destination.parent).st_mode):
        raise ValueError("Diagnostic ZIP parent must be a directory")

    omitted = []
    candidates = []
    for value, category, names in (
        (run_directory, "run", RUN_FILES),
        (diagnostic_directory, "diagnostic", DIAGNOSTIC_FILES),
    ):
        directory = _directory(value, category, omitted)
        if directory is not None:
            candidates.extend((directory / name, f"source/{category}/{name}") for name in names)
    startup = _directory(startup_directory, "startup", omitted)
    if startup is not None:
        candidates.extend(
            (path, f"source/startup/{path.name}") for path in _startup_reports(startup, omitted)
        )
    if any(destination == path for path, _ in candidates):
        raise ValueError("Diagnostic ZIP must not replace a source record")

    payloads = []
    files = []

    def include(name, content, source=None):
        payloads.append((name, content))
        files.append(
            dict(
                name=name,
                source=str(source) if source is not None else None,
                bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
            )
        )

    log = log_text[-MAX_LOG_BYTES:].encode("utf-8")
    limit = min(MAX_LOG_BYTES, MAX_FILE_BYTES, MAX_TOTAL_BYTES)
    if len(log_text) > MAX_LOG_BYTES or len(log) > limit:
        log = log[-limit:].decode("utf-8", errors="ignore").encode("utf-8") if limit else b""
        _omit(
            omitted,
            "gui/log.txt",
            "log_truncated",
            kept_bytes=len(log),
            original_characters=len(log_text),
        )
    include("gui/log.txt", log)
    used = len(log)
    for path, name in candidates:
        content = _read_snapshot(path, MAX_TOTAL_BYTES - used, omitted)
        if content is not None:
            include(name, content, path)
            used += len(content)
    manifest = dict(
        schema_version=1,
        kind="6517A local diagnostic bundle",
        created_at=datetime.now(UTC).isoformat(),
        software=dict(
            version=__version__,
            python=platform.python_version(),
            platform=sys.platform,
            machine=platform.machine(),
        ),
        hardware_accessed=False,
        automatically_uploaded=False,
        context=context,
        limits=dict(
            file_bytes=MAX_FILE_BYTES,
            total_bytes=MAX_TOTAL_BYTES,
            log_bytes=MAX_LOG_BYTES,
            startup_entries=MAX_STARTUP_ENTRIES,
        ),
        files=files,
        omitted=omitted,
    )
    while True:
        manifest_bytes = (
            json.dumps(manifest, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
        ).encode("utf-8")
        if used + len(manifest_bytes) <= MAX_TOTAL_BYTES:
            break
        if not payloads:
            raise ValueError("Diagnostic manifest exceeds the total size limit")
        name, content = payloads.pop()
        item = files.pop()
        used -= len(content)
        _omit(omitted, item["source"] or name, "manifest_total_size_limit", bytes=len(content))

    created = False
    try:
        with destination.open("xb") as stream:
            created = True
            with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, content in payloads:
                    archive.writestr(name, content)
                archive.writestr("manifest.json", manifest_bytes)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        if created:
            destination.unlink(missing_ok=True)
        raise
    return {
        "path": str(destination),
        "included": [name for name, _ in payloads] + ["manifest.json"],
        "omitted": omitted,
    }
