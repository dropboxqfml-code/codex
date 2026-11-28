import json
import sys
from contextlib import nullcontext
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest

from image_monitor import native_probe, native_state
from image_monitor.native_state import PendingSave, recover_pending
from image_monitor.native_ui import NativeUIError


def test_changing_work_root_cannot_bypass_shared_pending_state(tmp_path):
    marker = tmp_path / "app-state" / "native-save-session-1.json"
    first = PendingSave(marker)
    pending = first.begin(tmp_path / "root-a" / "run-a")
    second = PendingSave(marker)
    with pytest.raises(NativeUIError, match="unresolved"):
        second.begin(tmp_path / "root-b" / "run-b")
    assert second.read() == pending
    assert pending["run_directory"] == str(tmp_path / "root-a" / "run-a")


def test_crash_before_pid_registration_persists_and_blocks_active_profile_recovery(tmp_path):
    state = PendingSave(tmp_path / "pending.json")
    original = state.begin(tmp_path / "run")
    restarted = PendingSave(state.path)
    assert restarted.read()["browser_pid"] is None
    checks = []

    def active_profile(value):
        checks.append(value["browser_profile"])
        return True

    with pytest.raises(NativeUIError, match="still active"):
        recover_pending(restarted, is_running=active_profile)
    assert checks == [str(tmp_path / "run" / "browser-profile")]
    assert restarted.read() == original


@pytest.mark.parametrize("contents", ["{", "[]", "null", "{}", '{"run_id": 123}'])
def test_corrupt_or_invalid_state_blocks_new_saves_and_recovery(tmp_path, contents):
    path = tmp_path / "pending.json"
    path.write_text(contents, encoding="utf-8")
    state = PendingSave(path)
    is_running = MagicMock(return_value=False)
    with pytest.raises(NativeUIError, match="(unreadable|invalid)"):
        state.begin(tmp_path / "another-run")
    with pytest.raises(NativeUIError, match="(unreadable|invalid)"):
        recover_pending(state, is_running=is_running)
    is_running.assert_not_called()
    assert path.read_text(encoding="utf-8") == contents


def test_unreadable_state_is_not_treated_as_missing(tmp_path, monkeypatch):
    state = PendingSave(tmp_path / "pending.json")
    state.begin(tmp_path / "run")
    actual_open = Path.open

    def denied(path, *args, **kwargs):
        if path == state.path:
            raise PermissionError("Access denied")
        return actual_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied)
    with pytest.raises(NativeUIError, match="unreadable"):
        state.assert_clear()
    with pytest.raises(NativeUIError, match="unreadable"):
        recover_pending(state, is_running=lambda _value: False)
    assert state.path.exists()


def test_mismatched_run_token_cannot_finish_or_update_another_save(tmp_path):
    state = PendingSave(tmp_path / "pending.json")
    pending = state.begin(tmp_path / "run")
    other = pending | {"run_id": "different-run"}
    with pytest.raises(NativeUIError, match="changed unexpectedly"):
        state.finish(other)
    with pytest.raises(NativeUIError, match="changed unexpectedly"):
        state.update_browser(other, 123, 456.0)
    assert state.read() == pending


def test_successful_recovery_preserves_run_files_and_removes_only_marker(tmp_path):
    run = tmp_path / "run"
    (run / "_staging").mkdir(parents=True)
    (run / "browser-profile").mkdir()
    (run / "_staging" / "native-image.png").write_bytes(b"unfinished-bytes")
    (run / "report.json").write_text('{"status":"manual_review"}', encoding="utf-8")
    (run / "browser-profile" / "Preferences").write_bytes(b"profile-state")
    state = PendingSave(tmp_path / "app-state" / "pending.json")
    state.begin(run)
    unrelated = state.path.with_suffix(".unrelated")
    unrelated.write_bytes(b"preserve")
    before = {path.relative_to(run): path.read_bytes() for path in run.rglob("*") if path.is_file()}
    result = recover_pending(state, is_running=lambda _value: False)
    assert result == {"status": "resolved", "run_directory": str(run), "files_preserved": True}
    assert not state.path.exists()
    assert unrelated.read_bytes() == b"preserve"
    after = {path.relative_to(run): path.read_bytes() for path in run.rglob("*") if path.is_file()}
    assert before == after
    assert recover_pending(state, is_running=lambda _value: False) == {"status": "no_pending_save"}


def test_unverifiable_browser_status_does_not_clear_pending_state(tmp_path):
    state = PendingSave(tmp_path / "pending.json")
    original = state.begin(tmp_path / "run")

    def uncertain(_value):
        raise NativeUIError("Cannot inspect browser processes")

    with pytest.raises(NativeUIError, match="Cannot inspect"):
        recover_pending(state, is_running=uncertain)
    assert state.read() == original


def test_update_browser_persists_process_identity_across_restart(tmp_path):
    state = PendingSave(tmp_path / "pending.json")
    pending = state.begin(tmp_path / "run")
    state.update_browser(pending, 4567, 1234.5)
    restored = PendingSave(state.path).read()
    assert restored == pending
    assert restored["browser_pid"] == 4567
    assert restored["browser_create_time"] == 1234.5
    assert list(tmp_path.glob("*.tmp")) == []


def test_partial_initial_write_keeps_state_blocked(tmp_path, monkeypatch):
    state = PendingSave(tmp_path / "pending.json")

    def partial_write(_value, stream):
        stream.write('{"schema_version":')
        raise OSError("Simulated disk failure")

    monkeypatch.setattr(native_state.json, "dump", partial_write)
    with pytest.raises(OSError, match="disk failure"):
        state.begin(tmp_path / "run")
    assert state.path.exists()
    with pytest.raises(NativeUIError, match="unreadable"):
        state.begin(tmp_path / "another-run")
    with pytest.raises(NativeUIError, match="unreadable"):
        recover_pending(state, is_running=lambda _value: False)


@pytest.mark.parametrize("operation", ["write", "replace", "fsync"])
def test_failed_browser_identity_update_retains_blocking_original_state(
    tmp_path, monkeypatch, operation
):
    state = PendingSave(tmp_path / "pending.json")
    pending = state.begin(tmp_path / "run")
    original = pending.copy()

    def fail(*_args, **_kwargs):
        raise OSError("Simulated update failure")

    if operation == "write":
        monkeypatch.setattr(native_state.json, "dump", fail)
    elif operation == "replace":
        monkeypatch.setattr(Path, "replace", fail)
    else:
        monkeypatch.setattr(native_state.os, "fsync", fail)
    with pytest.raises(OSError, match="update failure"):
        state.update_browser(pending, 4567, 1234.5)
    assert pending == original
    assert state.read() == original
    with pytest.raises(NativeUIError, match="unresolved"):
        state.assert_clear()


def test_initial_fsync_failure_keeps_durable_state_blocked(tmp_path, monkeypatch):
    state = PendingSave(tmp_path / "pending.json")

    def fail(_descriptor):
        raise OSError("Simulated fsync failure")

    monkeypatch.setattr(native_state.os, "fsync", fail)
    with pytest.raises(OSError, match="fsync failure"):
        state.begin(tmp_path / "run")
    assert state.read()["browser_pid"] is None
    with pytest.raises(NativeUIError, match="unresolved"):
        state.assert_clear()


def test_native_ui_failure_blocks_launch_from_another_work_root(tmp_path, monkeypatch, capsys):
    marker = tmp_path / "app-state" / "pending.json"
    driver = MagicMock()
    monkeypatch.setitem(sys.modules, "playwright", ModuleType("playwright"))
    monkeypatch.setitem(
        sys.modules,
        "playwright.sync_api",
        SimpleNamespace(sync_playwright=lambda: SimpleNamespace(start=lambda: driver)),
    )
    monkeypatch.setitem(sys.modules, "pywinauto", ModuleType("pywinauto"))
    monkeypatch.setitem(
        sys.modules,
        "psutil",
        SimpleNamespace(Process=lambda _pid: SimpleNamespace(create_time=lambda: 1234.5)),
    )
    monkeypatch.setattr(native_probe, "require_windows", lambda: None)
    monkeypatch.setattr(native_probe, "browser_executable", lambda _name: tmp_path / "browser.exe")
    monkeypatch.setattr(native_probe, "NativeSaveLock", nullcontext)
    monkeypatch.setattr(native_probe, "shared_state_path", lambda: marker)
    process = SimpleNamespace(pid=4567)
    launch = MagicMock(return_value=process)
    monkeypatch.setattr(native_probe.subprocess, "Popen", launch)
    monkeypatch.setattr(native_probe, "wait_for_debug_port", lambda *_args: 12345)
    browser = MagicMock()
    browser.version = "test-browser"
    monkeypatch.setattr(native_probe, "connect_owned_browser", lambda *_args: browser)
    ui = SimpleNamespace(
        stage="save_dialog",
        target_hwnd=123,
        browser_suggested_filename=None,
        focus_snapshot=lambda: {"foreground_class": "ConsoleWindowClass"},
    )
    monkeypatch.setattr(native_probe, "WindowsUI", lambda *_args: ui)
    monkeypatch.setattr(native_probe, "environment_info", lambda _ui: {})
    monkeypatch.setattr(native_probe, "wait_for_user_start", lambda *_args: None)

    def fail_save(*_args):
        raise NativeUIError("Unrecognized native menu")

    monkeypatch.setattr(native_probe, "save_one_image", fail_save)
    with pytest.raises(NativeUIError, match="Unrecognized native menu"):
        native_probe.run_probe(tmp_path / "root-a", "edge")
    pending = PendingSave(marker).read()
    assert pending["browser_pid"] == 4567
    report = json.loads((Path(pending["run_directory"]) / "report.json").read_text())
    assert report["status"] == "manual_review"
    assert report["last_stage"] == "save_dialog"
    assert report["focus_at_failure"]["foreground_class"] == "ConsoleWindowClass"
    summary_line = next(
        line for line in capsys.readouterr().out.splitlines() if line.startswith("Probe summary: ")
    )
    summary = json.loads(summary_line.removeprefix("Probe summary: "))
    assert summary["last_stage"] == "save_dialog"
    assert summary["error_type"] == "NativeUIError"
    assert summary["browser_version"] == "test-browser"
    assert summary["environment"] == {}
    assert summary["focus_at_failure"] == report["focus_at_failure"]
    with pytest.raises(NativeUIError, match="unresolved"):
        native_probe.run_probe(tmp_path / "root-b", "edge")
    launch.assert_called_once()
    driver.stop.assert_called_once()
    assert PendingSave(marker).read() == pending


def mock_process_scan(monkeypatch, processes, *, registered_create_time=999.0):
    class ProcessError(Exception):
        pass

    class NoSuchProcess(ProcessError):
        pass

    lookup = MagicMock(return_value=SimpleNamespace(create_time=lambda: registered_create_time))
    psutil = SimpleNamespace(
        Process=lookup,
        process_iter=lambda _attrs: processes,
        Error=ProcessError,
        TimeoutExpired=type("TimeoutExpired", (ProcessError,), {}),
        NoSuchProcess=NoSuchProcess,
    )
    monkeypatch.setitem(sys.modules, "psutil", psutil)
    monkeypatch.setattr(native_state, "require_windows", lambda: None)
    monkeypatch.setattr(native_state, "session_id", lambda _pid=None: 1)
    return lookup


@pytest.mark.parametrize("split_argument", [False, True])
def test_recovery_scan_finds_active_profile_without_registered_pid(
    tmp_path,
    monkeypatch,
    split_argument,
):
    profile = tmp_path / "profile"
    args = ["--user-data-dir", str(profile)] if split_argument else [f"--user-data-dir={profile}"]
    process = SimpleNamespace(pid=4567, info={"name": "msedge.exe", "cmdline": args})
    lookup = mock_process_scan(monkeypatch, [process])
    value = {"browser_pid": None, "browser_profile": str(profile)}
    assert native_state.browser_still_running(value)
    lookup.assert_not_called()


def test_reused_pid_does_not_hide_a_restarted_browser_using_pending_profile(tmp_path, monkeypatch):
    profile = tmp_path / "profile"
    process = SimpleNamespace(
        pid=4567,
        info={"name": "chrome.exe", "cmdline": [f"--user-data-dir={profile}"]},
    )
    lookup = mock_process_scan(monkeypatch, [process], registered_create_time=222.0)
    value = {
        "browser_pid": 4567,
        "browser_create_time": 111.0,
        "browser_profile": str(profile),
    }
    assert native_state.browser_still_running(value)
    lookup.assert_called_once_with(4567)


@pytest.mark.parametrize("name,cmdline", [("chrome.exe", None), (None, [])])
def test_uninspectable_same_session_browser_blocks_recovery(tmp_path, monkeypatch, name, cmdline):
    process = SimpleNamespace(pid=4567, info={"name": name, "cmdline": cmdline})
    mock_process_scan(monkeypatch, [process])
    value = {"browser_pid": None, "browser_profile": str(tmp_path / "profile")}
    with pytest.raises(NativeUIError, match="recovery blocked"):
        native_state.browser_still_running(value)


@pytest.mark.parametrize(
    "registered_live,profile_elsewhere", [(False, False), (True, False), (False, True)]
)
def test_registered_process_handle_can_outlive_browser(
    tmp_path, monkeypatch, registered_live, profile_elsewhere
):
    profile = str(tmp_path / "profile")
    other = SimpleNamespace(
        pid=5678, info={"name": "chrome.exe", "cmdline": ["--user-data-dir", profile]}
    )
    lookup = mock_process_scan(monkeypatch, [other] if profile_elsewhere else [])
    wait = MagicMock(
        side_effect=sys.modules["psutil"].TimeoutExpired() if registered_live else None
    )
    lookup.return_value = SimpleNamespace(create_time=lambda: 999.0, wait=wait)
    value = {"browser_pid": 4567, "browser_create_time": 999.0, "browser_profile": profile}
    assert native_state.browser_still_running(value) is (registered_live or profile_elsewhere)
    wait.assert_called_once_with(timeout=0)
