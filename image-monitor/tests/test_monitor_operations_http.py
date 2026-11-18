"""Keep work summaries and explicit completion checks bounded at the HTTP boundary."""

import json
import threading
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from test_monitor_app import FakeController, action, authorized_fields, raw_request, request

from image_monitor.monitor_app import MonitorServer, share_monitor_report

COUNTS = {
    "candidate_uninspected": 1,
    "save_ready": 0,
    "save_planned": 0,
    "save_active": 0,
    "save_completed": 2,
    "save_unavailable": 0,
    "save_needs_review": 0,
}


class OperationsController(FakeController):
    def __init__(self):
        super().__init__()
        self.snapshot.update(
            task_kind="list",
            operations_status="ready",
            operations_reason="candidate_detail_required",
            operations_error_type=None,
            operations_counts=COUNTS | {"private_path": "C:/private/work"},
            operations_wait_until=None,
            operations_remaining_seconds=0,
            operations_can_finish=True,
            operations_rows=[
                {
                    "order": 1,
                    "status": "candidate_uninspected",
                    "reason": "candidate_detail_required",
                    "image_count": None,
                    "post_id": "private-post-id",
                    "post_url": "https://private.example/post",
                    "path": "C:/private/image.jpg",
                    "private_observation": {"nickname": "private author"},
                },
                {
                    "order": 2,
                    "status": "save_completed",
                    "reason": "save_completed",
                    "image_count": 2,
                },
            ],
            operations_rows_omitted=0,
            operations_finish_status=None,
            operations_finish_reason=None,
            operations_finish_error_type=None,
            operations_finish_files_verified=0,
        )

    def _require_idle(self):
        if (
            self.alive
            or self.snapshot["phase"] != "stopped"
            or self.snapshot["settings_editable"] is not True
            or self.snapshot["browser_closed"] is not True
        ):
            raise ValueError("Work checks require a stopped and idle controller")

    def refresh_operations(self):
        with self.lock:
            self._require_idle()
            self.snapshot["task_kind"] = "operations"
            return self._action("refresh_operations", "verifying_operations", alive=True)

    def finish_completed(self):
        with self.lock:
            self._require_idle()
            if self.snapshot["operations_can_finish"] is not True:
                raise ValueError("Only eligible existing completion records may be checked")
            self.snapshot["task_kind"] = "finish"
            return self._action("finish_completed", "finishing_completed", alive=True)


@pytest.fixture
def portal():
    controller = OperationsController()
    server = MonitorServer(controller)
    thread = threading.Thread(target=server.serve, daemon=True)
    thread.start()
    value = SimpleNamespace(
        controller=controller,
        server=server,
        thread=thread,
        path=urlsplit(server.url).path,
        authority=urlsplit(server.origin).netloc,
    )
    try:
        yield value
    finally:
        controller.failure = None
        controller.stop()
        server.closing.set()
        thread.join(5)
        server.server_close()
        assert not thread.is_alive()


@pytest.mark.parametrize(
    ("name", "task", "phase"),
    [
        ("refresh_operations", "operations", "verifying_operations"),
        ("finish_completed", "finish", "finishing_completed"),
    ],
)
def test_explicit_work_actions_use_the_existing_nonblocking_control_surface(
    portal, name, task, phase
):
    code, _, result = action(portal, name)
    assert code == 200
    assert result["status"]["phase"] == phase
    assert result["status"]["task_kind"] == task
    assert [call[0] for call in portal.controller.calls] == [name]
    code, _, body = request(portal)
    assert code == 200 and json.loads(body)["status"]["phase"] == phase
    assert action(portal, "stop")[0] == 200
    code, _, result = action(portal, "exit")
    assert code == 200 and result["closing"] is True
    portal.thread.join(3)
    assert not portal.thread.is_alive()
    assert [call[0] for call in portal.controller.calls] == [name, "stop", "stop"]
    assert not any(call[0] == "wait_stopped" for call in portal.controller.calls)


def test_work_status_and_shared_report_project_only_anonymous_summary_fields(portal):
    code, _, body = request(portal)
    assert code == 200
    status = json.loads(body)["status"]
    assert status["operations_counts"] == COUNTS
    assert status["operations_status"] == "ready"
    assert status["operations_can_finish"] is True
    assert status["operations_rows_omitted"] == 0
    assert status["operations_finish_files_verified"] == 0
    assert status["operations_rows"] == [
        {
            "order": 1,
            "status": "candidate_uninspected",
            "reason": "candidate_detail_required",
            "image_count": None,
        },
        {
            "order": 2,
            "status": "save_completed",
            "reason": "save_completed",
            "image_count": 2,
        },
    ]
    shared = share_monitor_report({"monitor_status": portal.controller.status()})
    assert shared["monitor_status"]["operations_counts"] == COUNTS
    assert shared["monitor_status"]["operations_rows"] == status["operations_rows"]
    for value in (body.decode(), json.dumps(shared)):
        for secret in ("private", "nickname", "https://", "post_id", "path"):
            assert secret not in value
    assert portal.controller.calls == []


def test_work_projection_bounds_rows_and_copies_nested_summaries(portal):
    row = portal.controller.snapshot["operations_rows"][1]
    portal.controller.snapshot["operations_rows"] = [row] * 24
    shared = share_monitor_report({"monitor_status": portal.controller.status()})
    public = shared["monitor_status"]
    assert len(public["operations_rows"]) == 20
    public["operations_rows"][0]["image_count"] = 99
    public["operations_counts"]["save_completed"] = 99
    assert row["image_count"] == 2
    assert portal.controller.snapshot["operations_counts"]["save_completed"] == 2


def test_completion_outcome_is_shared_as_fixed_summary_fields(portal):
    portal.controller.snapshot.update(
        operations_finish_status="batch_finish_completed",
        operations_finish_reason="completed_files_reverified_and_batch_resolved",
        operations_finish_error_type=None,
        operations_finish_files_verified=4,
    )
    code, _, body = request(portal)
    assert code == 200
    status = json.loads(body)["status"]
    assert status["operations_finish_status"] == "batch_finish_completed"
    assert status["operations_finish_reason"] == "completed_files_reverified_and_batch_resolved"
    assert status["operations_finish_files_verified"] == 4
    shared = share_monitor_report({"monitor_status": portal.controller.status()})
    assert shared["monitor_status"]["operations_finish_files_verified"] == 4
    assert portal.controller.calls == []


def test_work_projection_rejects_nested_private_values_even_in_known_fields(portal):
    injected = {"path": "C:/private/image.jpg", "url": "https://private.example/post"}
    portal.controller.snapshot.update(
        operations_reason=injected,
        operations_error_type=injected,
        operations_wait_until=injected,
        operations_finish_status=injected,
        operations_finish_reason=injected,
        operations_finish_error_type=injected,
        operations_rows_omitted=injected,
        operations_finish_files_verified=injected,
        operations_counts={key: injected for key in COUNTS},
        operations_rows=[
            {"order": injected, "status": injected, "reason": injected, "image_count": injected}
        ],
    )
    code, _, body = request(portal)
    assert code == 200
    public = json.loads(body)["status"]
    assert set(public["operations_counts"]) == set(COUNTS)
    assert all(type(value) is int and value >= 0 for value in public["operations_counts"].values())
    shared = share_monitor_report({"monitor_status": portal.controller.status()})
    assert "private" not in body.decode()
    assert "private" not in json.dumps(shared)


@pytest.mark.parametrize("name", ["refresh_operations", "finish_completed"])
@pytest.mark.parametrize(
    "extra",
    [
        {"work_root": "C:/foreign"},
        {"batch_id": "private-batch"},
        {"post_url": "https://foreign.example"},
        {"retry": True},
        {"max_tasks": 999},
    ],
)
def test_work_actions_cannot_choose_roots_targets_limits_or_retry_behavior(portal, name, extra):
    code, _, _ = action(portal, name, **extra)
    assert code == 400
    assert portal.controller.calls == []


@pytest.mark.parametrize("name", ["refresh_operations", "finish_completed"])
@pytest.mark.parametrize("header", ["Host", "Origin", "X-Image-Monitor-Token"])
@pytest.mark.parametrize("variation", ["wrong", "duplicate"])
def test_work_actions_keep_exact_single_host_origin_and_capability(portal, name, header, variation):
    body = json.dumps({"action": name}).encode()
    fields = authorized_fields(portal, body)
    if variation == "wrong":
        fields = [
            f"{header}: foreign" if line.startswith(header + ":") else line for line in fields
        ]
    else:
        fields.append(f"{header}: foreign")
    code, _, _ = raw_request(portal, fields=fields, body=body)
    assert code == 403
    assert portal.controller.calls == []


@pytest.mark.parametrize("name", ["refresh_operations", "finish_completed"])
def test_work_actions_reject_duplicate_json_fields_without_starting_work(portal, name):
    body = json.dumps({"action": name}).encode()
    body = body[:-1] + b',"action":"start"}'
    code, _, _ = raw_request(portal, fields=authorized_fields(portal, body), body=body)
    assert code == 400
    assert portal.controller.calls == []


@pytest.mark.parametrize("name", ["refresh_operations", "finish_completed"])
def test_active_worker_excludes_work_actions(portal, name):
    assert action(portal, "start")[0] == 200
    code, _, _ = action(portal, name)
    assert code == 409
    assert [call[0] for call in portal.controller.calls] == ["start"]


def test_explicit_finish_requires_current_eligibility(portal):
    portal.controller.snapshot["operations_can_finish"] = False
    code, _, result = action(portal, "finish_completed")
    assert code == 409
    assert result == {"error": "monitor_action_not_available"}
    assert portal.controller.calls == []


@pytest.mark.parametrize(
    ("name", "phase"),
    [("refresh_operations", "verifying_operations"), ("finish_completed", "finishing_completed")],
)
def test_actual_local_worker_keeps_http_status_stop_and_exit_responsive(tmp_path, name, phase):
    from test_monitor_operations_controller import finish_report, operations_snapshot

    from image_monitor.monitor_controller import MonitorController

    entered, release = threading.Event(), threading.Event()
    worker_ids = []

    def blocked(should_stop):
        worker_ids.append(threading.get_ident())
        entered.set()
        assert release.wait(5), "The simulated current file verification was not released"
        assert should_stop()

    def load(*_args, should_stop, **_kwargs):
        if name == "refresh_operations":
            blocked(should_stop)
        return operations_snapshot(can_finish=True)

    def finish(*_args, should_stop):
        blocked(should_stop)
        return finish_report(status="batch_finish_cancelled", reason="cancelled", files_verified=0)

    def forbidden(*_args, **_kwargs):
        pytest.fail("A local work check started unrelated browser or save work")

    controller = MonitorController(
        tmp_path / "watch",
        save_root=tmp_path / "legacy",
        batch_root=tmp_path / "batch",
        operations_loader=load,
        finish_runner=finish,
        run_cycle=forbidden,
        run_details=forbidden,
        catalog_loader=forbidden,
    )
    if name == "finish_completed":
        controller.refresh_operations()
        assert controller.wait_stopped(3)
        assert controller.status()["operations_can_finish"] is True
    server = MonitorServer(controller)
    thread = threading.Thread(target=server.serve, daemon=True)
    thread.start()
    portal = SimpleNamespace(
        controller=controller,
        server=server,
        thread=thread,
        path=urlsplit(server.url).path,
        authority=urlsplit(server.origin).netloc,
    )
    try:
        assert action(portal, name)[0] == 200
        assert entered.wait(3)
        code, _, body = request(portal)
        assert code == 200 and json.loads(body)["status"]["phase"] == phase
        assert action(portal, "stop")[0] == 200
        code, _, result = action(portal, "exit")
        assert code == 200 and result["closing"] is True
        assert controller.is_alive() and thread.is_alive()
        release.set()
        assert controller.wait_stopped(5)
        thread.join(5)
        assert not thread.is_alive()
        assert controller.status()["phase"] == "stopped"
        assert worker_ids and worker_ids[0] != threading.get_ident()
    finally:
        release.set()
        controller.stop()
        assert controller.wait_stopped(5)
        server.closing.set()
        thread.join(5)
        server.server_close()
