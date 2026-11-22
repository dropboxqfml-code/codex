"""Use the list-only launcher and real routed Chromium to resume a stored page-four bookmark."""

import json
import shutil
import sys
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

import pytest
from test_monitor_auto_review_integration import prime_historical_gap
from test_monitor_gap_followup_integration import listing
from test_monitor_inspection_retry_integration import deadline_chrome, page_rows
from test_monitor_long_gap import read_state
from test_watch_runtime import FakeClock, link
from test_watch_trial_browser import list_html, special_row

from image_monitor import __main__ as cli
from image_monitor import monitor_auto_session, watch_browser, watch_runtime
from image_monitor.monitor_auto_discovery import run_auto_discovery
from image_monitor.queue import QueueStore
from image_monitor.watch_store import MONITOR_SCOPE, WatchStore

DATE_CELL = '<td class="gall_date">12:00</td>'


def dated_list_chrome(variant, visits, unexpected):
    urls = {link(n)["canonical_url"]: n for n in (1, 2, 4, 5)}
    ad = special_row("광고", "/fixture/ad", has_writer=False).replace(DATE_CELL, "")
    notice = special_row("공지", "/board/view/?id=comic_new6&amp;no=1").replace(DATE_CELL, "")
    survey = special_row("설문", "javascript:void(0)")

    class ListChrome(watch_browser.HeadlessWatchBrowser):
        def __enter__(self):
            super().__enter__()

            def route_list(route):
                request = route.request
                if not request.is_navigation_request() or request.url not in urls:
                    unexpected.append(request.url)
                    route.abort()
                    return
                n = urls[request.url]
                visits.append(n)
                html = list_html(
                    page_rows(n),
                    link(n + 1)["canonical_url"],
                    excluded_html=ad + notice + survey if n == 1 else survey,
                    extra_page_urls=[link(4)["canonical_url"]] if n == 2 else [],
                )
                if variant == "ordinary_missing" and n == 1:
                    row = '<td class="gall_writer">Invented author</td>' + DATE_CELL
                    html = html.replace(row, '<td class="gall_writer">Invented author</td>', 1)
                if variant == "ambiguous_survey" and n == 1:
                    html = html.replace(
                        survey, special_row("설문", "/unconfirmed/survey").replace(DATE_CELL, "")
                    )
                route.fulfill(content_type="text/html; charset=utf-8", body=html)

            self._page.context.route("**/*", route_list)
            return self

    return ListChrome


@pytest.mark.parametrize("variant", ["recognized", "ordinary_missing", "ambiguous_survey"])
def test_reopen_list_recovery_with_three_special_rows(tmp_path, monkeypatch, capsys, variant):
    pytest.importorskip("playwright.sync_api")
    if sys.platform != "win32":
        executable = shutil.which("chromium") or shutil.which("google-chrome")
        if not executable:
            pytest.skip("Installed Chromium unavailable")
        monkeypatch.setattr(watch_browser, "require_windows", lambda: None)
        monkeypatch.setattr(watch_runtime, "require_windows", lambda: None)
        monkeypatch.setattr(watch_browser, "browser_executable", lambda _: Path(executable))

    watch = tmp_path / "watch"
    clock = FakeClock(datetime.now(UTC))
    prime_historical_gap(watch, clock, monkeypatch)
    segment = listing([page_rows(n) for n in range(1, 5)], [])(
        watch, clock=clock, interval_seconds=60
    )
    assert segment["recovery_status"] == "segment_queued" and segment["new_candidates"] == 80
    clock.wait(60)
    prior_visits, unexpected = [], []
    old_browser = deadline_chrome(clock, prior_visits, [], unexpected, True)
    previous = run_auto_discovery(
        watch,
        clock=clock,
        interval_seconds=60,
        run_cycle=partial(watch_runtime.run_watch_trial, backend_factory=old_browser),
    )
    assert prior_visits == [[1, 2, 4, 5]] and previous["review"]["failed_page"] == 5
    assert previous["review"]["snapshot_page_numbers"] == [1, 2, 4]
    checkpoint, prior_candidates = read_state(watch)
    clock.wait(60)

    visits = []
    backend = dated_list_chrome(variant, visits, unexpected)
    scan = partial(
        run_auto_discovery,
        run_cycle=partial(watch_runtime.run_watch_trial, backend_factory=backend),
    )
    monkeypatch.setattr(
        monitor_auto_session,
        "run_auto_monitor",
        partial(
            monitor_auto_session.run_auto_monitor,
            clock=clock,
            scan_runner=scan,
        ),
    )
    monkeypatch.setattr(
        sys, "argv", ["image-monitor", "test-list-recovery", "--watch-root", str(watch)]
    )
    code = cli.main()
    report = json.loads(capsys.readouterr().out)
    assert not unexpected
    assert report["mode"] == "list_recovery_test" and report["browser_closed"] is True
    assert report["previous_list_review"]["failed_page"] == 5
    assert [c["recovery_depth"] for c in report["previous_list_checks"]] == [4]
    assert (
        report["new_details_checked"]
        == report["native_save_tasks_started"]
        == report["files_verified"]
        == 0
    )
    assert report["last_collection"] is None and report["inspection_retries_scheduled"] == 0
    current_checkpoint, candidates = read_state(watch)
    assert current_checkpoint == checkpoint and prior_candidates.items() <= candidates.items()
    with QueueStore(watch / "watch.sqlite", read_only=True) as queue:
        state = WatchStore(queue).get_state(MONITOR_SCOPE)
        pages = state["latest_scan"]["result"]["private_observation"]["pages"]
        assert queue.summary()["jobs"] == queue.summary()["posts"] == 0
    if variant == "recognized":
        assert (code, report["status"]) == (0, "auto_monitor_completed"), report
        assert visits == [1, 2, 4, 5] and report["list_checks"] == 1
        assert (
            report["last_list"]["recovery_depth"] == 5
            and report["last_list"]["status"] == "partial"
        )
        [shown] = report["last_list"]["date_cell_checks"]
        assert (shown["visit"], shown["page"], shown["layout_status"]) == (1, 1, "site_verified")
        assert (shown["ordinary_rows"], shown["excluded_rows"]) == (20, 3)
        expected_mismatches = {"ad": {"missing": 1}, "pinned": {"missing": 1}}
        assert shown["date_cell_mismatches"] == expected_mismatches
        assert shown["date_cells"] == {
            "ordinary_rows_with_one": 20,
            "excluded_rows_counted": 3,
            "row_cell_total": 21,
            "table_cell_total": 21,
            "table_check": "matches_rows",
        }
        assert len(pages[0]["rows"]) == 20 and len(pages[0]["excluded_rows"]) == 3
        assert pages[0]["layout_status"] == "site_verified"
        assert report["new_candidates"] == 20
        assert candidates.keys() - prior_candidates.keys() == {str(post) for post in page_rows(5)}
    else:
        assert (code, report["status"]) == (2, "auto_monitor_review"), report
        assert visits == [1] and report["list_checks"] == report["new_candidates"] == 0
        assert candidates == prior_candidates and pages[0]["layout_status"] == "unverified"
        failure = report["last_list"]["review"]
        assert failure["visited_page_numbers"] == [1] and failure["stage"] == "partial_check"
        assert failure["evidence"] == "committed_scan"
        [problem] = failure["pages"]
        assert problem["profile_issue"] == "row_date_count" and problem["unsafe_exclusions"] == 1
        role = "ambiguous_row_fields" if variant == "ordinary_missing" else "other_excluded"
        assert problem["date_cell_mismatches"] == {
            "ad": {"missing": 1},
            "pinned": {"missing": 1},
            role: {"missing": 1},
        }
        counts = problem["date_cells"]
        assert counts["ordinary_rows_with_one"] == (19 if variant == "ordinary_missing" else 20)
        assert counts["row_cell_total"] == counts["table_cell_total"] == 20
        monkeypatch.setattr(
            sys, "argv", ["image-monitor", "monitor-diagnosis", "--work-root", str(watch)]
        )
        assert cli.main() == 0
        stored = json.loads(capsys.readouterr().out)
        [offline] = stored["previous_list_review"]["pages"]
        assert offline == problem
        assert (
            stored["list_diagnosis"]["pages"][0]["date_cell_mismatches"]
            == problem["date_cell_mismatches"]
        )
