"""Reopen a paused then stopped monitor and consume exactly its owed detail turn."""

import json
import threading
from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from test_candidate_runtime import BrowserFactory as DetailBrowser
from test_candidate_runtime import observed
from test_monitor_app import action, request
from test_monitor_controller import AutoClock, Clock, until
from test_monitor_details_integration import monitor_source
from test_monitor_gap_continuation import partial_pages, run_scan, seed_baseline
from test_monitor_integration import old_trial_records
from test_recent_candidate_save import recent as recent
from test_saved_catalog_batch import disk_bytes
from test_watch_images_check import complete
from test_watch_runtime import new_posts_outcome

from image_monitor.candidate_runtime import run_candidate_trial
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.monitor_app import MonitorServer
from image_monitor.monitor_controller import MONITOR_SCOPE, MonitorController
from image_monitor.queue import QueueStore


@contextmanager
def dashboard(controller):
    server = MonitorServer(controller)
    thread = threading.Thread(target=server.serve, daemon=True)
    thread.start()
    try:
        yield SimpleNamespace(
            server=server, path=server.base_path, authority=urlsplit(server.origin).netloc
        )
    finally:
        controller.stop()
        server.closing.set()
        thread.join(30)
        server.server_close()
        assert not thread.is_alive() and controller.wait_stopped(30)


@pytest.mark.parametrize("outcome", [new_posts_outcome, partial_pages], ids=["complete", "partial"])
def test_restart_finishes_one_owed_detail_then_returns_to_discovery(recent, outcome):
    complete(recent, "104")
    saved_root = SimpleNamespace(root=recent.roots[2])
    original_files = disk_bytes(saved_root)
    assert any(path.name == "001.png" for path in original_files)
    root = recent.watch
    database = root / "watch.sqlite"
    clock = Clock()
    clock.current = recent.clock.now() + timedelta(minutes=2)
    seed_baseline(root, clock)
    deadline = clock.now() + timedelta(minutes=5)
    list_times = []
    detail_browser = DetailBrowser(observed(published_at=clock.now()))

    def scan(work_root, _browser, **options):
        list_times.append(clock.now())
        return run_scan(work_root, clock, outcome, should_stop=options["should_stop"])

    def no_detail(*args, **kwargs):
        pytest.fail("A detail started without an eligible service slot")

    first = MonitorController(root, run_cycle=scan, run_details=no_detail, clock=clock)
    with dashboard(first) as portal:
        assert action(portal, "start")[0] == 200
        until(
            lambda: (
                first.status()["phase"] == "waiting"
                and first.status()["task_kind"] == "auto_details"
            ),
            timeout=30,
        )
        assert action(portal, "pause")[0] == 200
        until(lambda: first.status()["phase"] == "paused", timeout=30)
        assert action(portal, "stop")[0] == 200
        assert first.wait_stopped(30)
    assert len(list_times) == 1 and detail_browser.browser.calls == []

    with QueueStore(database) as queue:
        queue.defer_service("dcinside", deadline)
        source = monitor_source(queue)
        previous_trial = old_trial_records(queue)
        assert CandidateDetailStore(queue).list_details(MONITOR_SCOPE) == []
    scan_id = source["state"]["latest_scan"]["scan_id"]
    clock_after_stop = clock.now()
    clock = AutoClock()
    clock.current = clock_after_stop

    def detail(work_root, browser, **options):
        assert options["expected_scan_id"] == scan_id
        report = run_candidate_trial(work_root, browser, backend_factory=detail_browser, **options)
        assert report["status"] == "candidate_test_completed" and report["browser_closed"] is True
        second.stop()
        return report

    def no_list(*args, **kwargs):
        pytest.fail("A fresh list scan replaced the restored detail")

    second = MonitorController(root, run_cycle=no_list, run_details=detail, clock=clock)
    with dashboard(second) as portal:
        initial = json.loads(request(portal)[2])["status"]
        assert initial["phase"] == "stopped" and initial["resume_detail_pending"] is True
        assert len(list_times) == 1 and detail_browser.browser.calls == []
        assert action(portal, "start")[0] == 200
        assert second.wait_stopped(30)
        finished = json.loads(request(portal)[2])["status"]
        assert finished["auto_details_checked"] == 1 and finished["resumed_detail_slot"] is True
        assert finished["phase"] == "stopped" and finished["resume_detail_pending"] is False
    assert [(row["post_id"], stamp) for row, stamp in detail_browser.browser.calls] == [
        ("103", deadline)
    ]

    with QueueStore(database, read_only=True) as queue:
        assert monitor_source(queue) == source
        (attempt,) = CandidateDetailStore(queue).list_details(MONITOR_SCOPE)
        assert attempt["post_id"] == "103" and attempt["status"] == "completed"
        assert queue.summary()["posts"] == queue.summary()["jobs"] == 0

    def next_scan(*args, **options):
        report = scan(*args, **options)
        third.stop()
        return report

    third = MonitorController(root, run_cycle=next_scan, run_details=no_detail, clock=clock)
    with dashboard(third) as portal:
        reopened = json.loads(request(portal)[2])["status"]
        assert reopened["phase"] == "stopped" and reopened["resume_detail_pending"] is False
        assert action(portal, "start")[0] == 200 and third.wait_stopped(30)
        assert third.status()["phase"] == "stopped", third.status()
    assert len(list_times) == 2 and list_times[-1] == deadline + timedelta(seconds=60)
    with QueueStore(database, read_only=True) as queue:
        assert old_trial_records(queue) == previous_trial
        assert CandidateDetailStore(queue).list_details(MONITOR_SCOPE) == [attempt]
    assert disk_bytes(saved_root) == original_files
