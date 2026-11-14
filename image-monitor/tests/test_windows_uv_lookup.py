"""Exercise real CMD lookup without executing uv, installing anything, or opening a UI.

The registry case is restricted to explicitly opted-in GitHub Actions Windows runners.
It restores the exact previous User PATH value/type before leaving the test.
"""

import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Requires real Windows CMD")
LAUNCHER = Path(__file__).resolve().parents[1] / "RUN_WINDOWS_TEST.cmd"


def run_lookup(*, path: str) -> str:
    # Refuse to run an older launcher that could enter installation instead.
    assert "--find-uv" in LAUNCHER.read_text(encoding="ascii")
    environment = os.environ.copy()
    environment["PATH"] = path
    environment["PYTHONUTF8"] = "1"
    command_processor = Path(environment["SystemRoot"]) / "System32" / "cmd.exe"
    # /s /c needs one surrounding quote pair in addition to the executable's pair.
    command = f'"{command_processor}" /d /s /c ""{LAUNCHER}" --find-uv"'
    existing_logs = set(LAUNCHER.parent.glob("WINDOWS_TEST_RESULT-*.txt"))
    result = subprocess.run(
        command,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=30,
        check=False,
    )
    assert set(LAUNCHER.parent.glob("WINDOWS_TEST_RESULT-*.txt")) == existing_logs
    assert result.returncode == 0, result.stderr
    lines = result.stdout.strip().splitlines()
    assert len(lines) == 1, result.stdout
    assert lines[0].startswith('"') and lines[0].endswith('"'), result.stdout
    return lines[0][1:-1]


def fake_uv(directory: Path) -> Path:
    directory.mkdir()
    executable = directory / "uv.exe"
    # Deliberately not a PE executable. Lookup must never invoke it, even for --version.
    executable.write_bytes(b"not executable: discovery fixture only\r\n")
    return executable


def test_process_path_lookup_preserves_korean_spaces_and_ampersand(tmp_path):
    executable = fake_uv(tmp_path / "uv 한글 & space")
    system32 = Path(os.environ["SystemRoot"]) / "System32"
    found = run_lookup(path=f"{executable.parent};{system32}")
    assert os.path.normcase(found) == os.path.normcase(str(executable))


@contextmanager
def temporary_ci_user_path(value: str):
    # Keep the safety guard inside the helper too, not just in a pytest decorator.
    if not (
        sys.platform == "win32"
        and os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("IMAGE_MONITOR_ALLOW_PATH_TESTS") == "1"
    ):
        raise RuntimeError("User PATH mutation is permitted only in an opted-in Windows CI runner")
    import winreg

    access = winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, access) as key:
        try:
            original, original_type = winreg.QueryValueEx(key, "Path")
            existed = True
        except FileNotFoundError:
            original, original_type, existed = None, None, False
        winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, value)
        try:
            yield
        finally:
            if existed:
                winreg.SetValueEx(key, "Path", 0, original_type, original)
            else:
                winreg.DeleteValue(key, "Path")


def machine_path_has_uv() -> bool:
    import winreg

    machine_key = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, machine_key) as key:
        try:
            value, _kind = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            return False
    return any(
        (Path(os.path.expandvars(part.strip().strip('"'))) / "uv.exe").is_file()
        for part in value.split(";")
        if part.strip()
    )


@pytest.mark.skipif(
    os.environ.get("GITHUB_ACTIONS") != "true"
    or os.environ.get("IMAGE_MONITOR_ALLOW_PATH_TESTS") != "1",
    reason="Persistent PATH fixture is restricted to an explicitly opted-in GitHub Actions runner",
)
def test_stale_process_path_discovers_custom_registered_user_path(tmp_path):
    if machine_path_has_uv():
        pytest.skip("Machine PATH already resolves uv before the isolated User PATH fixture")
    executable = fake_uv(tmp_path / "새 설치 uv & space")
    system32 = Path(os.environ["SystemRoot"]) / "System32"
    # The parent process deliberately omits the new install directory. Only the
    # child resolver's registry refresh can see this custom, nondefault location.
    with temporary_ci_user_path(str(executable.parent)):
        found = run_lookup(path=str(system32))
    assert os.path.normcase(found) == os.path.normcase(str(executable))
