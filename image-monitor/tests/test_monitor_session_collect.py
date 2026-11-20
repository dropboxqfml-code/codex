"""Verify per-turn work limits and stop boundaries under the session's monitor lock."""

import uuid
from datetime import timedelta
from functools import partial

import pytest
from test_candidate_runtime import BrowserFactory
from test_monitor_auto_selection import roots as roots
from test_monitor_batch_runtime import Runner, ledger
from test_monitor_batch_runtime import data as data
from test_monitor_collect import forbidden, ready, targets
from test_watch_image_search import body

from image_monitor import candidate_runtime, monitor_collect
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.monitor_clock import wait_until
from image_monitor.monitor_settings import save_monitor_settings
from image_monitor.native_state import PendingSave
from image_monitor.queue import QueueStore
from image_monitor.watch_lock import WatchRunBusy, watch_run_lock
from image_monitor.watch_runtime import SERVICE_SCOPE
from image_monitor.watch_store import MONITOR_SCOPE


def test_owned_session_turn_checks_exactly_one_pending_post(roots):
    watch, legacy, batch, clock = roots
    database = watch / "watch.sqlite"
    inspect = partial(
        candidate_runtime.run_candidate_trial, backend_factory=BrowserFactory(body(0), body(0))
    )
    with watch_run_lock(database, MONITOR_SCOPE, purpose="monitor"):
        ordinary = monitor_collect.run_monitor_collect(watch, legacy, batch, clock=clock)
        assert ordinary["status"] == "monitor_collect_busy"
        for pending in (5, 4):
            report = monitor_collect.collect_session_turn(
                watch, legacy, batch, clock=clock, detail_runner=inspect, save_runner=forbidden
            )
            assert report["status"] == "monitor_collect_limit", report
            assert report["new_details_checked"] == 1 and report["native_save_tasks_started"] == 0
            with QueueStore(database, read_only=True) as queue:
                details = CandidateDetailStore(queue)
                assert len(details.list_pending(MONITOR_SCOPE, limit=10)) == pending
                assert len(details.list_details(MONITOR_SCOPE)) == 6 - pending
        with (
            pytest.raises(WatchRunBusy),
            watch_run_lock(database, MONITOR_SCOPE, purpose="monitor"),
        ):
            pytest.fail("Collection must preserve the session's lease")


@pytest.mark.parametrize("before_detail", [False, True])
def test_stop_during_configured_cooldown_preserves_only_finished_observations(roots, before_detail):
    watch, legacy, batch, clock = roots
    database = watch / "watch.sqlite"
    save_monitor_settings(watch, 180)
    if before_detail:
        with QueueStore(database) as queue:
            queue.defer_service(SERVICE_SCOPE, clock.now() + timedelta(seconds=180))
    inspect = partial(
        candidate_runtime.run_candidate_trial, backend_factory=BrowserFactory(body(1))
    )
    with watch_run_lock(database, MONITOR_SCOPE, purpose="monitor"):
        report = monitor_collect.collect_session_turn(
            watch,
            legacy,
            batch,
            clock=clock,
            should_stop=lambda: bool(clock.waits),
            detail_runner=inspect,
            save_runner=forbidden,
        )
    assert report["status"] == "monitor_collect_cancelled", report
    assert report["new_details_checked"] == int(not before_detail)
    assert report["native_save_tasks_started"] == report["files_verified"] == 0
    assert report["browser_closed"] and len(clock.waits) == 1 and clock.waits[0] <= 1
    with QueueStore(database, read_only=True) as queue:
        assert len(CandidateDetailStore(queue).list_details(MONITOR_SCOPE)) == int(
            not before_detail
        )


def test_stop_during_native_input_finishes_and_verifies_only_pinned_post(data, monkeypatch):
    selected, other = targets(data)
    monkeypatch.setattr(
        monitor_collect, "search_monitor_candidates", lambda *_a, **_kw: ready(selected)
    )
    runner = Runner(data)
    stopped = False

    def save(root, browser, url, *, automatic_start, **options):
        nonlocal stopped
        assert automatic_start
        stopped = True
        state = PendingSave(data.marker)
        directory = root / "session-1" / "runs" / uuid.uuid4().hex
        (directory / "browser-profile").mkdir(parents=True)
        (root / "session-1" / "images").mkdir()
        pending = state.begin(directory)
        state.update_browser(pending, 202, 100.0)
        result = runner(root, browser, url, **options)
        state.finish(pending)
        return result

    with watch_run_lock(data.watch / "watch.sqlite", MONITOR_SCOPE, purpose="monitor"):
        report = monitor_collect.collect_session_turn(
            data.watch,
            data.legacy,
            data.batch,
            clock=data.clock,
            save_runner=save,
            should_stop=lambda: stopped,
        )
    assert report["status"] == "monitor_collect_saved", report
    assert stopped and len(runner.calls) == report["files_verified"] == 1
    assert report["saved_files"][0]["detected_format"] == "PNG"
    assert report["browser_closed"] and not data.marker.exists()
    with ledger(data) as store:
        assert store.get_for_post(selected["post_id"])["status"] == "completed"
        assert store.get_for_post(other["post_id"]) is None


def test_wait_does_not_spin_if_clock_stops_advancing(roots, monkeypatch):
    clock = roots[3]
    monkeypatch.setattr(clock, "wait", lambda _seconds: None)
    with pytest.raises(ValueError, match="did not advance"):
        wait_until(clock, clock.now() + timedelta(seconds=5), lambda: False)
