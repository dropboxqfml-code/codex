"""Prove the automatic reader can recover content focus inside its own Windows Chrome."""

import time
import uuid

import pytest
from test_windows_post_pipeline import (
    bind_and_foreground_ci_window,
    close_ci_browser,
)
from test_windows_post_pipeline import pytestmark as windows_ci_only

from image_monitor.browser_completion import BrowserCompletion
from image_monitor.post_worker import NativeRuntime

pytestmark = windows_ci_only


def focus_owned_omnibox(page, ui):
    """Move real keyboard focus to this fixture's toolbar, keeping its page visible."""
    window = ui.desktop.window(handle=ui.target_hwnd).wrapper_object()
    edits = [
        e for e in window.descendants(control_type="Edit") if e.is_visible() and e.is_enabled()
    ]
    assert len(edits) == 1
    ui.assert_control_ready(edits[0], window)
    edits[0].element_info.element.SetFocus()
    page.wait_for_function("document.visibilityState === 'visible' && !document.hasFocus()")
    ui.assert_target_ready()
    return window


def test_visible_page_behind_its_own_omnibox_accepts_one_focus_click(tmp_path, monkeypatch):
    from ctypes import wintypes

    import psutil

    runtime = NativeRuntime()
    profile = tmp_path / "profile"
    profile.mkdir()
    process = runtime.launch(profile, "chrome")
    owned = psutil.Process(process.pid)
    created = owned.create_time()
    ui = session = None
    try:
        page = runtime.attach(profile, process)
        session = runtime.browser.new_browser_cdp_session()
        title = f"Image Monitor content focus {uuid.uuid4().hex}"
        page.goto(f"data:text/html,<title>{title}</title><main>Owned fixture</main>")
        ui = bind_and_foreground_ci_window(process, page)
        window = focus_owned_omnibox(page, ui)

        original = page.evaluate_handle
        clicks = []

        def click_focus_hint(script):
            host = original(script)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                ui.assert_target_ready()
                controls = [
                    button
                    for button in window.descendants(control_type="Button")
                    if button.window_text() == "이 창에서 저장 계속" and button.is_visible()
                ]
                if len(controls) == 1:
                    button = controls[0]
                    assert button.is_enabled() and button.process_id() in ui.process_ids()
                    mid = button.rectangle().mid_point()
                    ui.user32.WindowFromPoint.argtypes = [wintypes.POINT]
                    ui.user32.WindowFromPoint.restype = wintypes.HWND
                    hwnd = ui.user32.WindowFromPoint(wintypes.POINT(mid.x, mid.y))
                    assert ui.belongs_to_target(hwnd)
                    ui.assert_target_ready()
                    button.click_input()
                    clicks.append(True)
                    return host
                page.wait_for_timeout(100)
            host.dispose()
            pytest.fail("The owned source focus control did not appear in the Chrome UI tree")

        monkeypatch.setattr(page, "evaluate_handle", click_focus_hint)
        # Exercise the user fallback when the automatic control cannot restore focus.
        monkeypatch.setattr(BrowserCompletion, "_click_focus_control", lambda self: None)
        original_html = page.content()
        with BrowserCompletion(
            runtime.browser, runtime.context, page, "chrome", ui=ui, allow_focus_prompt=True
        ) as reader:
            assert reader._read_model()["items_available"]
            assert page.evaluate("document.hasFocus()") is True
        assert clicks == [True]
        assert page.content() == original_html and page.title() == title
        assert runtime.context.pages == [page]
    finally:
        try:
            close_ci_browser(process, owned, created, session, ui)
        finally:
            runtime.disconnect()
