import json
from functools import partial
from pathlib import Path

import pytest
from test_watch_runtime import FakeClock

from image_monitor import watch_runtime
from image_monitor.monitor_auto_discovery import run_auto_discovery
from image_monitor.monitor_list_attempt import uncommitted_list_review
from image_monitor.monitor_list_review import previous_list_review
from image_monitor.queue import QueueStore
from image_monitor.watch_browser import HeadlessWatchBrowser
from image_monitor.watch_store import MONITOR_SCOPE, WatchStore


@pytest.fixture
def failing_scan(monkeypatch):
    monkeypatch.setattr(watch_runtime, "require_windows", lambda: None)

    def enter(self):
        self.browser_closed = False
        return self

    def fail(self, *args, **kwargs):
        raise TimeoutError("private browser exception and URL")

    def close(self, *args):
        self.browser_closed = True

    monkeypatch.setattr(HeadlessWatchBrowser, "__enter__", enter)
    monkeypatch.setattr(HeadlessWatchBrowser, "scan", fail)
    monkeypatch.setattr(HeadlessWatchBrowser, "__exit__", close)


def test_default_worker_explains_its_own_zero_cycle_failure(tmp_path, failing_scan):
    result = run_auto_discovery(tmp_path, interval_seconds=60, clock=FakeClock())
    assert result["status"] == "review" and result["new_candidates"] == 0
    assert result["review"] == {
        "stage": "watch_result",
        "evidence": "worker_report",
        "watch_status": "watch_test_failed",
        "watch_stage": "list_observation",
        "error_type": "TimeoutError",
    }
    assert "private" not in json.dumps(result)
    assert previous_list_review(tmp_path) is None


def test_uncommitted_failure_requires_direct_worker_and_exact_local_receipt(tmp_path, failing_scan):
    database = tmp_path / "watch.sqlite"
    with QueueStore(database) as queue:
        before = WatchStore(queue).get_state(MONITOR_SCOPE)
    runner = partial(watch_runtime.run_watch_trial, backend_factory=HeadlessWatchBrowser)
    clock = FakeClock()
    raw = runner(
        tmp_path, "chrome", cycles=1, scope=MONITOR_SCOPE, clock=clock, follow_up_gaps=True
    )
    with QueueStore(database, read_only=True) as queue:
        after = WatchStore(queue).get_state(MONITOR_SCOPE)

    def review(report, *, after_state=after, worker=runner):
        return uncommitted_list_review(database, before, after_state, report, run_cycle=worker)

    assert review(raw)["evidence"] == "worker_report"
    assert review(raw, after_state=after | {"generation": 1}) is None
    assert review(raw | {"browser_closed": False}) is None
    assert review(raw | {"cycles_completed": 1}) is None
    assert review(raw | {"last_stage": "persist_scan"}) is None
    assert review(raw | {"report_path": str(tmp_path / "wrong" / "report.json")}) is None
    clock.wait(60)
    stale = run_auto_discovery(
        tmp_path, interval_seconds=60, clock=clock, run_cycle=lambda *a, **k: raw
    )
    assert stale["review"] == {"stage": "watch_result"}
    assert review(raw, worker=lambda *a, **k: raw) is None
    path = Path(raw["report_path"])
    path.write_text("{", encoding="utf-8")
    assert review(raw) is None
    path.unlink()
    assert review(raw) is None
