"""Read persisted monitor candidates using the actual controller, browser and DB."""

import io
import shutil
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from PIL import Image
from test_candidate_trial_browser import image_url, post_html, post_url
from test_monitor_integration import NOW, old_trial_records, seed_old_trial

from image_monitor import candidate_browser, candidate_runtime, watch_browser
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.monitor_controller import MONITOR_SCOPE, MonitorController
from image_monitor.queue import QueueStore
from image_monitor.search_list import build_list_url
from image_monitor.watch_lock import watch_run_lock
from image_monitor.watch_runtime import DEFAULT_SCOPE
from image_monitor.watch_store import WatchStore


class DetailClock:
    def __init__(self):
        self._current = NOW
        self._lock = threading.Lock()
        self.waits = []

    def now(self):
        with self._lock:
            return self._current

    def advance(self, seconds):
        with self._lock:
            self._current += timedelta(seconds=seconds)

    def wait_for(self, event, seconds):
        if not event.is_set():
            self.waits.append(seconds)
            self.advance(seconds)


def monitor_source(queue):
    store = WatchStore(queue)
    return {
        "state": store.get_state(MONITOR_SCOPE),
        "candidates": store.list_candidates(MONITOR_SCOPE),
        "scans": store.list_scans(MONITOR_SCOPE),
        "gaps": store.list_gaps(MONITOR_SCOPE),
    }


def seed_monitor_candidates(database):
    source = build_list_url("normal", "comic_new6", "ai")
    baseline = {
        "mode": "new",
        "observed_at": (NOW - timedelta(minutes=10)).isoformat(),
        "anchor_ids": ["100", "99"],
        "source_url": source,
        "requires_published_at_filter": True,
    }
    with QueueStore(database) as queue:
        store = WatchStore(queue)
        for generation, stamp, ids in (
            (0, NOW - timedelta(minutes=10), ()),
            (1, NOW - timedelta(minutes=2), ("104", "105")),
        ):
            store.persist_scan(
                MONITOR_SCOPE,
                observed_at=stamp,
                expected_generation=generation,
                scan_result={
                    "mode": "invented_monitor_fixture",
                    "queue_eligible": False,
                    "control": {
                        "finished_at": stamp.isoformat(),
                        "next_eligible_at": (stamp + timedelta(seconds=60)).isoformat(),
                        "interval_seconds": 60,
                        "blocked": False,
                    },
                },
                candidates=[
                    {
                        "post_id": post_id,
                        "post_url": post_url(post_id),
                        "title": f"Invented existing candidate {post_id}",
                        "shown_metadata": {
                            "baseline_observed_at": baseline["observed_at"],
                            "requires_published_at_filter": True,
                        },
                    }
                    for post_id in ids
                ],
                checkpoint={
                    "anchor_ids": list(ids) + baseline["anchor_ids"],
                    "observed_at": stamp.isoformat(),
                    "source_url": source,
                },
                complete=True,
                baseline=baseline if generation == 0 else None,
            )
        return monitor_source(queue)


@pytest.mark.parametrize("stop_after_first", [False, True])
def test_stopped_monitor_reads_real_detail_dom_without_changing_list_coverage(
    tmp_path, monkeypatch, stop_after_first
):
    pytest.importorskip("playwright.sync_api")
    if sys.platform != "win32":
        executable = shutil.which("chromium") or shutil.which("google-chrome")
        if not executable:
            pytest.skip("Installed Chromium unavailable")
        monkeypatch.setattr(candidate_runtime, "require_windows", lambda: None)
        monkeypatch.setattr(watch_browser, "require_windows", lambda: None)
        monkeypatch.setattr(watch_browser, "browser_executable", lambda _: Path(executable))

    database = tmp_path / "watch.sqlite"
    previous_trial = seed_old_trial(database)
    previous_source = seed_monitor_candidates(database)
    documents = {
        post_url("104"): post_html("104", "2026.11.17 16:55:00"),
        post_url("105"): post_html("105", "2026.11.17 16:49:59"),
    }
    png = io.BytesIO()
    Image.new("RGB", (4, 3), "#315781").save(png, format="PNG")
    local_image = png.getvalue()
    navigations = []
    image_requests = []
    unexpected_requests = []
    sessions = []
    owned_browsers = []
    reports = []
    worker_ids = []
    clock = DetailClock()

    def local_route(route):
        request = route.request
        if request.is_navigation_request() and request.url in documents:
            navigations.append(request.url)
            route.fulfill(
                status=200, content_type="text/html; charset=utf-8", body=documents[request.url]
            )
        elif request.resource_type == "image" and request.url in {
            image_url("104"),
            image_url("105"),
        }:
            image_requests.append(request.url)
            route.fulfill(status=200, content_type="image/png", body=local_image)
        else:
            unexpected_requests.append(request.url)
            route.abort()

    class RoutedCandidateBrowser(candidate_browser.HeadlessCandidateBrowser):
        def __enter__(self):
            entered = super().__enter__()
            sessions.append(self)
            owned_browsers.append(self._owned_browser)
            self._page.context.route("**/*", local_route)
            return entered

        def inspect(self, candidate, observed_at):
            result = super().inspect(candidate, observed_at)
            clock.advance(13)
            if stop_after_first:
                controller.stop()
            return result

    def no_list_scan(*_args, **_kwargs):
        pytest.fail("Detail inspection must not start a list scan")

    def run_details(*args, **kwargs):
        assert len(reports) < 2, "The bounded action exceeded two detail attempts"
        assert kwargs["scope"] == MONITOR_SCOPE
        assert kwargs["max_candidates"] == 1
        assert kwargs["interval_seconds"] == 60
        assert kwargs["clock"] is clock
        assert callable(kwargs["should_stop"])
        worker_ids.append(threading.get_ident())
        report = candidate_runtime.run_candidate_trial(
            *args, backend_factory=RoutedCandidateBrowser, **kwargs
        )
        reports.append(report)
        return report

    with watch_run_lock(database, MONITOR_SCOPE, purpose="monitor"):
        controller = MonitorController(
            tmp_path, run_cycle=no_list_scan, run_details=run_details, clock=clock
        )
        initial = controller.status()
        assert initial["phase"] == "stopped"
        assert initial["candidate_count"] == initial["detail_pending_count"] == 2
        assert initial["detail_count"] == 0
        assert navigations == []
        try:
            controller.inspect_candidates()
            assert controller.wait_stopped(60), "The detail worker failed to stop"
        finally:
            controller.stop()
            assert controller.wait_stopped(60), "The detail worker failed to clean up"

        status = controller.status()
        attempted = 1 if stop_after_first else 2
        assert status["phase"] == "stopped", status
        assert status["task_kind"] == "details"
        assert status["detail_count"] == status["detail_completed_count"] == attempted
        assert status["detail_pending_count"] == 2 - attempted
        assert status["detail_failed_count"] == 0
        assert status["browser_closed"] is True
        assert status["completed_cycles"] == status["new_candidates"] == 0
        assert status["candidate_count"] == 2
        assert status["last_scan_at"] == initial["last_scan_at"]
        assert status["baseline_initialized"] is True
        assert len(reports) == len(sessions) == len(owned_browsers) == attempted
        assert len(set(worker_ids)) == 1 and worker_ids[0] != threading.get_ident()
        assert all(session.browser_closed is True for session in sessions)
        assert all(browser.is_connected() is False for browser in owned_browsers)
        assert sum(clock.waits) == (0 if stop_after_first else 60)
        expected_urls = [post_url("104")] if stop_after_first else list(documents)
        assert navigations == expected_urls
        assert image_requests == [image_url("104")] + (
            [] if stop_after_first else [image_url("105")]
        )
        assert unexpected_requests == []
        assert all(report["images_saved"] is False for report in reports)
        assert all(report["image_jobs_created"] == 0 for report in reports)
        if not stop_after_first:
            assert all(report["status"] == "candidate_test_completed" for report in reports)
            assert controller.inspect_candidates()["phase"] == "stopped"
            assert controller.wait_stopped(60)
            assert len(reports) == 2 and navigations == expected_urls

    with QueueStore(database, read_only=True) as queue:
        assert old_trial_records(queue) == previous_trial
        assert monitor_source(queue) == previous_source
        assert queue.summary()["posts"] == queue.summary()["jobs"] == 0
        detail_store = CandidateDetailStore(queue)
        assert detail_store.list_details(DEFAULT_SCOPE) == []
        details = detail_store.list_details(MONITOR_SCOPE)
        assert len(details) == attempted
        assert all(row["status"] == "completed" for row in details)
        classifications = [row["result"]["classification"] for row in details]
        assert {item["time_status"] for item in classifications} == (
            {"at_or_after_baseline"}
            if stop_after_first
            else {"at_or_after_baseline", "before_baseline"}
        )
        assert all(
            item["save_approved"] is item["queue_eligible"] is False for item in classifications
        )
        assert all(
            row["result"]["private_observation"]["snapshot"]["image_counts"]["included_unique"] == 1
            for row in details
        )
        if not stop_after_first:
            starts = [datetime.fromisoformat(row["started_at"]) for row in details]
            first_finish = datetime.fromisoformat(details[0]["finished_at"])
            assert starts[1] - first_finish == timedelta(seconds=60)
            assert starts[1] - starts[0] == timedelta(seconds=73)
    assert not (tmp_path / "images").exists()
