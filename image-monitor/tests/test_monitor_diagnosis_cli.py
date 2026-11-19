"""Read an old watch failure through the actual offline CLI and Windows wrapper."""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_monitor_save_cmd import WINDOWS, copy_launcher, run_cmd
from test_search_list import URL, profile_row, reviewed_raw, row

from image_monitor import PUBLIC_VERSION
from image_monitor.monitor_diagnosis import PROFILE_GAP
from image_monitor.queue import QueueStore
from image_monitor.search_list import parse_list_snapshot
from image_monitor.watch_store import MONITOR_SCOPE, WatchStore

PROJECT = Path(__file__).resolve().parents[1]


def stored_failure(root, *, excluded_author_mismatch=False):
    root.mkdir(parents=True)
    if excluded_author_mismatch:
        ordinary = [profile_row(n) for n in range(120, 100, -1)]
        missing = row("공지", is_pinned=True, field_counts={"number": 1, "author": 0, "date": 1})
        raw = reviewed_raw([missing, row("광고", is_ad=True), row("광고", is_ad=True), *ordinary])
        raw["diagnostics"]["list_candidates"][0]["writer_field_count"] = 22
    else:
        raw = reviewed_raw()
        raw["rows"][0]["author_raw"] = ""
    raw["rows"][0]["links"][0]["text_raw"] = "PRIVATE_FIXTURE_ROW"
    page = parse_list_snapshot(
        raw, expected_url=URL, observed_at=datetime(2026, 11, 19, tzinfo=UTC)
    )
    # alpha.2 retained the observations but had no explicit profile failure field.
    page["layout_status"] = "unverified"
    page["selector_evidence"].pop("profile_issue", None)
    with QueueStore(root / "watch.sqlite") as queue:
        WatchStore(queue).persist_scan(
            MONITOR_SCOPE,
            observed_at=datetime(2026, 11, 19, tzinfo=UTC),
            expected_generation=0,
            scan_result={
                "gap_reason": PROFILE_GAP,
                "private_observation": {"status": "observed", "http_status": 200, "pages": [page]},
            },
            checkpoint={"anchor_ids": []},
            complete=False,
            gap_reason=PROFILE_GAP,
            candidates=[],
        )


@pytest.mark.parametrize(
    ("state", "expected", "code"),
    [
        ("previous", "diagnosis_found", 0),
        ("previous_exclusion", "diagnosis_found", 0),
        ("missing", "watch_database_missing", 0),
        ("empty", "no_saved_diagnosis", 0),
        ("broken", "diagnosis_read_failed", 2),
    ],
)
def test_offline_cli_reads_bounded_existing_data(tmp_path, state, expected, code):
    root = tmp_path / "retained records"
    if state in {"previous", "previous_exclusion"}:
        stored_failure(root, excluded_author_mismatch=state == "previous_exclusion")
    elif state == "empty":
        root.mkdir()
        with QueueStore(root / "watch.sqlite"):
            pass
    elif state == "broken":
        root.mkdir()
        (root / "watch.sqlite").write_bytes(b"private unreadable fixture")
    path = root / "watch.sqlite"
    before = path.read_bytes() if path.is_file() else None
    result = subprocess.run(
        [sys.executable, "-m", "image_monitor", "monitor-diagnosis", "--work-root", str(root)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    assert result.returncode == code, result.stderr
    assert not result.stderr
    report = json.loads(result.stdout)
    assert report["program_version"] == PUBLIC_VERSION and report["status"] == expected
    if state == "previous":
        assert report["list_diagnosis"]["pages"][0]["profile_issue"] == "ordinary_author_missing"
    elif state == "previous_exclusion":
        page = report["list_diagnosis"]["pages"][0]
        assert (page["ordinary_rows"], page["excluded_rows"], page["unsafe_exclusions"]) == (
            20,
            3,
            0,
        )
        assert page["profile_issue"] == "row_author_count"
        assert page["author_cell_mismatches"] == {"pinned": {"missing": 1}}
    else:
        assert report["list_diagnosis"] is None
    assert str(root) not in result.stdout and "PRIVATE_FIXTURE_ROW" not in result.stdout
    if before is None:
        assert not root.exists()
    else:
        assert path.read_bytes() == before


def launcher_after_setup(dispatch):
    # Keep the real TXT and mode dispatch, substituting the installed interpreter
    # for the pinned uv invocation. Capture the Notepad request without opening a UI.
    central = (PROJECT / "RUN_WINDOWS_TEST.cmd").read_text("ascii")
    central = central.replace(
        'if not exist "pyproject.toml" goto missing_project', "goto fixture_dispatch", 1
    ).replace(dispatch, ":fixture_dispatch\n" + dispatch + "\nexit /b 93", 1)
    invocation = (
        '"%UV_EXE%" --no-progress run --locked --extra windows --python 3.12.14 '
        "--managed-python image-monitor monitor-diagnosis"
    )
    assert central.count(invocation) == 1
    central = central.replace(invocation, '"%FIXTURE_PYTHON%" -m image_monitor monitor-diagnosis')
    return central.replace('start "" notepad.exe "%LOG_FILE%"', 'echo OPEN_RESULT="%LOG_FILE%"')


@WINDOWS
def test_double_click_diagnosis_dispatches_offline_cli_to_a_single_result_txt(tmp_path):
    central = launcher_after_setup('if "%MONITOR_DIAGNOSIS%"=="1" goto read_monitor_diagnosis')
    folder = tmp_path / "bundle with spaces"
    copy_launcher(folder, central)
    wrapper = folder / "CHECK_LAST_LIST.cmd"
    wrapper.write_bytes((PROJECT / wrapper.name).read_bytes())
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(tmp_path / "local data")
    env["FIXTURE_PYTHON"] = sys.executable
    stored_failure(Path(env["LOCALAPPDATA"]) / "ImageMonitorWatch")
    result = run_cmd(wrapper, [], environment=env)
    assert result.returncode == 0, result.stderr
    [log] = folder.glob("WINDOWS_TEST_RESULT-*.txt")
    content = log.read_text("utf-8")
    assert '"status": "diagnosis_found"' in content and "RESULT: STORED_LIST_DIAGNOSIS" in content
    assert "STAGE: stored_list_diagnosis" in content and "PRIVATE_FIXTURE_ROW" not in content


@WINDOWS
@pytest.mark.parametrize("history", ["previous", "broken", "missing"])
def test_watch_launcher_adds_optional_history_then_runs_live_trial_in_one_txt(tmp_path, history):
    central = launcher_after_setup('if "%WATCH_TEST%"=="1" goto start_watch_test')
    # The fresh trial uses a fixture so the launcher test does not visit the site.
    watch = (
        '"%UV_EXE%" --no-progress run --locked --extra windows --python 3.12.14 '
        "--managed-python image-monitor watch-test"
    )
    assert central.count(watch) == 1
    central = central.replace(watch, '"%FIXTURE_PYTHON%" -c "print(\'LIVE_TRIAL_RAN\')"')
    folder = tmp_path / "watch fixture"
    copy_launcher(folder, central)
    wrapper = folder / "RUN_WATCH_TEST.cmd"
    wrapper.write_bytes((PROJECT / wrapper.name).read_bytes())
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(tmp_path / "local data")
    env["FIXTURE_PYTHON"] = sys.executable
    root = Path(env["LOCALAPPDATA"]) / "ImageMonitorWatch"
    if history == "previous":
        stored_failure(root, excluded_author_mismatch=True)
    elif history == "broken":
        root.mkdir(parents=True)
        (root / "watch.sqlite").write_bytes(b"unreadable fixture")
    result = run_cmd(wrapper, [], environment=env)
    assert result.returncode == 0, result.stderr
    [log] = folder.glob("WINDOWS_TEST_RESULT-*.txt")
    assert [line for line in result.stdout.splitlines() if line.startswith("OPEN_RESULT=")] == [
        f'OPEN_RESULT="{log}"'
    ]
    content = log.read_text("utf-8")
    before_live, live = content.split("STAGE: watch_test")
    assert "LIVE_TRIAL_RAN" in live and "BOUNDED_LIST_WATCH_TRIAL" in live
    if history == "missing":
        assert "historical_monitor_list_diagnosis" not in content
        assert not root.exists()
    else:
        status = "diagnosis_found" if history == "previous" else "diagnosis_read_failed"
        assert "STAGE: historical_monitor_list_diagnosis" in before_live
        assert f'"status": "{status}"' in before_live
        code = 0 if history == "previous" else 2
        assert f"Historical diagnosis exit code: {code}" in before_live
        if history == "previous":
            assert '"profile_issue": "row_author_count"' in before_live
            assert '"pinned"' in before_live and "PRIVATE_FIXTURE_ROW" not in content
