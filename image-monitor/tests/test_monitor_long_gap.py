"""Run the actual discovery scheduler across multi-day gaps on an invented search feed."""

import json
import shutil
import subprocess
import sys
from datetime import datetime
from functools import partial
from html import escape
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_watch_runtime import FakeClock, link, snapshot
from test_watch_trial_browser import list_html

from image_monitor import watch_browser, watch_runtime
from image_monitor.monitor_auto_discovery import run_auto_discovery
from image_monitor.monitor_list_history import previous_list_checks
from image_monitor.queue import QueueStore
from image_monitor.search_list import build_list_url, validate_list_url
from image_monitor.watch_store import MONITOR_SCOPE, WatchStore

PAGE_SIZE = 10
OLD_HEAD = 1000
WINDOW_CURSORS = (None, "-39173", "-12008", "-99219", "-34029", "-72106", "-92109", "-82004")


class SearchFeed:
    """The displayed page numbers shift when newer posts arrive."""

    def __init__(self, ids, window_size=None):
        self.ids = ids
        self.window_size = window_size
        self.offered = {link(1)["canonical_url"]}
        self.visits = []
        self.last_page = None
        self.rate_limit_url = None

    def visit(self, url):
        assert url in self.offered, "Navigated to a URL never supplied by the search list"
        target = validate_list_url(url)
        assert target["canonical_url"] == url
        window = WINDOW_CURSORS.index(target["search_pos"])
        page = target["page"]
        assert self.window_size or window == 0
        assert not self.window_size or page <= self.window_size
        self.visits.append(window * (self.window_size or 0) + page)
        return target, window

    def document(self, url):
        target, window = self.visit(url)
        page = target["page"]
        start = (self.visits[-1] - 1) * PAGE_SIZE
        rows = self.ids[start : start + PAGE_SIZE]
        start_group = ((page - 1) // 10) * 10 + 1
        numbers = set(range(start_group, start_group + 10)) | {page + 1}
        if self.window_size is not None:
            numbers = {n for n in numbers if n <= self.window_size}
        if self.last_page is not None:
            numbers = {n for n in numbers if n <= self.last_page}
        links = [list_link(n, target["search_pos"]) for n in sorted(numbers) if n != page]
        if page == self.window_size and window + 1 < len(WINDOW_CURSORS):
            links.append(list_link(1, WINDOW_CURSORS[window + 1]) | {"label_kind": "next_search"})
        self.offered.update(item["canonical_url"] for item in links)
        return target, rows, links

    def run(self, root, clock):
        self.visits = []
        feed = self

        class Browser(watch_browser.HeadlessWatchBrowser):
            def __enter__(self):
                self._page = object()
                self.browser_closed = False
                return self

            def __exit__(self, *_):
                self._page = None
                self.browser_closed = True

            def _navigate(self, url):
                if url == feed.rate_limit_url:
                    feed.visit(url)
                    feed.rate_limit_url = None
                    return SimpleNamespace(status=429, header_value=lambda _: "180")
                return SimpleNamespace(status=200, header_value=lambda _: None)

            def _inspect_document(self, url, scan_time, *, can_settle):
                target, rows, links = feed.document(url)
                return snapshot(
                    rows,
                    scan_time,
                    page=target["page"],
                    url=url,
                    search_pos=target["search_pos"],
                    links=links,
                    counts={"list_containers": 1},
                )

        scan = partial(watch_runtime.run_watch_trial, backend_factory=Browser)
        result = run_auto_discovery(root, interval_seconds=60, clock=clock, run_cycle=scan)
        clock.wait(60)
        return result


def list_link(number, cursor):
    return {
        "canonical_url": build_list_url("normal", "comic_new6", "ai", number, cursor),
        "page": number,
        "search_pos": cursor,
    }


def read_state(root):
    with QueueStore(root / "watch.sqlite", read_only=True) as queue:
        state = WatchStore(queue).get_state(MONITOR_SCOPE)
        discovered = dict(
            queue.connection.execute("SELECT post_id, first_scan_id FROM watch_candidates")
        )
    return state["checkpoint"], discovered


@pytest.fixture
def starting_watch(tmp_path, monkeypatch):
    monkeypatch.setattr(watch_runtime, "require_windows", lambda: None)
    feed = SearchFeed(list(range(OLD_HEAD, OLD_HEAD - 220, -1)))
    clock = FakeClock()
    assert feed.run(tmp_path, clock)["status"] == "baseline"
    old_checkpoint, _ = read_state(tmp_path)
    return feed, clock, old_checkpoint


def child_turn():
    """An independent Python process receives only the fake site and clock, plus the watch path."""
    payload = json.load(sys.stdin)
    watch_runtime.require_windows = lambda: None
    feed = SearchFeed(payload["site_ids"], payload["window_size"])
    feed.offered.update(payload["offered"])
    clock = FakeClock(datetime.fromisoformat(payload["now"]))
    result = feed.run(Path(payload["root"]), clock)
    print(json.dumps([result, feed.visits, sorted(feed.offered)]))


def run_after_process_restart(root, feed, clock):
    payload = {
        "root": str(root),
        "site_ids": feed.ids,
        "window_size": feed.window_size,
        "offered": sorted(feed.offered),
        "now": clock.now().isoformat(),
    }
    proc = subprocess.run(
        [sys.executable, "-c", "from test_monitor_long_gap import child_turn; child_turn()"],
        input=json.dumps(payload),
        cwd=Path(__file__).parent,
        text=True,
        capture_output=True,
        timeout=45,
        check=True,
    )
    result, feed.visits, offered = json.loads(proc.stdout)
    feed.offered.update(offered)
    clock.wait(60)
    return result


@pytest.mark.parametrize(("pages", "days"), [(30, 1), (60, 2)])
def test_recovers_every_still_visible_new_post_after_days_offline(
    tmp_path, starting_watch, pages, days
):
    feed, clock, checkpoint = starting_watch
    if pages == 60:
        feed.window_size = 10
    clock.wait(days * 24 * 3600)
    # Some checkpoint posts disappear, others remain to prove the old boundary.
    for missing in (1000, 997):
        feed.ids.remove(missing)
    new_count = pages * PAGE_SIZE
    feed.ids[:0] = range(OLD_HEAD + new_count, OLD_HEAD, -1)
    pending = {str(i) for i in feed.ids if i > OLD_HEAD}
    original_discoveries = {}
    arrivals = set()
    maximum_page = 0
    restarted = False
    for turn in range(pages * 3):
        if turn in (4, 11, 17):
            new = feed.ids[0] + 1
            feed.ids.insert(0, new)
            pending.add(str(new))
            arrivals.add(str(new))
        if turn == 8:
            # This unobserved new post is deleted at the oldest end during recovery.
            vanished = OLD_HEAD + 2
            assert str(vanished) not in original_discoveries
            feed.ids.remove(vanished)
            pending.remove(str(vanished))
        if maximum_page >= 11 and not restarted:
            result = run_after_process_restart(tmp_path, feed, clock)
            restarted = True
            last = previous_list_checks(tmp_path)[-1]
            displayed = [
                (p - 1) % feed.window_size + 1 if feed.window_size else p for p in feed.visits
            ]
            assert last["visited_page_numbers"] == result["visited_page_numbers"] == displayed
            assert last["recovery_route"] == result["recovery_route"]
            assert last["recovery_status"] == result["recovery_status"]
        else:
            result = feed.run(tmp_path, clock)
        assert result["status"] in {"partial", "complete"}, result
        assert feed.visits[0] == 1 and len(feed.visits) <= 4
        maximum_page = max(maximum_page, *feed.visits)
        current_checkpoint, found = read_state(tmp_path)
        assert original_discoveries.items() <= found.items()
        assert arrivals <= found.keys(), "A current page-one arrival was starved by backfill"
        original_discoveries = found
        if result["status"] == "complete":
            assert current_checkpoint != checkpoint
            assert pending == found.keys()
            break
        assert current_checkpoint == checkpoint
    else:
        pytest.fail(
            f"Unresolved after {turn + 1} scans; reached page {maximum_page}, found {len(found)}"
        )
    assert restarted and maximum_page >= pages + 1


def test_no_asserted_coverage_if_every_checkpoint_post_disappears(tmp_path, starting_watch):
    feed, clock, checkpoint = starting_watch
    clock.wait(86400)
    del feed.ids[:PAGE_SIZE]
    feed.ids[:0] = range(OLD_HEAD + 35, OLD_HEAD, -1)
    feed.last_page = 8
    observed = set()
    for _ in range(12):
        result = feed.run(tmp_path, clock)
        assert result["status"] == "partial", result
        observed.update(feed.visits)
        assert read_state(tmp_path)[0] == checkpoint
    _, found = read_state(tmp_path)
    assert feed.last_page in observed
    assert {str(i) for i in range(OLD_HEAD + 1, OLD_HEAD + 36)} <= found.keys()


def test_another_long_outage_moves_the_in_progress_frontier_by_seven_pages(
    tmp_path, starting_watch
):
    feed, clock, checkpoint = starting_watch
    clock.wait(86400)
    feed.ids[:0] = range(OLD_HEAD + 190, OLD_HEAD, -1)
    furthest = 0
    second_outage = False
    rate_limited = False
    for _ in range(75):
        result = feed.run(tmp_path, clock)
        assert feed.visits and feed.visits[0] == 1 and len(feed.visits) <= 4
        if result["status"] == "waiting":
            assert result["reason"] == "service_wait" and feed.visits[-1] == 13
            assert not rate_limited and not second_outage
            rate_limited = True
            assert read_state(tmp_path)[0] == checkpoint
            # Restarting the worker before Retry-After expires must do zero requests.
            for _ in range(2):
                assert feed.run(tmp_path, clock)["status"] == "waiting"
                assert feed.visits == []
            continue
        assert result["status"] in {"partial", "complete"}, result
        furthest = max(furthest, *feed.visits)
        current_checkpoint, found = read_state(tmp_path)
        if result["status"] == "complete":
            assert second_outage and rate_limited and furthest >= 27
            assert current_checkpoint != checkpoint
            assert found.keys() == {str(i) for i in range(OLD_HEAD + 1, OLD_HEAD + 261)}
            break
        assert current_checkpoint == checkpoint
        if furthest == 12 and not rate_limited:
            feed.rate_limit_url = list_link(13, None)["canonical_url"]
        if furthest >= 14 and not second_outage:
            assert rate_limited
            clock.wait(86400)
            feed.ids[:0] = range(OLD_HEAD + 260, OLD_HEAD + 190, -1)
            second_outage = True
    else:
        pytest.fail(f"Second outage left recovery incomplete; visited as far as page {furthest}")


def test_a_missing_forward_link_cannot_be_guessed_or_complete_a_deep_gap(tmp_path, starting_watch):
    feed, clock, checkpoint = starting_watch
    clock.wait(86400)
    feed.ids[:0] = range(OLD_HEAD + 300, OLD_HEAD, -1)
    feed.last_page = 12
    maximum_page = 0
    for _ in range(18):
        result = feed.run(tmp_path, clock)
        assert result["status"] == "partial", result
        assert feed.visits
        maximum_page = max(maximum_page, *feed.visits)
    assert maximum_page == 12 and read_state(tmp_path)[0] == checkpoint


@pytest.mark.parametrize(("cursor_label", "window_size"), [("다음 검색", 4), ("이전 검색", 5)])
def test_real_chromium_uses_only_the_visible_forward_search_control(
    tmp_path, monkeypatch, cursor_label, window_size
):
    pytest.importorskip("playwright.sync_api")
    if sys.platform != "win32":
        executable = shutil.which("chromium") or shutil.which("google-chrome")
        if not executable:
            pytest.skip("Installed Chromium unavailable")
        monkeypatch.setattr(watch_browser, "browser_executable", lambda _: Path(executable))
        monkeypatch.setattr(watch_browser, "require_windows", lambda: None)
        monkeypatch.setattr(watch_runtime, "require_windows", lambda: None)

    feed = SearchFeed(list(range(OLD_HEAD, OLD_HEAD - 100, -1)), window_size=window_size)
    clock = FakeClock()

    def serve(route):
        target, rows, links = feed.document(route.request.url)
        controls = []
        for item in links:
            label = cursor_label if item.get("label_kind") == "next_search" else str(item["page"])
            controls.append(f'<a href="{escape(item["canonical_url"], quote=True)}">{label}</a>')
        body = list_html(rows, target["canonical_url"]).split('<div class="bottom_paging_box">')[0]
        body += '<div class="bottom_paging_box">' + "".join(controls) + "</div></body></html>"
        route.fulfill(status=200, content_type="text/html; charset=utf-8", body=body)

    class Routed(watch_browser.HeadlessWatchBrowser):
        def __enter__(self):
            browser = super().__enter__()
            self._page.context.route("**/*", serve)
            return browser

    def scan():
        feed.visits = []
        outcome = run_auto_discovery(
            tmp_path,
            interval_seconds=60,
            clock=clock,
            run_cycle=partial(watch_runtime.run_watch_trial, backend_factory=Routed),
        )
        assert feed.visits[0] == 1 and len(feed.visits) <= 4
        clock.wait(60)
        return outcome

    assert scan()["status"] == "baseline"
    old_checkpoint, _ = read_state(tmp_path)
    clock.wait(86400)
    arrivals = window_size * PAGE_SIZE + 5
    feed.ids[:0] = range(OLD_HEAD + arrivals, OLD_HEAD, -1)
    observed = []
    for _ in range(12):
        result = scan()
        assert result["status"] in {"partial", "complete"}, result
        observed.extend(feed.visits)
        if result["status"] == "complete":
            break
        if cursor_label == "이전 검색" and result.get("recovery_status") == "successor_unconfirmed":
            break
    if cursor_label == "이전 검색":
        assert (
            result["status"] == "partial" and result["recovery_status"] == "successor_unconfirmed"
        )
        assert max(observed) == window_size and read_state(tmp_path)[0] == old_checkpoint
        return
    assert result["status"] == "complete", observed
    assert set(range(1, 7)) <= set(observed)
    _, found = read_state(tmp_path)
    assert found.keys() == {str(i) for i in range(OLD_HEAD + 1, OLD_HEAD + arrivals + 1)}


@pytest.mark.parametrize("window_size", [1, 2, 3])
def test_short_initial_window_recovers_via_its_visible_next_search(
    tmp_path, starting_watch, window_size
):
    feed, clock, checkpoint = starting_watch
    feed.window_size = window_size
    feed.ids[:0] = range(OLD_HEAD + 50, OLD_HEAD, -1)
    clock.wait(86400)
    visited = set()
    saw_initial_crossing = False
    for _ in range(18):
        result = feed.run(tmp_path, clock)
        assert result["status"] in {"partial", "complete"}, result
        assert feed.visits[0] == 1 and len(feed.visits) <= 4
        if result.get("search_window_start_visits") and "recovery_route" not in result:
            historical = previous_list_checks(tmp_path)[-1]
            for field in ("visited_page_numbers", "search_window_start_visits", "page_limit"):
                assert historical[field] == result[field]
            saw_initial_crossing = True
        visited.update(feed.visits)
        current, candidates = read_state(tmp_path)
        if result["status"] == "complete":
            assert current != checkpoint
            assert candidates.keys() == {str(i) for i in range(OLD_HEAD + 1, OLD_HEAD + 51)}
            break
        assert current == checkpoint
    else:
        pytest.fail(f"Short starting window did not recover; visited {sorted(visited)}")
    assert saw_initial_crossing and set(range(1, 8)) <= visited


@pytest.mark.parametrize("window_size", [1, 2, 3])
@pytest.mark.parametrize("direction", ["unlabelled", "ambiguous"])
def test_short_initial_window_requires_a_unique_visible_forward_control(
    tmp_path, starting_watch, window_size, direction
):
    feed, clock, checkpoint = starting_watch
    feed.window_size = window_size
    document = feed.document

    def change_control(url):
        target, rows, links = document(url)
        for item in links.copy():
            if item.get("label_kind") != "next_search":
                continue
            if direction == "unlabelled":
                del item["label_kind"]
            else:
                other = list_link(1, WINDOW_CURSORS[2]) | {"label_kind": "next_search"}
                links.append(other)
                feed.offered.add(other["canonical_url"])
        return target, rows, links

    feed.document = change_control
    feed.ids[:0] = range(OLD_HEAD + 50, OLD_HEAD, -1)
    clock.wait(86400)
    visited = set()
    for _ in range(4):
        result = feed.run(tmp_path, clock)
        assert result["status"] in {"partial", "review"}, result
        assert read_state(tmp_path)[0] == checkpoint
        visited.update(feed.visits)
    assert visited == set(range(1, window_size + 1))
    assert list_link(1, WINDOW_CURSORS[1])["canonical_url"] in feed.offered


@pytest.mark.parametrize("movement", ["displaced", "deleted_with_arrivals", "deleted"])
def test_displaced_eleventh_page_rebuilds_connected_route_after_restart(
    tmp_path, starting_watch, movement
):
    feed, clock, checkpoint = starting_watch
    feed.window_size = 11
    feed.ids[:0] = range(OLD_HEAD + 160, OLD_HEAD, -1)
    for _ in range(15):
        turn = feed.run(tmp_path, clock)
        assert turn["status"] == "partial", turn
        if turn.get("recovery_depth") == 11:
            break
    assert turn["recovery_depth"] == 11
    _, known = read_state(tmp_path)
    if movement.startswith("deleted"):
        # None of the original page survives. The global checkpoint still does.
        del feed.ids[10 * PAGE_SIZE : 11 * PAGE_SIZE]
        if movement == "deleted_with_arrivals":
            feed.ids[:0] = range(feed.ids[0] + PAGE_SIZE, feed.ids[0], -1)
    else:
        # Two and a half pages arrive. The old head can be rejoined on the
        # recent route, but its formerly valid eleventh page now points elsewhere.
        feed.ids[:0] = range(feed.ids[0] + 25, feed.ids[0], -1)
        assert feed.run(tmp_path, clock)["recovery_status"] == "head_rejoined"
    turn = feed.run(tmp_path, clock)
    expected = [1, 2, 11] if movement == "deleted" else [1, 2, 11, 1]
    assert turn["visited_page_numbers"] == expected and turn["status"] == "partial", turn
    assert turn["recovery_status"] == "restart_pending"
    assert turn["candidate_eligible_visits"] == 2
    if movement != "deleted":
        assert turn["frontier_overlap"]["matched_rows"] == 0
    assert turn["recovery_depth"] == 11 and read_state(tmp_path)[0] == checkpoint

    # A rate limit while re-reading the recent chain cannot certify a replacement.
    feed.rate_limit_url = link(3)["canonical_url"]
    assert feed.run(tmp_path, clock)["status"] == "waiting"
    assert read_state(tmp_path)[0] == checkpoint
    clock.wait(180)
    turn = run_after_process_restart(tmp_path, feed, clock)
    assert turn["recovery_status"] == "restarted_from_head", turn
    assert turn["visited_page_numbers"] == [1, 2, 3, 4] and turn["recovery_depth"] == 4
    for i in range(30):
        if i == 3:
            feed.ids.insert(0, feed.ids[0] + 1)
        turn = feed.run(tmp_path, clock)
        current, found = read_state(tmp_path)
        assert known.items() <= found.items()
        known = found
        assert feed.visits[:2] == [1, 2] and len(feed.visits) <= 4
        assert str(feed.ids[0]) in found
        if turn["status"] == "complete":
            assert current != checkpoint
            assert {str(n) for n in feed.ids if n > OLD_HEAD} <= found.keys()
            return
        assert current == checkpoint and turn["status"] == "partial", turn
    pytest.fail("The rebuilt route never reached the original checkpoint")
