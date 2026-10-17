import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_rejects_non_windows_and_non_x64(monkeypatch):
    build = load_script("build_windows")
    monkeypatch.setattr(build, "sys", SimpleNamespace(platform="linux", stderr=sys.stderr))
    assert build.main() == 1
    monkeypatch.setattr(build, "sys", SimpleNamespace(platform="win32", stderr=sys.stderr))
    monkeypatch.setattr(build.struct, "calcsize", lambda _: 4)
    assert build.main() == 1


def test_windows_build_uses_spec_and_propagates_failure(monkeypatch):
    build = load_script("build_windows")
    monkeypatch.setattr(build, "sys", SimpleNamespace(platform="win32", executable="python.exe"))
    calls = []

    def fail(command, cwd):
        calls.append((command, cwd))
        return 7

    monkeypatch.setattr(build.subprocess, "call", fail)
    assert build.main() == 7
    command, cwd = calls[0]
    assert command[:3] == ["python.exe", "-m", "PyInstaller"]
    assert Path(command[-1]) == ROOT / "packaging" / "windows.spec"
    assert cwd == ROOT


def test_frozen_smoke_driver_exercises_gui_and_confirmations(tmp_path):
    # Source-mode test only, with a fake recycle location instead of the developer's trash.
    script = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from image_duplicate_finder import trash
import frozen_smoke
destination = Path(sys.argv[2]).parent / 'mock-recycled.bin'
trash.recycle_file = lambda path: Path(path).rename(destination)
frozen_smoke.verify_windows_recycle_bin = lambda *_: None
raise SystemExit(frozen_smoke.run(Path(sys.argv[2]), native_windows=False))
"""
    report = tmp_path / "smoke.json"
    result = subprocess.run(
        [sys.executable, "-c", script, str(ROOT / "packaging"), str(report)],
        cwd=tmp_path,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr + (
        report.read_text(encoding="utf-8") if report.exists() else ""
    )
    outcome = json.loads(report.read_text(encoding="utf-8"))
    assert outcome["status"] == "passed"
    assert outcome["frozen"] is False
    assert outcome["scan_gui_sqlite"] == "passed"
    assert outcome["confirmation_no_preserves_file"] == "passed"
    assert outcome["confirmation_yes_recycles_generated_copy"] == "passed"
    assert (tmp_path / "mock-recycled.bin").exists()
    assert report.with_suffix(".png").stat().st_size > 0
