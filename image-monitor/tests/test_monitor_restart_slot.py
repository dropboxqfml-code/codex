"""Recover only the unspent automatic detail turn belonging to a confirmed monitor scan."""

import pytest
from test_monitor_controller import AutoClock
from test_monitor_details_controller import record_detail
from test_monitor_gap_continuation import run_scan, seed_baseline
from test_watch_runtime import link, new_posts_outcome, observed, snapshot

from image_monitor import candidate_runtime, watch_runtime
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.monitor_controller import MONITOR_SCOPE, MonitorController
from image_monitor.queue import QueueStore
from image_monitor.watch_detail_source import monitor_detail_scan_id
from image_monitor.watch_runtime import _stored_time
from image_monitor.watch_store import WatchStore


@pytest.fixture(autouse=True)
def offline_backends(monkeypatch):
    monkeypatch.setattr(watch_runtime, "require_windows", lambda: None)
    monkeypatch.setattr(candidate_runtime, "require_windows", lambda: None)


@pytest.mark.parametrize("status", ["started", "failed", "completed"])
def test_spent_slot_cannot_inspect_a_second_post_under_the_lease(tmp_path, status):
    clock = AutoClock()
    seed_baseline(tmp_path, clock)
    run_scan(tmp_path, clock, new_posts_outcome)
    database = tmp_path / "watch.sqlite"
    clock.advance(60)
    with QueueStore(database) as queue:
        state = WatchStore(queue).get_state(MONITOR_SCOPE)
        slot = monitor_detail_scan_id(database, queue, state)
        assert slot == state["latest_scan"]["scan_id"]
        details = CandidateDetailStore(queue)
        first, second = details.list_pending(MONITOR_SCOPE)
        attempt = details.start(
            MONITOR_SCOPE,
            first["post_id"],
            expected_first_scan_id=first["first_scan_id"],
            baseline_observed_at=_stored_time(state["baseline"]["observed_at"]),
            started_at=clock.now(),
        )
        if status != "started":
            details.finish(attempt["attempt_id"], status=status, result={}, finished_at=clock.now())
        assert monitor_detail_scan_id(database, queue, state) is None

    def no_browser(*_, **__):
        pytest.fail("The second post must wait for another list turn")

    report = candidate_runtime.run_candidate_trial(
        tmp_path,
        scope=MONITOR_SCOPE,
        clock=clock,
        expected_scan_id=slot,
        max_candidates=1,
        backend_factory=no_browser,
    )
    assert report["reason"] == "no_verified_detail_slot" and report["candidates_completed"] == 0
    with QueueStore(database, read_only=True) as queue:
        assert CandidateDetailStore(queue).list_pending(MONITOR_SCOPE) == [second]


def test_new_list_work_never_inherits_an_externally_consumed_resume_slot(tmp_path):
    first = observed(
        lambda t: snapshot([101, 100, 99], t, links=[link()]),
        lambda t: snapshot([98], t, page=2),
    )
    calls = []

    class Clock(AutoClock):
        def wait_for(self, event, seconds):
            self.advance(seconds)
            if not calls:
                calls.append("other worker")
                record_detail(tmp_path, self)

    clock = Clock()
    seed_baseline(tmp_path, clock)
    run_scan(tmp_path, clock, first)

    def cycle(root, _browser, **_options):
        calls.append("new list")
        assert controller.status()["resume_detail_pending"] is False
        return run_scan(root, clock, new_posts_outcome)

    def detail(root, _browser, **_options):
        calls.append("new detail")
        result = record_detail(root, clock)
        controller.stop()
        return result

    controller = MonitorController(tmp_path, clock=clock, run_cycle=cycle, run_details=detail)
    try:
        assert controller.status()["resume_detail_pending"] is True
        controller.start()
        assert controller.wait_stopped(30)
        state = controller.status()
        assert calls == ["other worker", "new list", "new detail"]
        assert state["phase"] == "stopped" and state["auto_details_checked"] == 1
        assert not state["resumed_detail_slot"] and not state["resume_detail_pending"]
    finally:
        controller.stop()
        assert controller.wait_stopped(30)
