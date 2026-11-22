"""Reconnect a shifted feed using a durable watch, including archived-release upgrades in Git."""

import json
import os
import shutil
import subprocess
import sys
from contextlib import redirect_stdout
from datetime import datetime
from functools import partial
from io import StringIO
from pathlib import Path

import pytest
from test_monitor_gap_followup_integration import listing
from test_monitor_long_gap import read_state
from test_watch_runtime import FakeClock, link
from test_watch_trial_browser import list_html, special_row

from image_monitor import PUBLIC_VERSION, monitor_auto_session, watch_browser, watch_runtime
from image_monitor import __main__ as cli
from image_monitor.monitor_auto_discovery import run_auto_discovery
from image_monitor.queue import QueueStore
from image_monitor.watch_store import MONITOR_SCOPE, WatchStore

RELEASE_DIR = Path(__file__).resolve().parents[2] / "downloads"


def release_archive(release):
    return RELEASE_DIR / f"image-monitor-windows-test-0.5.0-alpha.{release}.zip"


def search_feed(shape):
    rows = list(range(400, 320, -1))
    if shape in ("two_losses", "three_losses"):
        missing = {400, 394} if shape == "two_losses" else {400, 394, 391}
        rows = list(range(469, 400, -1)) + [post for post in rows if post not in missing]
    return rows + list(range(300, 288, -1)) + list(range(100, 55, -1))


def chrome_turn(watch, clock, shape):
    feed = search_feed(shape)
    visits, unexpected = [], []
    numbers = {link(n)["canonical_url"]: n for n in range(1, 13)}
    notice = special_row("공지", "/board/view/?id=comic_new6&amp;no=1")
    ads = "".join(
        special_row("광고", "/fixture/" + name).replace('<td class="gall_date">12:00</td>', "")
        for name in ("first-ad", "second-ad")
    )

    class RoutedChrome(watch_browser.HeadlessWatchBrowser):
        def __enter__(self):
            super().__enter__()

            def serve(route):
                request = route.request
                if not request.is_navigation_request() or request.url not in numbers:
                    unexpected.append(request.url)
                    route.abort()
                    return
                page = numbers[request.url]
                visits.append(page)
                offset = 20 * (page - 1)
                html = list_html(
                    feed[offset : offset + 20],
                    link(page + 1)["canonical_url"],
                    excluded_html=notice + ads if shape == "old_dates" and page == 1 else notice,
                    extra_page_urls=[link(n)["canonical_url"] for n in range(4, 11)]
                    if page == 2
                    else [],
                )
                if shape == "old_inspection" and page == 5:
                    html += "<script>let t=0;performance.now=()=>t+=20000</script>"
                route.fulfill(content_type="text/html; charset=utf-8", body=html)

            self._page.context.route("**/*", serve)
            return self

    scan = partial(
        run_auto_discovery,
        run_cycle=partial(watch_runtime.run_watch_trial, backend_factory=RoutedChrome),
    )
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            monitor_auto_session,
            "run_auto_monitor",
            partial(monitor_auto_session.run_auto_monitor, clock=clock, scan_runner=scan),
        )
        patch.setattr(
            sys, "argv", ["image-monitor", "test-list-recovery", "--watch-root", str(watch)]
        )
        output = StringIO()
        with redirect_stdout(output):
            code = cli.main()
    assert not unexpected, unexpected
    return code, json.loads(output.getvalue()), visits


def enable_chrome(patch):
    if sys.platform != "win32":
        path = shutil.which("chromium") or shutil.which("google-chrome")
        if not path:
            pytest.skip("Installed Chromium unavailable")
        patch.setattr(watch_browser, "require_windows", lambda: None)
        patch.setattr(watch_runtime, "require_windows", lambda: None)
        patch.setattr(watch_browser, "browser_executable", lambda _: Path(path))


def due_clock(watch):
    with QueueStore(watch / "watch.sqlite", read_only=True) as queue:
        state = WatchStore(queue).get_state(MONITOR_SCOPE)
        return FakeClock(
            datetime.fromisoformat(state["latest_scan"]["result"]["control"]["next_eligible_at"])
        )


def prime_depth_four(watch):
    clock = FakeClock()
    assert listing([[100, 99]], [])(watch, clock=clock, interval_seconds=60)["status"] == "baseline"
    for count in (2, 3, 4):
        clock.wait(60)
        rows = search_feed("old")[: count * 20]
        checked = listing([rows[i : i + 20] for i in range(0, len(rows), 20)], [])(
            watch, clock=clock, interval_seconds=60
        )
        assert checked["status"] == "partial", checked


def child_check():
    # The child has only the installed release, watch path, and an offline HTML fixture.
    watch_name, shape = json.load(sys.stdin)
    watch = Path(watch_name)
    with pytest.MonkeyPatch.context() as patch:
        enable_chrome(patch)
        if shape == "prime":
            prime_depth_four(watch)
            # Earlier record: the fourth navigation succeeded, but no fifth-page snapshot completed.
            _, failed, visited = chrome_turn(watch, due_clock(watch), "old_inspection")
            assert failed["last_list"]["review"]["failed_page"] == 5 and visited[-1] == 5
            shape = "old_dates"
        code, report, visits = chrome_turn(watch, due_clock(watch), shape)
    print(json.dumps([code, report, visits]))


def restart(watch, shape, release=None):
    env = os.environ | {"PYTHONUTF8": "1"}
    if release:
        shipped = release_archive(release)
        env["PYTHONPATH"] = str(shipped / "image-monitor" / "src")
    process = subprocess.run(
        [
            sys.executable,
            "-c",
            "from test_monitor_recent_tail_integration import child_check;child_check()",
        ],
        cwd=Path(__file__).parent,
        input=json.dumps([str(watch), shape]),
        capture_output=True,
        encoding="utf-8",
        env=env,
        timeout=90,
    )
    assert process.returncode == 0, process.stderr
    code, report, visits = json.loads(process.stdout)
    assert report["program_version"] == (f"0.5.0-alpha.{release}" if release else PUBLIC_VERSION)
    return code, report, visits


def test_69_current_candidates_then_checked_gap_recovery_after_restart(tmp_path, monkeypatch):
    pytest.importorskip("playwright.sync_api")
    enable_chrome(monkeypatch)
    watch = tmp_path / "watch"
    archives_available = all(release_archive(release).is_file() for release in (14, 15))
    if (RELEASE_DIR.parent / ".git").exists():
        assert archives_available, "Historical release ZIPs are required in the repository checkout"
    if archives_available:
        code, old, visits = restart(watch, "prime", release=14)
        assert code == 2 and visits == [1] and old["status"] == "auto_monitor_review", old
        [p] = old["last_list"]["review"]["pages"]
        assert (
            p["profile_issue"],
            p["ordinary_rows"],
            p["excluded_rows"],
            p["unsafe_exclusions"],
        ) == (
            "row_date_count",
            20,
            3,
            0,
        )
        checkpoint, seeded = read_state(watch)

        code, old, visits = restart(watch, "two_losses", release=15)
        assert old["previous_list_review"]["pages"][0]["date_cell_mismatches"] == {
            "ad": {"missing": 2}
        }
    else:
        # The standalone distribution carries the current release and no historical ZIPs.
        prime_depth_four(watch)
        checkpoint, seeded = read_state(watch)
        code, old, visits = chrome_turn(watch, due_clock(watch), "three_losses")
    assert code == 0 and visits == [1, 2, 3, 4] and old["new_candidates"] == 69, old
    assert old["last_list"]["recovery_status"] == "held" and old["last_list"]["recovery_depth"] == 4
    assert all(
        old[key] == 0
        for key in ("new_details_checked", "native_save_tasks_started", "files_verified")
    )
    original_checkpoint, known = read_state(watch)
    assert original_checkpoint == checkpoint and seeded.items() <= known.items()
    assert known.keys() - seeded.keys() == {str(n) for n in range(401, 470)}

    code, held, visits = chrome_turn(watch, due_clock(watch), "three_losses")
    assert code == 0 and visits == [1, 2, 3, 4] and held["new_candidates"] == 0
    assert (held["last_list"]["recovery_status"], held["last_list"]["recovery_reason"]) == (
        "held",
        "recent_overlap_unconfirmed",
    )
    assert read_state(watch) == (checkpoint, known)

    code, first, visits = chrome_turn(watch, due_clock(watch), "two_losses")
    assert code == 0 and visits == [1, 2, 3, 4] and first["new_candidates"] == 0, first
    assert (first["last_list"]["recovery_status"], first["last_list"]["recovery_reason"]) == (
        "segment_queued",
        "recent_tail_overlap",
    )
    assert first["last_list"]["recovery_depth"] == 4 and read_state(watch) == (checkpoint, known)
    with QueueStore(watch / "watch.sqlite", read_only=True) as queue:
        scan = WatchStore(queue).get_state(MONITOR_SCOPE)["latest_scan"]
        [retained] = scan["result"]["gap_recovery"]["bookmark"]["deferred"]
        assert retained["head_ids"] == [str(n) for n in range(400, 380, -1)]
        assert retained["frontier_ids"] == [str(n) for n in range(340, 320, -1)]
        assert retained["depth"] == 4 and retained["frontier"]["page"] == 4

    code, rejoined, visits = restart(watch, "two_losses")
    assert code == 0 and visits == [1, 2, 4, 5] and rejoined["last_list"]["recovery_depth"] == 5, (
        rejoined
    )
    assert rejoined["last_list"]["recovery_status"] == "segment_rejoined"
    assert read_state(watch)[0] == checkpoint
    for boundary in (5, 6, 7, 8):
        code, report, visits = chrome_turn(watch, due_clock(watch), "two_losses")
        assert code == 0 and visits == [1, 2, boundary, boundary + 1], report
        current, found = read_state(watch)
        assert (
            known.items() <= found.items() and len(found) == len(known) + report["new_candidates"]
        )
        known = found
        assert (report["last_list"]["status"] == "complete") == (boundary == 8)
        assert (current == checkpoint) == (boundary < 8)
        assert (
            report["native_save_tasks_started"]
            == report["files_verified"]
            == report["new_details_checked"]
            == 0
        )
    assert set(known) == {str(n) for n in search_feed("two_losses") if n > 100} | set(seeded)
