"""Continue a beta.3 backlog through real DOM inspection and durable image verification."""

import json
import re
import shutil
import sys
import uuid
from contextlib import nullcontext
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from test_candidate_runtime import BrowserFactory, http_failure
from test_candidate_save_selection import snapshot
from test_candidate_trial_browser import image_url, post_html, post_url
from test_monitor_batch_runtime import Runner, ledger, run
from test_monitor_details_integration import monitor_source
from test_monitor_gap_continuation import run_scan
from test_monitor_resume_once_integration import partial_pages
from test_recent_candidate_save import recent as recent
from test_watch_runtime import baseline_outcome

from image_monitor import (
    candidate_browser,
    candidate_runtime,
    monitor_operations,
    monitor_resume_once,
    watch_browser,
    watch_runtime,
)
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.native_state import PendingSave
from image_monitor.queue import QueueStore
from image_monitor.watch_store import MONITOR_SCOPE


def prepare_beta3(data):
    clock = data.clock
    clock.wait(60)
    assert run_scan(data.watch, clock, baseline_outcome)["status"] == "watch_test_completed"
    clock.wait(60)

    def body(candidate, now):
        observed = snapshot(candidate, observed_at=now, published=now, count=count)
        observed["nickname"] = "fx"
        data.observations[candidate["post_url"]] = observed
        return {
            "status": "observed",
            "http_status": 200,
            "navigation_attempts": 1,
            "url": candidate["post_url"],
            "snapshot": observed,
        }

    def deleted(candidate, now):
        return http_failure(404)(candidate, now) | {"url": candidate["post_url"]}

    for newest, count in ((340, 1), (380, 1), (384, None), (385, 0)):
        scan = run_scan(data.watch, clock, partial_pages(newest))
        assert scan["status"] == "watch_test_partial" and scan["reason"] == "anchor_not_reached"
        clock.wait(60)
        factory = BrowserFactory(deleted if count is None else body)
        inspect = partial(candidate_runtime.run_candidate_trial, backend_factory=factory)
        if count == 0:
            result = monitor_resume_once.run_monitor_resume_once(
                data.watch, clock=clock, run_details=inspect
            )
            assert result["status"] == "monitor_resume_completed" and result["resumed_detail_slot"]
            assert result["detail"]["image_count"] == 0 and result["detail_pending_count"] == 81
        else:
            result = inspect(data.watch, scope=MONITOR_SCOPE, clock=clock, max_candidates=1)
            assert result["candidates_completed"] == 1
        clock.wait(60)
        if newest == 380:
            assert run(data)["tasks_completed"] == 2
            clock.wait(60)


def saved_content(data):
    return {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in data.batch.glob("tasks/*/session-*/images/**/*")
        if path.name in {"001.png", "metadata.json"}
    }


def test_auto_collect_reopens_beta3_skips_image_free_posts_and_preserves_every_completed_file(
    recent, monkeypatch
):
    from image_monitor import monitor_collect

    pytest.importorskip("playwright.sync_api")
    if sys.platform != "win32":
        chrome = shutil.which("chromium") or shutil.which("google-chrome")
        if not chrome:
            pytest.skip("System Chromium unavailable")
        monkeypatch.setattr(watch_browser, "require_windows", lambda: None)
        monkeypatch.setattr(watch_browser, "browser_executable", lambda _: Path(chrome))

    root = recent.watch.parent
    data = SimpleNamespace(
        watch=recent.watch,
        legacy=root / "l",
        batch=root / "b",
        marker=root / "pending.json",
        clock=recent.clock,
        observations={},
    )
    monkeypatch.setattr(monitor_operations, "NativeSaveLock", nullcontext)
    monkeypatch.setattr(monitor_operations, "shared_state_path", lambda: data.marker)
    monkeypatch.setattr(monitor_operations, "session_id", lambda: 1)
    prepare_beta3(data)
    database = data.watch / "watch.sqlite"
    with QueueStore(database, read_only=True) as queue:
        original = monitor_source(queue)
        store = CandidateDetailStore(queue)
        original_details = store.list_details(MONITOR_SCOPE)
        posts = [row["post_id"] for row in store.list_pending(MONITOR_SCOPE, limit=100)]
        assert len(posts) == 81 and len(original_details) == 4
        prior_trial = store.list_details(watch_runtime.DEFAULT_SCOPE)
    old_files = saved_content(data)
    assert len(old_files) == 4
    image_bytes = next(content for p, (content, _) in old_files.items() if p.name == "001.png")
    date = data.clock.now().astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y.%m.%d %H:%M:%S")
    documents = {}
    for post in posts[:5]:
        html = post_html(post, date).replace("Invented author", "fx")
        documents[post_url(post)] = html if post == posts[1] else re.sub(r"<img[^>]*>", "", html)
    requests = []
    browsers = []

    def route(request):
        req = request.request
        requests.append(req.url)
        if req.is_navigation_request() and req.url in documents:
            request.fulfill(content_type="text/html; charset=utf-8", body=documents[req.url])
        elif req.resource_type == "image" and req.url == image_url(posts[1]):
            request.fulfill(content_type="image/png", body=image_bytes)
        else:
            request.abort()

    class RoutedCandidate(candidate_browser.HeadlessCandidateBrowser):
        def __enter__(self):
            entered = super().__enter__()
            self._page.context.route("**/*", route)
            browsers.append(self._owned_browser)
            return entered

    def inspect(root, browser, **options):
        return candidate_runtime.run_candidate_trial(
            root, browser, backend_factory=RoutedCandidate, **options
        )

    native = Runner(data)

    def save(root, browser, url, *, candidate_permit, navigation_observer, automatic_start):
        assert automatic_start is True and url == post_url(posts[1])
        state = PendingSave(data.marker)
        base = root / "session-1"
        directory = base / "runs" / uuid.uuid4().hex
        (directory / "browser-profile").mkdir(parents=True)
        (base / "images").mkdir()
        pending = state.begin(directory)
        state.update_browser(pending, 202, 100.0)
        data.observations[url] = candidate_permit.reference_snapshot
        result = native(
            root,
            browser,
            url,
            candidate_permit=candidate_permit,
            navigation_observer=navigation_observer,
        )
        state.finish(pending)
        return result

    for expected, inspected in (("monitor_collect_saved", 2), ("monitor_collect_limit", 3)):
        report = monitor_collect.run_monitor_collect(
            data.watch,
            data.legacy,
            data.batch,
            clock=data.clock,
            detail_runner=inspect,
            save_runner=save,
        )
        assert report["status"] == expected, json.dumps(report, indent=2)
        assert report["new_details_checked"] == inspected and report["browser_closed"] is True
        assert (
            report["files_verified"] == report["native_save_tasks_started"] == int(inspected == 2)
        )
        assert monitor_collect.monitor_collect_exit_code(report) == 0
        assert str(data.batch) not in json.dumps(report)
        if inspected == 2:
            assert report["saved_files"][0]["detected_format"] == "PNG"
            all_files = saved_content(data)
            assert len(all_files) == 6 and all(all_files[p] == v for p, v in old_files.items())
            [image] = [p for p in all_files.keys() - old_files.keys() if p.name == "001.png"]
            assert image.parent.name == posts[1] and image.read_bytes() == image_bytes
        else:
            assert saved_content(data) == all_files
    assert requests == [
        post_url(posts[0]),
        post_url(posts[1]),
        image_url(posts[1]),
        *map(post_url, posts[2:5]),
    ]
    assert (
        len(native.calls) == 1
        and len(browsers) == 5
        and all(not b.is_connected() for b in browsers)
    )
    assert not data.marker.exists()
    with ledger(data) as store:
        tasks = store.list_tasks()
        assert len(tasks) == 3 and all(task["status"] == "completed" for task in tasks)
    with QueueStore(database, read_only=True) as queue:
        assert monitor_source(queue) == original
        store = CandidateDetailStore(queue)
        assert store.list_details(watch_runtime.DEFAULT_SCOPE) == prior_trial
        assert store.list_details(MONITOR_SCOPE)[:4] == original_details
        assert [p["post_id"] for p in store.list_pending(MONITOR_SCOPE, limit=100)] == posts[5:]
        assert queue.summary()["posts"] == queue.summary()["jobs"] == 0
