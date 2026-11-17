"""Persist immutable monitor plans without retrying uncertain native attempts."""

import copy
import json
import sqlite3
from datetime import datetime, timedelta

import pytest
from test_candidate_save_policy import NOW, candidate_evidence

from image_monitor.candidate_policy import classify_candidate_detail
from image_monitor.candidate_save_policy import MONITOR_SCOPE, make_candidate_save_permit
from image_monitor.monitor_save_ledger import (
    APPLICATION_ID,
    LEDGER_NAME,
    MAX_JSON_BYTES,
    LedgerStore,
    batch_service_blocked,
    task_native_base,
    task_work_root,
)
from image_monitor.queue import QueueError, QueueStore


def frozen(post_id="103"):
    candidate, baseline, detail = candidate_evidence(image_count=1)
    candidate["watch_name"] = detail["watch_name"] = MONITOR_SCOPE[0]
    candidate["post_id"] = detail["post_id"] = post_id
    candidate["post_url"] = f"https://gall.dcinside.com/board/view/?id=comic_new6&no={post_id}"
    observation = detail["result"]["private_observation"]
    observation["url"] = candidate["post_url"]
    observation["snapshot"].update(post_id=post_id, post_url=candidate["post_url"])
    detail["result"]["classification"] = classify_candidate_detail(
        candidate, baseline, observation["snapshot"]
    )
    return candidate, detail, make_candidate_save_permit(candidate, baseline, detail)


@pytest.fixture
def roots(tmp_path):
    watch, legacy, batch = tmp_path / "watch", tmp_path / "legacy", tmp_path / "batch"
    watch.mkdir()
    with QueueStore(watch / "watch.sqlite"):
        pass
    old = watch / "monitor-save-selection.json"
    old.write_bytes(b"Existing immutable pilot selection, untouched")
    return {"watch_root": watch, "legacy_root": legacy, "batch_root": batch}


def open_ledger(roots, **options):
    return LedgerStore(roots["watch_root"] / LEDGER_NAME, **roots, **options)


def plan(store, post_id="103", *, kind="managed"):
    return store.plan(*frozen(post_id), output_kind=kind, now=NOW)


def test_new_ledger_is_separate_and_never_changes_discovery_or_previous_files(roots):
    watch = roots["watch_root"]
    source = (watch / "watch.sqlite").read_bytes()
    selection = (watch / "monitor-save-selection.json").read_bytes()
    with open_ledger(roots) as ledger:
        task = plan(ledger)
        assert task["status"] == "planned"
        assert task["native_session"] is None
        assert task["relative_root"] == f"tasks/{task['task_id']}"
        assert len(task["task_id"]) == 32 and task["post_id"] == "103"
        assert task["task_id"] not in task["post_url"]
        assert task["control"] == {"blocked": False}
        assert (watch / "watch.sqlite").read_bytes() == source
        assert (watch / "monitor-save-selection.json").read_bytes() == selection
        assert not roots["legacy_root"].exists() and not roots["batch_root"].exists()
    with open_ledger(roots, read_only=True) as ledger:
        assert ledger.list_tasks() == [task]
        assert ledger.get_for_post("103") == task


def test_native_session_and_attempt_state_persist_before_runner_can_start(roots):
    with open_ledger(roots) as first, open_ledger(roots) as observer:
        task = plan(first)
        started = first.start(task["task_id"], NOW + timedelta(seconds=1), native_session=7)
        assert observer.get_task(task["task_id"]) == started
        assert started["native_session"] == 7
        assert task_native_base(started, roots["batch_root"], roots["legacy_root"]) == (
            roots["batch_root"] / "tasks" / task["task_id"] / "session-7"
        )
    with open_ledger(roots) as restarted:
        with pytest.raises(QueueError):
            restarted.start(task["task_id"], NOW + timedelta(seconds=2), native_session=9)
        assert restarted.get_task(task["task_id"]) == started


def test_uncertain_attempt_blocks_other_plans_until_completed_only_reconciliation(roots):
    with open_ledger(roots) as ledger:
        first, second = plan(ledger), plan(ledger, "104")
        ledger.start(first["task_id"], NOW, native_session=1)
        with pytest.raises(QueueError, match="reconciliation"):
            ledger.start(second["task_id"], NOW, native_session=1)
        failed = ledger.finish(
            first["task_id"], status="needs_review", result={"reason": "interrupted"}, now=NOW
        )
        with pytest.raises(QueueError):
            ledger.start(first["task_id"], NOW, native_session=1)
        with pytest.raises(QueueError, match="reconciliation"):
            ledger.start(second["task_id"], NOW, native_session=1)
        completed = ledger.reconcile_completed(
            first["task_id"], result={"files_verified": 1}, now=NOW + timedelta(seconds=10)
        )
        assert failed["status"] == "needs_review" and completed["status"] == "completed"
        assert completed["native_session"] == 1
        assert ledger.start(second["task_id"], NOW + timedelta(seconds=10), native_session=2)


def test_completed_tasks_cannot_be_started_or_reconciled_again(roots):
    with open_ledger(roots) as ledger:
        task = plan(ledger)
        ledger.start(task["task_id"], NOW, native_session=0)
        done = ledger.finish(task["task_id"], status="completed", result={"verified": 1}, now=NOW)
        for operation in (
            lambda: ledger.start(task["task_id"], NOW, native_session=0),
            lambda: ledger.finish(task["task_id"], status="completed", result={}, now=NOW),
            lambda: ledger.reconcile_completed(task["task_id"], result={}, now=NOW),
        ):
            with pytest.raises(QueueError):
                operation()
        assert ledger.get_task(task["task_id"]) == done


def test_unavailable_task_is_terminal_without_blocking_the_next_candidate(roots):
    with open_ledger(roots) as ledger:
        first, second = plan(ledger), plan(ledger, "104")
        ledger.start(first["task_id"], NOW, native_session=1)
        unavailable = ledger.finish(
            first["task_id"], status="unavailable", result={"http_status": 404}, now=NOW
        )
        assert unavailable["status"] == "unavailable"
        assert ledger.start(second["task_id"], NOW, native_session=1)["status"] == "started"
        with pytest.raises(QueueError):
            ledger.start(first["task_id"], NOW, native_session=1)
        with pytest.raises(QueueError):
            ledger.reconcile_completed(first["task_id"], result={}, now=NOW)


def test_legacy_adoption_uses_bound_old_root_and_preserves_one_immutable_task(roots):
    with open_ledger(roots) as ledger:
        task = plan(ledger, kind="legacy")
        assert task["relative_root"] is None
        assert (
            task_work_root(task, roots["batch_root"], roots["legacy_root"]) == roots["legacy_root"]
        )
        assert plan(ledger, kind="legacy") == task
        with pytest.raises(QueueError, match="binding changed"):
            plan(ledger, kind="managed")
        ledger.start(task["task_id"], NOW, native_session=17)
        assert (
            task_native_base(
                ledger.get_task(task["task_id"]),
                **{"batch_root": roots["batch_root"], "legacy_root": roots["legacy_root"]},
            )
            == roots["legacy_root"] / "session-17"
        )


def test_atomic_adoption_failure_rolls_back_and_retry_never_exposes_a_runnable_legacy_gap(
    roots, monkeypatch
):
    with open_ledger(roots) as ledger, open_ledger(roots) as observer:
        original = ledger.get_task

        def interrupted_after_insert(task_id):
            assert original(task_id)["status"] == "completed"
            assert observer.get_for_post("103") is None
            raise KeyboardInterrupt

        monkeypatch.setattr(ledger, "get_task", interrupted_after_insert)
        with pytest.raises(KeyboardInterrupt):
            ledger.adopt_completed(
                *frozen(), native_session=3, result={"files_verified": 1}, now=NOW
            )
        assert observer.list_tasks() == []
        monkeypatch.setattr(ledger, "get_task", original)
        adopted = ledger.adopt_completed(
            *frozen(), native_session=3, result={"files_verified": 1}, now=NOW
        )
        assert observer.get_for_post("103") == adopted
        assert adopted["status"] == "completed" and adopted["output_kind"] == "legacy"
        assert adopted["created_at"] == adopted["started_at"] == adopted["finished_at"]
        assert task_native_base(adopted, roots["batch_root"], roots["legacy_root"]) == (
            roots["legacy_root"] / "session-3"
        )


def test_atomic_adoption_is_repeat_safe_and_only_promotes_unattempted_legacy_plans(roots):
    with open_ledger(roots) as ledger:
        planned = plan(ledger, kind="legacy")
        adopted = ledger.adopt_completed(
            *frozen(), native_session=3, result={"files_verified": 1}, now=NOW
        )
        assert adopted["task_id"] == planned["task_id"]
        assert (
            ledger.adopt_completed(
                *frozen(), native_session=3, result={"files_verified": 1}, now=NOW
            )
            == adopted
        )
        with pytest.raises(QueueError, match="session changed"):
            ledger.adopt_completed(*frozen(), native_session=4, result={}, now=NOW)
        other = plan(ledger, "104", kind="legacy")
        ledger.start(other["task_id"], NOW, native_session=3)
        with pytest.raises(QueueError, match="reconciliation"):
            ledger.adopt_completed(*frozen("104"), native_session=3, result={}, now=NOW)
        assert ledger.get_task(other["task_id"])["status"] == "started"


def test_plan_reuses_frozen_identity_after_harmless_list_refresh_but_refuses_new_detail(roots):
    candidate, detail, permit = frozen()
    with open_ledger(roots) as ledger:
        initial = ledger.plan(candidate, detail, permit, now=NOW)
        candidate.update(title="Updated list title", last_seen_at=NOW.isoformat())
        assert ledger.plan(candidate, detail, permit, now=NOW) == initial
        changed = copy.deepcopy(detail)
        changed["attempt_id"] = "d" * 32
        baseline = {"observed_at": detail["baseline_observed_at"], "mode": "new"}
        other = make_candidate_save_permit(candidate, baseline, changed)
        with pytest.raises(QueueError, match="binding changed"):
            ledger.plan(candidate, changed, other, now=NOW)
        assert ledger.get_task(initial["task_id"]) == initial


@pytest.mark.parametrize("field", ["watch_name", "keyword", "gallery_id", "search_type"])
def test_planning_rejects_mixed_or_changed_scope_before_creating_task(roots, field):
    candidate, detail, permit = frozen()
    candidate[field] = "Unreviewed scope"
    with open_ledger(roots) as ledger:
        with pytest.raises(QueueError):
            ledger.plan(candidate, detail, permit, now=NOW)
        assert ledger.list_tasks() == []


@pytest.mark.parametrize("session", [None, True, -1, 2**32, "1"])
def test_session_identity_is_validated_before_attempt_state_changes(roots, session):
    with open_ledger(roots) as ledger:
        task = plan(ledger)
        with pytest.raises(QueueError):
            ledger.start(task["task_id"], NOW, native_session=session)
        assert ledger.get_task(task["task_id"]) == task


@pytest.mark.parametrize("operation", ["start", "finish", "reconcile"])
def test_aware_timing_and_monotonic_attempt_times_are_required(roots, operation):
    with open_ledger(roots) as ledger:
        task = plan(ledger)
        if operation != "start":
            ledger.start(task["task_id"], NOW, native_session=1)
        bad_times = [datetime(2026, 1, 1), NOW - timedelta(seconds=1)]
        for stamp in bad_times:
            with pytest.raises(QueueError):
                if operation == "start":
                    ledger.start(task["task_id"], stamp, native_session=1)
                elif operation == "finish":
                    ledger.finish(task["task_id"], status="completed", result={}, now=stamp)
                else:
                    ledger.reconcile_completed(task["task_id"], result={}, now=stamp)


def test_global_block_and_inflight_state_survive_reconciliation_and_cannot_be_reset(roots):
    watch_database = roots["watch_root"] / "watch.sqlite"
    assert batch_service_blocked(watch_database) is False
    with open_ledger(roots) as ledger:
        task = plan(ledger)
        ledger.start(task["task_id"], NOW, native_session=1)
        ledger.update_control(task["task_id"], {"blocked": False, "in_flight": True})
        assert batch_service_blocked(watch_database) is True
        ledger.update_control(task["task_id"], {"blocked": False, "in_flight": False})
        assert batch_service_blocked(watch_database) is False
        ledger.update_control(
            task["task_id"], {"blocked": True, "in_flight": False, "http_status": 403}
        )
        ledger.reconcile_completed(task["task_id"], result={"verified": 1}, now=NOW)
        assert batch_service_blocked(watch_database) is True
        with pytest.raises(QueueError, match="access block"):
            ledger.update_control(task["task_id"], {"blocked": False})
        second = plan(ledger, "104")
        with pytest.raises(QueueError, match="access block"):
            ledger.start(second["task_id"], NOW, native_session=1)


@pytest.mark.parametrize(
    "control",
    [
        {"blocked": 1},
        {"blocked": False, "in_flight": 1},
        {"blocked": False, "http_status": True},
        {"blocked": False, "http_status": 600},
        {"blocked": False, "next_eligible_at": "yesterday"},
        {"blocked": False, "interval_seconds": 0},
        {"blocked": False, "extra": "x" * MAX_JSON_BYTES},
        {"blocked": False, "extra": float("nan")},
    ],
)
def test_invalid_control_never_changes_durable_evidence(roots, control):
    with open_ledger(roots) as ledger:
        task = plan(ledger)
        with pytest.raises(QueueError):
            ledger.update_control(task["task_id"], control)
        assert ledger.get_task(task["task_id"]) == task


def test_readonly_open_and_missing_existing_only_open_never_create_files(roots):
    path = roots["watch_root"] / LEDGER_NAME
    for options in ({"read_only": True}, {"create": False}):
        with pytest.raises(QueueError):
            open_ledger(roots, **options)
        assert not path.exists()
    with open_ledger(roots) as ledger:
        task = plan(ledger)
    with open_ledger(roots, read_only=True) as ledger:
        assert ledger.get_task(task["task_id"]) == task
        for operation in (
            lambda: ledger.plan(*frozen("104"), now=NOW),
            lambda: ledger.start(task["task_id"], NOW, native_session=1),
            lambda: ledger.update_control(task["task_id"], {"blocked": True}),
        ):
            with pytest.raises(QueueError, match="read-only"):
                operation()


@pytest.mark.parametrize("change", ["app", "version", "extra_table", "scope", "root", "control"])
def test_unknown_or_corrupted_existing_ledger_is_preserved_and_blocks_navigation(roots, change):
    path = roots["watch_root"] / LEDGER_NAME
    with open_ledger(roots) as ledger:
        task = plan(ledger)
    with sqlite3.connect(path) as connection:
        if change == "app":
            connection.execute(f"PRAGMA application_id={APPLICATION_ID + 1}")
        elif change == "version":
            connection.execute("PRAGMA user_version=99")
        elif change == "extra_table":
            connection.execute("CREATE TABLE foreign_data(value)")
        elif change == "scope":
            connection.execute("UPDATE ledger_meta SET scope_json='[]'")
        elif change == "root":
            connection.execute(
                "UPDATE ledger_meta SET watch_root=?", (str(path.parent / "foreign"),)
            )
        else:
            connection.execute(
                "UPDATE save_tasks SET control_json=? WHERE task_id=?",
                (json.dumps({"blocked": "no"}), task["task_id"]),
            )
    before = path.read_bytes()
    with pytest.raises(QueueError):
        open_ledger(roots)
    with pytest.raises(QueueError):
        batch_service_blocked(roots["watch_root"] / "watch.sqlite")
    assert path.read_bytes() == before


def test_foreign_empty_database_and_changed_bound_roots_are_never_initialized_or_adopted(roots):
    path = roots["watch_root"] / LEDGER_NAME
    path.touch()
    with pytest.raises(QueueError, match="schema"):
        open_ledger(roots)
    assert path.read_bytes() == b""
    path.unlink()
    with open_ledger(roots):
        pass
    before = path.read_bytes()
    other = roots | {"batch_root": roots["batch_root"].with_name("changed-batch")}
    with pytest.raises(QueueError, match="roots"):
        open_ledger(other)
    assert path.read_bytes() == before


@pytest.mark.parametrize("relative", ["../foreign", "tasks/foreign", "/absolute", "tasks\\foreign"])
def test_output_paths_only_derive_from_exact_task_uuid_and_frozen_session(roots, relative):
    with open_ledger(roots) as ledger:
        task = plan(ledger)
    with pytest.raises(QueueError):
        task_work_root(
            task | {"relative_root": relative}, roots["batch_root"], roots["legacy_root"]
        )
    with pytest.raises(QueueError):
        task_native_base(task, roots["batch_root"], roots["legacy_root"])


def test_two_connections_plan_one_identity_and_only_one_start_commits(roots):
    with open_ledger(roots) as first, open_ledger(roots) as second:
        task = plan(first)
        assert plan(second) == task
        first.start(task["task_id"], NOW, native_session=1)
        with pytest.raises(QueueError):
            second.start(task["task_id"], NOW, native_session=2)
        assert second.get_task(task["task_id"])["native_session"] == 1
