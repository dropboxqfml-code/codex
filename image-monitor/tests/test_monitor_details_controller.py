"""Exercise bounded detail work through the real monitor's owned worker."""

import json
import threading
from datetime import timedelta

import pytest
from test_monitor_controller import NOW, AutoClock, Clock, persist, until

from image_monitor import monitor_controller as monitor
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.monitor_controller import MONITOR_SCOPE, MonitorController
from image_monitor.queue import QueueError, QueueStore
from image_monitor.watch_runtime import DEFAULT_SCOPE
from image_monitor.watch_store import WatchStore


@pytest.fixture
def controllers():
    values = []
    yield values
    for value in values:
        value.stop()
        assert value.wait_stopped(3), "An owned detail worker leaked"


def create(controllers, root, runner, *, clock=None, cycle=None):
    value = MonitorController(
        root,
        run_cycle=cycle or (lambda *_args, **_kwargs: pytest.fail("Details refreshed the list")),
        run_details=runner,
        clock=clock or Clock(),
    )
    controllers.append(value)
    return value


def seed(root, clock, *, candidates=("101", "102", "103")):
    persist(root, clock, added=candidates)


def record_detail(
    root, clock, *, scope=MONITOR_SCOPE, http=200, time_status="at_or_after_baseline"
):
    with QueueStore(root / "watch.sqlite") as queue:
        store = CandidateDetailStore(queue)
        candidate = store.list_pending(scope, limit=1)[0]
        baseline = WatchStore(queue).get_state(scope)["baseline"]
        attempt = store.start(
            scope,
            candidate["post_id"],
            expected_first_scan_id=candidate["first_scan_id"],
            baseline_observed_at=monitor._stored_time(baseline["observed_at"]),
            started_at=clock.now(),
        )
        due = clock.now() + timedelta(seconds=60)
        classification = {
            "time_status": time_status,
            "reason": "candidate_unavailable"
            if http in {404, 410}
            else "published_at_or_after_baseline",
        }
        store.finish(
            attempt["attempt_id"],
            finished_at=clock.now(),
            status="completed" if http in {200, 404, 410} else "failed",
            result={
                "classification": classification,
                "control": {
                    "blocked": http in {401, 403},
                    "finished_at": clock.now().isoformat(),
                    "next_eligible_at": due.isoformat(),
                },
                "private_observation": {
                    "http_status": http,
                    "snapshot": {
                        "title": "Invented private title",
                        "nickname": "Invented private nickname",
                        "post_url": candidate["post_url"],
                        "image_counts": {"included_unique": 2, "pending": 0},
                    },
                },
            },
        )
        queue.defer_service("dcinside", due)
    return {
        "status": "candidate_test_completed",
        "candidates_completed": 1,
        "browser_closed": True,
        "details": [
            {
                "status": "observed" if http == 200 else "http_error",
                "http_status": http,
                "time_status": time_status,
            }
        ],
        "next_eligible_at_local": due.isoformat(),
    }


def test_opening_and_no_baseline_detail_action_does_not_create_database(tmp_path, controllers):
    calls = []
    value = create(controllers, tmp_path, lambda *_args, **_kwargs: calls.append(True))
    status = value.inspect_candidates()
    assert status["phase"] == "stopped"
    assert status["reason"] == "existing_baseline_required"
    assert status["task_kind"] == "details"
    assert status["detail_count"] == status["detail_pending_count"] == 0
    assert not value.is_alive()
    assert not (tmp_path / "watch.sqlite").exists()
    assert calls == []


def test_two_details_obey_both_cooldowns_and_never_discover_or_change_baseline(
    tmp_path, controllers
):
    clock = AutoClock()
    seed(tmp_path, clock)
    persist(tmp_path, clock, scope=DEFAULT_SCOPE, added=("201",))
    with QueueStore(tmp_path / "watch.sqlite", read_only=True) as queue:
        before = WatchStore(queue).get_state(MONITOR_SCOPE)
        old_trial = WatchStore(queue).get_state(DEFAULT_SCOPE)
    calls = []
    worker_ids = []

    def details(root, browser, **options):
        calls.append(clock.now())
        worker_ids.append(threading.get_ident())
        assert browser == "chrome"
        assert options == {
            "scope": MONITOR_SCOPE,
            "max_candidates": 1,
            "interval_seconds": 60,
            "should_stop": value._requested_stop,
            "clock": clock,
        }
        assert value.status()["phase"] == "inspecting"
        return record_detail(root, clock)

    value = create(controllers, tmp_path, details, clock=clock)
    last_scan = value.status()["last_scan_at"]
    assert value.status()["detail_pending_count"] == 3
    value.inspect_candidates()
    assert value.wait_stopped(3)
    status = value.status()
    assert status["phase"] == "stopped" and status["task_kind"] == "details"
    assert status["detail_count"] == status["detail_completed_count"] == 2
    assert status["detail_pending_count"] == 1
    assert status["detail_failed_count"] == 0
    assert status["completed_cycles"] == status["new_candidates"] == 0
    assert status["last_scan_at"] == last_scan
    assert calls == [NOW + timedelta(seconds=60), NOW + timedelta(seconds=120)]
    assert len(set(worker_ids)) == 1 and worker_ids[0] != threading.get_ident()
    assert len(status["details"]) == 2
    assert status["details"][0]["image_count"] == 2
    assert "Invented private" not in json.dumps(status)
    with QueueStore(tmp_path / "watch.sqlite", read_only=True) as queue:
        assert WatchStore(queue).get_state(MONITOR_SCOPE) == before
        assert WatchStore(queue).get_state(DEFAULT_SCOPE) == old_trial
        assert queue.summary()["posts"] == queue.summary()["jobs"] == 0
    status["details"][0]["image_count"] = 99
    assert value.status()["details"][0]["image_count"] == 2


def test_no_pending_is_an_inert_action_and_restart_reads_existing_detail_summary(
    tmp_path, controllers
):
    clock = AutoClock()
    seed(tmp_path, clock, candidates=("101",))
    clock.advance(60)
    record_detail(tmp_path, clock)
    calls = []
    value = create(controllers, tmp_path, lambda *_args, **_kwargs: calls.append(True), clock=clock)
    status = value.inspect_candidates()
    assert status["phase"] == "stopped" and status["reason"] == "no_unattempted_candidates"
    assert status["detail_count"] == status["detail_completed_count"] == 1
    assert status["detail_pending_count"] == 0
    assert not value.is_alive() and calls == []


def test_stop_during_initial_cooldown_never_opens_detail_browser(tmp_path, controllers):
    clock = Clock()
    seed(tmp_path, clock)
    calls = []
    value = create(controllers, tmp_path, lambda *_args, **_kwargs: calls.append(True), clock=clock)
    value.inspect_candidates()
    until(lambda: value.status()["phase"] == "waiting")
    assert value.status()["remaining_seconds"] == 60
    value.stop()
    assert value.wait_stopped(3)
    assert calls == []
    assert value.status()["detail_pending_count"] == 3


def test_stop_after_first_detail_keeps_completed_result_and_does_not_start_second(
    tmp_path, controllers
):
    clock = AutoClock()
    seed(tmp_path, clock)
    calls = []

    def details(root, _browser, **_options):
        calls.append(True)
        result = record_detail(root, clock)
        value.stop()
        return result

    value = create(controllers, tmp_path, details, clock=clock)
    value.inspect_candidates()
    assert value.wait_stopped(3)
    assert calls == [True]
    assert value.status()["phase"] == "stopped"
    assert value.status()["detail_count"] == 1
    assert value.status()["detail_pending_count"] == 2


def test_pause_resume_continues_same_detail_batch_without_starting_list(tmp_path, controllers):
    clock = Clock()
    seed(tmp_path, clock)
    clock.advance(60)
    entered, release = threading.Event(), threading.Event()
    calls = []

    def details(root, _browser, **options):
        calls.append(clock.now())
        if len(calls) == 1:
            entered.set()
            assert release.wait(3)
            assert options["should_stop"]()
        return record_detail(root, clock)

    value = create(controllers, tmp_path, details, clock=clock)
    value.inspect_candidates()
    try:
        assert entered.wait(3)
        assert value.pause()["phase"] == "pausing"
        release.set()
        until(lambda: value.status()["phase"] == "paused")
        assert len(calls) == 1
        clock.advance(60)
        assert value.start()["task_kind"] == "details"
        assert value.wait_stopped(3)
        assert calls == [NOW + timedelta(seconds=60), NOW + timedelta(seconds=120)]
    finally:
        release.set()


@pytest.mark.parametrize("http", [401, 403])
def test_access_block_wins_over_stop_and_review_is_sticky(tmp_path, controllers, http):
    clock = AutoClock()
    seed(tmp_path, clock)
    calls = []

    def details(root, _browser, **_options):
        calls.append(True)
        report = record_detail(root, clock, http=http)
        value.stop()
        report["status"] = "candidate_test_cancelled"
        return report

    value = create(controllers, tmp_path, details, clock=clock)
    value.inspect_candidates()
    assert value.wait_stopped(3)
    assert value.status()["phase"] == "needs_review"
    assert value.status()["reason"] == "access_block_requires_review"
    value.stop()
    assert value.status()["phase"] == "needs_review"
    with pytest.raises(QueueError):
        value.start()
    with pytest.raises(QueueError):
        value.inspect_candidates()
    assert calls == [True]


@pytest.mark.parametrize("http", [404, 410])
def test_deleted_detail_does_not_block_next_candidate(tmp_path, controllers, http):
    clock = AutoClock()
    seed(tmp_path, clock)
    calls = []

    def details(root, _browser, **_options):
        calls.append(True)
        return record_detail(root, clock, http=http if len(calls) == 1 else 200)

    value = create(controllers, tmp_path, details, clock=clock)
    value.inspect_candidates()
    assert value.wait_stopped(3)
    assert value.status()["phase"] == "stopped"
    assert value.status()["detail_count"] == 2
    assert calls == [True, True]


def test_busy_detail_backs_off_without_spending_batch_limit(tmp_path, controllers):
    clock = AutoClock()
    seed(tmp_path, clock)
    calls = []

    def details(root, _browser, **_options):
        calls.append(clock.now())
        if len(calls) == 1:
            return {"status": "candidate_busy", "browser_closed": True}
        return record_detail(root, clock)

    value = create(controllers, tmp_path, details, clock=clock)
    value.inspect_candidates()
    assert value.wait_stopped(3)
    assert calls == [
        NOW + timedelta(seconds=60),
        NOW + timedelta(seconds=75),
        NOW + timedelta(seconds=135),
    ]
    assert value.status()["detail_count"] == 2


def test_backend_exception_preserves_unknown_cleanup_and_rejects_restart(tmp_path, controllers):
    clock = AutoClock()
    seed(tmp_path, clock)

    def fail(*_args, **_options):
        raise RuntimeError("Invented private title and https://private.example/token")

    value = create(controllers, tmp_path, fail, clock=clock)
    value.inspect_candidates()
    assert value.wait_stopped(3)
    status = value.status()
    assert status["phase"] == "needs_review" and status["browser_closed"] is None
    assert status["error_type"] == "RuntimeError"
    assert "private.example" not in json.dumps(status)
    value.stop()
    with pytest.raises(QueueError):
        value.inspect_candidates()


def test_unknown_classification_stops_for_review_without_automatic_repetition(
    tmp_path, controllers
):
    clock = AutoClock()
    seed(tmp_path, clock)
    calls = []

    def details(root, _browser, **_options):
        calls.append(True)
        result = record_detail(root, clock, time_status="unknown")
        result.update(status="candidate_test_partial", reason="Invented private reason")
        return result

    value = create(controllers, tmp_path, details, clock=clock)
    value.inspect_candidates()
    assert value.wait_stopped(3)
    assert value.status()["phase"] == "needs_review"
    assert value.status()["reason"] == "detail_requires_review"
    value.stop()
    with pytest.raises(QueueError):
        value.start()
    assert calls == [True]


def test_detail_action_rejects_running_list_worker(tmp_path, controllers):
    clock = Clock()
    seed(tmp_path, clock)
    value = create(controllers, tmp_path, lambda *_args, **_kwargs: None, clock=clock)
    value.start()
    until(lambda: value.status()["phase"] == "waiting")
    with pytest.raises(QueueError):
        value.inspect_candidates()


def test_detail_action_and_http_status_do_not_read_sqlite(tmp_path, controllers, monkeypatch):
    value = create(controllers, tmp_path, lambda *_args, **_kwargs: None)

    def forbidden(*_args, **_kwargs):
        pytest.fail("A monitor command opened SQLite on the HTTP thread")

    monkeypatch.setattr(monitor, "QueueStore", forbidden)
    assert value.status()["detail_pending_count"] == 0
    assert value.inspect_candidates()["reason"] == "existing_baseline_required"


def test_increased_interval_after_detail_preserves_minimum_since_detail_finish(
    tmp_path, controllers
):
    clock = AutoClock()
    seed(tmp_path, clock)
    clock.advance(60)
    record_detail(tmp_path, clock)
    calls = []

    def details(root, _browser, **_options):
        calls.append(clock.now())
        result = record_detail(root, clock)
        value.stop()
        return result

    value = create(controllers, tmp_path, details, clock=clock)
    value.configure(300)
    value.inspect_candidates()
    assert value.wait_stopped(3)
    assert calls == [NOW + timedelta(seconds=360)]


def test_interrupted_attempt_is_counted_as_review_and_never_as_pending(tmp_path, controllers):
    clock = Clock()
    seed(tmp_path, clock, candidates=("101",))
    clock.advance(60)
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        store = CandidateDetailStore(queue)
        candidate = store.list_pending(MONITOR_SCOPE, limit=1)[0]
        store.start(
            MONITOR_SCOPE,
            candidate["post_id"],
            expected_first_scan_id=candidate["first_scan_id"],
            baseline_observed_at=NOW,
            started_at=clock.now(),
        )
    value = create(
        controllers,
        tmp_path,
        lambda *_args, **_kwargs: pytest.fail("Retried interrupted detail"),
        clock=clock,
    )
    status = value.inspect_candidates()
    assert status["detail_count"] == status["detail_failed_count"] == 1
    assert status["detail_pending_count"] == status["detail_completed_count"] == 0
    assert status["details"][0]["status"] == "started"
    assert status["details"][0]["image_count"] is None


@pytest.mark.parametrize("outcome", ["unknown", "network_error"])
def test_stop_does_not_hide_a_failed_or_unknown_observation(tmp_path, controllers, outcome):
    clock = AutoClock()
    seed(tmp_path, clock)
    calls = []

    def details(root, _browser, **_options):
        calls.append(True)
        result = record_detail(root, clock, time_status="unknown")
        if outcome == "network_error":
            result["details"][0].update(status="network_error", http_status=None)
        value.stop()
        result["status"] = "candidate_test_cancelled"
        return result

    value = create(controllers, tmp_path, details, clock=clock)
    value.inspect_candidates()
    assert value.wait_stopped(3)
    assert value.status()["phase"] == "needs_review"
    assert value.status()["reason"] == "detail_requires_review"
    assert calls == [True]


@pytest.mark.parametrize("http", [429, 503])
def test_retry_after_ends_batch_with_wait_preserved_and_no_automatic_next_candidate(
    tmp_path, controllers, http
):
    clock = AutoClock()
    seed(tmp_path, clock)
    calls = []
    deadline = NOW + timedelta(seconds=60 + 3600)

    def details(root, _browser, **_options):
        calls.append(True)
        result = record_detail(root, clock, http=http)
        with QueueStore(root / "watch.sqlite") as queue:
            queue.defer_service("dcinside", deadline)
        result.update(status="candidate_waiting", next_eligible_at_local=deadline.isoformat())
        return result

    value = create(controllers, tmp_path, details, clock=clock)
    value.inspect_candidates()
    assert value.wait_stopped(3)
    status = value.status()
    assert status["phase"] == "stopped"
    assert status["reason"] == "service_retry_after"
    assert status["remaining_seconds"] == 3600
    assert status["detail_count"] == status["detail_failed_count"] == 1
    assert status["detail_pending_count"] == 2
    assert calls == [True]
    assert clock.now() == NOW + timedelta(seconds=60)


def test_aggregate_summary_is_bounded_and_never_reads_whole_private_results(tmp_path, controllers):
    clock = AutoClock()
    seed(tmp_path, clock, candidates=tuple(str(i) for i in range(101, 116)))
    for _ in range(15):
        clock.advance(60)
        record_detail(tmp_path, clock)
    value = create(controllers, tmp_path, lambda *_args, **_kwargs: None, clock=clock)
    status = value.status()
    assert status["detail_count"] == status["detail_completed_count"] == 15
    assert len(status["details"]) == 10
    assert [row["order"] for row in status["details"]] == list(range(6, 16))
    assert all(
        set(row) == {"order", "status", "time_status", "reason", "image_count", "pending_images"}
        for row in status["details"]
    )
    assert "Invented private" not in json.dumps(status)


def test_readonly_v4_database_reports_pending_without_detail_table(tmp_path, controllers):
    import sqlite3
    from contextlib import closing

    from image_monitor.queue import APPLICATION_ID, V4_SCHEMA

    database = tmp_path / "watch.sqlite"
    with closing(sqlite3.connect(database)) as connection:
        connection.executescript(V4_SCHEMA)
        connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
        connection.execute("PRAGMA user_version=4")
        connection.commit()
    value = create(controllers, tmp_path, lambda *_args, **_kwargs: None)
    status = value.status()
    assert status["phase"] == "stopped"
    assert status["detail_count"] == status["detail_pending_count"] == 0
    assert status["details"] == []
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 4


@pytest.mark.parametrize("summary", [[], ["not an object"], [{}, {}]])
def test_malformed_report_summaries_fail_closed(tmp_path, controllers, summary):
    clock = AutoClock()
    seed(tmp_path, clock)

    def details(root, _browser, **_options):
        result = record_detail(root, clock)
        result["details"] = summary
        return result

    value = create(controllers, tmp_path, details, clock=clock)
    value.inspect_candidates()
    assert value.wait_stopped(3)
    assert value.status()["phase"] == "needs_review"
    assert value.status()["error_type"] == "QueueError"


@pytest.mark.parametrize("task_kind", ["list", "details"])
def test_commands_cannot_hide_review_before_worker_finally_runs(
    tmp_path, controllers, monkeypatch, task_kind
):
    clock = AutoClock()
    seed(tmp_path, clock)
    entered, release = threading.Event(), threading.Event()

    def fail(*_args, **_options):
        raise RuntimeError("Invented private failure")

    value = create(controllers, tmp_path, fail, clock=clock, cycle=fail)
    original_review = value._review

    def held_review(*args, **kwargs):
        original_review(*args, **kwargs)
        entered.set()
        assert release.wait(3)

    monkeypatch.setattr(value, "_review", held_review)
    if task_kind == "details":
        value.inspect_candidates()
    else:
        value.start()
    try:
        assert entered.wait(3)
        assert value.is_alive()
        assert value.status()["phase"] == "needs_review"
        assert value.pause()["phase"] == "needs_review"
        with pytest.raises(QueueError):
            value.start()
        assert value.stop()["phase"] == "needs_review"
        assert value.status()["browser_closed"] is None
    finally:
        release.set()
    assert value.wait_stopped(3)
    assert value.status()["phase"] == "needs_review"
    assert value.stop()["phase"] == "needs_review"
