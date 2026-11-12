"""Test a delivered Windows ZIP after relocation; all instrument work is simulated."""

from __future__ import annotations

import argparse
import importlib.util
import json
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


def source_backed_caches(root: Path) -> list[Path]:
    caches = []
    for path in root.rglob("*.pyc"):
        if path.parent.name != "__pycache__":
            continue
        try:
            source = Path(importlib.util.source_from_cache(str(path)))
        except ValueError:
            continue
        if source.is_file():
            caches.append(path)
    return caches


def extract_bundle(archive: Path, destination: Path) -> Path:
    with zipfile.ZipFile(archive) as stream:
        roots = set()
        names = set()
        for entry in stream.infolist():
            name = PurePosixPath(entry.filename)
            if (
                not name.parts
                or name.is_absolute()
                or ".." in name.parts
                or "\\" in entry.filename
                or ":" in entry.filename
                or stat.S_ISLNK(entry.external_attr >> 16)
                or entry.filename in names
            ):
                raise ValueError("Release ZIP contains an unsafe or duplicate entry")
            names.add(entry.filename)
            roots.add(name.parts[0])
        if len(roots) != 1:
            raise ValueError("Release ZIP must contain exactly one bundle directory")
        stream.extractall(destination)
    root = (destination / roots.pop()).resolve()
    if not root.is_relative_to(destination.resolve()) or not root.is_dir():
        raise ValueError("Extracted release root is not a bundle directory")
    return root


def run_child(root: Path, arguments: list[str | Path], *, expected_code=0, timeout=180):
    result = subprocess.run(
        [str(value) for value in arguments],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if result.returncode != expected_code:
        raise RuntimeError(
            f"Relocated child exited {result.returncode}, expected {expected_code}\n"
            f"stdout:\n{result.stdout[-5000:]}\nstderr:\n{result.stderr[-5000:]}"
        )
    return result


def verify_files(root: Path, *, passed=True) -> dict:
    result = run_child(
        root,
        [
            root / "runtime/python.exe",
            "-I",
            "-B",
            "-X",
            "utf8",
            root / "tools/verify_bundle.py",
            root,
        ],
        expected_code=0 if passed else 2,
    )
    report = json.loads(result.stdout)
    expected_status = "passed" if passed else "failed"
    if report.get("status") != expected_status or report.get("hardware_verified") is not False:
        raise RuntimeError("Relocated verifier returned an unexpected result")
    if passed and report.get("errors"):
        raise RuntimeError("Relocated verifier reported file errors")
    return report


def verify_relocated_bundle(archive: Path) -> dict:
    print("[RELOCATION] Extracting delivered ZIP into a new path", file=sys.stderr, flush=True)
    with tempfile.TemporaryDirectory(prefix="6517a-relocation-") as temporary:
        destination = Path(temporary).resolve() / "relocated bundle 시험"
        destination.mkdir()
        root = extract_bundle(archive.resolve(), destination)
        manifest_path = root / "bundle_manifest.json"
        original_manifest = manifest_path.read_bytes()
        manifest = json.loads(original_manifest)
        files = manifest["files"]
        release = json.loads((root / "release.json").read_text(encoding="utf-8"))
        if (
            release.get("default_mode") != "SIMULATION"
            or release.get("automatic_output_enable") is not False
            or release.get("hardware_verified") is not False
        ):
            raise RuntimeError(
                "Relocation smoke requires a disconnected simulation-default release"
            )
        if source_backed_caches(root):
            raise RuntimeError("Delivered ZIP contains generated source-backed bytecode")
        for relative in files:
            path = root / relative
            if path.suffix == ".pyc" and path.parent.name == "__pycache__":
                try:
                    source = Path(importlib.util.source_from_cache(str(path)))
                except ValueError:
                    continue
                if source.is_file():
                    raise RuntimeError("Manifest includes mutable source-backed bytecode")
        first = verify_files(root)
        if first.get("verified_files") != len(files):
            raise RuntimeError("Initial relocated verification did not check every static file")

        print("[RELOCATION] Running bundled synthetic CLI and GUI", file=sys.stderr, flush=True)
        result = run_child(
            root,
            [
                root / "runtime/python.exe",
                "-I",
                "-B",
                "-X",
                "utf8",
                root / "tools/smoke.py",
                "--skip-optional-installer",
            ],
        )
        summary = json.loads(result.stdout.strip().splitlines()[-1])
        if (
            summary.get("status") != "passed"
            or summary.get("hardware_verified") is not False
            or summary.get("reference_1gohm_simulation_verified") is not True
        ):
            raise RuntimeError("Relocated synthetic CLI/GUI did not confirm success")

        print(
            "[RELOCATION] Regenerating mutable caches, then rechecking", file=sys.stderr, flush=True
        )
        before = len(source_backed_caches(root))
        probe = (
            "import json, sys; from pathlib import Path; "
            "sys.path.insert(0, str(Path.cwd() / 'app/src')); "
            "import keithley6517a.config; "
            "print(json.dumps({'bytecode_enabled': not sys.dont_write_bytecode}))"
        )
        result = run_child(root, [root / "runtime/python.exe", "-I", "-X", "utf8", "-c", probe])
        generated = len(source_backed_caches(root)) - before
        if not json.loads(result.stdout).get("bytecode_enabled") or generated <= 0:
            raise RuntimeError("Cache regression probe did not actually generate mutable bytecode")
        verify_files(root)

        print("[RELOCATION] Checking source and DLL tamper detection", file=sys.stderr, flush=True)
        changed_names = (
            "app/src/keithley6517a/__init__.py",
            "runtime/Lib/site-packages/PySide6/plugins/platforms/qwindows.dll",
        )
        originals = {}
        try:
            for relative in changed_names:
                if relative not in files:
                    raise RuntimeError("Source/DLL tamper probe is absent from the static manifest")
                path = root / relative
                original = path.read_bytes()
                if not original:
                    raise RuntimeError("Source/DLL tamper probe requires a nonempty file")
                originals[path] = original
                path.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
            failed = verify_files(root, passed=False)
            mismatches = {
                error["file"]
                for error in failed.get("errors", [])
                if error.get("reason") == "hash mismatch"
            }
            if mismatches != set(changed_names) or len(failed["errors"]) != len(changed_names):
                raise RuntimeError("Verifier did not identify exactly the changed source and DLL")
        finally:
            for path, original in originals.items():
                path.write_bytes(original)
        verify_files(root)
        if manifest_path.read_bytes() != original_manifest:
            raise RuntimeError("Relocation smoke changed the static integrity manifest")
        checks = {
            "archive_has_no_source_backed_bytecode": True,
            "initial_integrity_passed": True,
            "relocated_synthetic_cli_gui_passed": True,
            "reference_1gohm_simulation_verified": True,
            "regenerated_bytecode_files": generated,
            "integrity_after_cache_generation_passed": True,
            "source_and_dll_tampering_rejected": True,
            "restored_integrity_passed": True,
            "manifest_unchanged": True,
        }
    return {
        "status": "passed",
        "scope": "relocated Windows ZIP, synthetic CLI/GUI and static integrity regression",
        "relocated_windows_execution_verified": True,
        "hardware_verified": False,
        "checks": checks,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        raise RuntimeError("Relocated bundle verification requires an actual Windows host")
    report = verify_relocated_bundle(args.archive)
    print(json.dumps(report, ensure_ascii=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
