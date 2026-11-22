"""Exercise a fourth-document inspection failure and its bounded retry in real Chromium."""

import json
import shutil
import subprocess
import sys
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from threading import Event

import pytest
from test_candidate_runtime import BrowserFactory as DetailBrowser
from test_monitor_auto_review_integration import prime_historical_gap
from test_monitor_gap_followup_integration import listing
from test_monitor_long_gap import read_state
from test_watch_image_search import body
from test_watch_runtime import FakeClock, link
from test_watch_trial_browser import list_html, special_row

from image_monitor import (
    candidate_runtime,
    monitor_batch_runtime,
    monitor_operations,
    watch_browser,
    watch_runtime,
)
from image_monitor.monitor_auto_discovery import run_auto_discovery
from image_monitor.monitor_auto_session import run_auto_monitor
from image_monitor.monitor_collect import collect_session_turn
from image_monitor.monitor_list_review import previous_list_review
from image_monitor.queue import QueueStore
from image_monitor.watch_store import MONITOR_SCOPE, WatchStore


def page_rows(page):
    highest = 400 - (page - 1) * 20
    return list(range(highest, highest - 20, -1))


def deadline_chrome(clock, visits, launched, unexpected, second_failure):
    notice = special_row("공지", "/board/view/?id=comic_new6&amp;no=1")
    # Exercise the real extraction deadline without stalling a hosted Windows runner.
    slow_dom = "<script>let t = 0; performance.now = () => (t += 20000)</script>"
    routes = (1, 2, 4, 5)
    urls = {link(n)["canonical_url"]: n for n in routes}

    class OfflineChrome(watch_browser.HeadlessWatchBrowser):
        def __enter__(self):
            super().__enter__()
            visit = []
            visits.append(visit)
            launched.append(clock.now())
            attempt = len(visits)

            def serve(route):
                request = route.request
                if request.is_navigation_request() and request.url in urls:
                    number = urls[request.url]
                    visit.append(number)
                    fails = attempt == 1 or second_failure
                    rows = page_rows(number)
                    if number in (1, 2) and fails:
                        # A transient new post disappears before the next healthy check.
                        # Its uniquely identified first-page observation remains durable.
                        rows = [post + 1 for post in rows]
                    content = list_html(
                        rows,
                        link(number + 1)["canonical_url"],
                        excluded_html=notice,
                        extra_page_urls=[link(4)["canonical_url"]] if number == 2 else [],
                    )
                    if number == 5 and fails:
                        content += slow_dom
                    route.fulfill(content_type="text/html; charset=utf-8", body=content)
                else:
                    unexpected.append(request.url)
                    route.abort()

            self._page.context.route("**/*", serve)
            return self

    return OfflineChrome


def reopened_list_check():
    """A fresh interpreter receives only its existing watch path and current clock."""
    watch, timestamp = json.load(sys.stdin)
    clock = FakeClock(datetime.fromisoformat(timestamp))
    visits, launched, unexpected = [], [], []
    if sys.platform != "win32":
        path = shutil.which("chromium") or shutil.which("google-chrome")
        watch_browser.browser_executable = lambda _: Path(path)
        watch_browser.require_windows = watch_runtime.require_windows = lambda: None
    backend = deadline_chrome(clock, visits, launched, unexpected, True)
    scan = partial(
        run_auto_discovery,
        run_cycle=partial(watch_runtime.run_watch_trial, backend_factory=backend),
    )
    result = run_auto_monitor(
        Path(watch), None, None, max_cycles=1, list_only=True, clock=clock, scan_runner=scan
    )
    print(json.dumps([result, visits, [stamp.isoformat() for stamp in launched], unexpected]))


@pytest.mark.parametrize("outcome", ["resumes", "stops_after_retry", "stops_after_restart"])
def test_partial_gap_dom_budget_exhaustion_then_one_whole_list_retry(
    tmp_path, monkeypatch, outcome
):
    second_failure = outcome != "resumes"
    pytest.importorskip("playwright.sync_api")
    if sys.platform != "win32":
        path = shutil.which("chromium") or shutil.which("google-chrome")
        if not path:
            pytest.skip("Installed Chromium unavailable")
        monkeypatch.setattr(watch_browser, "require_windows", lambda: None)
        monkeypatch.setattr(watch_browser, "browser_executable", lambda _: Path(path))
    for module in (watch_runtime, candidate_runtime, monitor_batch_runtime):
        monkeypatch.setattr(module, "require_windows", lambda: None)
    monkeypatch.setattr(monitor_operations, "NativeSaveLock", nullcontext)
    monkeypatch.setattr(monitor_operations, "shared_state_path", lambda: tmp_path / "pending.json")
    watch, legacy, batch = [tmp_path / folder for folder in ("watch", "legacy", "batch")]
    clock = FakeClock(datetime.now(UTC) + timedelta(seconds=1))
    prime_historical_gap(watch, clock, monkeypatch)
    queued = listing([page_rows(n) for n in range(1, 5)], [])(
        watch, clock=clock, interval_seconds=60
    )
    assert queued["recovery_status"] == "segment_queued" and queued["new_candidates"] == 80
    checkpoint, candidates = read_state(watch)
    clock.wait(60)
    with QueueStore(watch / "watch.sqlite", read_only=True) as queue:
        generation = WatchStore(queue).get_state(MONITOR_SCOPE)["generation"]

    visits, launched, failed, unexpected = [], [], [], []
    routes = [1, 2, 4, 5]
    OfflineChrome = deadline_chrome(clock, visits, launched, unexpected, second_failure)

    def discover(*args, **kwargs):
        turn = run_auto_discovery(
            *args,
            **kwargs,
            run_cycle=partial(watch_runtime.run_watch_trial, backend_factory=OfflineChrome),
        )
        if turn["status"] == "review" or turn["reason"] == "inspection_retry_due":
            unchanged_checkpoint, found = read_state(watch)
            assert unchanged_checkpoint == checkpoint and candidates.items() <= found.items()
            assert found.keys() - candidates.keys() == {"401"}, turn
            with QueueStore(watch / "watch.sqlite", read_only=True) as queue:
                current = WatchStore(queue).get_state(MONITOR_SCOPE)
                assert current["generation"] == generation + len(failed) + 1
                first = queue.connection.execute(
                    "SELECT generation FROM watch_scans WHERE scan_id=?", (found["401"],)
                ).fetchone()
                assert first[0] == generation + 1
                assert turn["new_candidates"] == 0  # The failed turn never authorizes a collection.
                assert not current["latest_scan"]["complete"] and not queue.summary()["jobs"]
                control = current["latest_scan"]["result"]["control"]
                deadline = datetime.fromisoformat(control["next_eligible_at"])
            failed.append((turn, deadline))
        return turn

    stop = Event()

    def progress(report):
        # Bounded by assertions as well as the scheduler to avoid an endless test on regression.
        if outcome == "stops_after_restart" and report["inspection_retries_scheduled"]:
            stop.set()
        if report["cycles_completed"] == 1 or len(visits) > 2:
            stop.set()

    detail = DetailBrowser(body(0))

    def no_save(*args, **kwargs):
        pytest.fail("An unverified historical list or empty post started native input")

    session = run_auto_monitor(
        watch,
        legacy,
        batch,
        clock=clock,
        scan_runner=discover,
        should_stop=stop.is_set,
        on_progress=progress,
        collect_runner=partial(
            collect_session_turn,
            detail_runner=partial(candidate_runtime.run_candidate_trial, backend_factory=detail),
            save_runner=no_save,
        ),
    )
    assert not unexpected
    first, due = failed[0]
    assert first["status"] == "waiting" and first["reason"] == "inspection_retry_due"
    assert datetime.fromisoformat(first["next_eligible_at"]) == due
    assert session["inspection_retries_scheduled"] == 1
    assert session["last_inspection_retry"] == first["review"]
    if outcome == "stops_after_restart":
        assert session["status"] == "auto_monitor_stopped" and len(failed) == 1
        assert visits == [routes] and clock.now() < due and not detail.calls
        before_restart = read_state(watch)
        child = subprocess.run(
            [
                sys.executable,
                "-c",
                "from test_monitor_inspection_retry_integration import reopened_list_check; "
                "reopened_list_check()",
            ],
            cwd=Path(__file__).parent,
            input=json.dumps([str(watch), clock.now().isoformat()]),
            capture_output=True,
            encoding="utf-8",
            check=True,
            timeout=75,
        )
        result, later_visits, later_starts, other = json.loads(child.stdout)
        assert not other and later_visits == [routes] and len(later_starts) == 1
        assert datetime.fromisoformat(later_starts[0]) >= due
        assert (
            result["status"] == "auto_monitor_review"
            and result["inspection_retries_scheduled"] == 0
        )
        assert (
            result["last_list"]["review"]["inspection_failure"]
            == first["review"]["inspection_failure"]
        )
        assert (
            result["previous_list_review"]["inspection_failure"]
            == first["review"]["inspection_failure"]
        )
        assert result["new_details_checked"] == result["native_save_tasks_started"] == 0
        assert read_state(watch) == before_restart
        with QueueStore(watch / "watch.sqlite", read_only=True) as queue:
            assert WatchStore(queue).get_state(MONITOR_SCOPE)["generation"] == generation + 2
        return
    assert visits == [routes, routes], session
    assert len(failed) == 1 + second_failure
    assert launched[1] >= failed[0][1] >= launched[0] + timedelta(seconds=60)
    for turn, _deadline in failed:
        assert turn["browser_closed"] is True
        review = turn["review"]
        assert review["stage"] == "watch_result" and review["evidence"] == "committed_scan"
        assert (
            review["watch_status"] == "watch_test_failed"
            and review["watch_stage"] == "persist_scan"
        )
        assert (
            review["transport"] == "inspection_error" and review["error_type"] == "DCSnapshotError"
        )
        assert review["gap_reason"] == "list_transport_or_inspection_failure"
        assert review["http_status"] == 200 and review["visited_page_numbers"] == routes
        assert (
            review["snapshot_page_numbers"] == [p["page"] for p in review["pages"]] == routes[:-1]
        )
        assert (review["failed_page"], review["failed_visit"]) == (5, 4)
        failure = review["inspection_failure"]
        assert failure["stage"] == "dom_read" and failure["reason"] == "dom_budget_exceeded"
        for page in review["pages"]:
            assert (
                page["status"],
                page["layout_status"],
                page["ordinary_rows"],
                page["excluded_rows"],
                page["unsafe_exclusions"],
            ) == ("observed", "site_verified", 20, 1, 0)
    assert session["native_save_tasks_started"] == session["files_verified"] == 0
    if second_failure:
        assert session["status"] == "auto_monitor_review" and not detail.calls, session
        assert (
            failed[-1][0]["status"] == "review"
            and session["last_list"]["review"] == failed[-1][0]["review"]
        )
        assert session["list_checks"] == session["new_candidates"] == 0
        saved = previous_list_review(watch)
        assert (
            saved["visited_page_numbers"] == routes
            and saved["pages"] == failed[-1][0]["review"]["pages"]
        )
    else:
        assert session["status"] == "auto_monitor_stopped", session
        assert (
            session["cycles_completed"]
            == session["list_checks"]
            == session["new_details_checked"]
            == 1
        )
        assert session["new_candidates"] == 20 and session["last_list"]["recovery_depth"] == 5
        current_checkpoint, found = read_state(watch)
        assert current_checkpoint == checkpoint and candidates.items() <= found.items()
        assert found.keys() - candidates.keys() == {"401", *(str(n) for n in page_rows(5))}
