"""Resume the persisted two-page trial in real Chromium without reloading its list."""

import io
import shutil
import sys
from collections import deque
from pathlib import Path

import pytest
from PIL import Image
from test_candidate_trial_browser import AdvancingClock, image_url, list_state, post_html, post_url
from test_watch_trial_browser import list_html, special_row

from image_monitor import candidate_runtime, watch_browser, watch_runtime
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.queue import QueueStore
from image_monitor.search_list import build_list_url
from image_monitor.watch_runtime import DEFAULT_SCOPE


def test_resume_verified_latest_forty_candidates_without_refetching_the_list(tmp_path, monkeypatch):
    pytest.importorskip("playwright.sync_api")
    if sys.platform != "win32":
        executable = shutil.which("chromium") or shutil.which("google-chrome")
        if not executable:
            pytest.skip("Installed Chromium unavailable")
        monkeypatch.setattr(watch_browser, "require_windows", lambda: None)
        monkeypatch.setattr(watch_runtime, "require_windows", lambda: None)
        monkeypatch.setattr(candidate_runtime, "require_windows", lambda: None)
        monkeypatch.setattr(watch_browser, "browser_executable", lambda _: Path(executable))

    first, second, third = (build_list_url("normal", "comic_new6", "ai", p) for p in (1, 2, 3))
    survey = special_row("설문", "javascript:void(0)")
    # Baseline, six overlapping new posts, then forty beyond the last checkpoint.
    lists = deque(
        [
            (first, list_html(range(100, 80, -1), second)),
            (first, list_html(range(106, 86, -1), second)),
            (second, list_html(range(86, 66, -1), third)),
            (first, list_html(range(240, 220, -1), second, excluded_html=survey)),
            (second, list_html(range(220, 200, -1), third, excluded_html=survey)),
        ]
    )
    eligible = {post_url(str(i)): str(i) for i in range(201, 241)}
    bodies = []
    images = []
    unexpected = []
    png = io.BytesIO()
    Image.new("RGB", (4, 3)).save(png, format="PNG")

    def route_fixture(route):
        request = route.request
        if lists and request.is_navigation_request() and request.url == lists[0][0]:
            _, html = lists.popleft()
        elif request.is_navigation_request() and request.url in eligible:
            post_id = eligible[request.url]
            bodies.append(post_id)
            html = post_html(post_id, "2026.11.16 13:01:00")
        elif bodies and request.resource_type == "image" and request.url == image_url(bodies[-1]):
            images.append(bodies[-1])
            route.fulfill(status=200, content_type="image/png", body=png.getvalue())
            return
        else:
            unexpected.append(request.url)
            route.abort()
            return
        route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)

    enter = watch_browser.HeadlessWatchBrowser.__enter__

    def enter_routed(browser):
        session = enter(browser)
        session._page.context.route("**/*", route_fixture)
        return session

    monkeypatch.setattr(watch_browser.HeadlessWatchBrowser, "__enter__", enter_routed)
    clock = AdvancingClock()
    earlier = watch_runtime.run_watch_trial(tmp_path, clock=clock)
    assert earlier["status"] == "watch_test_completed" and earlier["new_candidates"] == 6
    clock.wait(60)
    latest = watch_runtime.run_watch_trial(tmp_path, clock=clock)
    assert latest["reason"] == "anchor_not_reached" and latest["new_candidates"] == 40
    assert latest["cycles_completed"] == 1 and latest["candidate_count"] == 46
    assert latest["browser_closed"] is True and not lists and not bodies

    database = tmp_path / "watch.sqlite"
    with QueueStore(database, read_only=True) as queue:
        before = list_state(queue)
        scan_id = before["state"]["latest_scan"]["scan_id"]
        assert before["state"]["generation"] == 3
        assert [gap["reason"] for gap in before["gaps"]] == ["anchor_not_reached"]

    # Each separate invocation reopens the existing DB and may select one unattempted post.
    for count, pending_at_selection in ((1, 40), (2, 39)):
        clock.wait(60)
        detail = candidate_runtime.run_candidate_trial(
            tmp_path, clock=clock, max_candidates=1, recent_scan_only=True
        )
        assert detail["status"] == "candidate_test_completed", detail
        assert detail["candidates_selected"] == detail["candidates_completed"] == 1
        assert detail["browser_closed"] is True and detail["images_saved"] is False
        assert detail["time_status_counts"] == {"at_or_after_baseline": 1}
        assert detail["details"][0]["image_counts"]["included_unique"] == 1
        source = candidate_runtime.share_candidate_report(detail)["source_scan"]
        assert source["generation"] == 3 and source["gap_reason"] == "anchor_not_reached"
        assert source["coverage"] == "partial" and source["new_candidates"] == 40
        assert source["unattempted_candidates"] == pending_at_selection
        assert len(set(bodies)) == len(bodies) == count
        assert images == bodies and not unexpected
        with QueueStore(database, read_only=True) as queue:
            assert list_state(queue) == before
            attempts = CandidateDetailStore(queue).list_details(DEFAULT_SCOPE)
            assert {item["post_id"] for item in attempts} == set(bodies)
            assert all(item["first_scan_id"] == scan_id for item in attempts)
            assert all(item["status"] == "completed" for item in attempts)
            assert queue.summary()["posts"] == queue.summary()["jobs"] == 0
