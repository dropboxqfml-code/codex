"""The dashboard runs one fixed, user-approved native save per request."""

import io
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from image_monitor import monitor_save_action as action


def completed():
    return {
        "status": "monitor_batch_completed",
        "reason": None,
        "tasks_started": 1,
        "tasks_completed": 1,
        "files_verified": 2,
        "browser_closed": True,
    }


def batch_report(file_count=2):
    return {
        "schema_version": 1,
        "mode": "bounded_monitor_candidate_native_batch",
        "status": "monitor_batch_completed",
        "last_stage": "complete",
        "max_tasks": 1,
        "tasks_started": 1,
        "tasks_completed": 1,
        "saved_files": [{"saved_filename": "PRIVATE"} for _ in range(file_count)],
        "browser_closed": True,
        "shared_pending_retained": False,
        "report_path": "PRIVATE",
    }


@pytest.mark.parametrize("file_count", [2, 10])
def test_dashboard_cli_sets_one_attempt_and_prints_only_counts(tmp_path, monkeypatch, file_count):
    from types import SimpleNamespace

    roots = [tmp_path / name for name in ("watch & 1", "legacy", "batch")]
    calls = []

    def run(*args, max_tasks, should_stop):
        calls.append((args, max_tasks, should_stop()))
        return batch_report(file_count)

    monkeypatch.setitem(
        sys.modules, "image_monitor.monitor_batch_runtime", SimpleNamespace(run_monitor_batch=run)
    )
    read_fd, write_fd = os.pipe()
    with os.fdopen(read_fd, "rb") as stream, os.fdopen(write_fd, "wb", buffering=0) as control:
        control.write(action._START)
        result = action.run_dashboard_child(*roots, stream=stream)
        assert result == completed() | {"files_verified": file_count}
    assert calls == [(tuple(roots), 1, False)]


def test_dashboard_launch_uses_fixed_absolute_paths_and_protocol(monkeypatch, tmp_path):
    calls = []
    roots = [tmp_path / "watch $(id)", tmp_path / "old", tmp_path / "batch"]

    def run(args, should_stop, *, start_line):
        calls.append((args, start_line))
        return 0, json.dumps(completed()).encode(), False, True

    monkeypatch.setattr(action, "_run_child", run)
    assert action.run_dashboard_save(*roots) == completed()
    args, token = calls.pop()
    assert not calls
    assert args == [
        sys.executable,
        "-m",
        "image_monitor",
        "monitor-save-one",
        "--watch-root",
        str(roots[0]),
        "--legacy-root",
        str(roots[1]),
        "--work-root",
        str(roots[2]),
    ]
    assert token == action._START


@pytest.mark.parametrize(
    ("update", "code"),
    [
        ({"status": "monitor_batch_failed"}, 2),
        ({"reason": "/private"}, 0),
        ({"tasks_started": True}, 0),
        ({"tasks_completed": 2}, 0),
        ({"files_verified": 0}, 0),
        ({"files_verified": 11}, 0),
        ({"browser_closed": False}, 0),
        ({"error_type": "/private"}, 0),
        ({}, 2),
        ({"status": "monitor_batch_waiting", "reason": "persisted_cooldown"}, 0),
    ],
)
def test_untrusted_or_inconsistent_child_report_requests_review(monkeypatch, update, code):
    report = completed() | update
    monkeypatch.setattr(
        action, "_run_child", lambda *a, **kw: (code, json.dumps(report).encode(), False, False)
    )
    assert action.run_dashboard_save("watch", "legacy", "batch") == action._fallback()


@pytest.mark.parametrize(
    "raw",
    [b"{}", b"junk", b" " * 1025, b'{"reason":null,"reason":null}', b'{"tasks_completed":1.0}'],
)
def test_invalid_protocol_report_stays_private(monkeypatch, raw):
    monkeypatch.setattr(action, "_run_child", lambda *a, **kw: (0, raw, False, False))
    assert action.run_dashboard_save("watch", "legacy", "batch") == action._fallback()


def test_completed_but_deleted_is_distinct_from_saving_files():
    result = completed() | {
        "reason": "candidate_unavailable",
        "files_verified": 0,
        "tasks_completed": 0,
    }
    assert action.validate_save_result(result) is result


def test_dashboard_child_rejects_batch_or_ambiguous_completion():
    for changes in [
        {"max_tasks": 2},
        {"max_tasks": True},
        {"mode": "other"},
        {"shared_pending_retained": True},
        {"last_stage": "native_post_worker"},
    ]:
        with pytest.raises(ValueError):
            action._single_result(batch_report() | changes)


def test_stop_before_child_launch_and_missing_parent_authorization(monkeypatch):
    monkeypatch.setattr(action, "_run_child", lambda *a, **kw: pytest.fail("child launched"))
    assert action.run_dashboard_save("a", "b", "c", should_stop=lambda: True) == action._fallback(
        cancelled=True
    )
    assert action.run_dashboard_child("a", "b", "c", stream=io.BytesIO(b"")) == action._fallback(
        cancelled=True
    )


def test_parent_pipe_eof_reaches_child_before_native_commit(tmp_path):
    # The child stands in for local verification before a native commit. Closing
    # the pipe must ask it to return without signalling or terminating it.
    ready = tmp_path / "ready"
    script = """
import sys, time
from pathlib import Path
from image_monitor.monitor_save_action import _watch_parent
stop = _watch_parent(sys.stdin.buffer)
Path(sys.argv[1]).touch()
deadline = time.monotonic()+10
while not stop() and time.monotonic() < deadline:
    time.sleep(0.01)
print("cooperatively stopped" if stop() else "timed out", flush=True)
"""
    args = [sys.executable, "-c", script, str(ready)]
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(action._run_child, args, ready.is_file, start_line=action._START)
        code, output, failed, _ = result.result(timeout=20)
    assert code == 0 and not failed
    assert output.strip() == b"cooperatively stopped"


def test_standalone_single_command_without_parent_does_not_create_roots(tmp_path):
    roots = [tmp_path / name for name in ("watch", "old", "batch")]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "image_monitor",
            "monitor-save-one",
            "--watch-root",
            str(roots[0]),
            "--legacy-root",
            str(roots[1]),
            "--work-root",
            str(roots[2]),
        ],
        input=b"",
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 130
    assert json.loads(result.stdout) == action._fallback(cancelled=True)
    assert not any(p.exists() for p in roots)
