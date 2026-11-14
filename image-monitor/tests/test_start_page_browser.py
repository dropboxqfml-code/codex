"""Real local-page handshake checks; never run the native-save UI."""

import shutil
import sys
import threading
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from image_monitor.native_probe import browser_executable, create_fixture, wait_for_user_start
from image_monitor.native_ui import NativeUIError

playwright = pytest.importorskip("playwright.sync_api", reason="Optional browser test dependency")


@pytest.fixture(scope="module")
def browser():
    if sys.platform == "win32":
        try:
            executable = str(browser_executable("edge"))
        except NativeUIError:
            pytest.skip("Installed Edge is unavailable")
    else:
        executable = shutil.which("chromium") or shutil.which("google-chrome")
        if not executable:
            pytest.skip("Installed Chromium is unavailable")
    with playwright.sync_playwright() as driver:
        instance = driver.chromium.launch(
            executable_path=executable, headless=True, args=["--disable-background-networking"]
        )
        yield instance
        instance.close()


class ReadyWindow:
    def __init__(self):
        self.checks = 0

    def assert_target_ready(self):
        self.checks += 1


@contextmanager
def local_fixture(directory):
    # The managed Linux browser disallows file:// navigation. Serve only this
    # disposable fixture over loopback; do not change browser policies.
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(directory)))
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.05), daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/probe.html"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def test_local_start_button_controls_handoff_in_real_browser(browser, tmp_path):
    html, _expected_hash = create_fixture(tmp_path / "fixture")
    page = browser.new_page()
    try:
        with local_fixture(html.parent) as url:
            page.goto(url)
            assert page.evaluate("window.imageMonitorStartRequested === true") is False
            button = page.get_by_role("button", name="시험 시작", exact=True)
            button.click()
            assert button.is_disabled()
            assert page.evaluate("window.imageMonitorStartRequested === true") is True
            owned_window = ReadyWindow()
            wait_for_user_start(page, owned_window, timeout=1)
            assert owned_window.checks == 1
            assert "시험 진행 중" in page.locator("#probe-status").inner_text()
            assert page.locator("#probe-image").evaluate("img => img.naturalWidth") == 96
    finally:
        page.close()


def test_no_click_times_out_without_foreground_or_save_actions(browser, tmp_path):
    html, _expected_hash = create_fixture(tmp_path / "fixture")
    page = browser.new_page()
    try:
        with local_fixture(html.parent) as url:
            page.goto(url)
            owned_window = ReadyWindow()
            with pytest.raises(NativeUIError, match="Start was not confirmed"):
                wait_for_user_start(page, owned_window, timeout=0.2)
            assert owned_window.checks == 0
            assert page.get_by_role("button", name="시험 시작", exact=True).is_enabled()
    finally:
        page.close()
