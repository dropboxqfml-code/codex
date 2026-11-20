"""The packaged auto-collection command must be harmless on an unused PC."""

import json
import subprocess
import sys

from test_monitor_resume_once_cli import OFFLINE_CLI

from image_monitor import PUBLIC_VERSION


def test_no_watch_data_needs_no_browser_directory_or_native_input(tmp_path):
    parent = tmp_path / "감시 & 저장"
    paths = [parent / name for name in ("watch", "legacy", "managed")]
    run = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            OFFLINE_CLI,
            "auto-collect-once",
            "--watch-root",
            str(paths[0]),
            "--legacy-root",
            str(paths[1]),
            "--work-root",
            str(paths[2]),
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        encoding="utf-8",
        timeout=20,
    )
    assert run.returncode == 0, run.stderr
    report = json.loads(run.stdout)
    assert report["program_version"] == PUBLIC_VERSION
    assert report["status"] == "monitor_collect_no_candidates"
    assert report["reason"] == "existing_watch_database_required"
    assert report["native_save_tasks_started"] == report["new_details_checked"] == 0
    assert report["files_verified"] == 0 and report["browser_closed"] is True
    assert not parent.exists()
