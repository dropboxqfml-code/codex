"""Check that an explicit, stopped dashboard request owns just one native save."""

import json
import threading
from datetime import timedelta

import pytest
from test_monitor_controller import NOW, Clock
from test_monitor_operations_controller import controllers as controllers
from test_monitor_operations_controller import create, operations_snapshot
from test_saved_catalog_controller import FIRST

from image_monitor.queue import QueueError


def save_ready(**changes):
    return operations_snapshot(count=0) | {"reason": "save_ready", "save_ready": 1} | changes


def completion():
    return {
        "status": "monitor_batch_completed",
        "reason": None,
        "tasks_started": 1,
        "tasks_completed": 1,
        "files_verified": 2,
        "browser_closed": True,
    }


def refresh(controller):
    controller.refresh_operations()
    assert controller.wait_stopped(3)
    return controller.status()["operations_can_save"]


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "busy"},
        {"status": "needs_review"},
        {"reason": "service_access_blocked"},
        {"reason": "navigation_in_progress"},
        {"reason": "pending_save_requires_review"},
        {"reason": "candidate_detail_requires_review"},
        {"reason": "service_cooldown"},
        {"save_active": 1},
        {"save_needs_review": 1},
        {"save_ready": 0},
        {"error_type": "QueueError"},
    ],
)
def test_save_rejects_unready_snapshot(tmp_path, controllers, changes):
    value = create(
        controllers, tmp_path / "watch", operations_loader=lambda *_, **__: save_ready(**changes)
    )
    assert not refresh(value)
    with pytest.raises(QueueError):
        value.save_one()
    assert value.status()["operations_save_status"] is None


def test_service_deadline_opens_only_the_advisory_gate_then_fresh_recheck_refuses(
    tmp_path, controllers
):
    clock = Clock()
    due = NOW + timedelta(minutes=2)
    calls = []

    def load(*_args, **_kwargs):
        calls.append("load")
        return save_ready(reason="service_cooldown", wait_until=due.isoformat())

    value = create(
        controllers,
        tmp_path / "watch",
        operations_loader=load,
        save_runner=lambda *_args, **_kwargs: calls.append("child"),
        clock=clock,
    )
    assert not refresh(value)
    with pytest.raises(QueueError):
        value.save_one()
    clock.advance(120)
    assert value.status()["operations_can_save"] is True
    due += timedelta(minutes=1)
    value.save_one()
    assert value.wait_stopped(3)
    status = value.status()
    assert status["operations_save_status"] == "save_not_started"
    assert status["operations_save_reason"] == "eligibility_changed"
    assert status["operations_remaining_seconds"] == 60
    assert status["operations_can_save"] is False
    assert calls == ["load", "load"]


@pytest.mark.parametrize("late_stop", [False, True])
def test_one_request_serializes_worker_and_preserves_result_even_on_late_stop(
    tmp_path, controllers, late_stop
):
    entered, release = threading.Event(), threading.Event()
    root = tmp_path / "watch"
    calls = []

    def load(*_args, **_kwargs):
        calls.append("load")
        if "child" in calls:
            return save_ready(reason="save_completed", save_ready=0, save_completed=1)
        return save_ready(reason="save_planned", save_planned=1, save_ready=0)

    def child(watch, legacy, batch, *, should_stop):
        calls.append("child")
        assert (watch, legacy, batch) == (root, tmp_path / "legacy", tmp_path / "batch")
        assert not should_stop()
        entered.set()
        assert release.wait(3)
        assert should_stop() is late_stop
        return completion()

    value = create(controllers, root, operations_loader=load, save_runner=child)
    with pytest.raises(QueueError):
        value.save_one()
    assert refresh(value)
    value.refresh_saved()
    assert value.wait_stopped(3)
    assert value.saved_image(FIRST) is not None
    value.save_one()
    try:
        assert entered.wait(3)
        assert value.status()["phase"] == "saving_candidate"
        assert value.status()["operations_can_save"] is False
        assert value.saved_image(FIRST) is None
        with pytest.raises(QueueError):
            value.save_one()
        with pytest.raises(QueueError):
            value.refresh_operations()
        if late_stop:
            value.stop()
        value.start()
        assert value.status()["task_kind"] == "save"
    finally:
        release.set()
    assert value.wait_stopped(3)
    status = value.status()
    assert status["phase"] == "stopped"
    assert status["operations_save_status"] == "monitor_batch_completed"
    assert status["operations_save_tasks_started"] == status["operations_save_tasks_completed"] == 1
    assert status["operations_save_files_verified"] == 2
    assert status["operations_save_browser_closed"] is True
    if late_stop:
        assert calls == ["load", "load", "child"]
        assert status["operations_status"] == status["saved_status"] == "cancelled"
    else:
        assert calls == ["load", "load", "child", "load"]
        assert status["operations_counts"]["save_completed"] == 1
        assert value.saved_image(FIRST) is not None
    assert status["operations_can_save"] is False


def test_stop_during_save_preflight_never_calls_child(tmp_path, controllers):
    entered, release = threading.Event(), threading.Event()
    calls = []

    def load(*_args, **_kwargs):
        if calls:
            entered.set()
            assert release.wait(3)
        calls.append("load")
        return save_ready()

    value = create(
        controllers,
        tmp_path / "watch",
        operations_loader=load,
        save_runner=lambda *_, **__: calls.append("child"),
    )
    assert refresh(value)
    value.save_one()
    try:
        assert entered.wait(3)
        value.stop()
    finally:
        release.set()
    assert value.wait_stopped(3)
    assert calls == ["load", "load"]
    assert value.status()["operations_save_status"] == "monitor_batch_cancelled"


@pytest.mark.parametrize("bad", ["adapter_failure", "malformed", "unconfirmed_close"])
def test_unknown_native_outcome_blocks_more_saves_until_review(tmp_path, controllers, bad):
    def child(*_args, **_kwargs):
        if bad == "adapter_failure":
            raise OSError("C:/private")
        if bad == "malformed":
            return completion() | {"secret": "C:/private"}
        return {
            "status": "monitor_batch_manual_review",
            "reason": "native_batch_task_requires_review",
            "tasks_started": 1,
            "tasks_completed": 0,
            "files_verified": 0,
            "browser_closed": False,
        }

    value = create(
        controllers,
        tmp_path / "watch",
        operations_loader=lambda *_, **__: save_ready(),
        save_runner=child,
    )
    assert refresh(value)
    value.save_one()
    assert value.wait_stopped(3)
    status = value.status()
    assert status["phase"] == "needs_review"
    assert status["operations_save_status"] == "monitor_batch_manual_review"
    assert status["operations_save_tasks_completed"] == 0
    assert not refresh(value)
    with pytest.raises(QueueError):
        value.save_one()
    assert "private" not in json.dumps(status)


def test_bad_followup_preserves_success_after_child(tmp_path, controllers):
    def broken(*_args, **_kwargs):
        raise OSError("private")

    value = create(
        controllers,
        tmp_path / "watch",
        operations_loader=lambda *_, **__: save_ready(),
        save_runner=lambda *_, **__: completion(),
        catalog_loader=broken,
    )
    assert refresh(value)
    value.save_one()
    assert value.wait_stopped(3)
    status = value.status()
    assert status["operations_status"] == "needs_review"
    assert status["operations_can_save"] is False
    assert status["operations_save_status"] == "monitor_batch_completed"
    assert status["operations_save_files_verified"] == 2


def test_beginning_discovery_invalidates_last_save_eligibility_until_readonly_refresh(
    tmp_path, controllers
):
    def cycle(*_args, **_kwargs):
        value.stop()
        return {
            "status": "watch_test_cancelled",
            "cycles_completed": 0,
            "new_candidates": 0,
            "browser_closed": True,
        }

    value = create(
        controllers,
        tmp_path / "watch",
        operations_loader=lambda *_, **__: save_ready(),
        run_cycle=cycle,
    )
    assert refresh(value)
    value.start()
    assert value.wait_stopped(3)
    assert value.status()["settings_editable"]
    assert not value.status()["operations_can_save"]
    with pytest.raises(QueueError):
        value.save_one()
    assert refresh(value)
