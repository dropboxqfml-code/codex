"""Refuse to reconnect or close unless every completed-browser proof agrees."""

import socket
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from image_monitor import completed_browser_close as recovery
from image_monitor.native_ui import NativeUIError

PORT = 43123
BROWSER_PATH = "/devtools/browser/12345678-1234-1234-1234-123456789abc"


class InspectionError(Exception):
    pass


class Gone(InspectionError):
    pass


class WaitExpired(InspectionError):
    pass


def listener(*, ip="127.0.0.1", port=PORT, status="LISTEN", family=socket.AF_INET):
    return SimpleNamespace(
        family=family,
        type=socket.SOCK_STREAM,
        status=status,
        laddr=SimpleNamespace(ip=ip, port=port),
    )


@pytest.fixture
def owned(tmp_path, monkeypatch):
    profile = tmp_path / "owned-profile"
    profile.mkdir()
    endpoint = profile / "DevToolsActivePort"
    endpoint.write_text(f"{PORT}\n{BROWSER_PATH}\n", encoding="ascii")
    process = Mock()
    process.pid = 4567
    process.create_time.return_value = 1234.5
    process.name.return_value = "chrome.exe"
    process.cmdline.return_value = ["chrome.exe", f"--user-data-dir={profile}"]
    process.net_connections.return_value = [listener()]
    process.wait.return_value = 0
    psutil = SimpleNamespace(
        Error=InspectionError,
        NoSuchProcess=Gone,
        TimeoutExpired=WaitExpired,
        CONN_LISTEN="LISTEN",
        Process=Mock(return_value=process),
    )
    driver, browser = Mock(), Mock()
    manager = SimpleNamespace(start=Mock(return_value=driver))
    connect = Mock(return_value=browser)
    close = Mock()
    running = Mock(return_value=False)
    monkeypatch.setattr(recovery, "require_windows", lambda: None)
    monkeypatch.setattr(recovery, "session_id", lambda _pid=None: 7)
    monkeypatch.setattr(recovery, "_psutil", lambda: psutil)
    playwright = Mock(return_value=manager)
    monkeypatch.setattr(recovery, "_playwright", playwright)
    monkeypatch.setattr(recovery, "connect_owned_browser", connect)
    monkeypatch.setattr(recovery, "close_probe_browser", close)
    monkeypatch.setattr(recovery, "browser_still_running", running)
    return SimpleNamespace(
        pending={
            "browser_pid": process.pid,
            "browser_create_time": 1234.5,
            "browser_profile": str(profile),
        },
        profile=profile,
        endpoint=endpoint,
        process=process,
        psutil=psutil,
        driver=driver,
        browser=browser,
        connect=connect,
        close=close,
        running=running,
        playwright=playwright,
    )


def assert_no_connection_or_close(owned):
    owned.playwright.assert_not_called()
    owned.connect.assert_not_called()
    owned.close.assert_not_called()
    owned.process.terminate.assert_not_called()
    owned.process.kill.assert_not_called()


def test_exact_owned_listener_is_rechecked_and_closed_without_launch_or_native_input(owned):
    assert recovery.close_completed_browser(owned.pending) is True
    owned.connect.assert_called_once_with(owned.driver, PORT)
    assert owned.process.create_time.call_count == 2
    assert owned.process.net_connections.call_args_list[0].kwargs == {"kind": "tcp"}
    assert owned.process.net_connections.call_count == 2
    owned.close.assert_called_once()
    browser, waiter = owned.close.call_args.args
    assert browser is owned.browser
    assert waiter.wait(timeout=10) == 0
    owned.process.wait.assert_called_once_with(timeout=10)
    owned.running.assert_called_once_with(owned.pending)
    owned.driver.stop.assert_called_once_with()
    owned.process.terminate.assert_not_called()
    owned.process.kill.assert_not_called()


def test_profile_remaining_after_process_close_is_not_success(owned):
    owned.running.return_value = True
    assert recovery.close_completed_browser(owned.pending) is False
    owned.close.assert_called_once()
    owned.driver.stop.assert_called_once()


@pytest.mark.parametrize("missing", [True, False])
def test_missing_or_reused_pid_never_reconnects_to_a_stale_port(owned, missing):
    if missing:
        owned.psutil.Process.side_effect = Gone("Synthetic gone process")
    else:
        owned.process.create_time.return_value = 9999
    assert recovery.close_completed_browser(owned.pending) is False
    assert_no_connection_or_close(owned)


@pytest.mark.parametrize(
    "change",
    [
        {"browser_pid": True},
        {"browser_pid": 0},
        {"browser_pid": -1},
        {"browser_create_time": True},
        {"browser_create_time": float("nan")},
        {"browser_create_time": float("inf")},
        {"browser_create_time": 10**1000},
    ],
)
def test_invalid_registration_is_refused_before_any_process_inspection(owned, change):
    with pytest.raises(NativeUIError, match="registration"):
        recovery.close_completed_browser(owned.pending | change)
    owned.psutil.Process.assert_not_called()
    assert_no_connection_or_close(owned)


def test_platform_guard_precedes_profile_or_process_access(owned, monkeypatch):
    def unsupported():
        raise NativeUIError("Windows required")

    monkeypatch.setattr(recovery, "require_windows", unsupported)
    with pytest.raises(NativeUIError, match="Windows"):
        recovery.close_completed_browser(owned.pending)
    owned.psutil.Process.assert_not_called()
    assert_no_connection_or_close(owned)


@pytest.mark.parametrize("name", ["msedge.exe", "python.exe", None])
def test_only_registered_chrome_can_be_closed(owned, name):
    owned.process.name.return_value = name
    with pytest.raises(NativeUIError, match="not Chrome"):
        recovery.close_completed_browser(owned.pending)
    assert_no_connection_or_close(owned)


def test_foreign_windows_session_is_refused(owned, monkeypatch):
    monkeypatch.setattr(recovery, "session_id", lambda pid=None: 8 if pid else 7)
    with pytest.raises(NativeUIError, match="session"):
        recovery.close_completed_browser(owned.pending)
    assert_no_connection_or_close(owned)


@pytest.mark.parametrize("kind", ["missing", "duplicate", "unknown", "relative", "wrong"])
def test_profile_flags_must_unambiguously_match_the_exact_registered_directory(owned, kind):
    profile_flag = f"--user-data-dir={owned.profile}"
    arguments = {
        "missing": ["chrome.exe"],
        "duplicate": ["chrome.exe", profile_flag, "--user-data-dir", str(owned.profile)],
        "unknown": ["chrome.exe", profile_flag, "--user-data-directory=elsewhere"],
        "relative": ["chrome.exe", "--user-data-dir=relative-profile"],
        "wrong": ["chrome.exe", f"--user-data-dir={owned.profile.parent}"],
    }
    owned.process.cmdline.return_value = arguments[kind]
    with pytest.raises(NativeUIError):
        recovery.close_completed_browser(owned.pending)
    assert_no_connection_or_close(owned)


def test_separate_profile_flag_argument_is_supported(owned):
    owned.process.cmdline.return_value = ["chrome.exe", "--user-data-dir", str(owned.profile)]
    assert recovery.close_completed_browser(owned.pending)


@pytest.mark.parametrize(
    "contents",
    [
        b"",
        b"0\n/path\n",
        b"65536\n/path\n",
        b"043123\n/path\n",
        f"{PORT}\n{BROWSER_PATH}?token=secret\n".encode(),
        f"{PORT}\n/devtools/page/123\n".encode(),
        f"{PORT}\n{BROWSER_PATH}\nextra\n".encode(),
        b"\xff\xfe",
    ],
)
def test_malformed_endpoint_never_connects(owned, contents):
    owned.endpoint.write_bytes(contents)
    with pytest.raises(NativeUIError, match="endpoint"):
        recovery.close_completed_browser(owned.pending)
    assert_no_connection_or_close(owned)


def test_oversized_endpoint_is_refused_before_opening_debugger(owned):
    owned.endpoint.write_bytes(b"x" * 4097)
    with pytest.raises(NativeUIError, match="endpoint"):
        recovery.close_completed_browser(owned.pending)
    assert_no_connection_or_close(owned)


def test_endpoint_symlink_is_refused_and_preserved(owned):
    original = owned.endpoint.read_bytes()
    foreign = owned.profile.parent / "foreign-port.txt"
    foreign.write_bytes(original)
    owned.endpoint.unlink()
    try:
        owned.endpoint.symlink_to(foreign)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation unavailable")
    with pytest.raises(NativeUIError, match="endpoint"):
        recovery.close_completed_browser(owned.pending)
    assert owned.endpoint.is_symlink()
    assert foreign.read_bytes() == original
    assert_no_connection_or_close(owned)


@pytest.mark.parametrize(
    "connections",
    [
        [],
        [listener(ip="0.0.0.0")],
        [listener(port=PORT + 1)],
        [listener(status="ESTABLISHED")],
        [listener(family=socket.AF_INET6)],
        [listener(), listener()],
    ],
)
def test_only_unique_ipv4_loopback_listener_of_registered_pid_is_accepted(owned, connections):
    owned.process.net_connections.return_value = connections
    with pytest.raises(NativeUIError, match="listener"):
        recovery.close_completed_browser(owned.pending)
    assert_no_connection_or_close(owned)


def test_unavailable_listener_inspection_refuses_without_a_bypass(owned):
    owned.process.net_connections.side_effect = InspectionError("Private connection details")
    with pytest.raises(NativeUIError, match="cannot be verified") as failed:
        recovery.close_completed_browser(owned.pending)
    assert "Private" not in str(failed.value)
    assert_no_connection_or_close(owned)


def test_malformed_listener_result_refuses_without_connecting(owned):
    owned.process.net_connections.return_value = [SimpleNamespace()]
    with pytest.raises(NativeUIError, match="listener cannot be verified"):
        recovery.close_completed_browser(owned.pending)
    assert_no_connection_or_close(owned)


def test_port_reuse_during_attach_never_sends_a_close_to_the_new_browser(owned):
    owned.process.create_time.side_effect = [1234.5, 9999]
    assert recovery.close_completed_browser(owned.pending) is False
    owned.connect.assert_called_once()
    owned.close.assert_not_called()
    owned.driver.stop.assert_called_once()


def test_listener_disappearing_during_attach_never_sends_browser_close(owned):
    owned.process.net_connections.side_effect = [[listener()], []]
    with pytest.raises(NativeUIError, match="listener"):
        recovery.close_completed_browser(owned.pending)
    owned.close.assert_not_called()
    owned.driver.stop.assert_called_once()


def test_endpoint_identity_changing_during_attach_never_sends_browser_close(owned):
    def connected(*_):
        owned.endpoint.write_text(
            f"{PORT}\n/devtools/browser/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa\n"
        )
        return owned.browser

    owned.connect.side_effect = connected
    with pytest.raises(NativeUIError, match="changed"):
        recovery.close_completed_browser(owned.pending)
    owned.close.assert_not_called()
    owned.driver.stop.assert_called_once()


def test_cdp_attachment_error_is_redacted_and_driver_stops(owned):
    owned.connect.side_effect = RuntimeError("Private browser URL token")
    with pytest.raises(NativeUIError, match="could not be closed safely") as failed:
        recovery.close_completed_browser(owned.pending)
    assert "Private" not in str(failed.value)
    owned.close.assert_not_called()
    owned.driver.stop.assert_called_once()


def test_shutdown_error_retains_safe_diagnostics_and_driver_stops(owned):
    failure = NativeUIError("Dedicated browser did not close")
    failure.shutdown_diagnostics = {"process_exit_confirmed": False}
    owned.close.side_effect = failure
    with pytest.raises(NativeUIError) as failed:
        recovery.close_completed_browser(owned.pending)
    assert failed.value is failure
    assert failed.value.shutdown_diagnostics == {"process_exit_confirmed": False}
    owned.driver.stop.assert_called_once()


def test_psutil_wait_timeout_is_converted_for_existing_close_helper(owned):
    owned.process.wait.side_effect = WaitExpired("Private process details")

    def close(_browser, waiter):
        with pytest.raises(subprocess.TimeoutExpired) as failed:
            waiter.wait(timeout=10)
        assert failed.value.timeout == 10
        assert "Private" not in str(failed.value)

    owned.close.side_effect = close
    assert recovery.close_completed_browser(owned.pending)
