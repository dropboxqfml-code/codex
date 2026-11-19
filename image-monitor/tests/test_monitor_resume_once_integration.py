"""Consume one persisted beta.2 monitor turn in a real, offline-routed Chrome session."""

import json
import shutil
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from test_candidate_runtime import BrowserFactory, http_failure, observed
from test_candidate_trial_browser import image_url, post_html, post_url
from test_monitor_controller import AutoClock
from test_monitor_details_integration import monitor_source
from test_monitor_gap_continuation import run_scan, seed_baseline
from test_monitor_integration import old_trial_records
from test_recent_candidate_save import recent as recent
from test_saved_catalog_batch import disk_bytes
from test_watch_images_check import complete
from test_watch_runtime import link, snapshot
from test_watch_runtime import observed as observed_list

from image_monitor import (
    PUBLIC_VERSION,
    candidate_runtime,
    monitor_resume_once,
    watch_browser,
    watch_runtime,
)
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.queue import QueueStore
from image_monitor.watch_store import MONITOR_SCOPE


def partial_pages(newest):
    return observed_list(
        lambda stamp: snapshot(range(newest, newest - 20, -1), stamp, links=[link(2)]),
        lambda stamp: snapshot(range(newest - 20, newest - 40, -1), stamp, page=2, links=[link(3)]),
    )


def closed_beta2_backlog(root, clock):
    seed_baseline(root, clock)
    for newest in (142, 145, 185, 187):
        scan = run_scan(root, clock, partial_pages(newest))
        assert scan["status"] == "watch_test_partial" and scan["reason"] == "anchor_not_reached"
        if newest == 187:
            return scan
        clock.advance(60)
        outcome = http_failure(404) if newest == 185 else observed(published_at=clock.now())
        detail = candidate_runtime.run_candidate_trial(
            root,
            scope=MONITOR_SCOPE,
            max_candidates=1,
            clock=clock,
            backend_factory=BrowserFactory(outcome),
        )
        assert detail["candidates_completed"] == 1
        clock.advance(60)


@pytest.mark.parametrize(
    ("http_status", "expected_status"),
    [(200, "monitor_resume_completed"), (404, "monitor_resume_unavailable")],
)
def test_one_click_reopens_beta2_receipt_checks_one_post_and_preserves_saved_files(
    recent, monkeypatch, http_status, expected_status
):
    pytest.importorskip("playwright.sync_api")
    if sys.platform != "win32":
        chrome = shutil.which("chromium") or shutil.which("google-chrome")
        if not chrome:
            pytest.skip("System Chromium unavailable")
        monkeypatch.setattr(watch_browser, "require_windows", lambda: None)
        monkeypatch.setattr(watch_browser, "browser_executable", lambda _: Path(chrome))

    complete(recent, "103")
    complete(recent, "104")
    saved_root = SimpleNamespace(root=recent.roots[2])
    saved_files = disk_bytes(saved_root)
    saved_images = [content for path, content in saved_files.items() if path.name == "001.png"]
    assert len(saved_images) == 2
    root = recent.watch
    database = root / "watch.sqlite"
    clock = AutoClock()
    clock.current = recent.clock.now() + timedelta(minutes=2)
    with monkeypatch.context() as previous:
        previous.setattr(watch_runtime, "PUBLIC_VERSION", "0.4.0-beta.2")
        scan = closed_beta2_backlog(root, clock)
    receipt = json.loads(Path(scan["report_path"]).read_text(encoding="utf-8"))
    assert receipt["program_version"] == "0.4.0-beta.2" and receipt["browser_closed"]
    scan_id = receipt["closed_monitor_scan"]["scan_id"]
    with QueueStore(database, read_only=True) as queue:
        monitor = monitor_source(queue)
        trial = old_trial_records(queue)
        store = CandidateDetailStore(queue)
        trial_details = store.list_details(watch_runtime.DEFAULT_SCOPE)
        earlier_details = store.list_details(MONITOR_SCOPE)
        pending = store.list_pending(MONITOR_SCOPE, limit=100)
        assert len(earlier_details) == 3 and len(pending) == 82 and len(monitor["candidates"]) == 85
        post = pending[0]["post_id"]
    deadline = clock.now() + timedelta(seconds=60)
    clock.advance(35)
    date = clock.now().astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y.%m.%d %H:%M:%S")
    requests = []
    browsers = []
    enter = watch_browser.HeadlessWatchBrowser.__enter__

    def route(route):
        req = route.request
        requests.append(req.url)
        if req.is_navigation_request() and req.url == post_url(post):
            route.fulfill(
                status=http_status,
                content_type="text/html; charset=utf-8",
                body=post_html(post, date) if http_status == 200 else "Deleted",
            )
        elif req.resource_type == "image" and req.url == image_url(post):
            route.fulfill(content_type="image/png", body=saved_images[0])
        else:
            route.abort()

    def routed(browser):
        opened = enter(browser)
        browsers.append(browser._owned_browser)
        browser._page.context.route("**/*", route)
        return opened

    monkeypatch.setattr(watch_browser.HeadlessWatchBrowser, "__enter__", routed)
    entries = []

    def detail(work_root, browser, **options):
        entries.append((clock.now(), options["expected_scan_id"]))
        return candidate_runtime.run_candidate_trial(work_root, browser, **options)

    for expected in (expected_status, "monitor_resume_no_slot"):
        result = monitor_resume_once.run_monitor_resume_once(root, clock=clock, run_details=detail)
        assert result["status"] == expected, result
        assert result["program_version"] == PUBLIC_VERSION and result["browser_closed"] is True
        assert result["worker_stopped"] is True and result["native_save_tasks_started"] == 0
        assert result["resumed_detail_slot"] is (expected != "monitor_resume_no_slot")
        assert result["resume_detail_pending"] is False
        assert monitor_resume_once.monitor_resume_once_exit_code(result) == 0
        assert result["details_checked"] == int(expected != "monitor_resume_no_slot")
        if expected == expected_status:
            assert result["detail"]["http_status"] == http_status
            if http_status == 200:
                assert result["detail"]["image_count"] == 1
        assert result["detail_pending_count"] == 81
        public = json.dumps(result)
        assert all(secret not in public for secret in (scan_id, "https://", "Invented"))
    assert entries == [(deadline, scan_id)]
    assert requests == (
        [post_url(post), image_url(post)] if http_status == 200 else [post_url(post)]
    )
    assert len(browsers) == 1 and not browsers[0].is_connected()
    with QueueStore(database, read_only=True) as queue:
        assert monitor_source(queue) == monitor and old_trial_records(queue) == trial
        store = CandidateDetailStore(queue)
        assert store.list_details(watch_runtime.DEFAULT_SCOPE) == trial_details
        details = store.list_details(MONITOR_SCOPE)
        assert details[:-1] == earlier_details
        assert details[-1]["post_id"] == post and details[-1]["status"] == "completed"
        assert queue.summary()["posts"] == queue.summary()["jobs"] == 0
    assert disk_bytes(saved_root) == saved_files
