"""Bound the regular scheduler to the exact automatic detail owed at launch."""

from datetime import timedelta
from pathlib import Path

import pytest
from test_candidate_runtime import BrowserFactory, http_failure, observed
from test_monitor_controller import AutoClock, Clock, until
from test_monitor_details_controller import record_detail
from test_monitor_gap_continuation import run_scan, seed_baseline
from test_watch_runtime import new_posts_outcome

from image_monitor import candidate_runtime, watch_runtime
from image_monitor.monitor_controller import MonitorController
from image_monitor.queue import QueueStore
from image_monitor.watch_lock import watch_run_lock
from image_monitor.watch_runtime import DEFAULT_SCOPE


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(watch_runtime, "require_windows", lambda: None)
    monkeypatch.setattr(candidate_runtime, "require_windows", lambda: None)


def seed(root, clock):
    seed_baseline(root, clock)
    return run_scan(root, clock, new_posts_outcome)


def forbidden(*args, **kwargs):
    pytest.fail("Unexpected navigation")


def resume(controller):
    try:
        controller.resume_once()
        assert controller.wait_stopped(10)
        return controller.status()
    finally:
        controller.stop()
        assert controller.wait_stopped(10)


@pytest.mark.parametrize(
    ("http", "status", "reason"),
    [
        (200, "completed", None),
        (404, "completed", None),
        (410, "completed", None),
        (403, "needs_review", "access_block_requires_review"),
        (429, "waiting", "service_retry_after"),
        (503, "waiting", "service_retry_after"),
        (500, "needs_review", "detail_requires_review"),
    ],
)
def test_reports_this_one_detail_and_never_falls_back_to_discovery(tmp_path, http, status, reason):
    clock = AutoClock()
    seed(tmp_path, clock)
    expected_time = clock.now() + timedelta(seconds=60)
    browser = BrowserFactory(
        observed(published_at=clock.now()) if http == 200 else http_failure(http, "600")
    )

    def detail(root, name, **options):
        return candidate_runtime.run_candidate_trial(root, name, backend_factory=browser, **options)

    controller = MonitorController(tmp_path, clock=clock, run_cycle=forbidden, run_details=detail)
    state = resume(controller)
    assert state["resume_once_status"] == status and state["reason"] == reason
    assert browser.calls == [("chrome", expected_time)] and len(browser.browser.calls) == 1
    assert state["resumed_detail_slot"] == (status == "completed")
    assert state["auto_details_checked"] == int(status == "completed")
    assert state["browser_closed"] is True and state["detail_pending_count"] == 1
    detail = state["resume_once_detail"]
    assert set(detail) == {"http_status", "reason", "time_status", "image_count", "pending_images"}
    assert detail["http_status"] == http
    assert detail["image_count"] == (1 if http == 200 else None)
    if http in {404, 410}:
        assert detail["reason"] == "candidate_deleted"
    if status == "waiting":
        assert state["remaining_seconds"] >= 600 and not state["resume_detail_pending"]
    if status == "completed":
        again = resume(controller)
        assert again["resume_once_status"] == "no_slot" and again["resume_once_detail"] is None
        assert len(browser.browser.calls) == 1


@pytest.mark.parametrize("missing", [True, False])
def test_old_or_missing_receipt_never_opens_a_list(tmp_path, missing):
    clock = AutoClock()
    scan = seed(tmp_path, clock)
    if missing:
        Path(scan["report_path"]).unlink()
    else:
        clock.advance(60)
        record_detail(tmp_path, clock)
    controller = MonitorController(
        tmp_path, run_details=forbidden, run_cycle=forbidden, clock=clock
    )
    state = resume(controller)
    assert state["resume_once_status"] == "no_slot"
    assert state["reason"] == "no_verified_detail_slot" and state["resume_once_detail"] is None
    assert state["auto_details_checked"] == 0 and state["phase"] == "stopped"


@pytest.mark.parametrize("during_wait", [True, False])
def test_deadline_over_budget_returns_without_another_wait(tmp_path, during_wait):
    waits = []

    def extend(clock):
        with QueueStore(tmp_path / "watch.sqlite") as queue:
            queue.defer_service("dcinside", clock.now() + timedelta(seconds=90))

    class ExtendingClock(AutoClock):
        def wait_for(self, event, seconds):
            waits.append(seconds)
            self.advance(seconds)
            extend(self)

    clock = ExtendingClock()
    seed(tmp_path, clock)
    if not during_wait:
        extend(clock)
    controller = MonitorController(
        tmp_path, run_details=forbidden, run_cycle=forbidden, clock=clock
    )
    result = resume(controller)
    assert result["resume_once_status"] == "waiting" and result["remaining_seconds"] == 90
    assert result["resume_detail_pending"] and result["resume_once_detail"] is None
    assert waits == ([60] if during_wait else [])


@pytest.mark.parametrize("competing_scan", [True, False])
@pytest.mark.parametrize("race_at_lease", [True, False])
def test_another_worker_consumes_or_replaces_only_pinned_slot(
    tmp_path, competing_scan, race_at_lease
):
    def compete():
        if competing_scan:
            run_scan(tmp_path, clock, new_posts_outcome)
        else:
            record_detail(tmp_path, clock)

    class RaceClock(AutoClock):
        def wait_for(self, event, seconds):
            self.advance(seconds)
            if not race_at_lease:
                compete()

    clock = RaceClock()
    seed(tmp_path, clock)
    calls = []

    def detail(root, name, **options):
        calls.append(options["expected_scan_id"])
        assert race_at_lease
        compete()
        return candidate_runtime.run_candidate_trial(
            root, name, backend_factory=forbidden, **options
        )

    controller = MonitorController(tmp_path, run_details=detail, run_cycle=forbidden, clock=clock)
    state = resume(controller)
    assert state["resume_once_status"] == "no_slot" and state["reason"] == "resume_slot_changed"
    assert state["auto_details_checked"] == 0 and state["resume_once_detail"] is None
    assert len(calls) == int(race_at_lease)


def test_shared_lease_busy_never_polls_or_navigates(tmp_path):
    clock = AutoClock()
    seed(tmp_path, clock)
    clock.advance(60)
    now = clock.now()
    with watch_run_lock(tmp_path / "watch.sqlite", DEFAULT_SCOPE):
        state = resume(MonitorController(tmp_path, run_cycle=forbidden, clock=clock))
    assert state["resume_once_status"] == "busy" and state["reason"] == "another_worker_active"
    assert state["resume_detail_pending"] and state["resume_once_detail"] is None
    assert clock.now() == now


def test_cancel_during_wait_retains_slot_and_returns_promptly(tmp_path):
    clock = Clock()
    seed(tmp_path, clock)
    controller = MonitorController(
        tmp_path, run_cycle=forbidden, run_details=forbidden, clock=clock
    )
    controller.resume_once()
    try:
        until(lambda: controller.status()["phase"] == "waiting")
        assert controller.resume_once()["resume_once_status"] == "busy"
    finally:
        controller.stop()
        assert controller.wait_stopped(10)
    state = controller.status()
    assert state["resume_once_status"] == "cancelled" and state["reason"] == "requested_stop"
    assert state["resume_detail_pending"] and state["browser_closed"] is True


def test_uncertain_browser_cleanup_overrides_success(tmp_path):
    clock = AutoClock()
    seed(tmp_path, clock)

    def detail(root, _, **options):
        return record_detail(root, clock) | {"browser_closed": False}

    controller = MonitorController(tmp_path, run_cycle=forbidden, run_details=detail, clock=clock)
    state = resume(controller)
    assert state["resume_once_status"] == "needs_review"
    assert state["reason"] == "owned_browser_cleanup_unconfirmed"
    assert not state["resumed_detail_slot"] and state["browser_closed"] is False
