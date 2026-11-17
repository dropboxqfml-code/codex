"""Reuse durable detail inspection in the live monitor without widening saving."""

from datetime import timedelta

import pytest
from test_candidate_runtime import (
    BASELINE_TIME,
    NOW,
    BrowserFactory,
    FakeClock,
    http_failure,
    no_browser,
    observed,
    seed,
)

from image_monitor import candidate_runtime
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.monitor_controller import MONITOR_SCOPE
from image_monitor.native_ui import NativeUIError
from image_monitor.queue import QueueStore
from image_monitor.search_list import build_list_url
from image_monitor.watch_lock import watch_run_lock
from image_monitor.watch_runtime import DEFAULT_SCOPE
from image_monitor.watch_store import WatchScope, WatchStore


@pytest.fixture(autouse=True)
def controlled_windows(monkeypatch):
    monkeypatch.setattr(candidate_runtime, "require_windows", lambda: None)


def monitor_records(queue):
    store = WatchStore(queue)
    return {
        "state": store.get_state(MONITOR_SCOPE),
        "scans": store.list_scans(MONITOR_SCOPE),
        "candidates": store.list_candidates(MONITOR_SCOPE),
        "gaps": store.list_gaps(MONITOR_SCOPE),
    }


def seed_monitor(root):
    seed(root, ids=("503",))
    baseline = {
        "mode": "new",
        "observed_at": BASELINE_TIME.isoformat(),
        "anchor_ids": ["200", "199"],
        "source_url": build_list_url("normal", "comic_new6", "ai"),
        "requires_published_at_filter": True,
    }
    with QueueStore(root / "watch.sqlite") as queue:
        store = WatchStore(queue)
        for generation, stamp, ids in (
            (0, BASELINE_TIME, ()),
            (1, NOW - timedelta(seconds=120), ("301", "302", "303")),
        ):
            store.persist_scan(
                MONITOR_SCOPE,
                observed_at=stamp,
                expected_generation=generation,
                scan_result={
                    "mode": "invented_monitor_fixture",
                    "control": {
                        "blocked": False,
                        "finished_at": stamp.isoformat(),
                        "next_eligible_at": (stamp + timedelta(seconds=60)).isoformat(),
                        "interval_seconds": 60,
                    },
                },
                candidates=[
                    {
                        "post_id": post_id,
                        "post_url": (
                            "https://gall.dcinside.com/board/view/?id=comic_new6&no=" + post_id
                        ),
                        "title": "Invented monitor candidate",
                        "shown_metadata": {"requires_published_at_filter": True},
                    }
                    for post_id in ids
                ],
                checkpoint=baseline | {"anchor_ids": list(ids) + ["200", "199"]},
                complete=True,
                baseline=baseline if generation == 0 else None,
            )
        return monitor_records(queue), store.get_state(DEFAULT_SCOPE)


def run(root, **options):
    return candidate_runtime.run_candidate_trial(root, scope=MONITOR_SCOPE, **options)


def details(root):
    with QueueStore(root / "watch.sqlite", read_only=True) as queue:
        return CandidateDetailStore(queue).list_details(MONITOR_SCOPE)


def service_due(root):
    with QueueStore(root / "watch.sqlite", read_only=True) as queue:
        value = queue.connection.execute(
            "SELECT not_before FROM service_limits WHERE scope='dcinside'"
        ).fetchone()[0]
    return candidate_runtime._stored_time(value)


def test_monitor_detail_uses_only_its_existing_candidates_and_preserves_both_scopes(tmp_path):
    before, old_state = seed_monitor(tmp_path)
    factory = BrowserFactory(observed())
    with watch_run_lock(tmp_path / "watch.sqlite", MONITOR_SCOPE, purpose="monitor"):
        report = run(tmp_path, max_candidates=1, clock=FakeClock(), backend_factory=factory)
    assert report["status"] == "candidate_test_completed", report
    assert report["images_saved"] is False
    assert report["image_jobs_created"] == 0
    assert factory.browser.calls[0][0]["post_id"] == "301"
    assert report["details"][0]["time_status"] == "at_or_after_baseline"
    assert report["details"][0]["save_approved"] is False
    with QueueStore(tmp_path / "watch.sqlite", read_only=True) as queue:
        assert monitor_records(queue) == before
        assert WatchStore(queue).get_state(DEFAULT_SCOPE) == old_state
        assert CandidateDetailStore(queue).list_details(DEFAULT_SCOPE) == []
        assert queue.summary()["posts"] == queue.summary()["jobs"] == 0
    assert not (tmp_path / "images").exists()


def test_monitor_detail_cannot_bypass_the_shared_legacy_scan_lease(tmp_path):
    seed_monitor(tmp_path)
    with watch_run_lock(tmp_path / "watch.sqlite", DEFAULT_SCOPE):
        report = run(tmp_path, clock=FakeClock(), backend_factory=no_browser)
    assert report["status"] == "candidate_busy"
    assert details(tmp_path) == []


def test_monitor_detail_honors_an_existing_global_wait_before_opening_browser(tmp_path):
    seed_monitor(tmp_path)
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        queue.defer_service("dcinside", NOW + timedelta(seconds=180))
    report = run(tmp_path, clock=FakeClock(), backend_factory=no_browser)
    assert report["status"] == "candidate_waiting"
    assert service_due(tmp_path) == NOW + timedelta(seconds=180)
    assert details(tmp_path) == []


def test_monitor_scope_does_not_reuse_the_older_trial_baseline(tmp_path):
    seed(tmp_path)
    report = run(tmp_path, clock=FakeClock(), backend_factory=no_browser)
    assert report["status"] == "candidate_no_baseline"
    with QueueStore(tmp_path / "watch.sqlite", read_only=True) as queue:
        assert WatchStore(queue).get_state(MONITOR_SCOPE)["baseline"] is None
        assert CandidateDetailStore(queue).list_details(DEFAULT_SCOPE) == []


def test_requested_stop_before_backend_keeps_every_candidate_unattempted(tmp_path):
    before, _ = seed_monitor(tmp_path)
    report = run(tmp_path, clock=FakeClock(), backend_factory=no_browser, should_stop=lambda: True)
    assert report["status"] == "candidate_test_cancelled"
    assert report["reason"] == "requested_stop"
    assert report["error_type"] is None and report["browser_closed"] is True
    assert details(tmp_path) == []
    with QueueStore(tmp_path / "watch.sqlite", read_only=True) as queue:
        assert monitor_records(queue) == before


def test_stop_while_browser_is_opened_closes_it_before_any_detail_attempt(tmp_path):
    seed_monitor(tmp_path)
    stopping = False
    original = BrowserFactory()

    def factory(*args, **kwargs):
        nonlocal stopping
        stopping = True
        return original(*args, **kwargs)

    report = run(tmp_path, clock=FakeClock(), backend_factory=factory, should_stop=lambda: stopping)
    assert report["status"] == "candidate_test_cancelled"
    assert report["browser_closed"] is True
    assert original.browser.calls == []
    assert details(tmp_path) == []


def test_stop_after_response_persists_completed_detail_and_wait_without_repeating_it(tmp_path):
    seed_monitor(tmp_path)
    clock = FakeClock()
    stopping = False

    def finish_current(candidate, stamp):
        nonlocal stopping
        clock.current += timedelta(seconds=15)
        stopping = True
        return observed()(candidate, stamp)

    factory = BrowserFactory(finish_current)
    report = run(tmp_path, clock=clock, backend_factory=factory, should_stop=lambda: stopping)
    assert report["status"] == "candidate_test_cancelled"
    assert report["candidates_completed"] == 1
    assert report["browser_closed"] is True
    assert len(details(tmp_path)) == 1 and details(tmp_path)[0]["status"] == "completed"
    assert service_due(tmp_path) == NOW + timedelta(seconds=75)
    clock.current += timedelta(seconds=300)
    later = BrowserFactory(observed())
    resumed = run(tmp_path, max_candidates=1, clock=clock, backend_factory=later)
    assert resumed["status"] == "candidate_test_completed"
    assert later.browser.calls[0][0]["post_id"] == "302"


@pytest.mark.parametrize("http_status", [401, 403])
def test_access_block_wins_over_simultaneous_stop_and_blocks_every_scope(tmp_path, http_status):
    seed_monitor(tmp_path)
    stopping = False

    def block(*args):
        nonlocal stopping
        stopping = True
        return http_failure(http_status)(*args)

    clock = FakeClock()
    report = run(
        tmp_path,
        clock=clock,
        backend_factory=BrowserFactory(block),
        should_stop=lambda: stopping,
    )
    assert report["status"] == "candidate_test_failed"
    assert report["reason"] == "access_block_requires_review"
    assert report["last_stage"] == "blocked"
    assert details(tmp_path)[0]["result"]["control"]["blocked"] is True
    clock.current += timedelta(seconds=300)
    for scope in (MONITOR_SCOPE, DEFAULT_SCOPE):
        repeated = candidate_runtime.run_candidate_trial(
            tmp_path,
            scope=scope,
            clock=clock,
            backend_factory=no_browser,
            should_stop=lambda: True,
        )
        assert repeated["status"] == "candidate_test_failed"
        assert repeated["reason"] == "access_block_requires_review"


@pytest.mark.parametrize("http_status", [429, 503])
def test_stop_after_server_wait_response_still_preserves_retry_after(tmp_path, http_status):
    seed_monitor(tmp_path)
    stopping = False

    def server_wait(*args):
        nonlocal stopping
        stopping = True
        return http_failure(http_status, "180")(*args)

    clock = FakeClock()
    report = run(
        tmp_path,
        clock=clock,
        backend_factory=BrowserFactory(server_wait),
        should_stop=lambda: stopping,
    )
    assert report["status"] == "candidate_test_cancelled"
    assert details(tmp_path)[0]["status"] == "failed"
    assert service_due(tmp_path) == NOW + timedelta(seconds=180)
    repeated = run(tmp_path, clock=clock, backend_factory=no_browser)
    assert repeated["status"] == "candidate_waiting"


def test_requested_stop_interrupts_between_detail_wait_without_starting_the_second(tmp_path):
    seed_monitor(tmp_path)
    clock = FakeClock()
    stopping = False

    def wait(seconds):
        nonlocal stopping
        assert 0 < seconds <= 0.1
        clock.current += timedelta(seconds=seconds)
        stopping = True

    clock.wait = wait
    factory = BrowserFactory(observed())
    report = run(tmp_path, clock=clock, backend_factory=factory, should_stop=lambda: stopping)
    assert report["status"] == "candidate_test_cancelled"
    assert report["browser_closed"] is True
    assert len(details(tmp_path)) == 1
    assert details(tmp_path)[0]["status"] == "completed"
    assert len(factory.browser.calls) == 1


@pytest.mark.parametrize("failure", [KeyboardInterrupt, RuntimeError])
def test_monitor_interrupted_attempt_is_audited_and_never_automatically_repeated(tmp_path, failure):
    seed_monitor(tmp_path)
    clock = FakeClock()

    def interrupted(*_):
        clock.current += timedelta(seconds=15)
        raise failure("Invented private exception text")

    report = run(
        tmp_path,
        clock=clock,
        backend_factory=BrowserFactory(interrupted),
        should_stop=lambda: False,
    )
    assert report["status"] == (
        "candidate_test_cancelled" if failure is KeyboardInterrupt else "candidate_test_failed"
    )
    assert details(tmp_path)[0]["status"] == "started"
    assert service_due(tmp_path) == NOW + timedelta(seconds=75)
    assert report["browser_closed"] is True
    clock.current += timedelta(seconds=300)
    later = BrowserFactory(observed())
    resumed = run(tmp_path, max_candidates=1, clock=clock, backend_factory=later)
    assert resumed["status"] == "candidate_test_completed"
    assert later.browser.calls[0][0]["post_id"] == "302"
    assert {row["status"] for row in details(tmp_path)} == {"started", "completed"}


def test_requested_stop_report_does_not_claim_an_unproven_browser_cleanup(tmp_path):
    seed_monitor(tmp_path)
    stopping = False

    def complete(candidate, stamp):
        nonlocal stopping
        stopping = True
        return observed()(candidate, stamp)

    original = BrowserFactory(complete)

    class UnconfirmedClose:
        browser_version = "test-browser"
        browser_closed = False

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def inspect(self, *args):
            return original.browser.inspect(*args)

    report = run(
        tmp_path,
        clock=FakeClock(),
        backend_factory=lambda *_, **__: UnconfirmedClose(),
        should_stop=lambda: stopping,
    )
    assert report["status"] == "candidate_test_cancelled"
    assert report["browser_closed"] is False
    assert details(tmp_path)[0]["status"] == "completed"


@pytest.mark.parametrize(
    "scope",
    [
        None,
        "목록 감시",
        WatchScope("arbitrary", "normal", "comic_new6", "ai", "search_subject_memo"),
        WatchScope("목록 감시", "minor", "comic_new6", "ai", "search_subject_memo"),
        WatchScope("목록 감시", "normal", "comic_new6", "different", "search_subject_memo"),
    ],
)
def test_unreviewed_scope_is_rejected_before_creating_any_files(tmp_path, scope):
    root = tmp_path / "missing"
    with pytest.raises(NativeUIError):
        candidate_runtime.run_candidate_trial(root, scope=scope)
    assert not root.exists()


@pytest.mark.parametrize("condition", [False, True, 3, "stop"])
def test_noncallable_stop_is_rejected_before_creating_any_files(tmp_path, condition):
    root = tmp_path / "missing"
    with pytest.raises(NativeUIError):
        run(root, should_stop=condition)
    assert not root.exists()


def test_stop_predicate_must_return_a_boolean_before_browser_or_attempt(tmp_path):
    seed_monitor(tmp_path)
    report = run(
        tmp_path, clock=FakeClock(), backend_factory=no_browser, should_stop=lambda: "stop"
    )
    assert report["status"] == "candidate_test_failed"
    assert report["error_type"] == "QueueError"
    assert details(tmp_path) == []
