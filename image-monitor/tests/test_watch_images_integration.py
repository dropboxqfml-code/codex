"""Follow an attachment-only stored detail to one verified body-image save."""

import hashlib
import os
import re
import shutil
import sys
import tempfile
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from test_candidate_trial_browser import list_state, post_url
from test_monitor_batch_runtime import finalize
from test_watch_runtime import BrowserFactory, FakeClock, baseline_outcome, link, observed, snapshot
from test_windows_candidate_save import (
    CandidatePageView,
    inspect_unverified_candidate,
    run_owned_candidate_native,
)
from test_windows_monitor_batch import _html
from test_windows_post_pipeline import fixture_assets, serve_fixtures

from image_monitor import (
    candidate_finish,
    candidate_runtime,
    monitor_batch_runtime,
    watch_browser,
    watch_image_search,
    watch_runtime,
)
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.native_state import session_id
from image_monitor.queue import QueueStore
from image_monitor.watch_runtime import DEFAULT_SCOPE


def seed_list(watch, clock):
    def pages(first, second):
        return observed(
            lambda t: snapshot(first, t, links=[link(2)]),
            lambda t: snapshot(second, t, page=2, links=[link(3)]),
        )

    previous = watch_runtime.run_watch_trial(
        watch,
        clock=clock,
        backend_factory=BrowserFactory(baseline_outcome, pages(range(106, 98, -1), [98])),
    )
    assert previous["new_candidates"] == 6
    clock.wait(60)
    latest = watch_runtime.run_watch_trial(
        watch,
        clock=clock,
        backend_factory=BrowserFactory(pages(range(240, 220, -1), range(220, 200, -1))),
    )
    assert latest["reason"] == "anchor_not_reached"
    assert latest["new_candidates"] == 40 and latest["candidate_count"] == 46


@pytest.mark.skipif(
    sys.platform == "win32"
    and not (
        os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("IMAGE_MONITOR_ALLOW_PATH_TESTS") == "1"
    ),
    reason="The owned native Chrome test requires the opted-in Windows CI session",
)
def test_search_skips_stored_attachment_only_detail_and_saves_the_next_exact_body(monkeypatch):
    from image_monitor.watch_images import run_watch_images

    playwright = pytest.importorskip("playwright.sync_api")
    clock = FakeClock(datetime.now(UTC) - timedelta(minutes=15))
    published = clock.now() + timedelta(seconds=30)
    header = {
        "title": "Synthetic image post",
        "nickname": "fixture",
        "published_at_raw": published.astimezone(ZoneInfo("Asia/Seoul")).strftime(
            "%Y.%m.%d %H:%M:%S"
        ),
        "ip_display": None,
    }
    png = fixture_assets("Watch images")["/render-first.png"]
    assets = {"/render-first.png": png}
    with (
        tempfile.TemporaryDirectory(prefix="i6-", dir=os.getenv("RUNNER_TEMP")) as folder,
        serve_fixtures(assets) as (origin, requested),
    ):
        root = Path(folder).resolve()
        watch, legacy, work = root / "w", root / "l", root / "b"
        if sys.platform != "win32":
            chrome = shutil.which("chromium") or shutil.which("google-chrome")
            if not chrome:
                pytest.skip("System Chromium unavailable")
            for module in (
                watch_browser,
                candidate_runtime,
                watch_runtime,
                monitor_batch_runtime,
                watch_image_search,
            ):
                monkeypatch.setattr(module, "require_windows", lambda: None)
            monkeypatch.setattr(watch_browser, "browser_executable", lambda _: Path(chrome))
            monkeypatch.setattr(monitor_batch_runtime, "session_id", lambda: 1)
            monkeypatch.setattr(monitor_batch_runtime, "NativeSaveLock", nullcontext)
            monkeypatch.setattr(
                monitor_batch_runtime, "shared_state_path", lambda: root / "pending.json"
            )
            monkeypatch.setattr(
                candidate_finish,
                "exclusive_digest",
                lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest(),
            )

        seed_list(watch, clock)
        document = _html("Owned watch candidate", header).replace(
            b"/render-first.png", (origin + "/render-first.png").encode()
        )
        assets["/post"] = ("text/html; charset=utf-8", document)
        empty = re.sub(rb"<img\b[^>]+>", b"Plain body", document, count=1)
        documents = {post_url("240"): empty, post_url("239"): document}
        bodies, image_requests, unexpected = [], [], []

        def route_fixture(route):
            request = route.request
            if request.is_navigation_request() and request.url in documents:
                bodies.append(request.url)
                route.fulfill(
                    status=200, content_type="text/html; charset=utf-8", body=documents[request.url]
                )
            elif request.resource_type == "image" and request.url == origin + "/render-first.png":
                image_requests.append(request.url)
                route.fulfill(status=200, content_type=png[0], body=png[1])
            else:
                unexpected.append(request.url)
                route.abort()

        enter = watch_browser.HeadlessWatchBrowser.__enter__

        def enter_routed(browser):
            result = enter(browser)
            browser._page.context.route("**/*", route_fixture)
            return result

        monkeypatch.setattr(watch_browser.HeadlessWatchBrowser, "__enter__", enter_routed)

        detail = candidate_runtime.run_candidate_trial(
            watch, clock=clock, max_candidates=1, recent_scan_only=True
        )
        assert detail["status"] == "candidate_test_completed", detail
        first = detail["details"][0]
        assert first["layout_status"] == "unverified" and first["attachment_count"] == 1
        assert first["image_counts"] == dict(
            body_occurrences=0, included_unique=0, excluded=0, pending=0
        )
        with QueueStore(watch / "watch.sqlite", read_only=True) as queue:
            before = list_state(queue)
            (original,) = CandidateDetailStore(queue).list_details(DEFAULT_SCOPE)
        calls = []

        def worker(task_root, browser, url, *, candidate_permit, navigation_observer):
            assert browser == "chrome" and url == candidate_permit.post_url == post_url("239")
            calls.append(url)
            if sys.platform == "win32":
                return run_owned_candidate_native(
                    monkeypatch,
                    root=task_root / f"session-{session_id()}",
                    post_url=url,
                    permit_factory=lambda _: (candidate_permit, candidate_permit.first_seen_at),
                    header=header,
                    fixtures=(origin, requested),
                    queue_name="queue.sqlite",
                    navigation_observer=navigation_observer,
                )
            with playwright.sync_playwright() as driver:
                owned = driver.chromium.launch(executable_path=chrome, headless=True)
                page = owned.new_page()
                navigation_observer.before()
                response = page.goto(origin + "/post", wait_until="load")
                navigation_observer.after(response, None)
                fresh = inspect_unverified_candidate(
                    CandidatePageView(page, post_url=url), clock.now()
                )
                finalize(task_root, candidate_permit, fresh, clock.now())
                owned.close()
            return {
                "status": "post_completed",
                "browser_closed": True,
                "shared_pending_retained": False,
                "job_counts": {"observed": 1, "completed": 1, "unresolved": 0},
            }

        result = run_watch_images(watch, legacy, work, clock=clock, save_runner=worker)
        assert result["status"] == "watch_images_saved", result
        assert (
            result["search"]["new_details_checked"] == result["search"]["stored_empty_posts"] == 1
        )
        assert result["search"]["outcome_counts"] == {"no_body_images_observed": 1, "save_ready": 1}
        assert calls == [post_url("239")]
        assert bodies == [post_url("240"), post_url("239")]
        assert image_requests == [origin + "/render-first.png"] and unexpected == []
        assert set(requested) <= {"/post", "/render-first.png", "/favicon.ico"}
        assert requested.count("/post") == 1 and "/render-first.png" in requested
        save = result["save"]
        assert save["tasks_completed"] == save["tasks_started"] == save["saved_file_count"] == 1
        assert len(save["saved_files"]) == 1
        with QueueStore(watch / "watch.sqlite", read_only=True) as queue:
            assert list_state(queue) == before and queue.summary()["jobs"] == 0
            details = CandidateDetailStore(queue).list_details(DEFAULT_SCOPE)
            assert details[0] == original and [d["post_id"] for d in details] == ["240", "239"]
