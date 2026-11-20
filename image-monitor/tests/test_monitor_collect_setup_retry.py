"""Revalidate the exact previous run before a one-click retry can issue native input."""

from datetime import timedelta

import pytest
from test_monitor_batch_runtime import data as data
from test_monitor_batch_runtime import ledger, run
from test_monitor_collect import forbidden, ready, targets

from image_monitor import monitor_batch_runtime as batch
from image_monitor import monitor_collect as collect
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
