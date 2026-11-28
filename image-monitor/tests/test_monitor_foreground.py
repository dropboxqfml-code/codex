"""Exercise the actual browser button separately from the simulated Windows focus guard."""

import shutil
import sys
from types import SimpleNamespace

import pytest

from image_monitor.monitor_foreground import ForegroundControl
from image_monitor.native_ui import NativeFocusError


def test_only_a_trusted_click_and_verified_foreground_release_the_hold(monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    if sys.platform == "win32":
        from image_monitor.native_probe import browser_executable

        executable = str(browser_executable("chrome"))
    else:
        executable = shutil.which("chromium") or shutil.which("google-chrome")
        if not executable:
            pytest.skip("Installed Chromium unavailable")
    events = []
    with playwright.sync_playwright() as driver:
        browser = driver.chromium.launch(executable_path=executable, headless=True)
        try:
            page = browser.new_page()
            page.set_content("<title>owned fixture</title><p>fixture</p>")

            def poll(_delay):
                events.append("poll")
                polls = events.count("poll")
                button = page.get_by_role("button", name="저장 재개")
                if polls == 1:
                    page.evaluate("globalThis.resumeClicked = () => true")
                    button.evaluate("b => b.click()")
                elif polls == 2:
                    assert "guard" not in events
                    button.click(timeout=3000)
                else:
                    assert polls == 3 and events.count("guard") == 1

            def guard():
                events.append("guard")
                if events.count("guard") == 1:
                    raise NativeFocusError("different foreground")

            monkeypatch.setattr(page, "wait_for_timeout", poll)
            control = ForegroundControl(
                None, lambda: events.append("hold"), lambda: events.append("resume")
            )
            control.wait(page, SimpleNamespace(assert_target_ready=guard), page.url, page.title())
            assert events == ["hold", "poll", "poll", "guard", "poll", "guard", "resume"]
            assert control.resumed and not page.get_by_role("button", name="저장 재개").count()
        finally:
            browser.close()
