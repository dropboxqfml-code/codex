"""Restore a monitor slot only when the exact scan's owned browser closed."""

import json
from pathlib import Path

import pytest
from test_watch_runtime import (
    BrowserFactory,
    FakeClock,
    ScriptedBrowser,
    baseline_outcome,
    link,
    new_posts_outcome,
    observed,
    snapshot,
)

from image_monitor import watch_runtime as runtime
from image_monitor.queue import QueueStore
from image_monitor.watch_store import MONITOR_SCOPE, WatchStore


@pytest.fixture(autouse=True)
def controlled_backends(monkeypatch):
    monkeypatch.setattr(runtime, "require_windows", lambda: None)


def recorded(root, factory, *, scope=MONITOR_SCOPE):
    report = runtime.run_watch_trial(root, clock=FakeClock(), backend_factory=factory, scope=scope)
    database = root / "watch.sqlite"
    with QueueStore(database, read_only=True) as queue:
        latest = WatchStore(queue).get_state(scope)["latest_scan"]
    return database, latest, report


@pytest.mark.parametrize("partial", [False, True])
def test_final_monitor_report_confirms_only_its_last_scan(tmp_path, partial):
    second = (
        observed(
            lambda now: snapshot([104, 103], now, links=[link(2)]),
            lambda now: snapshot([102, 101], now, page=2, links=[link(3)]),
        )
        if partial
        else new_posts_outcome
    )
    database, latest, report = recorded(tmp_path, BrowserFactory(baseline_outcome, second))
    assert latest["complete"] is not partial
    assert runtime.confirmed_monitor_scan(database, latest)
    with QueueStore(database, read_only=True) as queue:
        earlier = WatchStore(queue).list_scans(MONITOR_SCOPE)[-1]
    assert not runtime.confirmed_monitor_scan(database, earlier)
    shared = json.dumps(runtime.share_watch_report(report))
    assert latest["scan_id"] not in shared and Path(report["report_path"]).parent.name not in shared


def test_legacy_or_unrelated_trial_has_no_restorable_monitor_receipt(tmp_path):
    database, latest, report = recorded(
        tmp_path, BrowserFactory(baseline_outcome, new_posts_outcome), scope=runtime.DEFAULT_SCOPE
    )
    assert "monitor_run_id" not in latest["result"]["control"]
    assert "closed_monitor_scan" not in report
    assert not runtime.confirmed_monitor_scan(database, latest)


@pytest.mark.parametrize("failure", ["uncertain", "interrupted", "error"])
def test_unfinished_shutdown_after_a_committed_scan_cannot_confirm_cleanup(tmp_path, failure):
    class IncompleteShutdown(ScriptedBrowser):
        def __exit__(self, *_):
            if failure == "uncertain":
                return
            self.browser_closed = True
            if failure == "interrupted":
                raise KeyboardInterrupt
            raise RuntimeError("test shutdown failure")

    def factory(*_, **__):
        return IncompleteShutdown([baseline_outcome, new_posts_outcome])

    database, latest, report = recorded(tmp_path, factory)
    assert latest["complete"] and latest["generation"] == 2
    assert "closed_monitor_scan" not in report
    assert not runtime.confirmed_monitor_scan(database, latest)


def test_missing_wrong_or_modified_final_report_cannot_confirm_cleanup(tmp_path):
    database, latest, report = recorded(
        tmp_path, BrowserFactory(baseline_outcome, new_posts_outcome)
    )
    path = Path(report["report_path"])
    other = {**report["closed_monitor_scan"], "scan_id": "0" * 32}
    for altered in (
        report | {"closed_monitor_scan": other},
        report | {"browser_closed": False},
        report | {"status": "watch_test_cancelled"},
        report | {"error_type": "RuntimeError"},
        report | {"next_eligible_at_local": "2000-01-01T00:00:00+00:00"},
    ):
        path.write_text(json.dumps(altered), encoding="utf-8")
        assert not runtime.confirmed_monitor_scan(database, latest)
    path.write_bytes(b"invalid")
    assert not runtime.confirmed_monitor_scan(database, latest)
    path.unlink()
    assert not runtime.confirmed_monitor_scan(database, latest)
    latest["result"]["control"].pop("monitor_run_id")
    assert not runtime.confirmed_monitor_scan(database, latest)
