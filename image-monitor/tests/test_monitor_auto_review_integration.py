"""Reopen an interrupted continuous monitor after a new gap segment and one empty detail."""

import json
import os
import shutil
import subprocess
import sys
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path

import pytest
from test_candidate_runtime import BrowserFactory as DetailBrowser
from test_monitor_gap_followup_integration import listing, saved_state
from test_monitor_long_gap import read_state
from test_watch_image_search import body
from test_watch_runtime import BrowserFactory, FakeClock, link, observed, snapshot
from test_watch_trial_browser import list_html

from image_monitor import __main__ as cli
from image_monitor import (
    candidate_runtime,
    monitor_auto_session,
    monitor_batch_runtime,
    monitor_operations,
    watch_browser,
    watch_runtime,
)
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.monitor_auto_discovery import run_auto_discovery
from image_monitor.monitor_auto_session import run_auto_monitor
from image_monitor.monitor_collect import collect_session_turn
from image_monitor.queue import QueueStore
from image_monitor.watch_store import MONITOR_SCOPE


def prime_historical_gap(watch, clock, monkeypatch):
    with monkeypatch.context() as legacy:
        legacy.setattr(watch_runtime, "PUBLIC_VERSION", "0.5.0-alpha.11")
        for numbers, content in [
            ([1], [[100]]),
            ([1, 2], [[150], [149]]),
            ([1, 2, 3], [[150], [149], [148]]),
            ([1, 2, 3, 4], [[150], [149], [148], [147]]),
            ([1, 2, 4, 5], [[150], [149], [147], [146]]),
            ([1, 2, 3, 4], [[200], [199], [198], [197]]),
            ([1, 2, 4, 5], [[200], [199], [197], [196]]),
        ]:
            visits = []
            result = listing(content, visits, page_numbers=numbers)(
                watch, interval_seconds=60, clock=clock, recover_long_gaps=False
            )
            assert result["status"] in {"baseline", "partial"}, result
            assert visits == [link(n)["canonical_url"] for n in numbers]
            clock.wait(60)


def chrome_with_changed_writer_cells(monkeypatch, rows):
    pytest.importorskip("playwright.sync_api")
    if sys.platform != "win32":
        executable = shutil.which("chromium") or shutil.which("google-chrome")
        if not executable:
            pytest.skip("Installed Chromium unavailable")
        monkeypatch.setattr(watch_browser, "require_windows", lambda: None)
        monkeypatch.setattr(watch_browser, "browser_executable", lambda _: Path(executable))

    documents = {
        link(1)["canonical_url"]: list_html(rows[0], link(2)["canonical_url"]),
        link(2)["canonical_url"]: list_html(rows[1], link(3)["canonical_url"]).replace(
            'class="gall_writer"', 'class="unknown_column"'
        ),
    }

    class ChangedChrome(watch_browser.HeadlessWatchBrowser):
        def __enter__(self):
            super().__enter__()

            def serve(route):
                request = route.request
                if request.is_navigation_request() and request.url in documents:
                    route.fulfill(
                        content_type="text/html; charset=utf-8", body=documents[request.url]
                    )
                else:
                    route.abort()

            self._page.context.route("**/*", serve)
            return self

    return ChangedChrome


@pytest.mark.parametrize(
    "real_chrome", [False, True], ids=["unverified_snapshot", "changed_chrome_dom"]
)
def test_segment_queued_empty_detail_then_layout_review_and_offline_report(
    tmp_path, monkeypatch, capsys, real_chrome
):
    watch, legacy, batch = (tmp_path / directory for directory in ("watch", "legacy", "batch"))
    for module in (candidate_runtime, watch_runtime, monitor_batch_runtime):
        monkeypatch.setattr(module, "require_windows", lambda: None)
    monkeypatch.setattr(monitor_operations, "NativeSaveLock", nullcontext)
    monkeypatch.setattr(monitor_operations, "shared_state_path", lambda: tmp_path / "pending.json")

    clock = FakeClock(datetime.now(UTC) + timedelta(seconds=62))
    prime_historical_gap(watch, clock, monkeypatch)
    state, earlier_posts, _ = saved_state(watch)
    checkpoint = state["checkpoint"]
    rows = [list(range(first, first - 20, -1)) for first in (400, 380, 360, 340)]
    visits = []
    capture = listing(rows, visits)
    unverified = observed(
        lambda stamp: snapshot(rows[0], stamp, links=[link()]),
        lambda stamp: snapshot(rows[1], stamp, page=2, layout_status="unverified"),
    )
    backend = (
        chrome_with_changed_writer_cells(monkeypatch, rows)
        if real_chrome
        else BrowserFactory(unverified)
    )
    failed = partial(
        run_auto_discovery,
        run_cycle=partial(watch_runtime.run_watch_trial, backend_factory=backend),
    )
    scans = [capture, failed]

    def discover(*args, **kwargs):
        outcome = scans[0](*args, **kwargs)
        if outcome["status"] != "waiting":
            scans.pop(0)
        return outcome

    def forbidden(*args, **kwargs):
        pytest.fail("A zero-image detail or unverified list cannot start a native task")

    details = DetailBrowser(body(0), body(0))
    collect = partial(
        collect_session_turn,
        detail_runner=partial(candidate_runtime.run_candidate_trial, backend_factory=details),
        save_runner=forbidden,
    )
    with monkeypatch.context() as launch:
        launch.setattr(
            sys,
            "argv",
            [
                "image-monitor",
                "auto-monitor",
                "--watch-root",
                str(watch),
                "--legacy-root",
                str(legacy),
                "--work-root",
                str(batch),
            ],
        )
        launch.setattr(
            monitor_auto_session,
            "run_auto_monitor",
            partial(run_auto_monitor, clock=clock, scan_runner=discover, collect_runner=collect),
        )
        assert cli.main() == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "auto_monitor_review", result
    assert result["max_cycles"] is None and result["interval_seconds"] == 60
    assert (
        result["cycles_completed"] == result["list_checks"] == result["new_details_checked"] == 1
    ), result
    assert result["new_candidates"] == 80 and result["native_save_tasks_started"] == 0
    assert result["posts_saved"] == result["files_verified"] == 0 and result["browser_closed"], (
        result
    )
    assert result["last_collection"] == {
        "status": "monitor_collect_limit",
        "reason": "fresh_detail_limit",
        "fresh_detail_outcome": "before_baseline",
        "detail_selection_order": "oldest_discovery",
        "uninspected_at_selection": 89,
        "detail_attempts_at_selection": 1,
    }
    assert [item["historical_reason"] for item in result["previous_list_checks"]] == [
        "previous_head_not_matched",
        "boundary_extended",
    ]
    [recent] = result["recent_list_checks"]
    assert recent["recovery_status"] == "segment_queued" and recent["recovery_depth"] == 4
    assert recent["visited_page_numbers"] == [1, 2, 3, 4]
    assert visits == [link(n)["canonical_url"] for n in (1, 2, 3, 4)]
    after, all_posts, gaps = saved_state(watch)
    assert after["checkpoint"] == checkpoint
    assert set(all_posts) == set(earlier_posts) | {str(i) for i in range(321, 401)}
    assert all(
        all_posts[post]["first_scan_id"] == row["first_scan_id"]
        for post, row in earlier_posts.items()
    )
    with QueueStore(watch / "watch.sqlite", read_only=True) as queue:
        assert len(CandidateDetailStore(queue).list_details(MONITOR_SCOPE)) == 1
        assert queue.summary()["jobs"] == 0
    command = subprocess.run(
        [sys.executable, "-m", "image_monitor", "monitor-diagnosis", "--work-root", str(watch)],
        capture_output=True,
        encoding="utf-8",
        env=os.environ | {"PYTHONUTF8": "1"},
        timeout=20,
        check=True,
    )
    reopened = json.loads(command.stdout)
    assert reopened["status"] == "diagnosis_found", reopened
    live = result["last_list"]["review"]
    assert live["stage"] == "partial_check" and live["evidence"] == "committed_scan", live
    assert live["watch_status"] == "watch_test_partial" and live["watch_stage"] == "persist_scan"
    if real_chrome:
        assert live["gap_reason"] == "list_navigation_unverified"
        failed_page = live["pages"][1]
        assert (
            failed_page["profile_issue"] == "no_ordinary_rows" and failed_page["ordinary_rows"] == 0
        )
        assert failed_page["unsafe_exclusions"] == failed_page["excluded_rows"] == 20
        assert reopened["list_diagnosis"] is None
    else:
        assert live["planner_issue"] == "snapshot_layout"
        assert live["gap_reason"] == "list_profile_unverified_or_incomplete"
        assert reopened["list_diagnosis"]["http_status"] == 200
    assert live["http_status"] == 200
    assert live["visited_page_numbers"] == [1, 2]
    assert [p["layout_status"] for p in live["pages"]] == ["site_verified", "unverified"]
    stored = reopened["previous_list_review"]
    assert live["stage_ko"] and stored["stage_ko"] and stored["stage"] == "stored_scan"
    for key in live.keys() - {"stage", "stage_ko"}:
        assert live[key] == stored[key]
    for private in ("Invented private", "gall.dcinside", "?id=", str(watch)):
        assert private not in json.dumps([result, reopened], ensure_ascii=False)
    assert saved_state(watch) == (after, all_posts, gaps)
    resume_visits = []
    resumed = run_auto_monitor(
        watch,
        legacy,
        batch,
        clock=clock,
        max_cycles=1,
        collect_runner=collect,
        scan_runner=listing(
            [rows[0], rows[1], rows[3], list(range(320, 300, -1))],
            resume_visits,
            page_numbers=[1, 2, 4, 5],
        ),
    )
    assert resumed["status"] == "auto_monitor_completed", (resumed, resume_visits)
    assert resumed["previous_list_review"] == {
        key: value for key, value in stored.items() if not key.endswith("_ko")
    }
    assert resumed["list_checks"] == 1 and resumed["new_candidates"] == 20
    assert resumed["posts_saved"] == resumed["native_save_tasks_started"] == 0
    assert resumed["last_list"]["recovery_depth"] == 5
    assert resume_visits == [link(n)["canonical_url"] for n in (1, 2, 4, 5)]
    final_checkpoint, final_posts = read_state(watch)
    assert final_checkpoint == checkpoint
    assert len(final_posts) == len(all_posts) + 20
    assert all(final_posts[p] == row["first_scan_id"] for p, row in all_posts.items())
