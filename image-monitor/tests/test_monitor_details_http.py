"""Keep detail controls bounded and anonymous at the real local HTTP boundary."""

import json
import threading
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from test_monitor_app import FakeController, action, request

from image_monitor.monitor_app import MonitorServer, share_monitor_report


class DetailController(FakeController):
    def __init__(self):
        super().__init__()
        self.snapshot.update(
            task_kind="list",
            baseline_initialized=True,
            detail_count=2,
            detail_pending_count=4,
            detail_completed_count=1,
            detail_failed_count=1,
            details=[
                {
                    "order": 1,
                    "status": "completed",
                    "time_status": "at_or_after_baseline",
                    "reason": "published_at_or_after_baseline",
                    "image_count": 2,
                    "pending_images": 0,
                    "title": "Invented private title",
                    "post_url": "https://private.example/post",
                    "private_observation": {"snapshot": {"nickname": "Invented author"}},
                }
            ],
        )

    def inspect_candidates(self):
        if self.snapshot["phase"] != "stopped":
            raise ValueError("Stop before inspecting existing candidates")
        self.snapshot["task_kind"] = "details"
        return self._action("inspect_candidates", "inspecting", alive=True)


@pytest.fixture
def portal():
    controller = DetailController()
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


def test_detail_action_uses_the_existing_nonblocking_control_surface(portal):
    code, _, payload = action(portal, "inspect_candidates")
    assert code == 200
    assert payload["status"]["phase"] == "inspecting"
    assert payload["status"]["task_kind"] == "details"
    assert [call[0] for call in portal.controller.calls] == ["inspect_candidates"]
    code, _, payload = action(portal, "pause")
    assert code == 200 and payload["status"]["phase"] == "paused"
    code, _, payload = action(portal, "stop")
    assert code == 200 and payload["status"]["phase"] == "stopped"
    assert not any(call[0] == "wait_stopped" for call in portal.controller.calls)


def test_detail_status_and_shared_report_project_only_anonymous_summary_fields(portal):
    code, _, body = request(portal)
    assert code == 200
    status = json.loads(body)["status"]
    assert status["detail_pending_count"] == 4
    assert status["details"] == [
        {
            "order": 1,
            "status": "completed",
            "time_status": "at_or_after_baseline",
            "reason": "published_at_or_after_baseline",
            "image_count": 2,
            "pending_images": 0,
        }
    ]
    shared = share_monitor_report({"monitor_status": portal.controller.status()})
    assert shared["monitor_status"]["details"] == status["details"]
    for value in (body.decode(), json.dumps(shared)):
        assert "private" not in value and "nickname" not in value and "https://" not in value


def test_detail_projection_is_bounded_and_does_not_alias_controller_rows(portal):
    row = portal.controller.snapshot["details"][0]
    portal.controller.snapshot["details"] = [row] * 20
    shared = share_monitor_report({"monitor_status": portal.controller.status()})
    assert len(shared["monitor_status"]["details"]) == 10
    shared["monitor_status"]["details"][0]["image_count"] = 99
    assert row["image_count"] == 2


@pytest.mark.parametrize(
    "extra",
    [
        {"scope": "previous trial"},
        {"max_candidates": 999},
        {"post_url": "https://foreign.example"},
        {"interval_seconds": 0},
        {"work_root": "C:/foreign"},
    ],
)
def test_detail_action_cannot_choose_targets_scope_or_limits(portal, extra):
    code, _, _ = action(portal, "inspect_candidates", **extra)
    assert code == 400
    assert portal.controller.calls == []


def test_detail_action_keeps_authentication_and_active_worker_exclusion(portal):
    code, _, _ = request(
        portal,
        "POST",
        "api/action",
        payload={"action": "inspect_candidates"},
        headers={"X-Image-Monitor-Token": "foreign"},
    )
    assert code == 403 and portal.controller.calls == []
    action(portal, "start")
    code, _, _ = action(portal, "inspect_candidates")
    assert code == 409
    assert [call[0] for call in portal.controller.calls] == ["start"]


def test_exit_while_details_active_stops_without_joining_in_request_thread(portal):
    action(portal, "inspect_candidates")
    code, _, payload = action(portal, "exit")
    assert code == 200 and payload["closing"] is True
    portal.thread.join(3)
    assert not portal.thread.is_alive()
    assert [call[0] for call in portal.controller.calls] == ["inspect_candidates", "stop"]


def test_actual_detail_worker_keeps_http_status_stop_and_exit_responsive(tmp_path):
    from test_monitor_details_integration import DetailClock, seed_monitor_candidates

    from image_monitor.monitor_controller import MonitorController

    seed_monitor_candidates(tmp_path / "watch.sqlite")
    entered = threading.Event()
    release = threading.Event()
    worker_ids = []

    def run_details(*_args, **options):
        worker_ids.append(threading.get_ident())
        entered.set()
        assert release.wait(5), "The simulated current navigation was not released"
        assert options["should_stop"]()
        return {
            "status": "candidate_test_cancelled",
            "reason": "requested_stop",
            "candidates_completed": 0,
            "browser_closed": True,
            "details": [],
        }

    controller = MonitorController(tmp_path, run_details=run_details, clock=DetailClock())
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
        assert action(portal, "inspect_candidates")[0] == 200
        assert entered.wait(3)
        code, _, body = request(portal)
        assert code == 200 and json.loads(body)["status"]["phase"] == "inspecting"
        assert controller.is_alive()
        assert action(portal, "stop")[0] == 200
        code, _, payload = action(portal, "exit")
        assert code == 200 and payload["closing"] is True
        assert controller.is_alive() and thread.is_alive()
        release.set()
        assert controller.wait_stopped(5)
        thread.join(5)
        assert not thread.is_alive()
        assert controller.status()["phase"] == "stopped"
        assert worker_ids[0] != threading.get_ident()
    finally:
        release.set()
        controller.stop()
        assert controller.wait_stopped(5)
        server.closing.set()
        thread.join(5)
        server.server_close()
