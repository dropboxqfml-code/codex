"""The explicit collection handoff owns one exact post across cooldown races."""

from datetime import timedelta

import pytest
from test_monitor_batch_runtime import Runner, ledger, prepare_legacy, run
from test_monitor_batch_runtime import data as data
from test_monitor_save_ledger import plan

from image_monitor import monitor_batch_runtime as batch
from image_monitor import monitor_collect as collect
from image_monitor.candidate_save_selection import (
    MANIFEST_NAME,
    MONITOR_MANIFEST_NAME,
    select_candidate_save,
)
from image_monitor.queue import QueueError, QueueStore
from image_monitor.watch_lock import WatchRunBusy, watch_run_lock
from image_monitor.watch_runtime import DEFAULT_SCOPE, SERVICE_SCOPE


def targets(data):
    with QueueStore(data.watch / "watch.sqlite", read_only=True) as queue:
        choices = []
        for detail in batch._details(queue):
            candidate, permit = batch._eligible_permit(queue, detail)
            choices.append(
                {
                    "post_id": candidate["post_id"],
                    "attempt_id": detail["attempt_id"],
                    "fingerprint": permit.fingerprint,
                }
            )
        return choices


def ready(target):
    return {
        "status": "ready",
        "reason": "save_ready",
        "browser_closed": True,
        "new_details_checked": 0,
        "next_eligible_at": None,
        "eligible_body_images": 1,
    }, target


def forbidden(*args, **kwargs):
    pytest.fail("Unexpected native worker")


@pytest.mark.parametrize(
    ("expected", "reported", "listed", "status"),
    [
        (10, 10, 10, "saved"),
        (10, 10, 4, "review"),
        (10, 11, 10, "review"),
        (11, 11, 11, "review"),
        (1, True, 1, "review"),
    ],
)
def test_a_complete_monitor_post_requires_all_expected_file_receipts(
    expected, reported, listed, status
):
    report = {
        "status": "monitor_batch_completed",
        "reason": None,
        "last_stage": "complete",
        "browser_closed": True,
        "shared_pending_retained": False,
        "tasks_started": 1,
        "tasks_completed": 1,
        "saved_file_count": reported,
        "saved_files": [{"saved_filename": f"{slot:03d}.png"} for slot in range(1, listed + 1)],
    }
    assert collect._save_status(report, expected) == "monitor_collect_" + status


@pytest.mark.parametrize(
    ("scope", "manifest", "posts"),
    [
        (DEFAULT_SCOPE, MANIFEST_NAME, ("102",)),
        (batch.MONITOR_SCOPE, MONITOR_MANIFEST_NAME, ("201", "202")),
    ],
)
def test_a_new_legacy_selection_skips_posts_owned_by_monitor_collection(
    data, scope, manifest, posts
):
    # The fixture normally represents a previous trial selection. Start this
    # case immediately before that first selection in its temporary directory.
    (data.watch / manifest).unlink(missing_ok=True)
    with ledger(data, readonly=False) as store:
        for post in posts:
            plan(store, post)
    with QueueStore(data.watch / "watch.sqlite") as queue:
        assert select_candidate_save(queue, scope, data.watch / manifest) is None
    assert not (data.watch / manifest).exists()


def test_conflicting_existing_trial_manifest_is_preserved_and_cannot_start_a_save(data):
    manifest = data.watch / MANIFEST_NAME
    original = manifest.read_bytes()
    with ledger(data, readonly=False) as store:
        plan(store, "102")
    with (
        QueueStore(data.watch / "watch.sqlite") as queue,
        pytest.raises(QueueError, match="claimed"),
    ):
        select_candidate_save(queue, DEFAULT_SCOPE, manifest)
    assert manifest.read_bytes() == original


def test_adopted_original_legacy_manifest_can_still_verify_its_same_post(data):
    permit = prepare_legacy(data)
    assert run(data)["adopted_count"] == 1
    with QueueStore(data.watch / "watch.sqlite") as queue:
        selected = select_candidate_save(
            queue, batch.MONITOR_SCOPE, data.watch / MONITOR_MANIFEST_NAME
        )
    assert selected.fingerprint == permit.fingerprint


@pytest.mark.parametrize("field", ["post_id", "attempt_id", "fingerprint"])
def test_mixed_monitor_evidence_is_rejected_before_planning(data, field):
    first, second = targets(data)
    first[field] = second[field]
    outcome = run(data, forbidden, max_tasks=1, monitor_handoff=first)
    assert outcome["status"] == "monitor_batch_manual_review"
    assert outcome["tasks_started"] == outcome["tasks_planned"] == 0
    assert not (data.watch / batch.LEDGER_NAME).exists()


def test_a_save_claimed_during_the_wait_does_not_retarget_another_planned_post(data, monkeypatch):
    first, other = targets(data)
    database = data.watch / "watch.sqlite"

    def select(*_roots, **_options):
        with QueueStore(database) as queue:
            queue.defer_service(SERVICE_SCOPE, data.clock.now() + timedelta(seconds=17))
        return ready(first)

    ordinary_save = Runner(data)
    advance = data.clock.wait

    def wait(seconds):
        assert seconds == 17
        advance(seconds)
        with (
            pytest.raises(WatchRunBusy),
            watch_run_lock(database, batch.MONITOR_SCOPE, purpose="monitor"),
        ):
            pytest.fail("Collector released the app lock before settling its selected task")
        assert run(data, ordinary_save, max_tasks=1)["tasks_completed"] == 1

    data.clock.wait = wait
    monkeypatch.setattr(collect, "search_monitor_candidates", select)
    result = collect.run_monitor_collect(
        data.watch, data.legacy, data.batch, clock=data.clock, save_runner=forbidden
    )
    assert result["status"] == "monitor_collect_already_handled", result
    assert result["native_save_tasks_started"] == result["files_verified"] == 0
    assert result["browser_closed"] and collect.monitor_collect_exit_code(result) == 0
    assert len(ordinary_save.calls) == 1
    with ledger(data) as store:
        assert store.get_for_post(first["post_id"])["status"] == "completed"
        assert store.get_for_post(other["post_id"])["status"] == "planned"


def test_extended_wait_after_selection_returns_without_native_input(data, monkeypatch):
    selected, _ = targets(data)
    due = data.clock.now() + timedelta(seconds=300)
    with QueueStore(data.watch / "watch.sqlite") as queue:
        queue.defer_service(SERVICE_SCOPE, due)
    monkeypatch.setattr(collect, "search_monitor_candidates", lambda *_a, **_k: ready(selected))
    result = collect.run_monitor_collect(
        data.watch, data.legacy, data.batch, clock=data.clock, save_runner=forbidden
    )
    assert result["status"] == "monitor_collect_waiting" and not data.clock.waits
    assert result["next_eligible_at"] == collect._stamp(due)
    assert result["native_save_tasks_started"] == result["worker_images_completed"] == 0
    assert result["saved_files"] == []


def test_missing_owned_browser_identity_cannot_start_automatic_navigation(data):
    first, _ = targets(data)

    def worker(*_args, navigation_observer, automatic_start, **_options):
        assert automatic_start
        navigation_observer.before()
        pytest.fail("An automatic worker needs its owned browser identity before navigation")

    out = run(data, worker, max_tasks=1, monitor_handoff=first)
    assert out["status"] == "monitor_batch_manual_review" and out["tasks_needing_review"] == 1
    assert out["tasks_started"] == 1 and out["worker_images_completed"] is None
    with ledger(data) as store:
        assert store.get_for_post(first["post_id"])["control"] == {"blocked": False}


def test_worker_progress_without_full_post_verification_is_reported_separately(data, monkeypatch):
    first, _ = targets(data)
    monkeypatch.setattr(collect, "search_monitor_candidates", lambda *_a, **_k: ready(first))

    def interrupted(*_args, **_options):
        return {
            "status": "manual_review",
            "browser_closed": True,
            "shared_pending_retained": True,
            "job_counts": {"observed": 1, "completed": 1, "unresolved": 0},
        }

    report = collect.run_monitor_collect(
        data.watch, data.legacy, data.batch, clock=data.clock, save_runner=interrupted
    )
    assert report["status"] == "monitor_collect_review"
    assert report["worker_images_completed"] == 1 and report["files_verified"] == 0
    assert report["saved_files"] == [] and report["save"]["tasks_needing_review"] == 1
    repeated = run(data, forbidden, max_tasks=1, monitor_handoff=first)
    assert repeated["tasks_started"] == 0 and repeated["tasks_needing_review"] == 1
