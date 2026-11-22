"""Exercise bounded gap recovery through the real discovery worker and routed Chrome DOM."""

import shutil
import sys
from datetime import datetime, timedelta
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
def list_clock():
    return AdvancingClock()


@pytest.fixture
def routed_scan(tmp_path, monkeypatch, list_clock):
    pytest.importorskip("playwright.sync_api")
    if sys.platform != "win32":
        executable = shutil.which("chromium") or shutil.which("google-chrome")
        if not executable:
            pytest.skip("Installed Chromium unavailable")
        monkeypatch.setattr(watch_runtime, "require_windows", lambda: None)
        monkeypatch.setattr(watch_browser, "require_windows", lambda: None)
        monkeypatch.setattr(watch_browser, "browser_executable", lambda _: Path(executable))

    def run(documents, *, throttle_at=None, throttle_body=""):
        visits = []
        unexpected = []

        def serve(route):
            request = route.request
            index = len(visits)
            if (
                index < len(documents)
                and request.is_navigation_request()
                and request.url == page_url(documents[index][0])
            ):
                _, rows, linked_pages = documents[index]
                visits.append(request.url)
                if request.url == throttle_at:
                    route.fulfill(
                        status=429,
                        headers={"Retry-After": "600"},
                        content_type="text/html; charset=utf-8" if throttle_body else None,
                        body=throttle_body,
                    )
                    return
                route.fulfill(
                    status=200,
                    content_type="text/html; charset=utf-8",
                    body=list_html(
                        rows,
                        page_url(linked_pages[0]),
                        extra_page_urls=[page_url(n) for n in linked_pages[1:]],
                    ),
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
            clock=list_clock,
            run_cycle=partial(watch_runtime.run_watch_trial, backend_factory=RoutedChrome),
        )
        assert not unexpected, unexpected
        assert visits == [page_url(n) for n, _, _ in documents], outcome
        assert outcome["browser_closed"] is True
        list_clock.wait(60)
        return outcome

    return run


@pytest.fixture
def scan(routed_scan):
    def legacy_sequence(*pages):
        return routed_scan(
            [(n, rows, [linked_page]) for n, (rows, linked_page) in enumerate(pages, 1)]
        )

    return legacy_sequence


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


@pytest.fixture
def four_page_gap(scan):
    assert scan(([100, 99], 2))["status"] == "baseline"
    pages = [([130, 129, 128], 2), ([127, 126, 125], 3), ([124, 123, 122], 4), ([121, 120, 119], 5)]
    for depth in (2, 3, 4):
        partial = scan(*pages[:depth])
        assert partial["status"] == "partial" and partial["pages_checked"] == depth


def read_watch(root):
    with QueueStore(root / "watch.sqlite", read_only=True) as queue:
        watch = WatchStore(queue)
        candidates = {
            row["post_id"]: (row["first_scan_id"], row["first_seen_at"])
            for row in watch.list_candidates(MONITOR_SCOPE)
        }
        return watch.get_state(MONITOR_SCOPE), candidates, watch.list_gaps(MONITOR_SCOPE)


def test_shifted_list_continues_in_four_requests_and_waits_for_overlap(
    tmp_path, four_page_gap, routed_scan, scan
):
    original, old_posts, old_gaps = read_watch(tmp_path)
    # New post 131 pushes an item from the previous first page onto page two,
    # and the last row of the former fourth page onto page five.
    result = routed_scan(
        [
            (1, [131, 130, 129], [2]),
            (2, [128, 127, 126], [3, 4]),
            (4, [122, 121, 120], [5]),
            (5, [119, 111, 100], [6]),
        ]
    )
    assert (result["status"], result["new_candidates"]) == ("partial", 2), result
    assert result["historical_boundary_page"] == 4 and result["historical_status"] == "extended"
    assert result["visited_page_numbers"] == [1, 2, 4, 5]
    after, candidates, gaps = read_watch(tmp_path)
    assert after["checkpoint"] == original["checkpoint"]
    assert candidates.keys() - old_posts.keys() == {"111", "131"}
    assert old_posts.items() <= candidates.items()
    assert gaps[1:] == old_gaps

    # Identical post 100 moves onto page six after one more insertion. Seeing
    # it there still requires reading the next real page on a later turn.
    result = routed_scan(
        [
            (1, [132, 131, 130], [2]),
            (2, [129, 128, 127], [3, 5]),
            (5, [120, 119, 111], [6]),
            (6, [100, 99, 98], [7]),
        ]
    )
    assert (result["status"], result["new_candidates"]) == ("partial", 1), result
    assert result["visited_page_numbers"] == [1, 2, 5, 6]
    before_overlap, known, gaps = read_watch(tmp_path)
    assert before_overlap["checkpoint"] == original["checkpoint"]
    assert candidates.items() <= known.items()

    result = routed_scan(
        [
            (1, [132, 131, 130], [2]),
            (2, [129, 128, 127], [3, 6]),
            (6, [100, 99, 98], [7]),
            (7, [97, 96, 95], [8]),
        ]
    )
    assert (result["status"], result["new_candidates"]) == ("complete", 0), result
    assert result["visited_page_numbers"] == [1, 2, 6, 7]
    final, post_ids, gap_history = read_watch(tmp_path)
    assert final["baseline"] == original["baseline"]
    assert final["checkpoint"]["anchor_ids"] == ["132", "131", "130"]
    assert known == post_ids and gaps == gap_history
    assert scan(([132, 131, 130], 2), ([129, 128, 127], 3))["page_limit"] == 2


def test_changed_frontier_cannot_connect_unrelated_posts_to_existing_coverage(
    tmp_path, four_page_gap, routed_scan
):
    before, old_posts, _ = read_watch(tmp_path)
    result = routed_scan(
        [
            (1, [131, 130, 129], [2]),
            (2, [128, 127, 126], [3, 4]),
            (4, [115, 114, 113], [5]),
        ]
    )
    assert result["status"] == "partial", result
    assert result["historical_status"] == "boundary_changed"
    assert result["visited_page_numbers"] == [1, 2, 4]
    after, candidates, _ = read_watch(tmp_path)
    assert before["checkpoint"] == after["checkpoint"]
    assert old_posts.items() <= candidates.items()
    assert candidates.keys() - old_posts.keys() == {"131"}


def test_missing_boundary_link_uses_only_live_consecutive_links(
    tmp_path, four_page_gap, routed_scan
):
    before, old_posts, _ = read_watch(tmp_path)
    # The historical page 4 exists on page 1 but no such link is on page 2.
    result = routed_scan(
        [
            (1, [131, 130, 129], [2, 4]),
            (2, [128, 127, 126], [3]),
            (3, [125, 124, 123], [4]),
            (4, [122, 121, 120], [5]),
        ]
    )
    assert (result["status"], result["new_candidates"]) == ("partial", 1), result
    assert result["visited_page_numbers"] == [1, 2, 3, 4]
    assert result["historical_status"] == "recent_pages_only"
    after, candidates, _ = read_watch(tmp_path)
    assert after["checkpoint"] == before["checkpoint"]
    assert old_posts.items() <= candidates.items()


@pytest.mark.parametrize(
    "response_body",
    ["", "<!doctype html><title>Please try again later</title>"],
    ids=["empty", "html"],
)
def test_historical_service_deadline_survives_reopening_database(
    tmp_path, four_page_gap, routed_scan, list_clock, response_body
):
    baseline, old_posts, _ = read_watch(tmp_path)
    start = list_clock.now()
    result = routed_scan(
        [
            (1, [131, 130, 129], [2]),
            (2, [128, 127, 126], [3, 4]),
            (4, [122, 121, 120], [5]),
            (5, [], []),
        ],
        throttle_at=page_url(5),
        throttle_body=response_body,
    )
    assert result["status"] == "waiting", result
    assert datetime.fromisoformat(result["next_eligible_at"]) == start + timedelta(seconds=600)
    after, candidates, _ = read_watch(tmp_path)
    assert after["checkpoint"] == baseline["checkpoint"]
    assert old_posts.items() <= candidates.items()
    list_clock.wait(539)

    def no_scan(*args, **kwargs):
        pytest.fail("The service cooldown was lost on reopen")

    waiting = run_auto_discovery(tmp_path, interval_seconds=60, clock=list_clock, run_cycle=no_scan)
    assert waiting["status"] == "waiting"
    assert waiting["next_eligible_at"] == result["next_eligible_at"]
