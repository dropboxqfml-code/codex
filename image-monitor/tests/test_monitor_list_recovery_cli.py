"""The one-click live list check uses the saved monitor and never opens a post."""

import json
import sys
from functools import partial

import pytest
from test_monitor_gap_followup_integration import listing
from test_watch_runtime import FakeClock

from image_monitor import __main__, monitor_auto_session, watch_runtime
from image_monitor.monitor_auto_session import run_auto_monitor
from image_monitor.queue import QueueStore


def invoke(watch, monkeypatch):
    monkeypatch.setattr(
        sys, "argv", ["image-monitor", "test-list-recovery", "--watch-root", str(watch)]
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
