"""Run the automatic worker against a loopback post on an owned Windows desktop."""

import hashlib
import json
import logging
import os
import sys
import tempfile
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from test_monitor_candidate_native import _freeze_monitor_candidate
from test_windows_candidate_save import POST_URL, CandidatePageView
from test_windows_completion_focus import focus_owned_omnibox
from test_windows_monitor_batch import _html
from test_windows_post_pipeline import (
    close_ci_browser,
    fixture_assets,
    foreground_ci_window,
    owned_ci_focus_distractor,
    serve_fixtures,
)
from test_windows_post_pipeline import pytestmark as windows_ci_only

from image_monitor import post_worker
from image_monitor.dcinside import inspect_post
from image_monitor.native_probe import browser_executable
from image_monitor.native_state import session_id
from image_monitor.queue import QueueStore

pytestmark = windows_ci_only


def test_automatic_save_requires_foreground_and_completes_one_native_file(monkeypatch):
    import psutil
    import pywinauto  # noqa: F401
    from playwright.sync_api import sync_playwright

    for handler in logging.getLogger("pywinauto").handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(
            handler, logging.FileHandler
        ):
            monkeypatch.setattr(handler, "stream", sys.__stderr__)

    published = datetime.now(ZoneInfo("Asia/Seoul")) - timedelta(minutes=2)
    png = fixture_assets("Automatic post")["/render-first.png"]
    assets = {
        "/post": (
            "text/html; charset=utf-8",
            _html(
                "Automatic post",
                {
                    "title": "Owned automatic post",
                    "nickname": "fixture",
                    "published_at_raw": published.strftime("%Y.%m.%d %H:%M:%S"),
                },
            ),
        ),
        "/render-first.png": png,
    }
    with (
        tempfile.TemporaryDirectory(prefix="a5-", dir=os.environ["RUNNER_TEMP"]) as directory,
        serve_fixtures(assets) as (origin, requested),
        ExitStack() as cleanup,
    ):
        root = Path(directory)
        watch = root / "watch"
        watch.mkdir()
        with sync_playwright() as driver:
            browser = driver.chromium.launch(executable_path=str(browser_executable("chrome")))
            try:
                page = browser.new_page()
                page.goto(origin + "/post", wait_until="load")
                snapshot = inspect_post(
                    CandidatePageView(page), expected_url=POST_URL, observed_at=datetime.now(UTC)
                )
                permit, _ = _freeze_monitor_candidate(watch, snapshot)
            finally:
                browser.close()

        class LocalPost(CandidatePageView):
            def goto(self, url, **kwargs):
                assert url == POST_URL
                return self._page.goto(origin + "/post", **kwargs)

            @property
            def url(self):
                assert self._page.url == origin + "/post"
                return POST_URL

        inspections = []
        native_calls = []
        navigation = []
        focus_losses = []
        observer = SimpleNamespace(
            before=lambda: navigation.append("start"),
            after=lambda response, error: navigation.append((response.status, error)),
        )
        real_save = post_worker.save_body_image

        def native_save(page, ui, **options):
            native_calls.append(page.url)
            ui.assert_target_ready()
            assert page.evaluate("document.hasFocus()") is True
            assert page.evaluate("window.fixtureInputEvents") == []
            assert page.locator("iframe").count() == 0
            return real_save(page, ui, **options)

        class DownloadsRoundTrip(post_worker.BrowserCompletion):
            def __enter__(self):
                self.source_page.evaluate("""() => {
                    window.fixtureInputEvents = [];
                    for (const kind of ['pointerdown', 'mousedown', 'click']) {
                        document.addEventListener(kind, e => {
                            if (e.isTrusted) window.fixtureInputEvents.push(e.type);
                        }, true);
                    }
                }""")
                focus_owned_omnibox(self.source_page, self.ui)
                focus_losses.append("initial")
                return super().__enter__()

            def _read_model(self):
                model = super()._read_model()
                if model["items_available"] and focus_losses == ["initial"]:
                    # User returned to the article's tab; Chrome's toolbar still holds focus.
                    self.ui.assert_target_ready()
                    self._page.bring_to_front()
                    self.source_page.wait_for_function("document.hidden", timeout=5_000)
                    self.source_page.bring_to_front()
                    self.source_page.wait_for_function("!document.hidden", timeout=5_000)
                    assert self.ui.user32.GetForegroundWindow() == self.ui.target_hwnd
                    focus_owned_omnibox(self.source_page, self.ui)
                    focus_losses.append("after_downloads")
                return model

        class LocalRuntime(post_worker.NativeRuntime):
            def launch(self, profile, browser_kind):
                process = super().launch(profile, browser_kind)
                owned = psutil.Process(process.pid)
                cleanup.callback(close_ci_browser, process, owned, owned.create_time(), None, None)
                return process

            def attach(self, profile, process):
                return LocalPost(super().attach(profile, process))

            def bind(self, process, title):
                ui = super().bind(process, title)
                foreground_ci_window(self.page, ui)
                if distract:
                    pause.enter_context(owned_ci_focus_distractor(ui))
                return ui

            def inspect(self, page, url, *, before_interaction=None):
                inspections.append(url)
                assert not distract
                assert before_interaction is not None
                assert page.locator("#image-monitor-save-panel").count() == 0
                return super().inspect(page, url, before_interaction=before_interaction)

        def unexpected_approval(*args, **kwargs):
            pytest.fail("The explicitly started worker requested an additional click")

        pending_path = root / "pending.json"
        monkeypatch.setattr(post_worker, "shared_state_path", lambda: pending_path)
        monkeypatch.setattr(post_worker, "NativeRuntime", LocalRuntime)
        monkeypatch.setattr(post_worker, "BrowserCompletion", DownloadsRoundTrip)
        monkeypatch.setattr(post_worker, "install_approval", unexpected_approval)
        monkeypatch.setattr(post_worker, "wait_for_approval", unexpected_approval)
        monkeypatch.setattr(post_worker, "save_body_image", native_save)

        for distract in (True, False):
            work = root / ("away" if distract else "ready")
            with ExitStack() as pause:
                result = post_worker.run_post_save(
                    work,
                    url=POST_URL,
                    candidate_permit=permit,
                    navigation_observer=observer,
                    automatic_start=True,
                )
            assert result["browser_closed"] and not result["shared_pending_retained"], result
            assert not pending_path.exists()
            base = work / f"session-{session_id()}"
            with QueueStore(base / "queue.sqlite", read_only=True) as queue:
                if distract:
                    assert result["error_type"] == "NativeFocusError", result
                    assert not inspections and not native_calls
                    assert result["saved_files"] == [] and queue.list_jobs() == []
                    assert not list((base / "images").iterdir())
                else:
                    assert result["status"] == "post_completed", result
                    assert focus_losses == ["initial", "after_downloads"]
                    assert len(inspections) >= 2 and native_calls == [POST_URL]
                    assert result["job_counts"] == {"observed": 1, "completed": 1, "unresolved": 0}
                    [saved] = result["saved_files"]
                    assert saved["sha256"] == hashlib.sha256(png[1]).hexdigest()
                    assert (saved["saved_filename"], saved["width"], saved["height"]) == (
                        "001.png",
                        4,
                        3,
                    )
                    [final] = (base / "images").rglob("001.png")
                    assert final.read_bytes() == png[1]
                    artifact = json.loads(final.with_name("metadata.json").read_bytes())["images"][
                        0
                    ]["artifact"]
                    assert artifact["completion"]["state"] == "COMPLETE"
                    assert artifact["completion"]["source_confirmed"]
                    assert artifact["completion"]["destination_confirmed"]
        assert navigation == ["start", (200, None)] * 2
        assert requested.count("/post") == 3
        assert set(requested) <= {"/post", "/render-first.png", "/favicon.ico"}
