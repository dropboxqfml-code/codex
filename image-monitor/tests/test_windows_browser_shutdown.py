"""Exercise production shutdown against one disposable headed Windows Chrome."""

import logging
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import pytest
from test_windows_post_pipeline import close_ci_browser

from image_monitor.completed_browser_close import close_completed_browser
from image_monitor.native_probe import (
    browser_executable,
    close_probe_browser,
    connect_owned_browser,
    wait_for_debug_port,
)
from image_monitor.native_state import browser_still_running
from image_monitor.native_ui import NativeSaveLock, NativeUIError, WindowsUI

pytestmark = pytest.mark.skipif(
    sys.platform != "win32"
    or os.environ.get("GITHUB_ACTIONS") != "true"
    or os.environ.get("IMAGE_MONITOR_ALLOW_PATH_TESTS") != "1",
    reason="Real headed shutdown requires an explicitly enabled Windows CI session",
)


def _completed_close_diagnostics(process, pending):
    diagnostics = {"registered_process_exited": process.poll() is not None}
    try:
        diagnostics["registered_profile_in_use"] = browser_still_running(pending)
    except Exception as error:
        diagnostics["profile_check_error_type"] = type(error).__name__
    return diagnostics


@pytest.mark.parametrize("reconnect_completed", [False, True])
def test_production_shutdown_exits_owned_process_and_releases_exact_profile(
    monkeypatch, reconnect_completed
):
    import psutil
    import pywinauto  # noqa: F401
    from playwright.sync_api import sync_playwright

    assert sys.__stderr__ is not None and not sys.__stderr__.closed
    for handler in logging.getLogger("pywinauto").handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(
            handler, logging.FileHandler
        ):
            monkeypatch.setattr(handler, "stream", sys.__stderr__)

    title = "Image Monitor owned shutdown " + uuid.uuid4().hex
    with (
        tempfile.TemporaryDirectory(prefix="ims-", dir=os.environ["RUNNER_TEMP"]) as directory,
        NativeSaveLock(),
    ):
        profile = Path(directory) / "browser-profile"
        profile.mkdir()
        process = subprocess.Popen(
            [
                str(browser_executable("chrome")),
                f"--user-data-dir={profile}",
                "--remote-debugging-port=0",
                "--remote-debugging-address=127.0.0.1",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-background-networking",
                "--disable-background-mode",
                "--force-renderer-accessibility",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        owned_process = psutil.Process(process.pid)
        created_at = owned_process.create_time()
        pending = {
            "browser_pid": process.pid,
            "browser_create_time": created_at,
            "browser_profile": str(profile),
        }
        driver = cleanup_session = ui = None
        try:
            port = wait_for_debug_port(profile, process, timeout=30)
            driver = sync_playwright().start()
            browser = connect_owned_browser(driver, port)
            cleanup_session = browser.new_browser_cdp_session()
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()
            assert page.url == "about:blank"
            page.evaluate("title => { document.title = title; }", title)
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                try:
                    ui = WindowsUI(process.pid, title)
                    break
                except NativeUIError:
                    time.sleep(0.1)
            assert ui is not None, "The exact owned headed window was not found"
            owned_ids = ui.process_ids()
            assert ui.user32.IsWindow(ui.target_hwnd)
            assert ui._window_pid(ui.target_hwnd) in owned_ids
            assert browser_still_running(pending)

            # This production helper must succeed before the fixture-only
            # cleanup below is allowed to mask a remaining disposable process.
            if reconnect_completed:
                # Simulate the prior worker disconnecting while its dedicated
                # completed browser remains alive. Recovery must independently
                # prove the persisted process, profile and local listener.
                driver.stop()
                driver = None
                assert process.poll() is None
                assert browser_still_running(pending)
                completed_close = close_completed_browser(pending)
                assert completed_close is True, _completed_close_diagnostics(process, pending)
            else:
                close_probe_browser(browser, process)

            assert process.poll() is not None, "Production did not confirm owned process exit"
            assert not (
                ui.user32.IsWindow(ui.target_hwnd) and ui._window_pid(ui.target_hwnd) in owned_ids
            ), "The exact owned headed window remained alive"
            deadline = time.monotonic() + 5
            while browser_still_running(pending) and time.monotonic() < deadline:
                time.sleep(0.1)
            assert not browser_still_running(pending), "The exact owned profile remained active"
        finally:
            # A failed assertion still needs bounded cleanup of this disposable
            # test fixture, guarded by exact PID and process birth time.
            close_ci_browser(process, owned_process, created_at, cleanup_session, ui)
            if driver is not None:
                driver.stop()
