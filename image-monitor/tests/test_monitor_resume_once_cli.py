"""Open a saved monitoring session in a fresh CLI while the service is still cooling down."""

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta

from test_monitor_controller import AutoClock
from test_monitor_gap_continuation import partial_pages, run_scan, seed_baseline

from image_monitor import PUBLIC_VERSION, watch_runtime
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.queue import QueueStore
from image_monitor.watch_store import MONITOR_SCOPE, WatchStore

OFFLINE_CLI = """
import runpy, sys
def offline(event, args):
    if event in {"socket.connect", "subprocess.Popen", "os.startfile", "webbrowser.open"}:
        raise AssertionError("The waiting command tried to navigate or open a browser")
sys.addaudithook(offline)
runpy.run_module("image_monitor", run_name="__main__", alter_sys=True)
"""


def test_cli_leaves_a_long_server_wait_and_its_unspent_detail_intact(tmp_path, monkeypatch):
    monkeypatch.setattr(watch_runtime, "require_windows", lambda: None)
    root = tmp_path / "감시 data"
    clock = AutoClock()
    clock.current = datetime.now(UTC) - timedelta(minutes=5)
    seed_baseline(root, clock)
    assert run_scan(root, clock, partial_pages)["recent_pages_verified"]
    deadline = datetime.now(UTC) + timedelta(minutes=5)
    database = root / "watch.sqlite"
    with QueueStore(database) as queue:
        queue.defer_service(watch_runtime.SERVICE_SCOPE, deadline)
        before = WatchStore(queue).get_state(MONITOR_SCOPE)
        candidates = WatchStore(queue).list_candidates(MONITOR_SCOPE)

    finished = subprocess.run(
        [sys.executable, "-B", "-c", OFFLINE_CLI, "monitor-resume-once", "--work-root", str(root)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert finished.returncode == 0, finished.stderr
    report = json.loads(finished.stdout)
    assert (
        report["program_version"] == PUBLIC_VERSION and report["status"] == "monitor_resume_waiting"
    )
    assert datetime.fromisoformat(report["next_eligible_at"]) == deadline
    assert report["details_checked"] == 0 and report["detail"] is None
    assert report["worker_stopped"] and report["resume_detail_pending"]
    assert before["latest_scan"]["scan_id"] not in finished.stdout
    with QueueStore(database, read_only=True) as queue:
        assert WatchStore(queue).get_state(MONITOR_SCOPE) == before
        assert WatchStore(queue).list_candidates(MONITOR_SCOPE) == candidates
        assert CandidateDetailStore(queue).list_details(MONITOR_SCOPE) == []
