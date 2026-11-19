"""Pause on the boundary between selecting a detail and navigating to it."""

from contextlib import nullcontext
from datetime import timedelta
from threading import Event

import pytest
from test_candidate_runtime import BrowserFactory, http_failure
from test_monitor_controller import AutoClock, until
from test_monitor_gap_continuation import partial_pages, run_scan, seed_baseline

from image_monitor import candidate_runtime, watch_runtime
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.monitor_controller import BUSY_BACKOFF_SECONDS, MONITOR_SCOPE, MonitorController
from image_monitor.queue import QueueStore
from image_monitor.watch_lock import watch_run_lock
from image_monitor.watch_store import WatchStore


@pytest.mark.parametrize("consumed_while_paused", [False, True])
def test_resume_after_detail_preflight_honors_the_original_slot(
    tmp_path, monkeypatch, consumed_while_paused
):
    monkeypatch.setattr(watch_runtime, "require_windows", lambda: None)
    monkeypatch.setattr(candidate_runtime, "require_windows", lambda: None)
    paused = Event()

    class Clock(AutoClock):
        def wait_for(self, wake, seconds):
            if paused.is_set():
                wake.wait(10)
            else:
                self.advance(seconds)

    clock = Clock()
    seed_baseline(tmp_path, clock)
    detail_browser = BrowserFactory(http_failure(404))
    actions = []
    scan_ids = []

    def cycle(root, _browser, **options):
        if actions:
            controller.stop()
        actions.append("list")
        return run_scan(root, clock, partial_pages, should_stop=options["should_stop"])

    def detail(root, browser, **options):
        scan_ids.append(options["expected_scan_id"])
        if len(scan_ids) == 1:
            actions.append("preflight")
            paused.set()
            controller.pause()
        else:
            actions.append("detail")
        report = candidate_runtime.run_candidate_trial(
            root, browser, backend_factory=detail_browser, **options
        )
        if len(scan_ids) > 1:
            controller.stop()
        return report

    controller = MonitorController(tmp_path, clock=clock, run_cycle=cycle, run_details=detail)
    try:
        controller.start()
        until(lambda: controller.status()["phase"] == "paused", timeout=15)
        assert actions == ["list", "preflight"] and not detail_browser.calls
        with QueueStore(tmp_path / "watch.sqlite", read_only=True) as queue:
            store = CandidateDetailStore(queue)
            assert store.list_details(MONITOR_SCOPE) == []
            (pending,) = store.list_pending(MONITOR_SCOPE, limit=1)
            scan = WatchStore(queue).get_state(MONITOR_SCOPE)["latest_scan"]
            assert scan["scan_id"] == scan_ids[0]
        if consumed_while_paused:
            # A separate worker can consume this turn while the dashboard is paused.
            result = candidate_runtime.run_candidate_trial(
                tmp_path,
                scope=MONITOR_SCOPE,
                clock=clock,
                max_candidates=1,
                expected_scan_id=scan["scan_id"],
                backend_factory=detail_browser,
            )
            assert result["candidates_completed"] == 1

        paused.clear()
        controller.start()
        assert controller.wait_stopped(15)
        assert actions == ["list", "preflight", "list" if consumed_while_paused else "detail"]
        if not consumed_while_paused:
            assert scan_ids == [scan["scan_id"], scan["scan_id"]]
        assert [row["post_id"] for row, _ in detail_browser.browser.calls] == [pending["post_id"]]
        with QueueStore(tmp_path / "watch.sqlite", read_only=True) as queue:
            (attempt,) = CandidateDetailStore(queue).list_details(MONITOR_SCOPE)
            assert attempt["post_id"] == pending["post_id"] and attempt["status"] == "completed"
            assert queue.summary()["jobs"] == 0
    finally:
        paused.clear()
        controller.stop()
        assert controller.wait_stopped(15)


@pytest.mark.parametrize(
    ("deferred", "competitor_finishes"),
    [("candidate_waiting", False), ("candidate_busy", False), ("candidate_busy", True)],
)
def test_unspent_restored_detail_waits_then_rechecks_consumption(
    tmp_path, monkeypatch, deferred, competitor_finishes
):
    monkeypatch.setattr(watch_runtime, "require_windows", lambda: None)
    monkeypatch.setattr(candidate_runtime, "require_windows", lambda: None)
    browser = BrowserFactory(http_failure(404))
    actions = []
    results = []

    class Clock(AutoClock):
        def wait_for(self, wake, seconds):
            self.advance(seconds)
            if competitor_finishes and results == [deferred] and not browser.calls:
                done = candidate_runtime.run_candidate_trial(
                    tmp_path,
                    scope=MONITOR_SCOPE,
                    clock=self,
                    max_candidates=1,
                    expected_scan_id=scan_id,
                    backend_factory=browser,
                )
                assert done["candidates_completed"] == 1

    clock = Clock()
    seed_baseline(tmp_path, clock)
    saved = run_scan(tmp_path, clock, partial_pages)
    assert saved["status"] == "watch_test_partial"
    database = tmp_path / "watch.sqlite"
    with QueueStore(database, read_only=True) as queue:
        scan_id = WatchStore(queue).get_state(MONITOR_SCOPE)["latest_scan"]["scan_id"]
        (pending,) = CandidateDetailStore(queue).list_pending(MONITOR_SCOPE, limit=1)

    def cycle(root, _browser, **options):
        actions.append(("list", clock.now()))
        controller.stop()
        return run_scan(root, clock, partial_pages, should_stop=options["should_stop"])

    def detail(root, name, **options):
        assert options["expected_scan_id"] == scan_id
        actions.append(("detail", clock.now()))
        if not results and deferred == "candidate_waiting":
            with QueueStore(database) as queue:
                queue.defer_service("dcinside", clock.now() + timedelta(seconds=180))
        lease = (
            watch_run_lock(database, watch_runtime.DEFAULT_SCOPE)
            if not results and deferred == "candidate_busy"
            else nullcontext()
        )
        with lease:
            report = candidate_runtime.run_candidate_trial(
                root, name, backend_factory=browser, **options
            )
        if not results:
            assert report["status"] == deferred and report["candidates_completed"] == 0
            assert not browser.calls
        elif report["status"] != "candidate_no_pending":
            controller.stop()
        results.append(report["status"])
        return report

    controller = MonitorController(tmp_path, clock=clock, run_cycle=cycle, run_details=detail)
    try:
        controller.start()
        assert controller.wait_stopped(15)
        delay = 180 if deferred == "candidate_waiting" else BUSY_BACKOFF_SECONDS
        if competitor_finishes:
            delay += 60  # The competing detail set a fresh service deadline.
            assert actions[-1][0] == "list"
            # The controller or the candidate worker may recognize the durable completion.
            assert results in ([deferred], [deferred, "candidate_no_pending"])
        else:
            assert [kind for kind, _ in actions] == ["detail", "detail"]
            assert results == [deferred, "candidate_test_completed"]
        assert actions[-1][1] - actions[0][1] == timedelta(seconds=delay)
        assert [row["post_id"] for row, _ in browser.browser.calls] == [pending["post_id"]]
    finally:
        controller.stop()
        assert controller.wait_stopped(15)
