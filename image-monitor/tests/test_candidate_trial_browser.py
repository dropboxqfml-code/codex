"""Connect the candidate trial to real browser DOM, policy, and durable storage."""

import io
import shutil
import sys
from datetime import UTC, datetime, timedelta
from html import escape
from pathlib import Path

import pytest
from PIL import Image

from image_monitor import candidate_browser, candidate_runtime, watch_browser
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.queue import QueueStore
from image_monitor.search_list import build_list_url
from image_monitor.watch_runtime import DEFAULT_SCOPE
from image_monitor.watch_store import WatchStore

NOW = datetime(2026, 11, 16, 4, 0, tzinfo=UTC)
BASELINE = NOW - timedelta(minutes=10)


class AdvancingClock:
    def __init__(self):
        self.current = NOW
        self.waits = []

    def now(self):
        return self.current

    def wait(self, seconds):
        self.waits.append(seconds)
        self.current += timedelta(seconds=seconds)


def list_state(queue):
    store = WatchStore(queue)
    return {
        "state": store.get_state(DEFAULT_SCOPE),
        "candidates": store.list_candidates(DEFAULT_SCOPE),
        "scans": store.list_scans(DEFAULT_SCOPE),
        "gaps": store.list_gaps(DEFAULT_SCOPE),
    }


def seed_candidates(database):
    baseline = {
        "mode": "new",
        "observed_at": BASELINE.isoformat(),
        "anchor_ids": ["100", "99"],
        "source_url": build_list_url("normal", "comic_new6", "ai"),
        "requires_published_at_filter": True,
    }
    with QueueStore(database) as queue:
        store = WatchStore(queue)
        for generation, stamp, posts in (
            (0, BASELINE, ()),
            (1, NOW - timedelta(minutes=2), ("104", "105")),
        ):
            store.persist_scan(
                DEFAULT_SCOPE,
                observed_at=stamp,
                expected_generation=generation,
                scan_result={
                    "mode": "invented_fixture",
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
                        "title": f"Invented list title {post_id}",
                        "shown_metadata": {
                            "baseline_observed_at": baseline["observed_at"],
                            "requires_published_at_filter": True,
                        },
                    }
                    for post_id in posts
                ],
                checkpoint={
                    "anchor_ids": list(posts) + ["100", "99"],
                    "observed_at": stamp.isoformat(),
                    "source_url": baseline["source_url"],
                },
                complete=True,
                baseline=baseline if generation == 0 else None,
            )
        return list_state(queue)


def post_url(post_id):
    return f"https://gall.dcinside.com/board/view/?id=comic_new6&no={post_id}"


def image_url(post_id):
    return f"https://dcimg3.dcinside.co.kr/viewimage.php?id=fixture&no=invented-{post_id}"


def post_html(post_id, published):
    image = escape(image_url(post_id), quote=True)
    attachment = escape(
        f"https://image.dcinside.com/download.php?no=invented-{post_id}&f_no=fixture", quote=True
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"></head><body>
      <div class="gallview_head">
        <span class="title_subject">Invented detail title {post_id}</span>
        <span class="gall_writer" data-nick="Invented author"></span>
        <span class="gall_date" title="{published}">Invented displayed date</span>
      </div>
      <div class="write_div"><img src="{image}" width="4" height="3"></div>
      <div class="appending_file"><a href="{attachment}">invented-{post_id}.png</a></div>
      </body></html>"""


def test_real_browser_trial_classifies_times_without_changing_watch_coverage_or_image_work(
    tmp_path, monkeypatch
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
    before = seed_candidates(database)
    documents = {
        post_url("104"): post_html("104", "2026.11.16 12:55:00"),
        post_url("105"): post_html("105", "2026.11.16 12:49:59"),
    }
    png = io.BytesIO()
    Image.new("RGB", (4, 3), "#315781").save(png, format="PNG")
    image_bytes = png.getvalue()
    document_requests = []
    image_requests = []
    unexpected_requests = []
    sessions = []
    owned_browsers = []

    def local_route(route):
        url = route.request.url
        if route.request.is_navigation_request() and url in documents:
            document_requests.append(url)
            route.fulfill(status=200, content_type="text/html; charset=utf-8", body=documents[url])
        elif route.request.resource_type == "image" and url in {
            image_url("104"),
            image_url("105"),
        }:
            image_requests.append(url)
            route.fulfill(status=200, content_type="image/png", body=image_bytes)
        else:
            unexpected_requests.append(url)
            route.abort()

    class RoutedBrowser(candidate_browser.HeadlessCandidateBrowser):
        def __enter__(self):
            entered = super().__enter__()
            sessions.append(self)
            owned_browsers.append(self._owned_browser)
            self._page.context.route("**/*", local_route)
            return entered

    clock = AdvancingClock()
    report = candidate_runtime.run_candidate_trial(
        tmp_path, clock=clock, backend_factory=RoutedBrowser
    )

    assert report["status"] == "candidate_test_completed", report
    assert report["candidates_selected"] == report["candidates_completed"] == 2
    assert report["time_status_counts"] == {"at_or_after_baseline": 1, "before_baseline": 1}
    assert report["images_saved"] is False and report["image_jobs_created"] == 0
    assert clock.waits == [60]
    assert document_requests == [post_url("104"), post_url("105")]
    assert image_requests == [image_url("104"), image_url("105")]
    assert unexpected_requests == []
    assert len(sessions) == len(owned_browsers) == 1
    assert report["browser_closed"] is sessions[0].browser_closed is True
    assert owned_browsers[0].is_connected() is False
    assert all(
        item["queue_eligible"] is item["save_approved"] is False for item in report["details"]
    )
    assert all(item["layout_status"] == "unverified" for item in report["details"])
    assert all(item["image_counts"]["included_unique"] == 1 for item in report["details"])
    assert all(item["image_counts"]["pending"] == 0 for item in report["details"])
    assert all(item["attachment_matching_counts"] == {"matched": 1} for item in report["details"])

    with QueueStore(database) as queue:
        assert list_state(queue) == before
        assert queue.summary()["posts"] == queue.summary()["jobs"] == 0
        detail_store = CandidateDetailStore(queue)
        assert detail_store.list_pending(DEFAULT_SCOPE) == []
        details = detail_store.list_details(DEFAULT_SCOPE)
        assert len(details) == 2
        assert {item["status"] for item in details} == {"completed"}
        assert {item["result"]["classification"]["time_status"] for item in details} == {
            "at_or_after_baseline",
            "before_baseline",
        }
        assert all(
            item["result"]["classification"]["save_approved"] is False
            and item["result"]["classification"]["queue_eligible"] is False
            and item["result"]["private_observation"]["snapshot"]["queue_eligible"] is False
            for item in details
        )
        starts = sorted(datetime.fromisoformat(item["started_at"]) for item in details)
        assert starts[1] - starts[0] == timedelta(seconds=60)
