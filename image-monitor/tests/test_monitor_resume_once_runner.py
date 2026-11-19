import json

import pytest

from image_monitor import monitor_resume_once as runner
from image_monitor.queue import QueueStore
from image_monitor.watch_lock import WatchRunBusy, watch_run_lock
from image_monitor.watch_store import MONITOR_SCOPE


def test_missing_database_leaves_work_root_untouched(tmp_path):
    root = tmp_path / "absent"
    report = runner.run_monitor_resume_once(root)
    assert report["status"] == "monitor_resume_no_slot"
    assert report["reason"] == "existing_watch_database_required"
    assert report["detail_pending_count"] is None and report["resume_detail_pending"] is None
    assert report["detail_responses_received"] == 0 and report["details_checked"] == 0
    assert runner.monitor_resume_once_exit_code(report) == 0
    assert not root.exists()


def test_app_lease_prevents_opening_source_or_worker(tmp_path, monkeypatch):
    database = tmp_path / "watch.sqlite"
    database.touch()
    with watch_run_lock(database, MONITOR_SCOPE, purpose="monitor"):
        monkeypatch.setattr(runner, "MonitorController", lambda *a, **k: pytest.fail("opened"))
        report = runner.run_monitor_resume_once(tmp_path)
    assert report["status"] == "monitor_resume_busy"
    assert report["reason"] == "another_monitor_is_open"
    assert report["worker_stopped"] and report["detail_pending_count"] is None
    assert report["detail_responses_received"] == 0


def test_fresh_watch_has_no_verified_slot_or_pending_work(tmp_path):
    with QueueStore(tmp_path / "watch.sqlite"):
        pass
    report = runner.run_monitor_resume_once(tmp_path, run_details=lambda *a, **k: pytest.fail())
    assert report["status"] == "monitor_resume_no_slot"
    assert report["reason"] == "no_verified_detail_slot"
    assert report["detail_pending_count"] == 0 and report["resume_detail_pending"] is False
    assert report["detail_responses_received"] == 0 and report["native_save_tasks_started"] == 0


def test_bad_database_is_review_and_has_no_private_output(tmp_path):
    database = tmp_path / "watch.sqlite"
    database.write_text("private test text", encoding="utf-8")
    report = runner.run_monitor_resume_once(tmp_path)
    assert report["status"] == "monitor_resume_review"
    assert report["detail_pending_count"] is None
    assert runner.monitor_resume_once_exit_code(report) == 2
    assert "private test text" not in json.dumps(report)
    assert str(tmp_path) not in json.dumps(report)


@pytest.mark.parametrize("http", [None, 429, 503])
def test_waiting_counts_only_the_current_http_response(http):
    state = {
        "resume_once_status": "waiting",
        "reason": "service_retry_after" if http else "persisted_cooldown",
        "next_eligible_at": "2026-11-20T10:00:00+09:00",
        "remaining_seconds": 120,
        "detail_pending_count": 82,
        "resume_detail_pending": http is None,
        "resume_once_detail": dict(http_status=http, url="do-not-share") if http else None,
        "details": [{"http_status": 200, "url": "do-not-share"}],
    }
    report = runner._report(state)
    assert report["status"] == "monitor_resume_waiting"
    assert report["detail_responses_received"] == int(http is not None)
    assert report["details_checked"] == 0
    assert report["next_eligible_at"] == "2026-11-20T01:00:00.000000+00:00"
    assert report["remaining_seconds"] == 120
    assert "do-not-share" not in json.dumps(report)


def test_ctrl_c_keeps_app_lease_until_worker_stops(tmp_path, monkeypatch):
    database = tmp_path / "watch.sqlite"
    database.touch()
    stops = []

    class InterruptedController:
        def __init__(self, *args, **kwargs):
            self.active = True

        def resume_once(self):
            return {"resume_once_status": "running"}

        def is_alive(self):
            return self.active

        def stop(self):
            with (
                pytest.raises(WatchRunBusy),
                watch_run_lock(database, MONITOR_SCOPE, purpose="monitor"),
            ):
                pytest.fail("lease released before stopping the worker")
            stops.append(True)
            self.active = False

        def status(self):
            return {
                "resume_once_status": "cancelled",
                "resume_once_detail": None,
                "browser_closed": True,
            }

    def interrupt_sleep(seconds):
        if not stops:
            raise KeyboardInterrupt

    monkeypatch.setattr(runner, "MonitorController", InterruptedController)
    monkeypatch.setattr(runner.time, "sleep", interrupt_sleep)
    report = runner.run_monitor_resume_once(tmp_path)
    assert stops == [True]
    assert report["status"] == "monitor_resume_cancelled"
    assert report["worker_stopped"] and report["browser_closed"] is True
    assert runner.monitor_resume_once_exit_code(report) == 130
    with watch_run_lock(database, MONITOR_SCOPE, purpose="monitor"):
        pass
