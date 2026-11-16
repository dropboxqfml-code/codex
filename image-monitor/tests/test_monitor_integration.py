"""Run two periodic discovery cycles with real browser DOM and durable records."""

import shutil
import sys
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from test_watch_trial_browser import list_html

from image_monitor import watch_browser, watch_runtime
from image_monitor.monitor_controller import MONITOR_SCOPE, MonitorController
from image_monitor.queue import QueueStore
from image_monitor.search_list import build_list_url
from image_monitor.watch_lock import watch_run_lock
from image_monitor.watch_store import WatchStore

NOW = datetime(2026, 11, 17, 8, tzinfo=UTC)


class MonitorClock:
    def __init__(self):
        self._current = NOW
        self._lock = threading.Lock()
        self.waits = []

    def now(self):
        with self._lock:
            return self._current

    def wait_for(self, event, seconds):
        if not event.is_set():
            with self._lock:
                self.waits.append(seconds)
                self._current += timedelta(seconds=seconds)


def old_trial_records(queue):
    store = WatchStore(queue)
    return {
        "state": store.get_state(watch_runtime.DEFAULT_SCOPE),
        "candidates": store.list_candidates(watch_runtime.DEFAULT_SCOPE),
        "scans": store.list_scans(watch_runtime.DEFAULT_SCOPE),
        "gaps": store.list_gaps(watch_runtime.DEFAULT_SCOPE),
    }


def seed_old_trial(database):
    source = build_list_url("normal", "comic_new6", "ai")
    baseline_time = NOW - timedelta(minutes=10)
    baseline = {
        "mode": "new",
        "anchor_ids": ["77"],
        "observed_at": baseline_time.isoformat(),
        "source_url": source,
        "requires_published_at_filter": True,
    }
    with QueueStore(database) as queue:
        store = WatchStore(queue)
        store.persist_scan(
            watch_runtime.DEFAULT_SCOPE,
            observed_at=baseline_time,
            expected_generation=0,
            scan_result={"mode": "invented_old_trial", "queue_eligible": False},
            candidates=[],
            checkpoint=baseline,
            complete=True,
            gap_reason=None,
            baseline=baseline,
        )
        observed = baseline_time + timedelta(minutes=1)
        store.persist_scan(
            watch_runtime.DEFAULT_SCOPE,
            observed_at=observed,
            expected_generation=1,
            scan_result={"mode": "invented_old_trial", "queue_eligible": False},
            candidates=[
                {
                    "post_id": "78",
                    "post_url": "https://gall.dcinside.com/board/view/?id=comic_new6&no=78",
                    "title": "Invented earlier trial title",
                    "shown_metadata": {"requires_published_at_filter": True},
                }
            ],
            checkpoint=baseline | {"anchor_ids": ["78", "77"], "observed_at": observed.isoformat()},
            complete=True,
            gap_reason=None,
        )
        return old_trial_records(queue)


def test_periodic_monitor_uses_real_dom_and_preserves_the_existing_trial(tmp_path, monkeypatch):
    pytest.importorskip("playwright.sync_api")
    if sys.platform != "win32":
        executable = shutil.which("chromium") or shutil.which("google-chrome")
        if not executable:
            pytest.skip("Installed Chromium unavailable")
        monkeypatch.setattr(watch_runtime, "require_windows", lambda: None)
        monkeypatch.setattr(watch_browser, "require_windows", lambda: None)
        monkeypatch.setattr(watch_browser, "browser_executable", lambda _: Path(executable))

    database = tmp_path / "watch.sqlite"
    before = seed_old_trial(database)
    first_url = build_list_url("normal", "comic_new6", "ai")
    second_url = build_list_url("normal", "comic_new6", "ai", page=2)
    third_url = build_list_url("normal", "comic_new6", "ai", page=3)
    documents = [
        (first_url, list_html([100, 99], second_url)),
        (first_url, list_html([104, 103, 100, 99], second_url)),
        (second_url, list_html([98, 97], third_url)),
    ]
    navigation = []
    unexpected_requests = []
    owned_browsers = []
    sessions = []
    reports = []
    worker_ids = []

    def local_document(route):
        request = route.request
        if (
            request.is_navigation_request()
            and len(navigation) < len(documents)
            and request.url == documents[len(navigation)][0]
        ):
            html = documents[len(navigation)][1]
            navigation.append(request.url)
            route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
        else:
            unexpected_requests.append(request.url)
            route.abort()

    class RoutedBrowser(watch_browser.HeadlessWatchBrowser):
        def __enter__(self):
            entered = super().__enter__()
            sessions.append(self)
            owned_browsers.append(self._owned_browser)
            self._page.context.route("**/*", local_document)
            return entered

    clock = MonitorClock()

    def run_cycle(*args, **kwargs):
        assert len(reports) < 2, "The monitor began an unexpected extra scan"
        assert kwargs["scope"] == MONITOR_SCOPE
        assert kwargs["cycles"] == 1
        assert kwargs["interval_seconds"] == 60
        assert kwargs["clock"] is clock
        assert callable(kwargs["should_stop"])
        worker_ids.append(threading.get_ident())
        report = watch_runtime.run_watch_trial(*args, backend_factory=RoutedBrowser, **kwargs)
        reports.append(report)
        if len(reports) == 2:
            controller.stop()
        return report

    with watch_run_lock(database, MONITOR_SCOPE, purpose="monitor"):
        controller = MonitorController(tmp_path, run_cycle=run_cycle, clock=clock)
        assert controller.status()["phase"] == "stopped"
        assert not controller.status()["baseline_initialized"]
        try:
            controller.start()
            assert controller.wait_stopped(60), "The owned monitor thread did not stop"
        finally:
            controller.stop()
            assert controller.wait_stopped(60), "The owned monitor thread did not clean up"

    status = controller.status()
    assert status["phase"] == "stopped", status
    assert status["completed_cycles"] == 2
    assert status["candidate_count"] == status["new_candidates"] == 2
    assert status["baseline_initialized"]
    assert status["browser_closed"] is True
    assert len(set(worker_ids)) == 1 and worker_ids[0] != threading.get_ident()
    assert sum(clock.waits) == 60
    assert navigation == [first_url, first_url, second_url]
    assert unexpected_requests == []
    assert [report["status"] for report in reports] == ["watch_test_completed"] * 2
    assert [report["cycles"][0]["navigation_attempts"] for report in reports] == [1, 2]
    assert [report["new_candidates"] for report in reports] == [0, 2]
    assert len(sessions) == len(owned_browsers) == 2
    assert all(session.browser_closed is True for session in sessions)
    assert all(browser.is_connected() is False for browser in owned_browsers)

    with QueueStore(database, read_only=True) as queue:
        assert old_trial_records(queue) == before
        store = WatchStore(queue)
        state = store.get_state(MONITOR_SCOPE)
        scans = list(reversed(store.list_scans(MONITOR_SCOPE)))
        assert state["generation"] == 2
        assert state["baseline"]["anchor_ids"] == ["100", "99"]
        assert state["checkpoint"]["anchor_ids"] == ["104", "103", "100", "99"]
        assert {row["post_id"] for row in store.list_candidates(MONITOR_SCOPE)} == {"104", "103"}
        assert all(scan["complete"] is True for scan in scans)
        assert all(scan["result"]["queue_eligible"] is False for scan in scans)
        snapshots = [
            page for scan in scans for page in scan["result"]["private_observation"]["pages"]
        ]
        assert len(snapshots) == 3
        assert all(page["layout_status"] == "site_verified" for page in snapshots)
        assert queue.summary()["posts"] == queue.summary()["jobs"] == 0
        first_scan, second_scan = (datetime.fromisoformat(scan["observed_at"]) for scan in scans)
        assert second_scan - first_scan >= timedelta(seconds=60)
    assert not (tmp_path / "images").exists()
