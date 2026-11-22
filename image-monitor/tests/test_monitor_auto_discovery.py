"""The automatic session may hand off only its own verified single list scan."""

import json
from datetime import timedelta
from pathlib import Path

import pytest
from test_watch_runtime import (
    BrowserFactory,
    FakeClock,
    baseline_outcome,
    http_failure,
    link,
    new_posts_outcome,
    no_browser,
    observed,
    snapshot,
    unverified_second_page,
)

from image_monitor import watch_runtime
from image_monitor.monitor_auto_discovery import run_auto_discovery
from image_monitor.queue import QueueStore
from image_monitor.watch_lock import watch_run_lock


@pytest.fixture(autouse=True)
def windows(monkeypatch):
    monkeypatch.setattr(watch_runtime, "require_windows", lambda: None)


def scan(root, clock, outcome, *, interval=60, transform=None):
    factory = BrowserFactory(outcome)

    def cycle(*args, **kwargs):
        report = watch_runtime.run_watch_trial(*args, backend_factory=factory, **kwargs)
        return transform(report) if transform else report

    return run_auto_discovery(root, interval_seconds=interval, clock=clock, run_cycle=cycle)


def preflight(root, clock, interval=60, **kwargs):
    return run_auto_discovery(
        root, interval_seconds=interval, clock=clock, run_cycle=no_browser, **kwargs
    )


def test_first_then_two_complete_turns_and_adjusted_deadline(tmp_path):
    clock = FakeClock()
    first = scan(tmp_path, clock, baseline_outcome)
    assert first == {
        "status": "baseline",
        "reason": None,
        "new_candidates": 0,
        "next_eligible_at": watch_runtime._stamp(clock.now() + timedelta(seconds=60)),
        "browser_closed": True,
        "page_limit": 1,
        "pages_checked": 1,
        "visited_page_numbers": [1],
    }
    clock.wait(60)
    delayed = preflight(tmp_path, clock, interval=180)
    assert delayed["status"] == "waiting" and delayed["browser_closed"] is None
    assert delayed["next_eligible_at"] == watch_runtime._stamp(clock.now() + timedelta(seconds=120))
    clock.wait(120)
    fresh = scan(tmp_path, clock, new_posts_outcome)
    assert (fresh["status"], fresh["new_candidates"]) == ("complete", 2)
    clock.wait(60)
    duplicate = scan(tmp_path, clock, new_posts_outcome)
    assert (duplicate["status"], duplicate["new_candidates"]) == ("complete", 0)


@pytest.mark.parametrize(
    ("outcome", "status", "added"),
    [
        (
            observed(
                lambda t: snapshot([104, 103], t, links=[link()]),
                lambda t: snapshot([102, 101], t, page=2, links=[link(3)]),
            ),
            "partial",
            4,
        ),
        (unverified_second_page, "review", 0),
    ],
)
def test_only_verified_partial_can_proceed(tmp_path, outcome, status, added):
    clock = FakeClock()
    assert scan(tmp_path, clock, baseline_outcome)["status"] == "baseline"
    clock.wait(60)
    result = scan(tmp_path, clock, outcome)
    assert (result["status"], result["new_candidates"]) == (status, added)


@pytest.mark.parametrize(
    "tamper",
    ["cleanup", "missing", "count", "marker", "stale", "navigation", "candidate", "unearned_limit"],
)
def test_unconfirmed_receipt_or_navigation_stops_handoff(tmp_path, tamper):
    old = []

    def keep(report):
        old.append(report)
        return report

    clock = FakeClock()
    assert scan(tmp_path, clock, baseline_outcome, transform=keep)["status"] == "baseline"
    clock.wait(60)

    def transform(report):
        if tamper == "missing":
            Path(report["report_path"]).unlink()
        if tamper == "cleanup":
            report["browser_closed"] = False
        if tamper == "count":
            report["new_candidates"] += 1
        if tamper == "marker":
            report["closed_monitor_scan"] = old[0]["closed_monitor_scan"]
        if tamper == "candidate":
            with QueueStore(tmp_path / "watch.sqlite") as queue:
                queue.connection.execute(
                    "UPDATE watch_candidates SET post_id='500' WHERE post_id='104'"
                )
        if tamper == "unearned_limit":
            with QueueStore(tmp_path / "watch.sqlite") as queue:
                scan_id = report["closed_monitor_scan"]["scan_id"]
                stored = queue.connection.execute(
                    "SELECT result_json FROM watch_scans WHERE scan_id=?", (scan_id,)
                ).fetchone()
                record = json.loads(stored[0])
                record["control"]["follow_up_page_limit"] = 3
                queue.connection.execute(
                    "UPDATE watch_scans SET result_json=? WHERE scan_id=?",
                    (json.dumps(record), scan_id),
                )
        return old[0] if tamper == "stale" else report

    def outcome(stamp):
        data = new_posts_outcome(stamp)
        if tamper == "navigation":
            data["navigation"][1]["url"] = data["pages"][0]["url"]
        return data

    result = scan(tmp_path, clock, outcome, transform=transform)
    assert (result["status"], result["new_candidates"]) == ("review", 0)
    assert result["browser_closed"] is (tamper != "cleanup")


@pytest.mark.parametrize(
    ("http", "expected"), [(429, "waiting"), (503, "waiting"), (403, "blocked")]
)
def test_service_signals_persist_across_reopen(tmp_path, http, expected):
    clock = FakeClock()
    result = scan(tmp_path, clock, http_failure(http, "600"))
    assert result["status"] == expected
    assert result["browser_closed"] is True
    clock.wait(120)
    check = preflight(tmp_path, clock)
    assert (check["status"], check["new_candidates"], check["browser_closed"]) == (
        expected,
        0,
        None,
    )
    assert check["next_eligible_at"] == result["next_eligible_at"]
    assert len(list((tmp_path / "runs").iterdir())) == 1


def test_busy_stop_and_persisted_wait_do_not_create_a_run(tmp_path):
    clock = FakeClock()
    base = tmp_path / "new"
    assert preflight(base, clock, should_stop=lambda: True)["status"] == "cancelled"
    assert not base.exists()
    with watch_run_lock(tmp_path / "watch.sqlite", watch_runtime.DEFAULT_SCOPE):
        assert preflight(tmp_path, clock)["status"] == "busy"
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        queue.defer_service("dcinside", clock.now() + timedelta(days=1))
    assert preflight(tmp_path, clock)["status"] == "waiting"
    assert not (tmp_path / "runs").exists()
