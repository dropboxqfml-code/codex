"""Route the monitor's reviewed candidate through its isolated native-save pilot."""

import json
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_candidate_save_runtime import BASELINE, NOW, FakeClock, seed, snapshot

from image_monitor import candidate_save_runtime as runtime
from image_monitor.candidate_policy import classify_candidate_detail
from image_monitor.candidate_save_selection import (
    MANIFEST_NAME,
    MONITOR_MANIFEST_NAME,
    read_selection,
    select_candidate_save,
    write_selection_control,
)
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.monitor_controller import MONITOR_SCOPE
from image_monitor.native_ui import NativeUIError
from image_monitor.queue import QueueError, QueueStore
from image_monitor.watch_lock import watch_run_lock
from image_monitor.watch_runtime import DEFAULT_SCOPE, _eligibility
from image_monitor.watch_store import WatchScope, WatchStore


@pytest.fixture(autouse=True)
def allow_controlled_windows_wrapper(monkeypatch):
    monkeypatch.setattr(runtime, "require_windows", lambda: None)


def seed_monitor(watch_root, *, image_count=1):
    """Keep an earlier trial and add two independently observed monitor candidates."""
    observations = seed(watch_root)
    baseline = {"observed_at": BASELINE.isoformat(), "anchor_ids": ["200"], "mode": "new"}
    with QueueStore(watch_root / "watch.sqlite") as queue:
        watch = WatchStore(queue)
        for generation, stamp, posts in (
            (0, BASELINE, ()),
            (1, NOW - timedelta(seconds=120), ("201", "202")),
        ):
            watch.persist_scan(
                MONITOR_SCOPE,
                observed_at=stamp,
                expected_generation=generation,
                scan_result={
                    "mode": "invented_monitor_fixture",
                    "control": {
                        "finished_at": stamp.isoformat(),
                        "next_eligible_at": (stamp + timedelta(seconds=60)).isoformat(),
                        "interval_seconds": 60,
                        "blocked": False,
                    },
                },
                candidates=[
                    {
                        "post_id": post_id,
                        "post_url": (
                            f"https://gall.dcinside.com/board/view/?id=comic_new6&no={post_id}"
                        ),
                        "title": "Invented monitor list title",
                        "shown_metadata": {"baseline_observed_at": baseline["observed_at"]},
                    }
                    for post_id in posts
                ],
                checkpoint=baseline | {"anchor_ids": [*posts, "200"]},
                complete=True,
                baseline=baseline if generation == 0 else None,
            )
        details = CandidateDetailStore(queue)
        for candidate in watch.list_candidates(MONITOR_SCOPE):
            attempt = details.start(
                MONITOR_SCOPE,
                candidate["post_id"],
                expected_first_scan_id=candidate["first_scan_id"],
                baseline_observed_at=BASELINE,
                started_at=NOW - timedelta(seconds=90),
            )
            observed = snapshot(candidate, NOW - timedelta(seconds=85), count=image_count)
            observations[candidate["post_url"]] = observed
            details.finish(
                attempt["attempt_id"],
                finished_at=NOW - timedelta(seconds=80),
                result={
                    "classification": classify_candidate_detail(candidate, baseline, observed),
                    "private_observation": {
                        "status": "observed",
                        "url": candidate["post_url"],
                        "http_status": 200,
                        "navigation_attempts": 1,
                        "snapshot": observed,
                    },
                    "control": {
                        "blocked": False,
                        "finished_at": (NOW - timedelta(seconds=80)).isoformat(),
                        "next_eligible_at": (NOW - timedelta(seconds=20)).isoformat(),
                        "interval_seconds": 60,
                        "http_status": 200,
                    },
                },
            )
        legacy = select_candidate_save(queue, DEFAULT_SCOPE, watch_root / MANIFEST_NAME)
        assert legacy is not None and legacy.watch_name == DEFAULT_SCOPE.watch_name
    return observations


def source_evidence(watch_root):
    with QueueStore(watch_root / "watch.sqlite", read_only=True) as queue:
        store = WatchStore(queue)
        result = []
        for scope in (DEFAULT_SCOPE, MONITOR_SCOPE):
            result.append(
                {
                    "state": store.get_state(scope),
                    "candidates": store.list_candidates(scope),
                    "scans": store.list_scans(scope),
                    "gaps": store.list_gaps(scope),
                    "details": CandidateDetailStore(queue).list_details(scope),
                }
            )
        assert queue.summary()["posts"] == queue.summary()["jobs"] == 0
        return result


def never_run(*_args, **_kwargs):
    pytest.fail("No native worker should be started")


class MonitorRunner:
    def __init__(self, clock, observations, *, status=200, retry_after=None):
        self.clock = clock
        self.observations = observations
        self.status = status
        self.retry_after = retry_after
        self.calls = []

    def __call__(self, work_root, browser, url, *, candidate_permit, navigation_observer):
        self.calls.append((work_root, browser, url, candidate_permit))
        assert candidate_permit.watch_name == MONITOR_SCOPE.watch_name
        assert navigation_observer.scope == MONITOR_SCOPE
        assert navigation_observer.manifest.name == MONITOR_MANIFEST_NAME
        navigation_observer.before()
        assert read_selection(navigation_observer.manifest)["control"]["in_flight"] is True
        self.clock.current += timedelta(seconds=15)
        navigation_observer.after(
            SimpleNamespace(status=self.status, header_value=lambda _key: self.retry_after), None
        )
        if self.status >= 400:
            return {
                "status": "manual_review",
                "browser_closed": True,
                "shared_pending_retained": False,
                "error_type": "NativeUIError",
            }
        fresh = deepcopy(self.observations[url])
        fresh["observed_at"] = self.clock.now().isoformat()
        approved = candidate_permit.authorize_snapshot(fresh)
        assert len(approved["images"]) == 1
        return {
            "status": "post_completed",
            "browser_closed": True,
            "shared_pending_retained": False,
            "last_stage": "complete",
            "job_counts": {"observed": 1, "completed": 1, "unresolved": 0},
            "saved_files": [],
        }


def test_monitor_uses_its_own_selection_and_preserves_trial_data_and_saved_files(tmp_path):
    watch_root = tmp_path / "watch"
    observations = seed_monitor(watch_root)
    legacy = (watch_root / MANIFEST_NAME).read_bytes()
    before = source_evidence(watch_root)
    old_output = tmp_path / "earlier-native"
    old_output.mkdir()
    existing = old_output / "001.png"
    existing.write_bytes(b"Preserve the earlier trial image")
    clock = FakeClock()
    runner = MonitorRunner(clock, observations)
    output = tmp_path / "monitor-native"

    report = runtime.run_candidate_save_trial(
        watch_root, output, scope=MONITOR_SCOPE, clock=clock, save_runner=runner
    )

    assert report["status"] == "candidate_save_completed", report
    assert report["image_count"] == 1
    assert report["job_counts"] == {"observed": 1, "completed": 1, "unresolved": 0}
    assert len(runner.calls) == 1 and runner.calls[0][0] == output
    selected = read_selection(watch_root / MONITOR_MANIFEST_NAME)
    assert selected["post_id"] in {"201", "202"}
    assert runner.calls[0][2].endswith("no=" + selected["post_id"])
    assert (watch_root / MANIFEST_NAME).read_bytes() == legacy
    assert existing.read_bytes() == b"Preserve the earlier trial image"
    assert source_evidence(watch_root) == before
    assert json.loads(Path(report["report_path"]).read_text()) == report


def test_monitor_repeat_is_pinned_and_respects_finish_based_service_wait(tmp_path):
    watch_root = tmp_path / "watch"
    observations = seed_monitor(watch_root)
    output = tmp_path / "native"
    clock = FakeClock()
    first = MonitorRunner(clock, observations)
    runtime.run_candidate_save_trial(
        watch_root, output, scope=MONITOR_SCOPE, clock=clock, save_runner=first
    )
    frozen = read_selection(watch_root / MONITOR_MANIFEST_NAME)
    waiting = runtime.run_candidate_save_trial(
        watch_root, output, scope=MONITOR_SCOPE, clock=clock, save_runner=never_run
    )
    assert waiting["status"] == "candidate_save_waiting"
    clock.current += timedelta(seconds=300)
    repeated = MonitorRunner(clock, observations)
    report = runtime.run_candidate_save_trial(
        watch_root, output, scope=MONITOR_SCOPE, clock=clock, save_runner=repeated
    )
    assert report["status"] == "candidate_save_completed"
    assert repeated.calls[0][2] == first.calls[0][2]
    current = read_selection(watch_root / MONITOR_MANIFEST_NAME)
    assert {k: v for k, v in current.items() if k != "control"} == {
        k: v for k, v in frozen.items() if k != "control"
    }


def test_monitor_does_not_fall_back_to_legacy_details_or_selection(tmp_path):
    watch_root = tmp_path / "watch"
    seed(watch_root)
    with QueueStore(watch_root / "watch.sqlite") as queue:
        select_candidate_save(queue, DEFAULT_SCOPE, watch_root / MANIFEST_NAME)
    before = (watch_root / MANIFEST_NAME).read_bytes()
    report = runtime.run_candidate_save_trial(
        watch_root,
        tmp_path / "native",
        scope=MONITOR_SCOPE,
        clock=FakeClock(),
        save_runner=never_run,
    )
    assert report["status"] == "candidate_save_no_candidate"
    assert not (watch_root / MONITOR_MANIFEST_NAME).exists()
    assert (watch_root / MANIFEST_NAME).read_bytes() == before


def test_monitor_save_takes_the_legacy_shared_scan_lease(tmp_path):
    watch_root = tmp_path / "watch"
    seed_monitor(watch_root)
    with watch_run_lock(watch_root / "watch.sqlite", DEFAULT_SCOPE):
        report = runtime.run_candidate_save_trial(
            watch_root,
            tmp_path / "native",
            scope=MONITOR_SCOPE,
            clock=FakeClock(),
            save_runner=never_run,
        )
    assert report["status"] == "candidate_save_busy"
    assert not (watch_root / MONITOR_MANIFEST_NAME).exists()


@pytest.mark.parametrize("status", [401, 403])
def test_monitor_native_block_stops_both_scopes_after_cooldown(tmp_path, status):
    watch_root = tmp_path / "watch"
    observations = seed_monitor(watch_root)
    clock = FakeClock()
    report = runtime.run_candidate_save_trial(
        watch_root,
        tmp_path / "native",
        scope=MONITOR_SCOPE,
        clock=clock,
        save_runner=MonitorRunner(clock, observations, status=status),
    )
    assert report["status"] == "candidate_save_failed"
    clock.current += timedelta(seconds=300)
    with QueueStore(watch_root / "watch.sqlite") as queue:
        for scope in (MONITOR_SCOPE, DEFAULT_SCOPE):
            assert _eligibility(queue, WatchStore(queue).get_state(scope), clock.now())[0] == (
                "blocked"
            )


@pytest.mark.parametrize("status", [429, 503])
def test_monitor_retry_after_is_persisted_and_does_not_mutate_legacy_control(tmp_path, status):
    watch_root = tmp_path / "watch"
    observations = seed_monitor(watch_root)
    legacy = (watch_root / MANIFEST_NAME).read_bytes()
    clock = FakeClock()
    report = runtime.run_candidate_save_trial(
        watch_root,
        tmp_path / "native",
        scope=MONITOR_SCOPE,
        clock=clock,
        save_runner=MonitorRunner(clock, observations, status=status, retry_after="300"),
    )
    assert report["status"] == "candidate_save_waiting"
    assert (watch_root / MANIFEST_NAME).read_bytes() == legacy
    control = read_selection(watch_root / MONITOR_MANIFEST_NAME)["control"]
    assert datetime.fromisoformat(control["next_eligible_at"]) == clock.now() + timedelta(
        seconds=300
    )
    with QueueStore(watch_root / "watch.sqlite") as queue:
        eligibility, due = _eligibility(
            queue, WatchStore(queue).get_state(DEFAULT_SCOPE), clock.now()
        )
    assert eligibility == "waiting" and due == clock.now() + timedelta(seconds=300)


def test_existing_legacy_block_prevents_monitor_selection_and_worker(tmp_path):
    watch_root = tmp_path / "watch"
    seed_monitor(watch_root)
    write_selection_control(watch_root / MANIFEST_NAME, {"blocked": True})
    report = runtime.run_candidate_save_trial(
        watch_root,
        tmp_path / "native",
        scope=MONITOR_SCOPE,
        clock=FakeClock(),
        save_runner=never_run,
    )
    assert report["reason"] == "access_block_requires_review"
    assert not (watch_root / MONITOR_MANIFEST_NAME).exists()


def test_monitor_worker_guard_keeps_pending_unknown_and_marker_untouched(tmp_path):
    watch_root = tmp_path / "watch"
    seed_monitor(watch_root)
    marker = tmp_path / "shared-pending.json"
    marker.write_bytes(b"Preserve an unrelated unresolved save marker")

    def guarded(*_args, **_kwargs):
        raise NativeUIError("An existing unresolved writer requires review")

    report = runtime.run_candidate_save_trial(
        watch_root,
        tmp_path / "native",
        scope=MONITOR_SCOPE,
        clock=FakeClock(),
        save_runner=guarded,
    )
    assert report["status"] == "candidate_save_failed"
    assert report["browser_closed"] is report["shared_pending_retained"] is None
    assert marker.read_bytes() == b"Preserve an unrelated unresolved save marker"
    assert read_selection(watch_root / MONITOR_MANIFEST_NAME)["control"] == {"blocked": False}


@pytest.mark.parametrize(
    "scope",
    [None, "monitor", WatchScope("other", "normal", "comic_new6", "ai", "search_subject_memo")],
)
def test_unreviewed_save_scope_is_rejected_before_creating_any_files(tmp_path, scope):
    with pytest.raises(QueueError):
        runtime.run_candidate_save_trial(
            tmp_path / "watch", tmp_path / "native", scope=scope, save_runner=never_run
        )
    assert list(tmp_path.iterdir()) == []
