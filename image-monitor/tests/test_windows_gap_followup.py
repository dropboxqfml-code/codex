"""Exercise bounded gap recovery through the real discovery worker and routed Chrome DOM."""

import shutil
import sys
from functools import partial
from pathlib import Path

import pytest
from test_watch_trial_browser import AdvancingClock, list_html

from image_monitor import watch_browser, watch_runtime
from image_monitor.monitor_auto_discovery import run_auto_discovery
from image_monitor.queue import QueueStore
from image_monitor.search_list import build_list_url
from image_monitor.watch_store import MONITOR_SCOPE, WatchStore


def page_url(number):
    return build_list_url("normal", "comic_new6", "ai", page=number)


@pytest.fixture
def scan(tmp_path, monkeypatch):
    pytest.importorskip("playwright.sync_api")
    if sys.platform != "win32":
        executable = shutil.which("chromium") or shutil.which("google-chrome")
        if not executable:
            pytest.skip("Installed Chromium unavailable")
        monkeypatch.setattr(watch_runtime, "require_windows", lambda: None)
        monkeypatch.setattr(watch_browser, "require_windows", lambda: None)
        monkeypatch.setattr(watch_browser, "browser_executable", lambda _: Path(executable))

    clock = AdvancingClock()

    def run(*pages):
        visits = []
        unexpected = []

        def serve(route):
            request = route.request
            index = len(visits)
            if (
                index < len(pages)
                and request.is_navigation_request()
                and request.url == page_url(index + 1)
            ):
                rows, linked_page = pages[index]
                visits.append(request.url)
                route.fulfill(
                    status=200,
                    content_type="text/html; charset=utf-8",
                    body=list_html(rows, page_url(linked_page)),
                )
            else:
                unexpected.append(request.url)
                route.abort()

        class RoutedChrome(watch_browser.HeadlessWatchBrowser):
            def __enter__(self):
                super().__enter__()
                self._page.context.route("**/*", serve)
                return self

        outcome = run_auto_discovery(
            tmp_path,
            interval_seconds=60,
            clock=clock,
            run_cycle=partial(watch_runtime.run_watch_trial, backend_factory=RoutedChrome),
        )
        assert not unexpected, unexpected
        assert visits == [page_url(i) for i in range(1, len(pages) + 1)], outcome
        assert outcome["browser_closed"] is True
        clock.wait(60)
        return outcome

    return run


def test_adaptive_gap_rechecks_fresh_links_and_covers_one_page_past_old_anchor(tmp_path, scan):
    baseline = scan(([100, 99], 2))
    assert baseline["status"] == "baseline"
    first = scan(([115, 114], 2), ([113, 112], 3))
    assert (first["status"], first["reason"], first["new_candidates"]) == (
        "partial",
        "anchor_not_reached",
        4,
    )
    third_page = scan(([116, 115], 2), ([114, 113], 3), ([112, 111, 100, 99], 4))
    assert (third_page["status"], third_page["reason"], third_page["new_candidates"]) == (
        "partial",
        "overlap_incomplete",
        2,
    )
    with QueueStore(tmp_path / "watch.sqlite", read_only=True) as queue:
        store = WatchStore(queue)
        state = store.get_state(MONITOR_SCOPE)
        assert state["checkpoint"]["anchor_ids"] == ["100", "99"]
        open_history = store.list_gaps(MONITOR_SCOPE)
        assert len(open_history) == 2
        first_discovery = {
            row["post_id"]: row["first_scan_id"] for row in store.list_candidates(MONITOR_SCOPE)
        }
    fourth_page = scan(
        ([117, 116], 2), ([115, 114], 3), ([113, 112, 111, 110, 100, 99], 4), ([98, 97], 5)
    )
    assert (fourth_page["status"], fourth_page["new_candidates"]) == ("complete", 2)
    normal_cycle = scan(([118, 117, 116], 2), ([115, 114, 113], 3))
    assert (normal_cycle["status"], normal_cycle["new_candidates"]) == ("complete", 1)
    with QueueStore(tmp_path / "watch.sqlite", read_only=True) as queue:
        store = WatchStore(queue)
        state = store.get_state(MONITOR_SCOPE)
        assert state["baseline"]["anchor_ids"] == ["100", "99"]
        assert state["checkpoint"]["anchor_ids"] == ["118", "117", "116"]
        assert store.list_gaps(MONITOR_SCOPE) == open_history
        candidates = {row["post_id"]: row for row in store.list_candidates(MONITOR_SCOPE)}
        assert candidates.keys() == {str(i) for i in range(110, 119)}
        assert all(
            candidates[key]["first_scan_id"] == value for key, value in first_discovery.items()
        )
        assert queue.summary()["jobs"] == queue.summary()["posts"] == 0


def test_previous_page_three_link_cannot_replace_a_missing_current_link(tmp_path, scan):
    assert scan(([100, 99], 2))["status"] == "baseline"
    assert scan(([115, 114], 2), ([113, 112], 3))["status"] == "partial"
    # The previous scan linked page 3. The fresh DOM offers only a nonadjacent page 4.
    result = scan(([116, 115], 2), ([114, 113], 4))
    assert result["status"] == "review"
    with QueueStore(tmp_path / "watch.sqlite", read_only=True) as queue:
        state = WatchStore(queue).get_state(MONITOR_SCOPE)
        assert state["checkpoint"]["anchor_ids"] == ["100", "99"]
        assert state["latest_scan"]["complete"] is False
        assert state["latest_scan"]["gap_reason"] == "pagination_missing"
