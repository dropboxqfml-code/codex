"""Require owned process exit even when Chromium has already closed its window."""

import subprocess
from unittest.mock import MagicMock, call

import pytest

from image_monitor.native_probe import close_probe_browser
from image_monitor.native_ui import NativeUIError


def test_normal_browser_exit_needs_no_transport_fallback():
    browser, process = MagicMock(), MagicMock()

    close_probe_browser(browser, process)

    browser.new_browser_cdp_session.return_value.send.assert_called_once_with(
        "Browser.close", timeout=5_000
    )
    process.wait.assert_called_once_with(timeout=10)
    browser.close.assert_not_called()
    process.terminate.assert_not_called()
    process.kill.assert_not_called()


def test_delayed_exit_releases_our_cdp_client_before_waiting_again():
    browser, process = MagicMock(), MagicMock()
    events = []

    def wait(*, timeout):
        events.append(("wait", timeout))
        if timeout == 10:
            raise subprocess.TimeoutExpired("owned-browser", timeout)
        assert events[-2] == ("disconnect", None)
        return 0

    process.wait.side_effect = wait
    browser.close.side_effect = lambda: events.append(("disconnect", None))

    close_probe_browser(browser, process)

    assert events == [("wait", 10), ("disconnect", None), ("wait", 20)]
    browser.close.assert_called_once_with()
    process.terminate.assert_not_called()
    process.kill.assert_not_called()


@pytest.mark.parametrize("stage", ["session", "command"])
def test_cdp_shutdown_disconnect_is_not_failure_when_process_exits(stage):
    browser, process = MagicMock(), MagicMock()
    if stage == "session":
        browser.new_browser_cdp_session.side_effect = RuntimeError("Already disconnected")
    else:
        browser.new_browser_cdp_session.return_value.send.side_effect = RuntimeError(
            "Browser closed before replying"
        )

    close_probe_browser(browser, process)

    process.wait.assert_called_once_with(timeout=10)
    browser.close.assert_not_called()


def test_transport_cleanup_exception_still_requires_and_accepts_process_exit():
    browser, process = MagicMock(), MagicMock()
    process.wait.side_effect = [subprocess.TimeoutExpired("owned-browser", 10), 0]
    browser.close.side_effect = RuntimeError("Transport is already gone")

    close_probe_browser(browser, process)

    assert process.wait.call_args_list == [call(timeout=10), call(timeout=20)]
    browser.close.assert_called_once_with()
    process.terminate.assert_not_called()
    process.kill.assert_not_called()


def test_window_or_transport_closure_never_substitutes_for_process_exit():
    browser, process = MagicMock(), MagicMock()
    process.wait.side_effect = subprocess.TimeoutExpired("owned-browser", 10)

    with pytest.raises(NativeUIError, match="did not close") as failed:
        close_probe_browser(browser, process)

    assert failed.value.shutdown_diagnostics == {
        "cdp_close_requested": True,
        "cdp_error_type": None,
        "transport_disconnect_attempted": True,
        "transport_error_type": None,
        "process_exit_confirmed": False,
        "process_wait_seconds": 30,
    }
    assert process.wait.call_args_list == [call(timeout=10), call(timeout=20)]
    browser.close.assert_called_once_with()
    process.terminate.assert_not_called()
    process.kill.assert_not_called()


def test_failed_shutdown_diagnostics_keep_only_exception_classes():
    browser, process = MagicMock(), MagicMock()
    browser.new_browser_cdp_session.side_effect = ValueError("Private owned profile path")
    browser.close.side_effect = RuntimeError("Private browser URL token")
    process.wait.side_effect = subprocess.TimeoutExpired("private-browser-command", 10)

    with pytest.raises(NativeUIError, match="did not close") as failed:
        close_probe_browser(browser, process)

    diagnostics = failed.value.shutdown_diagnostics
    assert diagnostics["cdp_close_requested"] is False
    assert diagnostics["cdp_error_type"] == "ValueError"
    assert diagnostics["transport_error_type"] == "RuntimeError"
    assert "private" not in str(diagnostics).lower()
    process.terminate.assert_not_called()
    process.kill.assert_not_called()


def test_cancel_during_transport_cleanup_is_not_swallowed():
    browser, process = MagicMock(), MagicMock()
    process.wait.side_effect = subprocess.TimeoutExpired("owned-browser", 10)
    browser.close.side_effect = KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        close_probe_browser(browser, process)

    process.wait.assert_called_once_with(timeout=10)
    process.terminate.assert_not_called()
    process.kill.assert_not_called()
