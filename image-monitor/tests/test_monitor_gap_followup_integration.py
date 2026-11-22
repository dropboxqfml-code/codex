"""Reopen a real monitor queue and exercise bounded, latest-first Chrome list traversal."""

from datetime import UTC, datetime, timedelta
from functools import partial
from types import SimpleNamespace

from test_monitor_auto_session_integration import local_workers
from test_monitor_auto_session_integration import session_data as session_data
from test_post_worker import pilot as pilot
from test_watch_runtime import FakeClock, link, no_browser, snapshot

from image_monitor import watch_runtime
from image_monitor.monitor_auto_discovery import run_auto_discovery
from image_monitor.monitor_auto_session import run_auto_monitor
from image_monitor.monitor_collect import collect_session_turn
from image_monitor.queue import QueueStore
from image_monitor.watch_browser import HeadlessWatchBrowser
from image_monitor.watch_store import MONITOR_SCOPE, WatchStore


def listing(pages, visits, *, rate_limited_page=None, page_numbers=None):
    """Substitute only the page transport and DOM for the production traversal."""
    if page_numbers is None:
        page_numbers = list(range(1, len(pages) + 1))
    assert len(page_numbers) == len(pages) and page_numbers[0] == 1

    class LocalBrowser(HeadlessWatchBrowser):
        def __enter__(self):
            self._page = self
            self.browser_closed = False
            self.browser_version = "fixture"
            return self

        def __exit__(self, *_):
            self._page = None
            self.browser_closed = True

        def _navigate(self, url):
            assert len(visits) < len(pages), "A page outside the fixture budget was requested"
            page = page_numbers[len(visits)]
            assert url == link(page)["canonical_url"]
            visits.append(url)
            if page == rate_limited_page:
                return SimpleNamespace(status=429, header_value=lambda _: "600")
            return SimpleNamespace(status=200, header_value=lambda _: None)

        def _inspect_document(self, url, scan_time, *, can_settle):
            position = len(visits) - 1
            page = page_numbers[position]
            assert visits[-1] == url and can_settle and page != rate_limited_page
            links = [link(page + 1)]
            if position + 1 < len(pages) and page_numbers[position + 1] > page + 1:
                links.append(link(page_numbers[position + 1]))
            return snapshot(
                pages[position],
                scan_time,
                page=page,
                links=links,
                counts={"list_containers": 1},
            )

    return partial(
        run_auto_discovery,
        run_cycle=partial(watch_runtime.run_watch_trial, backend_factory=LocalBrowser),
    )


def saved_state(watch):
    with QueueStore(watch / "watch.sqlite", read_only=True) as queue:
        store = WatchStore(queue)
        return (
            store.get_state(MONITOR_SCOPE),
            {item["post_id"]: item for item in store.list_candidates(MONITOR_SCOPE)},
            store.list_gaps(MONITOR_SCOPE),
        )


def test_reopened_monitor_recovers_historical_posts_and_saves_each_once(
    monkeypatch, pilot, session_data
):
    roots = session_data.watch, session_data.legacy, session_data.batch
    watch = roots[0]
    clock = FakeClock(datetime.now(UTC) + timedelta(seconds=62))
    events, owned = [], []
    detail, save = local_workers(monkeypatch, pilot, clock, events, owned)
    collect = partial(collect_session_turn, detail_runner=detail, save_runner=save)

    visits = []
    assert (
        listing([[200, 199]], visits)(watch, interval_seconds=60, clock=clock)["status"]
        == "baseline"
    )
    assert visits == [link(1)["canonical_url"]]
    clock.wait(60)

    def run(pages):
        visits = []
        result = run_auto_monitor(
            *roots,
            max_cycles=1,
            clock=clock,
            scan_runner=listing(pages, visits),
            collect_runner=collect,
        )
        assert result["status"] == "auto_monitor_completed", result
        assert result["browser_closed"] and result["list_checks"] == result["cycles_completed"] == 1
        assert (
            result["new_details_checked"]
            == result["posts_saved"]
            == result["newly_saved_files"]
            == 1
        )
        assert visits == [link(n)["canonical_url"] for n in range(1, len(pages) + 1)]
        return result

    first = run([[210], [209]])
    assert first["new_candidates"] == 2 and first["partial_list_checks"] == 1
    assert first["gap_followup_checks"] == first["gap_followups_completed"] == 0
    state, old, first_gaps = saved_state(watch)
    checkpoint = state["checkpoint"]
    assert checkpoint["anchor_ids"] == ["200", "199"] and len(first_gaps) == 1

    extended = run([[211, 210], [209], [208]])
    assert extended["new_candidates"] == 2 and extended["partial_list_checks"] == 1
    assert extended["last_list"]["pages_checked"] == extended["last_list"]["page_limit"] == 3
    assert extended["gap_followup_checks"] == 1 and extended["gap_followups_completed"] == 0
    state, middle, gaps = saved_state(watch)
    assert state["checkpoint"] == checkpoint and len(gaps) == 2 and gaps[-1] == first_gaps[0]
    assert {post: row["first_scan_id"] for post, row in old.items()} == {
        post: middle[post]["first_scan_id"] for post in old
    }
    assert middle["208"]["first_scan_id"] == state["latest_scan"]["scan_id"]

    recovered = run([[212, 211], [210, 209], [208, 207, 200], [199, 198]])
    assert recovered["new_candidates"] == 2 and recovered["partial_list_checks"] == 0
    assert recovered["last_list"]["pages_checked"] == recovered["last_list"]["page_limit"] == 4
    assert recovered["gap_followup_checks"] == recovered["gap_followups_completed"] == 1
    state, all_posts, old_gaps = saved_state(watch)
    assert state["checkpoint"]["anchor_ids"] == ["212", "211"]
    assert state["baseline"]["anchor_ids"] == ["200", "199"] and old_gaps == gaps
    assert state["latest_scan"]["result"]["first_anchor_id"] == "200"
    assert set(all_posts) == {str(post) for post in range(207, 213)}
    assert all(
        all_posts[post]["first_scan_id"] == row["first_scan_id"] for post, row in middle.items()
    )
    assert [post for event, post, _ in events if event == "save"] == ["209", "210", "208"]

    ordinary = run([[212, 211], [210, 209]])
    assert ordinary["new_candidates"] == ordinary["partial_list_checks"] == 0
    assert ordinary["gap_followup_checks"] == ordinary["gap_followups_completed"] == 0
    assert ordinary["last_list"]["page_limit"] == 2
    assert [post for event, post, _ in events if event == "save"] == ["209", "210", "208", "211"]
    assert len(list(roots[2].glob("tasks/*/session-*/images/**/001.png"))) == 4
    assert all(browser.browser_closed for browser in owned)


def test_automatic_collection_saves_post_first_seen_on_historical_page_five(
    monkeypatch, pilot, session_data
):
    roots = session_data.watch, session_data.legacy, session_data.batch
    clock = FakeClock(datetime.now(UTC) + timedelta(seconds=62))
    events, browsers = [], []
    detail, save = local_workers(monkeypatch, pilot, clock, events, browsers)
    collect = partial(collect_session_turn, detail_runner=detail, save_runner=save)

    def run(numbers, contents):
        visits = []
        session = run_auto_monitor(
            *roots,
            max_cycles=1,
            clock=clock,
            scan_runner=listing(contents, visits, page_numbers=numbers),
            collect_runner=collect,
        )
        assert session["status"] == "auto_monitor_completed", session
        assert visits == [link(n)["canonical_url"] for n in numbers]
        return session

    run([1], [[200]])
    for count in (2, 3, 4):
        numbers = list(range(1, count + 1))
        result = run(numbers, [[208 - n] for n in numbers])
        assert result["partial_list_checks"] == result["posts_saved"] == 1
    before, old_posts, _ = saved_state(roots[0])
    assert {"204", "205", "206", "207"} == old_posts.keys()

    extended = run([1, 2, 4, 5], [[207], [206], [204], [203, 200]])
    assert extended["last_list"]["recovery_status"] == "overlap_pending"
    assert extended["new_candidates"] == extended["partial_list_checks"] == 1
    halfway, all_posts, _ = saved_state(roots[0])
    assert halfway["checkpoint"] == before["checkpoint"]
    assert all_posts["203"]["first_scan_id"] == halfway["latest_scan"]["scan_id"]

    completed = run([1, 2, 5, 6], [[207], [206], [203, 200], [199]])
    assert completed["gap_followups_completed"] == 1
    assert completed["last_list"]["visited_page_numbers"] == [1, 2, 5, 6]
    assert completed["new_details_checked"] == completed["posts_saved"] == 1
    assert completed["newly_saved_files"] == 1
    [image] = roots[2].glob("tasks/*/session-*/images/**/203/001.png")
    original = image.stat().st_mtime_ns, image.read_bytes()
    ordinary = run([1, 2], [[207], [206]])
    assert ordinary["new_candidates"] == ordinary["posts_saved"] == 0
    assert (image.stat().st_mtime_ns, image.read_bytes()) == original
    assert [post for event, post, _ in events if event == "save"].count("203") == 1


def test_rate_limited_third_page_preserves_checkpoint_and_defers_reopen(tmp_path, monkeypatch):
    monkeypatch.setattr(watch_runtime, "require_windows", lambda: None)
    clock = FakeClock()
    for pages, status in [([[200]], "baseline"), ([[210], [209]], "partial")]:
        result = listing(pages, [])(tmp_path, interval_seconds=60, clock=clock)
        assert result["status"] == status, result
        clock.wait(60)
    before, known, gaps = saved_state(tmp_path)
    visits = []
    result = listing([[211, 210], [209], [208]], visits, rate_limited_page=3)(
        tmp_path, interval_seconds=60, clock=clock
    )
    assert visits == [link(i)["canonical_url"] for i in (1, 2, 3)]
    assert result["status"] == "waiting" and result["browser_closed"] is True
    assert datetime.fromisoformat(result["next_eligible_at"]) == clock.now() + timedelta(
        seconds=600
    )
    after, candidates, retained_gaps = saved_state(tmp_path)
    assert after["checkpoint"] == before["checkpoint"] and not after["latest_scan"]["complete"]
    assert set(known) <= set(candidates)
    assert "208" not in candidates and retained_gaps[-1] == gaps[-1]
    clock.wait(599)
    waiting = run_auto_discovery(tmp_path, interval_seconds=60, clock=clock, run_cycle=no_browser)
    assert waiting["status"] == "waiting" and waiting["browser_closed"] is None
    assert waiting["next_eligible_at"] == result["next_eligible_at"]
    assert saved_state(tmp_path) == (after, candidates, retained_gaps)


def test_anchor_on_fourth_page_remains_a_gap_until_a_full_overlap_page_is_seen(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(watch_runtime, "require_windows", lambda: None)
    clock = FakeClock()
    attempts = [
        ([[200]], "baseline"),
        ([[210], [209]], "partial"),
        ([[211], [210], [209]], "partial"),
        ([[212], [211], [210], [209, 200]], "partial"),
        ([[213], [212], [210, 209], [200, 199]], "partial"),
    ]
    for index, (pages, status) in enumerate(attempts):
        visits = []
        # The old fourth page has shifted. Rediscover its anchor on page five.
        numbers = [1, 2, 4, 5] if index == 4 else list(range(1, len(pages) + 1))
        result = listing(pages, visits, page_numbers=numbers)(
            tmp_path, interval_seconds=60, clock=clock
        )
        assert result["status"] == status, result
        assert visits == [link(n)["canonical_url"] for n in numbers]
        state, _, _ = saved_state(tmp_path)
        assert state["checkpoint"]["anchor_ids"] == ["200"]
        if len(pages) == 4:
            assert state["latest_scan"]["gap_reason"] == "overlap_incomplete"
        clock.wait(60)


def test_upgrade_preserves_a_closed_alpha11_frontier_beyond_the_first_four_pages(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(watch_runtime, "require_windows", lambda: None)
    clock = FakeClock()

    def run(numbers, rows, *, legacy):
        visits = []
        scan = listing(rows, visits, page_numbers=numbers)
        outcome = scan(tmp_path, interval_seconds=60, clock=clock, recover_long_gaps=not legacy)
        assert visits == [link(number)["canonical_url"] for number in numbers]
        clock.wait(60)
        return outcome

    with monkeypatch.context() as old:
        old.setattr(watch_runtime, "PUBLIC_VERSION", "0.5.0-alpha.11")
        assert run([1], [[100]], legacy=True)["status"] == "baseline"
        for length in (2, 3, 4):
            numbers = list(range(1, length + 1))
            assert run(numbers, [[151 - n] for n in numbers], legacy=True)["status"] == "partial"
        for n in (4, 5):
            numbers = [1, 2, n, n + 1]
            assert (
                run(numbers, [[151 - i] for i in numbers], legacy=True)["historical_status"]
                == "extended"
            )
    state, candidates, _ = saved_state(tmp_path)
    old_checkpoint = state["checkpoint"]
    upgraded = run([1, 2, 6, 7], [[150], [149], [145], [144, 100]], legacy=False)
    assert upgraded["status"] == "partial" and upgraded["recovery_depth"] == 7
    state, current, _ = saved_state(tmp_path)
    assert state["checkpoint"] == old_checkpoint
    assert {p: c["first_scan_id"] for p, c in candidates.items()}.items() <= {
        p: c["first_scan_id"] for p, c in current.items()
    }.items()
    result = run([1, 2, 7, 8], [[150], [149], [144, 100], [99]], legacy=False)
    assert result["status"] == "complete" and result["recovery_depth"] == 8
