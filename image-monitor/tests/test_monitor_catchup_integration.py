"""Run the list-only catch-up CLI twice on the same watch, with an offline search feed."""

import json
import os
import subprocess
import sys
from contextlib import redirect_stdout
from datetime import timedelta
from functools import partial
from io import StringIO
from pathlib import Path

import pytest
from test_monitor_gap_followup_integration import listing
from test_monitor_long_gap import read_state
from test_monitor_recent_tail_integration import due_clock, enable_chrome
from test_watch_runtime import FakeClock, link
from test_watch_trial_browser import list_html

from image_monitor import __main__ as cli
from image_monitor import monitor_auto_session, watch_browser, watch_runtime
from image_monitor.monitor_auto_discovery import run_auto_discovery

PAGE_SIZE = 20
FEED = [*range(497, 222, -1), *range(100, 55, -1)]


def seed_open_gap(watch):
    clock = FakeClock()
    assert listing([[100, 99]], [])(watch, clock=clock, interval_seconds=60)["status"] == "baseline"
    original = [i for i in FEED if i <= 400 and i != 399]
    # Earlier scans already saw 69 arrivals, but could not verify the displaced old head.
    held_feed = [*range(469, 400, -1), *(i for i in original if i not in {400, 398, 397})]
    for feed, count in ((original, 2), (original, 3), (original, 4), (held_feed, 4)):
        clock.wait(60)
        pages = [feed[n * PAGE_SIZE : (n + 1) * PAGE_SIZE] for n in range(count)]
        result = listing(pages, [])(watch, clock=clock, interval_seconds=60)
        assert result["status"] == "partial", result
    assert result["recovery_status"] == "held" and result["new_candidates"] == 69


def run_catchup(watch):
    # Start early on purpose. A wait carried over from another process must not burn a scan.
    clock = due_clock(watch)
    clock.current -= timedelta(seconds=12)
    started = clock.now()
    trace, visits, unexpected = [], [], []
    page_by_url = {link(n)["canonical_url"]: n for n in range(1, 17)}

    class OfflineChrome(watch_browser.HeadlessWatchBrowser):
        def __enter__(self):
            super().__enter__()

            def serve(route):
                page = page_by_url.get(route.request.url)
                if not route.request.is_navigation_request() or page is None:
                    unexpected.append(route.request.url)
                    route.abort()
                    return
                visits.append(page)
                offset = (page - 1) * PAGE_SIZE
                body = list_html(FEED[offset : offset + PAGE_SIZE], link(page + 1)["canonical_url"])
                route.fulfill(status=200, content_type="text/html; charset=utf-8", body=body)

            self._page.context.route("**/*", serve)
            return self

    def scan(root, **kwargs):
        visits.clear()
        previous, known = read_state(root)
        result = run_auto_discovery(
            root,
            **kwargs,
            run_cycle=partial(watch_runtime.run_watch_trial, backend_factory=OfflineChrome),
        )
        assert not unexpected, unexpected
        if visits:
            checkpoint, found = read_state(root)
            assert known.items() <= found.items()
            new = set(found) - known.keys()
            assert len(new) == result["new_candidates"]
            assert (checkpoint != previous) == (result["status"] == "complete")
            trace.append(
                {
                    "pages": visits.copy(),
                    "elapsed": (clock.now() - started).total_seconds(),
                    "new": sorted(new),
                }
            )
        else:
            assert result["reason"] == "persisted_cooldown" and read_state(root) == (
                previous,
                known,
            )
        return result

    def forbid_collection(*args, **kwargs):
        pytest.fail("List-only recovery invoked the detail/native collector")

    with pytest.MonkeyPatch.context() as patch:
        enable_chrome(patch)
        patch.setattr(
            monitor_auto_session,
            "run_auto_monitor",
            partial(
                monitor_auto_session.run_auto_monitor,
                clock=clock,
                scan_runner=scan,
                collect_runner=forbid_collection,
            ),
        )
        patch.setattr(
            sys,
            "argv",
            ["image-monitor", "test-list-recovery", "--watch-root", str(watch), "--catch-up"],
        )
        output = StringIO()
        with redirect_stdout(output):
            code = cli.main()
    assert code == 0, output.getvalue()
    return json.loads(output.getvalue()), trace


def fresh_process(watch):
    run = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json,sys; from pathlib import Path; "
            "from test_monitor_catchup_integration import run_catchup; "
            "print(json.dumps(run_catchup(Path(sys.argv[1]))))",
            str(watch),
        ],
        cwd=Path(__file__).parent,
        env=os.environ | {"PYTHONUTF8": "1"},
        capture_output=True,
        encoding="utf-8",
        timeout=120,
    )
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


def assert_public_checks(report, trace):
    assert report["status"] == "auto_monitor_completed", report
    assert report["max_cycles"] == 8 and report["interval_seconds"] == 60
    assert report["list_checks"] == report["cycles_completed"] == len(trace)
    checks = report["recent_list_checks"]
    assert [item["visited_page_numbers"] for item in checks] == [t["pages"] for t in trace]
    assert all(item["pages_checked"] == item["page_limit"] == 4 for item in checks)
    assert [item["new_candidates"] for item in checks] == [len(t["new"]) for t in trace]
    assert report["new_candidates"] == sum(len(t["new"]) for t in trace)
    assert [t["elapsed"] for t in trace] == [12 + 60 * n for n in range(len(trace))]
    assert (
        report["new_details_checked"]
        == report["native_save_tasks_started"]
        == report["files_verified"]
        == 0
    )
    assert report["last_collection"] is None and report["browser_closed"] is True


def test_two_catchup_processes_confirm_full_gap_without_duplicating_discoveries(
    tmp_path, monkeypatch
):
    pytest.importorskip("playwright.sync_api")
    enable_chrome(monkeypatch)
    watch = tmp_path / "이전 기록"
    seed_open_gap(watch)
    checkpoint, seeded = read_state(watch)

    first, trace = run_catchup(watch)
    assert_public_checks(first, trace)
    assert first["reason"] == "cycle_limit_reached" and len(trace) == 8
    assert trace[0]["pages"] == [1, 2, 3, 4] and set(trace[0]["new"]) == {
        str(i) for i in range(470, 498)
    }
    assert trace[1]["pages"] == [1, 2, 4, 5] and trace[1]["new"] == ["399"]
    assert [item["recovery_status"] for item in first["recent_list_checks"][:2]] == [
        "segment_queued",
        "advanced",
    ]
    initial = first["recent_list_checks"][0]
    assert (
        initial["recovery_observation"] == "disjoint_recent_rows"
        and initial["recovery_observation_ko"]
    )
    assert first["gap_followups_completed"] == 0
    assert all(item["status"] == "partial" for item in first["recent_list_checks"])
    saved, after_first = read_state(watch)
    assert saved == checkpoint and seeded.items() <= after_first.items()

    second, resumed = fresh_process(watch)
    assert_public_checks(second, resumed)
    assert second["reason"] == "list_coverage_confirmed" and 1 <= len(resumed) < 8
    frontier = trace[-1]["pages"][-1]
    assert resumed[0]["pages"] == [1, 2, frontier, frontier + 1]
    assert all(item["status"] == "partial" for item in second["recent_list_checks"][:-1])
    assert second["recent_list_checks"][-2]["recovery_status"] == "overlap_pending"
    assert (
        second["last_list"]["recovery_status"] == "completed"
        and second["gap_followups_completed"] == 1
    )
    anchor = FEED.index(100) // PAGE_SIZE + 1
    assert resumed[-2]["pages"][-1] == anchor
    assert resumed[-1]["pages"] == [1, 2, anchor, anchor + 1]

    latest, found = read_state(watch)
    assert latest["anchor_ids"][0] == "497" and after_first.items() <= found.items()
    assert set(found) == {str(i) for i in FEED if i > 100}
