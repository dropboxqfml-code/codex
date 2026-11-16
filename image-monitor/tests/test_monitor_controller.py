import json
import threading
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from image_monitor import monitor_controller as monitor
from image_monitor.monitor_controller import MONITOR_SCOPE, MonitorController
from image_monitor.queue import QueueError, QueueStore
from image_monitor.watch_runtime import DEFAULT_SCOPE
from image_monitor.watch_store import WatchStore

NOW = datetime(2026, 11, 17, 5, tzinfo=UTC)


class Clock:
    def __init__(self):
        self.current = NOW

    def now(self):
        return self.current

    def advance(self, seconds):
        self.current += timedelta(seconds=seconds)


class AutoClock(Clock):
    def wait_for(self, event, seconds):
        self.advance(seconds)


def until(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    assert predicate(), "The monitor worker did not reach the expected state"


def persist(root, clock, *, scope=MONITOR_SCOPE, added=(), interval=60, status=200, complete=True):
    root.mkdir(parents=True, exist_ok=True)
    observed = clock.now()
    due = observed + timedelta(seconds=interval)
    with QueueStore(root / "watch.sqlite") as queue:
        store = WatchStore(queue)
        state = store.get_state(scope)
        checkpoint = {
            "anchor_ids": ["100"],
            "observed_at": observed.isoformat(),
            "source_url": "https://gall.dcinside.com/board/lists/?id=comic_new6",
        }
        baseline = (
            checkpoint | {"mode": "new", "requires_published_at_filter": True}
            if state["baseline"] is None and complete
            else None
        )
        stored = store.persist_scan(
            scope,
            observed_at=observed,
            expected_generation=state["generation"],
            scan_result={
                "complete": complete,
                "gap_reason": None if complete else "max_pages",
                "control": {
                    "blocked": status in {401, 403, 404, 410},
                    "finished_at": observed.isoformat(),
                    "next_eligible_at": due.isoformat(),
                    "interval_seconds": interval,
                    "http_status": status,
                    "transport_status": "observed" if status == 200 else "http_error",
                },
            },
            candidates=[
                {
                    "post_id": post_id,
                    "post_url": f"https://gall.dcinside.com/board/view/?id=comic_new6&no={post_id}",
                    "title": "Invented private candidate title",
                    "shown_metadata": {"author_raw": "Invented private author"},
                }
                for post_id in added
            ],
            checkpoint=checkpoint,
            complete=complete,
            gap_reason=None if complete else "max_pages",
            baseline=baseline,
        )
        queue.defer_service("dcinside", due)
    return {
        "status": "watch_test_completed" if complete else "watch_test_partial",
        "cycles_completed": 1,
        "new_candidates": stored["candidates_added"],
        "browser_closed": True,
        "cycles": [{"http_status": status}],
        "next_eligible_at_local": due.isoformat(),
    }


@pytest.fixture(autouse=True)
def enough_disk(monkeypatch):
    monkeypatch.setattr(monitor.shutil, "disk_usage", lambda _: SimpleNamespace(free=10**12))


@pytest.fixture
def controllers():
    values = []
    yield values
    for controller in values:
        controller.stop()
        assert controller.wait_stopped(5), "A controlled monitor thread leaked"


def create(controllers, root, cycle, clock=None):
    value = MonitorController(root, run_cycle=cycle, clock=clock or Clock())
    controllers.append(value)
    return value


def test_opening_status_stays_stopped_and_does_not_create_a_database(tmp_path, controllers):
    calls = []
    value = create(controllers, tmp_path, lambda *_args, **_kwargs: calls.append(True))
    status = value.status()
    assert status["phase"] == "stopped"
    assert status["candidate_count"] == 0
    assert status["settings_editable"]
    assert not status["baseline_initialized"]
    assert not (tmp_path / "watch.sqlite").exists()
    assert calls == []


def test_new_scope_preserves_trial_and_records_only_its_new_candidates(tmp_path, controllers):
    clock = AutoClock()
    persist(tmp_path, clock, scope=DEFAULT_SCOPE, added=("103", "104"))
    clock.advance(120)
    calls = []

    def cycle(root, browser, **options):
        assert browser == "chrome" and options["scope"] == MONITOR_SCOPE
        assert options["cycles"] == 1 and options["interval_seconds"] == 60
        calls.append(clock.now())
        result = persist(root, clock, added=() if len(calls) == 1 else ("108",))
        if len(calls) == 2:
            value.stop()
        return result

    value = create(controllers, tmp_path, cycle, clock)
    value.start()
    assert value.wait_stopped(3)
    status = value.status()
    assert status["phase"] == "stopped"
    assert status["completed_cycles"] == 2
    assert status["candidate_count"] == status["new_candidates"] == 1
    assert calls[1] - calls[0] >= timedelta(seconds=60)
    with QueueStore(tmp_path / "watch.sqlite", read_only=True) as queue:
        store = WatchStore(queue)
        assert len(store.list_candidates(DEFAULT_SCOPE)) == 2
        assert len(store.list_candidates(MONITOR_SCOPE)) == 1
        assert (
            datetime.fromisoformat(store.get_state(MONITOR_SCOPE)["baseline"]["observed_at"])
            == calls[0]
        )
        assert queue.summary()["posts"] == queue.summary()["jobs"] == 0


@pytest.mark.parametrize(
    ("old_interval", "new_interval", "expected"), [(60, 300, 300), (300, 60, 300)]
)
def test_interval_changes_do_not_advance_any_persisted_wait(
    tmp_path, controllers, old_interval, new_interval, expected
):
    clock = AutoClock()
    persist(tmp_path, clock, interval=old_interval)
    calls = []

    def cycle(root, _browser, **_options):
        calls.append(clock.now())
        result = persist(root, clock, interval=new_interval)
        value.stop()
        return result

    value = create(controllers, tmp_path, cycle, clock)
    value.configure(new_interval)
    value.start()
    assert value.wait_stopped(3)
    assert calls == [NOW + timedelta(seconds=expected)]
    reopened = create(controllers, tmp_path, lambda *_args, **_kwargs: None)
    assert reopened.status()["phase"] == "stopped"
    assert reopened.status()["interval_seconds"] == new_interval


def test_pause_is_nonblocking_and_resume_keeps_the_persisted_deadline(tmp_path, controllers):
    clock = Clock()
    entered, release = threading.Event(), threading.Event()
    calls = []

    def cycle(root, _browser, **options):
        calls.append(clock.now())
        if len(calls) == 1:
            entered.set()
            assert release.wait(3)
            assert options["should_stop"]()
        result = persist(root, clock)
        if len(calls) == 2:
            value.stop()
        return result

    value = create(controllers, tmp_path, cycle, clock)
    value.start()
    try:
        assert entered.wait(3)
        assert value.pause()["phase"] == "pausing"
        with pytest.raises(QueueError):
            value.configure(120)
        release.set()
        until(lambda: value.status()["phase"] == "paused")
        assert len(calls) == 1
        clock.advance(60)
        value.start()
        assert value.wait_stopped(3)
        assert len(calls) == 2
    finally:
        release.set()


def test_repeated_start_does_not_create_another_worker(tmp_path, controllers):
    entered, release = threading.Event(), threading.Event()
    calls = []
    clock = Clock()

    def cycle(root, _browser, **_options):
        calls.append(True)
        entered.set()
        assert release.wait(3)
        value.stop()
        return persist(root, clock)

    value = create(controllers, tmp_path, cycle, clock)
    value.start()
    try:
        assert entered.wait(3)
        value.start()
        value.start()
        assert calls == [True]
    finally:
        release.set()
    assert value.wait_stopped(3)


def test_service_wait_prevents_any_cycle_call_until_the_committed_time(tmp_path, controllers):
    clock = Clock()
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        queue.defer_service("dcinside", NOW + timedelta(seconds=180))
    calls = []
    value = create(controllers, tmp_path, lambda *_args, **_kwargs: calls.append(True), clock)
    value.start()
    until(lambda: value.status()["phase"] == "waiting")
    assert value.status()["remaining_seconds"] == 180
    assert calls == []
    value.stop()
    assert value.wait_stopped(3)


@pytest.mark.parametrize("http_status", [429, 503])
def test_server_wait_continues_later_without_shortening_retry_after(
    tmp_path, controllers, http_status
):
    calls = []
    clock = AutoClock()

    def cycle(root, _browser, **_options):
        calls.append(clock.now())
        if len(calls) == 1:
            report = persist(root, clock, status=http_status, interval=180, complete=False)
            report["status"] = "watch_test_failed"
            return report
        result = persist(root, clock)
        value.stop()
        return result

    value = create(controllers, tmp_path, cycle, clock)
    value.start()
    assert value.wait_stopped(3)
    assert calls == [NOW, NOW + timedelta(seconds=180)]
    assert value.status()["completed_cycles"] == 1


@pytest.mark.parametrize("http_status", [401, 403, 404, 410])
def test_access_block_stops_without_a_second_request(tmp_path, controllers, http_status):
    calls = []
    clock = Clock()

    def cycle(root, _browser, **_options):
        calls.append(True)
        result = persist(root, clock, status=http_status, complete=False)
        result.update(status="watch_test_failed", reason="access_block_requires_review")
        return result

    value = create(controllers, tmp_path, cycle, clock)
    value.start()
    assert value.wait_stopped(3)
    assert value.status()["phase"] == "needs_review"
    assert value.status()["reason"] == "access_block_requires_review"
    assert calls == [True]
    with pytest.raises(QueueError):
        value.start()


def test_partial_coverage_preserves_baseline_and_stops_for_review(tmp_path, controllers):
    clock = Clock()
    persist(tmp_path, clock)
    with QueueStore(tmp_path / "watch.sqlite", read_only=True) as queue:
        before = WatchStore(queue).get_state(MONITOR_SCOPE)
    clock.advance(60)
    calls = []

    def cycle(root, _browser, **_options):
        calls.append(True)
        return persist(root, clock, added=("105",), complete=False)

    value = create(controllers, tmp_path, cycle, clock)
    value.start()
    assert value.wait_stopped(3)
    assert value.status()["phase"] == "needs_review"
    assert value.status()["gap_reason"] == "max_pages"
    assert value.status()["candidate_count"] == 1
    assert value.status()["new_candidates"] == value.status()["current_cycle_new"] == 1
    assert calls == [True]
    with QueueStore(tmp_path / "watch.sqlite", read_only=True) as queue:
        after = WatchStore(queue).get_state(MONITOR_SCOPE)
        assert after["baseline"] == before["baseline"]
        assert after["checkpoint"] == before["checkpoint"]


@pytest.mark.parametrize("outcome", ["cancelled", "service_wait"])
def test_partial_candidates_are_counted_even_when_the_cycle_does_not_complete(
    tmp_path, controllers, outcome
):
    clock = Clock()
    persist(tmp_path, clock)
    clock.advance(60)

    def cycle(root, _browser, **_options):
        result = persist(root, clock, added=("105",), complete=False)
        if outcome == "cancelled":
            value.stop()
            result["status"] = "watch_test_cancelled"
        else:
            result["status"] = "watch_test_failed"
            result["cycles"] = [{"http_status": 429}]
        return result

    value = create(controllers, tmp_path, cycle, clock)
    value.start()
    if outcome == "service_wait":
        until(lambda: value.status()["phase"] == "waiting")
        value.stop()
    assert value.wait_stopped(3)
    status = value.status()
    assert status["candidate_count"] == 1
    assert status["new_candidates"] == status["current_cycle_new"] == 1
    assert status["completed_cycles"] == 0


def test_access_block_observed_during_stop_is_not_hidden_as_a_normal_stop(tmp_path, controllers):
    clock = Clock()

    def cycle(root, _browser, **_options):
        result = persist(root, clock, status=403, complete=False)
        result["status"] = "watch_test_cancelled"
        value.stop()
        return result

    value = create(controllers, tmp_path, cycle, clock)
    value.start()
    assert value.wait_stopped(3)
    status = value.status()
    assert status["phase"] == "needs_review"
    assert status["reason"] == "access_block_requires_review"
    assert status["browser_closed"] is True


def test_busy_cycle_uses_a_bounded_wait_instead_of_a_hot_retry_loop(tmp_path, controllers):
    calls = []
    clock = AutoClock()

    def cycle(root, _browser, **_options):
        calls.append(clock.now())
        if len(calls) == 1:
            return {"status": "watch_busy", "browser_closed": True}
        result = persist(root, clock)
        value.stop()
        return result

    value = create(controllers, tmp_path, cycle, clock)
    value.start()
    assert value.wait_stopped(3)
    assert calls == [NOW, NOW + timedelta(seconds=monitor.BUSY_BACKOFF_SECONDS)]


def test_low_disk_space_stops_before_any_scan(tmp_path, controllers, monkeypatch):
    calls = []
    value = create(controllers, tmp_path, lambda *_args, **_kwargs: calls.append(True))
    monkeypatch.setattr(monitor.shutil, "disk_usage", lambda _: SimpleNamespace(free=0))
    value.start()
    assert value.wait_stopped(3)
    assert value.status()["phase"] == "needs_review"
    assert value.status()["reason"] == "insufficient_free_space"
    assert calls == []


@pytest.mark.parametrize("failure", [RuntimeError, KeyboardInterrupt])
def test_unreported_failure_keeps_cleanup_unknown_and_never_restarts(
    tmp_path, controllers, failure
):
    def fail(*_args, **_kwargs):
        raise failure("Invented private URL https://private.example/token")

    value = create(controllers, tmp_path, fail)
    value.start()
    assert value.wait_stopped(3)
    status = value.status()
    assert status["phase"] == "needs_review"
    assert status["browser_closed"] is None
    value.stop()
    assert value.status()["phase"] == "needs_review"
    with pytest.raises(QueueError):
        value.start()
    assert "private.example" not in json.dumps(status)


def test_failed_owned_cleanup_is_not_claimed_stopped(tmp_path, controllers):
    def fail(*_args, **_kwargs):
        return {"status": "watch_test_failed", "browser_closed": False}

    value = create(controllers, tmp_path, fail)
    value.start()
    assert value.wait_stopped(3)
    value.stop()
    assert value.status()["phase"] == "needs_review"
    assert value.status()["browser_closed"] is False


def test_status_commands_do_not_open_sqlite_on_the_http_thread(tmp_path, controllers, monkeypatch):
    value = create(controllers, tmp_path, lambda *_args, **_kwargs: None)

    def forbidden(*_args, **_kwargs):
        pytest.fail("HTTP status/actions must not open a SQLite connection")

    monkeypatch.setattr(monitor, "QueueStore", forbidden)
    assert value.status()["phase"] == "stopped"
    assert value.pause()["phase"] == "stopped"
    assert value.stop()["phase"] == "stopped"
    assert value.configure(120)["interval_seconds"] == 120
