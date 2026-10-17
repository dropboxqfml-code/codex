"""Validate a real frozen Windows executable and record reproducible build metadata."""

import hashlib
import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def main() -> int:
    if sys.platform != "win32":
        print("Windows frozen executable verification requires Windows.", file=sys.stderr)
        return 1
    root = Path(__file__).resolve().parents[1]
    bundle = root / "dist" / "Image Duplicate Finder"
    exe = bundle / "Image Duplicate Finder.exe"
    if not exe.is_file() or exe.read_bytes()[:2] != b"MZ":
        raise RuntimeError("Expected a Windows PE executable, not a source or Unix binary")
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    report = reports / "frozen-smoke.json"
    report.unlink(missing_ok=True)
    screenshot = report.with_suffix(".png")
    screenshot.unlink(missing_ok=True)
    # Running outside the checkout prevents source imports from masking missing bundled modules.
    result = subprocess.run(
        [str(exe), "--build-smoke-report", str(report)], cwd=bundle, timeout=120, check=False
    )
    if not report.is_file():
        raise RuntimeError(
            f"Frozen app did not produce a fresh smoke report (exit {result.returncode})"
        )
    outcome = json.loads(report.read_text(encoding="utf-8"))
    required = (
        "scan_gui_sqlite",
        "confirmation_no_preserves_file",
        "confirmation_yes_recycles_generated_copy",
        "native_windows_recycle_bin_bytes",
    )
    if (
        result.returncode != 0
        or outcome.get("status") != "passed"
        or outcome.get("platform") != "win32"
        or not outcome.get("frozen")
        or outcome.get("qt_platform") != "windows"
        or not outcome.get("python_guard_enabled")
        or any(outcome.get("python_blocked_attempts", {}).values())
        or any(outcome.get(key) != "passed" for key in required)
        or not screenshot.is_file()
    ):
        raise RuntimeError(f"Frozen Windows smoke failed: {outcome}")
    versions = {
        name: importlib.metadata.version(name)
        for name in [
            "PyInstaller",
            "PySide6-Essentials",
            "Pillow",
            "ImageHash",
            "Send2Trash",
            "pywin32",
        ]
    }
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    info = {
        "commit": commit,
        "built_at_utc": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "architecture": platform.machine(),
        "dependencies": versions,
        "code_signed": False,
        "automated_frozen_smoke": outcome,
        "manual_windows_acceptance": "not performed by this workflow",
    }
    (root / "dist" / "BUILD-INFO.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    shutil.copyfile(root / "packaging" / "READ_ME_FIRST.txt", bundle / "READ_ME_FIRST.txt")
    shutil.copyfile(root / "docs" / "windows-acceptance.md", bundle / "WINDOWS-ACCEPTANCE.md")
    files = sorted(p for p in (root / "dist").rglob("*") if p.is_file())
    with (root / "dist" / "SHA256SUMS.txt").open("w", encoding="utf-8", newline="\n") as stream:
        for path in files:
            if path.name == "SHA256SUMS.txt" and path.parent == root / "dist":
                continue
            with path.open("rb") as source:
                digest = hashlib.file_digest(source, "sha256").hexdigest()
            stream.write(f"{digest}  {path.relative_to(root / 'dist').as_posix()}\n")
    print("PASS: frozen Windows Qt, image matching, SQLite, confirmation and Recycle Bin checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
