"""A resumed detail belongs to the same recent list even across a service wait."""

from datetime import timedelta

import pytest
from test_candidate_runtime import BrowserFactory as DetailBrowser
from test_candidate_runtime import no_browser, observed, saved
from test_watch_runtime import (
    BrowserFactory,
    FakeClock,
    baseline_outcome,
    link,
    new_posts_outcome,
    snapshot,
)

from image_monitor import candidate_runtime, watch_runtime
from image_monitor.queue import QueueStore
from image_monitor.watch_detail_source import scan_plan_candidates
from image_monitor.watch_lock import watch_run_lock
from image_monitor.watch_planner import plan_scan
from image_monitor.watch_runtime import DEFAULT_SCOPE, SERVICE_SCOPE
from image_monitor.watch_store import MONITOR_SCOPE, WatchStore


@pytest.fixture
def current(tmp_path, monkeypatch):
    monkeypatch.setattr(candidate_runtime, "require_windows", lambda: None)
    monkeypatch.setattr(watch_runtime, "require_windows", lambda: None)
    clock = FakeClock()
    report = watch_runtime.run_watch_trial(
        tmp_path, clock=clock, backend_factory=BrowserFactory(baseline_outcome, new_posts_outcome)
    )
    assert report["status"] == "watch_test_completed" and report["new_candidates"] == 2
    clock.waits.clear()
    return clock


def resume(root, clock, backend=no_browser):
    return candidate_runtime.run_candidate_trial(
        root, recent_scan_only=True, max_candidates=1, clock=clock, backend_factory=backend
    )


def test_complete_window_waits_once_without_owning_lease_then_uses_list_order(tmp_path, current):
    before = saved(tmp_path)
    advance = current.wait

    def wait(seconds):
        with watch_run_lock(tmp_path / "watch.sqlite", DEFAULT_SCOPE):
            advance(seconds)

    current.wait = wait
    factory = DetailBrowser(observed(published_at=current.now()))
    report = resume(tmp_path, current, factory)
    assert current.waits == [60]
    assert report["status"] == "candidate_test_completed" and report["browser_closed"]
    assert report["source_scan"] == {
        "generation": 2,
        "coverage": "complete",
        "gap_reason": None,
        "page_count": 2,
        "ordinary_rows": 6,
        "new_candidates": 2,
        "unattempted_candidates": 2,
    }
    assert [call[0]["post_id"] for call in factory.browser.calls] == ["104"]
    after = saved(tmp_path)
    for key in ("state", "scans", "candidates", "gaps"):
        assert after[key] == before[key]
    assert len(after["details"]) == 1 and after["summary"]["jobs"] == 0


def test_a_different_generation_during_wait_cannot_dispatch_a_detail(tmp_path, current):
    advance = current.wait

    def wait(seconds):
        advance(seconds)
        result = watch_runtime.run_watch_trial(
            tmp_path, cycles=1, clock=current, backend_factory=BrowserFactory(new_posts_outcome)
        )
        assert result["cycles_completed"] == 1

    current.wait = wait
    report = resume(tmp_path, current)
    assert current.waits == [60]
    assert (report["status"], report["reason"]) == (
        "candidate_scan_unverified",
        "source_scan_changed",
    )
    assert saved(tmp_path)["details"] == []


def test_longer_service_wait_returns_immediately_without_selecting_a_post(tmp_path, current):
    due = current.now() + timedelta(seconds=240)
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        queue.defer_service(SERVICE_SCOPE, due)
    report = resume(tmp_path, current)
    assert report["status"] == "candidate_waiting" and current.waits == []
    assert report["candidates_selected"] == 0 and saved(tmp_path)["details"] == []


@pytest.mark.parametrize(
    "tamper",
    [
        "DELETE FROM watch_candidates WHERE post_id='104'",
        "UPDATE watch_candidates SET post_url='https://invalid.example/post' WHERE post_id='103'",
    ],
    ids=["missing_record", "changed_identity"],
)
def test_only_matching_unattempted_records_can_reach_detail(tmp_path, current, tamper):
    with QueueStore(tmp_path / "watch.sqlite") as queue, queue.connection:
        queue.connection.execute(tamper)
    report = resume(tmp_path, current)
    assert report["status"] == "candidate_scan_unverified"
    assert current.waits == [] and saved(tmp_path)["details"] == []


def test_exhausted_window_never_retries_a_detail(tmp_path, current):
    for _ in range(2):
        result = resume(tmp_path, current, DetailBrowser(observed(published_at=current.now())))
        assert result["status"] == "candidate_test_completed"
    report = resume(tmp_path, current)
    assert report["status"] == "candidate_no_pending"
    assert current.waits == [60, 60]
    assert report["source_scan"]["unattempted_candidates"] == 0


def test_removing_database_during_wait_never_initializes_a_new_one(tmp_path, current):
    database = tmp_path / "watch.sqlite"
    advance = current.wait

    def wait(seconds):
        database.rename(tmp_path / "previous.sqlite")
        advance(seconds)

    current.wait = wait
    report = resume(tmp_path, current)
    assert report["reason"] == "source_scan_changed"
    assert not database.exists() and (tmp_path / "previous.sqlite").is_file()


def test_dense_three_page_scan_reconciles_previous_and_new_rows_after_reopen(tmp_path):
    path = tmp_path / "watch.sqlite"
    clock = FakeClock()
    with QueueStore(path) as queue:
        store = WatchStore(queue)
        for count in (1, 2, 3):
            now = clock.now()
            if count == 1:
                pages = baseline_outcome(now)["pages"]
            else:
                pages = [
                    snapshot(range(650, 450, -1), now, links=[link(2)]),
                    snapshot(range(450, 250, -1), now, page=2, links=[link(3)]),
                    snapshot([250, 249], now, page=3, links=[link(4)]),
                ][:count]
            plan = plan_scan(
                MONITOR_SCOPE, store.get_state(MONITOR_SCOPE), pages, now, allow_verified_live=True
            )
            plan["scan_result"]["private_observation"] = {"pages": pages}
            persisted = store.persist_scan(MONITOR_SCOPE, **plan)
            assert persisted["candidates_added"] == {1: 0, 2: 400, 3: 2}[count]
            clock.wait(60)

    with QueueStore(path, read_only=True) as queue:
        store = WatchStore(queue)
        state = store.get_state(MONITOR_SCOPE)
        summary, candidates = scan_plan_candidates(queue, MONITOR_SCOPE, state, plan)
        assert summary["page_count"] == 3 and summary["ordinary_rows"] == 402
        assert summary["new_candidates"] == summary["unattempted_candidates"] == 2
        assert [row["post_id"] for row in candidates] == ["250", "249"]
        assert state["checkpoint"]["anchor_ids"] == ["100", "99"]
        assert len(store.list_gaps(MONITOR_SCOPE)) == 2
        assert scan_plan_candidates(queue, DEFAULT_SCOPE, state, plan) == (None, [])

        # The SQL records and candidate plan agree about the two new identities.
        # A changed historical boundary cannot authorize those third-page rows.
        plan["scan_result"]["historical_follow_up"] = {
            "boundary_page": 4,
            "status": "boundary_changed",
        }
        assert scan_plan_candidates(queue, MONITOR_SCOPE, state, plan) == (None, [])
        del plan["scan_result"]["historical_follow_up"]

        # Keep the fresh page's size unchanged, but remove a known identity
        # the store claims to have refreshed this turn.
        pages = state["latest_scan"]["result"]["private_observation"]["pages"]
        replacement = snapshot([651], clock.now())["rows"][0]
        pages[0]["rows"][0] = replacement
        assert scan_plan_candidates(queue, MONITOR_SCOPE, state, plan) == (None, [])
