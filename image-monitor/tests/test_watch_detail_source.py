"""A resumed detail belongs to the same recent list even across a service wait."""

from datetime import timedelta

import pytest
from test_candidate_runtime import BrowserFactory as DetailBrowser
from test_candidate_runtime import no_browser, observed, saved
from test_watch_runtime import (
    BrowserFactory,
    FakeClock,
    baseline_outcome,
    new_posts_outcome,
)

from image_monitor import candidate_runtime, watch_runtime
from image_monitor.queue import QueueStore
from image_monitor.watch_lock import watch_run_lock
from image_monitor.watch_runtime import DEFAULT_SCOPE, SERVICE_SCOPE


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
