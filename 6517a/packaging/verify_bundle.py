"""Verify static package files. This does not validate VISA hardware or Windows execution."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath


def verify(root: Path, *, progress=None) -> dict:
    manifest = json.loads((root / "bundle_manifest.json").read_text(encoding="utf-8"))
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != 1
        or not isinstance(manifest.get("files"), dict)
    ):
        raise ValueError("Unsupported bundle manifest")
    errors = []
    verified = 0
    resolved_root = root.resolve()
    total = len(manifest["files"])
    if progress is not None:
        progress(0, total)
    for checked, (relative, expected) in enumerate(manifest["files"].items(), start=1):
        name = PurePosixPath(relative)
        if name.is_absolute() or ".." in name.parts or "\\" in relative or ":" in relative:
            raise ValueError("Manifest paths must stay inside the bundle")
        path = root.joinpath(*name.parts)
        if not path.resolve().is_relative_to(resolved_root):
            raise ValueError("Manifest symlink escapes the bundle")
        if not path.is_file():
            errors.append({"file": relative, "reason": "missing"})
        else:
            try:
                with path.open("rb") as stream:
                    actual = hashlib.file_digest(stream, "sha256").hexdigest()
            except OSError as exc:
                errors.append({"file": relative, "reason": str(exc)})
            else:
                if actual != expected:
                    errors.append({"file": relative, "reason": "hash mismatch"})
                else:
                    verified += 1
        if progress is not None:
            progress(checked, total)
    return {
        "status": "passed" if not errors else "failed",
        "verified_files": verified,
        "errors": errors,
        "scope": "static file integrity only",
        "native_windows_execution_verified": manifest.get("native_windows_execution_verified"),
        "hardware_verified": False,
    }


def save_report(root: Path, report: dict) -> dict:
    directory = root / "diagnostics"
    directory.mkdir(exist_ok=True)
    name = datetime.now(UTC).strftime("bundle-verification-%Y%m%dT%H%M%S%f")
    path = directory / f"{name}-{os.getpid()}.json"
    saved = dict(report, report_saved=True, report_path=str(path))
    with path.open("x", encoding="utf-8") as stream:
        json.dump(saved, stream, ensure_ascii=False, indent=2)
    return saved


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--progress", action="store_true", help="Show processed file counts")
    parser.add_argument("--save-report", action="store_true", help="Save a report in diagnostics")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    last_tick = 0.0

    def progress(checked, total):
        nonlocal last_tick
        now = time.monotonic()
        if checked in (0, total) or checked % 250 == 0 or now - last_tick >= 1.0:
            print(f"[CHECK] {checked}/{total} files processed", file=sys.stderr, flush=True)
            last_tick = now

    try:
        report = verify(root, progress=progress if args.progress else None)
    except (OSError, ValueError, TypeError) as exc:
        report = {
            "status": "failed",
            "verified_files": 0,
            "errors": [{"file": "bundle_manifest.json", "reason": str(exc)}],
            "scope": "static file integrity only",
            "native_windows_execution_verified": None,
            "hardware_verified": False,
        }
    if args.save_report:
        try:
            report = save_report(root, report)
        except OSError as exc:
            report.update(report_saved=False, report_error=str(exc))
            print(
                f"[WARN] Verification report could not be saved: {exc}", file=sys.stderr, flush=True
            )
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
