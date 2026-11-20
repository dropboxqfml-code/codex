"""Revalidate the exact previous run before a one-click retry can issue native input."""

import json
import uuid
from contextlib import nullcontext
from datetime import timedelta
from types import SimpleNamespace

import pytest
from test_monitor_batch_runtime import data as data
from test_monitor_batch_runtime import ledger, run
from test_monitor_collect import forbidden, ready, targets
from test_monitor_setup_retry_evidence import evidence as evidence

from image_monitor import monitor_auto_selection as selection
from image_monitor import monitor_batch_runtime as batch
from image_monitor import monitor_collect as collect
from image_monitor import monitor_operations
from image_monitor.native_state import PendingSave
from image_monitor.queue import QueueStore
from image_monitor.watch_runtime import SERVICE_SCOPE


def interrupted_task(data):
    with (
        QueueStore(data.watch / "watch.sqlite", read_only=True) as queue,
        ledger(data, readonly=False) as store,
    ):
        for detail in batch._details(queue):
            candidate, permit = batch._eligible_permit(queue, detail)
            store.plan(candidate, detail, permit, now=data.clock.now())
        first = store.get_for_post(targets(data)[0]["post_id"])
        store.start(first["task_id"], data.clock.now(), native_session=1)
        return store.finish(
            first["task_id"],
            status="needs_review",
            result={"worker_status": "manual_review", "error_type": "BrowserCompletionError"},
            now=data.clock.now(),
        )


@pytest.mark.parametrize("change", ["task", "post", "run"])
def test_mixing_another_binding_or_prior_native_run_cannot_rearm_a_task(data, monkeypatch, change):
    original = interrupted_task(data)
    first, second = targets(data)
    with ledger(data) as store:
        before = store.list_tasks()
    target = first | {"retry_task_id": original["task_id"], "prior_run": "a" * 32}
    if change == "task":
        target["retry_task_id"] = next(
            t["task_id"] for t in before if t["post_id"] != original["post_id"]
        )
    elif change == "post":
        target.update(second)
    verified = []

    def verify(store, task, permit):
        verified.append(task["task_id"])
        return "b" * 32, None

    monkeypatch.setattr(batch, "verify_setup_retry", verify)
    result = run(data, forbidden, max_tasks=1, monitor_handoff=target)
    assert result["status"] == "monitor_batch_manual_review"
    assert result["tasks_started"] == result["tasks_planned"] == 0
    assert result["setup_retry_started"] is False
    assert verified == ([original["task_id"]] if change == "run" else [])
    with ledger(data) as store:
        assert store.list_tasks() == before


def test_existing_server_wait_does_not_consume_the_one_retry(data, monkeypatch):
    old = interrupted_task(data)
    first, _ = targets(data)
    target = first | {"retry_task_id": old["task_id"], "prior_run": "a" * 32}
    deadline = data.clock.now() + timedelta(seconds=180)
    with QueueStore(data.watch / "watch.sqlite") as queue:
        queue.defer_service(SERVICE_SCOPE, deadline)
    monkeypatch.setattr(collect, "search_monitor_candidates", lambda *_a, **_kw: ready(target))
    monkeypatch.setattr(batch, "verify_setup_retry", forbidden)
    result = collect.run_monitor_collect(
        data.watch, data.legacy, data.batch, clock=data.clock, save_runner=forbidden
    )
    assert result["status"] == "monitor_collect_waiting" and not data.clock.waits
    assert result["setup_retry_started"] is False and result["native_save_tasks_started"] == 0
    assert result["next_eligible_at"] == collect._stamp(deadline)
    with ledger(data) as store:
        assert store.get_task(old["task_id"]) == old


@pytest.mark.parametrize("evidence", ["foreground"], indirect=True)
def test_foreground_retry_exhaustion_reports_cause_on_this_and_next_invocation(
    evidence, monkeypatch
):
    store, task, _permit, base, previous, _, data = evidence
    previous_bytes = previous.read_bytes()
    monkeypatch.setattr(selection, "NativeSaveLock", nullcontext)
    monkeypatch.setattr(monitor_operations, "NativeSaveLock", nullcontext)
    monkeypatch.setattr(monitor_operations, "shared_state_path", lambda: data.marker)
    monkeypatch.setattr(monitor_operations, "session_id", lambda: 1)

    def fail_again(_work_root, _browser, _url, *, navigation_observer, **_options):
        directory = base / "runs" / uuid.uuid4().hex
        (directory / "browser-profile").mkdir(parents=True)
        state = PendingSave(data.marker)
        pending = state.begin(directory)
        state.update_browser(pending, 2345, 67.0)
        navigation_observer.before()
        navigation_observer.after(SimpleNamespace(status=200), None)
        state.finish(pending)
        return {
            "status": "manual_review",
            "last_stage": "automatic_foreground_check",
            "error_type": "NativeFocusError",
            "browser_closed": True,
            "shared_pending_retained": False,
            "focus_at_failure": {
                "target_exists": True,
                "target_foreground": False,
                "belongs_to_target": False,
                "foreground_hwnd": None,
                "foreground_pid": 298765,
                "foreground_class": "PRIVATE_WINDOW_CLASS",
            },
        }

    roots = data.watch, data.legacy, data.batch
    current = collect.run_monitor_collect(*roots, clock=data.clock, save_runner=fail_again)
    assert current["status"] == "monitor_collect_review", current
    assert current["reason"] == "automatic_foreground_retry_exhausted", current
    assert current["setup_retry_started"] and current["native_save_tasks_started"] == 1
    assert current["search"]["reason"] == "automatic_foreground_retry_ready"
    assert current["search"]["previous_failure_reason"] == "automatic_foreground_unconfirmed"
    assert "previous_completion_setup_reason" not in current["search"]
    assert current["save"]["previous_failure_reason"] == "automatic_foreground_unconfirmed"
    assert current["save"]["focus_at_failure"] == {
        "target_exists": True,
        "target_foreground": False,
        "belongs_to_target": False,
        "foreground_identified": False,
    }
    assert "PRIVATE_WINDOW_CLASS" not in json.dumps(current) and "298765" not in json.dumps(current)
    consumed = store.get_task(task["task_id"])
    assert consumed["control"]["setup_retry"]["prior_run"] == previous.parent.name
    later = collect.run_monitor_collect(
        *roots, clock=data.clock, save_runner=forbidden, detail_runner=forbidden
    )
    assert later["reason"] == current["reason"] and not later["setup_retry_started"], later
    assert later["save"] is None and later["native_save_tasks_started"] == 0
    assert store.get_task(task["task_id"]) == consumed and previous.read_bytes() == previous_bytes


@pytest.mark.parametrize(
    ("snapshot", "expected"),
    [
        (
            {"foreground_hwnd": 87333, "target_exists": True},
            {"foreground_identified": True, "target_exists": True},
        ),
        ({"target_exists": False, "target_foreground": "private"}, {"target_exists": False}),
        ({"foreground_class": "private", "foreground_hwnd": True}, None),
    ],
)
def test_public_initial_focus_contains_only_observed_booleans(snapshot, expected):
    shutdown = {"process_exit_confirmed": True}
    result = batch.share_batch_report(
        {
            "mode": "bounded_monitor_automatic_save",
            "worker_last_stage": "automatic_foreground_check",
            "focus_at_failure": snapshot,
            "shutdown": shutdown,
            "previous_failure_reason": "untrusted private text",
        }
    )
    assert result.get("focus_at_failure") == expected and result["shutdown"] == shutdown
    assert "previous_failure_reason" not in result and "private" not in json.dumps(result)
