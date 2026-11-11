"""Verify static package files. This does not validate VISA hardware or Windows execution."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path, PurePosixPath


def verify(root: Path) -> dict:
    manifest = json.loads((root / "bundle_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("files"), dict):
        raise ValueError("Unsupported bundle manifest")
    errors = []
    verified = 0
    resolved_root = root.resolve()
    for relative, expected in manifest["files"].items():
        name = PurePosixPath(relative)
        if name.is_absolute() or ".." in name.parts or "\\" in relative or ":" in relative:
            raise ValueError("Manifest paths must stay inside the bundle")
        path = root.joinpath(*name.parts)
        if not path.resolve().is_relative_to(resolved_root):
            raise ValueError("Manifest symlink escapes the bundle")
        if not path.is_file():
            errors.append({"file": relative, "reason": "missing"})
            continue
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != expected:
            errors.append({"file": relative, "reason": "hash mismatch"})
        else:
            verified += 1
    return {
        "status": "passed" if not errors else "failed",
        "verified_files": verified,
        "errors": errors,
        "scope": "static file integrity only",
        "native_windows_execution_verified": manifest.get("native_windows_execution_verified"),
        "hardware_verified": False,
    }


def main(argv=None) -> int:
    root = Path(argv[0]) if argv else Path(__file__).resolve().parents[1]
    report = verify(root)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
