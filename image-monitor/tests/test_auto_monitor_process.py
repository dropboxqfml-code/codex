"""Verify the double-click session's CLI with an occupied lease or a server cooldown."""

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta

from test_monitor_resume_once_cli import OFFLINE_CLI

from image_monitor import PUBLIC_VERSION
from image_monitor.queue import QueueStore
from image_monitor.watch_lock import watch_run_lock
from image_monitor.watch_runtime import SERVICE_SCOPE
from image_monitor.watch_store import MONITOR_SCOPE, WatchStore


def run_trial(parent):
    run = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            OFFLINE_CLI,
            "auto-monitor",
            "--max-cycles",
            "2",
            "--watch-root",
            str(parent / "watch"),
            "--legacy-root",
            str(parent / "legacy"),
            "--work-root",
            str(parent / "managed"),
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        encoding="utf-8",
        timeout=20,
    )
    assert run.returncode == 0, (run.stderr, run.stdout)
    report = json.loads(run.stdout)
    assert report["program_version"] == PUBLIC_VERSION
    assert report["cycles_completed"] == report["files_verified"] == 0
    assert not (parent / "legacy").exists() and not (parent / "managed").exists()
    return report


def test_other_process_holds_dashboard_lease_so_no_second_session_starts(tmp_path):
    watch = tmp_path / "watch"
    watch.mkdir()
    database = watch / "watch.sqlite"
    with watch_run_lock(database, MONITOR_SCOPE, purpose="monitor"):
        assert run_trial(tmp_path)["status"] == "auto_monitor_busy"
    assert not database.exists()


def test_bounded_session_exits_before_long_stored_cooldown_without_network(tmp_path):
    watch = tmp_path / "watch"
    watch.mkdir()
    database = watch / "watch.sqlite"
    due = datetime.now(UTC).replace(microsecond=0) + timedelta(hours=2)
    with QueueStore(database) as queue:
        queue.defer_service(SERVICE_SCOPE, due)
        before = WatchStore(queue).get_state(MONITOR_SCOPE)
    report = run_trial(tmp_path)
    assert report["status"] == "auto_monitor_waiting"
    assert datetime.fromisoformat(report["next_eligible_at"]) == due
    with QueueStore(database, read_only=True) as queue:
        assert WatchStore(queue).get_state(MONITOR_SCOPE) == before
        assert queue.summary()["posts"] == queue.summary()["jobs"] == 0
