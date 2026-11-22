"""The one-click live list check uses the saved monitor and never opens a post."""

import json
import sys
from datetime import timedelta
from functools import partial

import pytest
from test_monitor_auto_session import scan
from test_monitor_gap_followup_integration import listing
from test_watch_runtime import FakeClock

from image_monitor import __main__, monitor_auto_session, watch_runtime
from image_monitor.monitor_auto_session import run_auto_monitor
from image_monitor.queue import QueueStore


def invoke(watch, monkeypatch, *options):
    monkeypatch.setattr(
        sys, "argv", ["image-monitor", "test-list-recovery", "--watch-root", str(watch), *options]
    )
    return __main__.main()


@pytest.mark.parametrize("empty_db", [False, True])
def test_missing_history_leaves_new_scope_unused(tmp_path, empty_db, monkeypatch, capsys):
    watch = tmp_path / "감시 기록"
    if empty_db:
        watch.mkdir()
        with QueueStore(watch / "watch.sqlite"):
            pass
    assert invoke(watch, monkeypatch) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["reason"] == ("no_saved_baseline" if empty_db else "watch_database_missing")
    assert report["list_checks"] == report["native_save_tasks_started"] == 0
    assert not (watch / "runs").exists()
    assert watch.exists() == empty_db


def test_list_only_cli_checks_one_live_list_after_cooldown_without_collection(
    tmp_path, monkeypatch, capsys
):
    watch = tmp_path / "monitor"
    clock = FakeClock()
    monkeypatch.setattr(watch_runtime, "require_windows", lambda: None)
    assert listing([[100]], [])(watch, clock=clock, interval_seconds=60)["status"] == "baseline"
    visits = []

    def forbidden(*args, **kwargs):
        pytest.fail("A list-only check opened a detail or tried to save an image")

    monkeypatch.setattr(
        monitor_auto_session,
        "run_auto_monitor",
        partial(
            run_auto_monitor,
            clock=clock,
            scan_runner=listing([[101, 100], [99]], visits),
            collect_runner=forbidden,
        ),
    )
    assert invoke(watch, monkeypatch) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["mode"] == "list_recovery_test"
    assert report["list_checks"] == report["cycles_completed"] == 1
    assert report["new_candidates"] == 1 and visits
    assert report["new_details_checked"] == report["native_save_tasks_started"] == 0


def recovery_turn(status, *, candidates=0):
    complete = status == "completed"
    bookmark = status in {
        "completed",
        "advanced",
        "frontier_changed",
        "frontier_relocated",
        "segment_rejoined",
        "overlap_pending",
    }
    return scan("complete" if complete else "partial", candidates=candidates) | {
        "page_limit": 4,
        "pages_checked": 4,
        "visited_page_numbers": [1, 2, 4, 5] if bookmark else [1, 2, 3, 4],
        "recovery_status": status,
        "recovery_depth": 5 if bookmark else 4,
        "recovery_route": "bookmark" if bookmark else "recent",
        "recovery_crossed_search_range": False,
        **(
            {"recovery_reason": "frontier_prefix_overlap"} if status == "frontier_relocated" else {}
        ),
    }


@pytest.mark.parametrize(
    ("steps", "reason", "counts", "times"),
    [
        (["completed"], "list_coverage_confirmed", [1], [0]),
        (["held"], "recovery_followup_deferred", [1], [0]),
        (["frontier_changed"], "recovery_followup_deferred", [1], [0]),
        (["segment_queued", "advanced"], "cycle_limit_reached", [1, 2], [0, 60]),
        (["frontier_relocated", "advanced"], "cycle_limit_reached", [1, 2], [0, 60]),
        (["segment_rejoined", "completed"], "list_coverage_confirmed", [1, 2], [0, 60]),
        (["cooldown", "head_rejoined", "advanced"], "cycle_limit_reached", [2, 3], [0, 10, 70]),
        (["inspection_retry_due", "advanced"], "cycle_limit_reached", [2], [0, 60]),
        (["advanced", "inspection_retry_due"], "inspection_retry_due", [1], [0, 60]),
        (["inspection_retry_due", "inspection_retry_due"], "inspection_retry_due", [], [0, 60]),
    ],
)
def test_follow_gap_limits_actual_scans_and_only_follows_verified_progress(
    tmp_path, monkeypatch, capsys, steps, reason, counts, times
):
    watch = tmp_path / "monitor"
    clock = FakeClock()
    monkeypatch.setattr(watch_runtime, "require_windows", lambda: None)
    assert listing([[100]], [])(watch, clock=clock, interval_seconds=60)["status"] == "baseline"
    start = clock.now()
    calls = []

    def scripted(*args, **kwargs):
        step = steps[len(calls)]
        calls.append((clock.now() - start).total_seconds())
        if step in {"cooldown", "inspection_retry_due"}:
            due = clock.now() + timedelta(seconds=10 if step == "cooldown" else 60)
            return scan(
                "waiting",
                due=due.isoformat(),
                reason="persisted_cooldown" if step == "cooldown" else step,
                closed=None if step == "cooldown" else True,
            )
        return recovery_turn(step, candidates=len(calls))

    def forbidden(*args, **kwargs):
        pytest.fail("A list-only test attempted collection")

    monkeypatch.setattr(
        monitor_auto_session,
        "run_auto_monitor",
        partial(run_auto_monitor, clock=clock, scan_runner=scripted, collect_runner=forbidden),
    )
    assert invoke(watch, monkeypatch, "--follow-gap") == 0
    report = json.loads(capsys.readouterr().out)
    assert calls == times
    assert report["reason"] == reason and report["list_test_summary_ko"]
    assert report["status"] == (
        "auto_monitor_waiting" if reason == "inspection_retry_due" else "auto_monitor_completed"
    )
    assert report["list_checks"] == report["cycles_completed"] == len(counts)
    assert [check["new_candidates"] for check in report["recent_list_checks"]] == counts
    assert report["new_candidates"] == sum(counts)
    assert report["new_details_checked"] == report["native_save_tasks_started"] == 0
