"""Verify per-turn work limits and stop boundaries under the session's monitor lock."""

import uuid
from datetime import timedelta
from functools import partial

import pytest
from test_candidate_runtime import BrowserFactory, http_failure
from test_monitor_auto_selection import roots as roots
from test_monitor_auto_session import scan
from test_monitor_batch_runtime import Runner, ledger
from test_monitor_batch_runtime import data as data
from test_monitor_collect import forbidden, ready, targets
from test_watch_image_search import body

from image_monitor import candidate_runtime, monitor_collect
from image_monitor.auto_monitor_cli import _describe_result
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.monitor_auto_selection import search_monitor_candidates
from image_monitor.monitor_auto_session import run_auto_monitor
from image_monitor.monitor_clock import wait_until
from image_monitor.monitor_settings import save_monitor_settings
from image_monitor.native_state import PendingSave
from image_monitor.queue import QueueStore
from image_monitor.watch_lock import WatchRunBusy, watch_run_lock
from image_monitor.watch_runtime import SERVICE_SCOPE
from image_monitor.watch_store import MONITOR_SCOPE


def mark_picture(database):
    with QueueStore(database) as queue, queue._write():
        queue.connection.execute(
            "UPDATE watch_candidates SET shown_metadata_json=json_set(shown_metadata_json,"
            "'$.picture_marker',json('true')) WHERE watch_name=? AND post_id='106'",
            (MONITOR_SCOPE.watch_name,),
        )


@pytest.mark.parametrize("missing_status", [404, 410])
def test_missing_marked_post_allows_one_paced_followup_and_reports_both(roots, missing_status):
    watch, legacy, batch, clock = roots
    mark_picture(watch / "watch.sqlite")
    visits = []

    def missing(candidate, stamp):
        visits.append((candidate["post_id"], stamp))
        return http_failure(missing_status)(candidate, stamp) | {"url": candidate["post_url"]}

    # The first ordinary 404 uses its usual budget. The second turn picks the marked
    # post, then goes back to the oldest waiting post even if it too is missing.
    inspect = partial(
        candidate_runtime.run_candidate_trial,
        backend_factory=BrowserFactory(missing, missing, missing),
    )
    report = run_auto_monitor(
        watch,
        legacy,
        batch,
        clock=clock,
        max_cycles=2,
        scan_runner=lambda *args, **kwargs: scan(),
        collect_runner=partial(
            monitor_collect.collect_session_turn, detail_runner=inspect, save_runner=forbidden
        ),
    )
    assert report["status"] == "auto_monitor_completed", report
    assert report["new_details_checked"] == 3 and report["native_save_tasks_started"] == 0
    assert [post for post, _ in visits] == ["102", "106", "103"]
    assert visits[2][1] - visits[1][1] >= timedelta(seconds=60)
    first, second = report["recent_collection_attempts"]
    assert first["new_details_checked"] == 1 and "unavailable_picture_followup_started" not in first
    assert second["new_details_checked"] == 2 and second["unavailable_picture_followup_started"]
    assert second["detail_selection_order"] == "oldest_discovery"
    summary = _describe_result(report)["auto_test_summary_ko"]
    assert "열 수 없었던 사진 표시 글 → 오래 기다린 글" in summary and "한도(2건)" in summary


@pytest.mark.parametrize("stop_before_followup", [False, True])
def test_followup_handoff_or_stop_during_its_cooldown(roots, stop_before_followup):
    watch, legacy, batch, clock = roots
    mark_picture(watch / "watch.sqlite")
    missing_at = []

    def missing(candidate, stamp):
        missing_at.append(stamp)
        return http_failure(404)(candidate, stamp) | {"url": candidate["post_url"]}

    inspect = partial(
        candidate_runtime.run_candidate_trial,
        backend_factory=BrowserFactory(body(0), missing, body(1)),
    )
    search = partial(
        search_monitor_candidates,
        watch,
        legacy,
        batch,
        clock=clock,
        alternate_order=True,
        max_new_details=1,
        follow_unavailable_picture=True,
        detail_runner=inspect,
    )
    first, _ = search()
    assert first["status"] == "limit" and first["new_details_checked"] == 1
    report, target = search(
        should_stop=lambda: bool(
            stop_before_followup and missing_at and clock.now() > missing_at[0]
        )
    )
    if stop_before_followup:
        assert report["status"] == "cancelled" and target is None
        assert (
            report["new_details_checked"] == 1
            and "unavailable_picture_followup_started" not in report
        )
    else:
        assert report["status"] == "ready" and target["post_id"] == "103", report
        assert report["new_details_checked"] == 2 and report["unavailable_picture_followup_started"]
        assert report["last_fresh_detail_outcome"] == "save_ready"


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
