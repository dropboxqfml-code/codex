"""The explicit monitor action runs completed-only work outside its UI worker."""

import io
import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from image_monitor import monitor_finish_action as action


def report(status="batch_finish_completed"):
    value = {
        "schema_version": 1,
        "mode": "completed_monitor_batch_local_finish",
        "status": status,
        "last_stage": "complete",
        "error_type": None,
        "reason": action._STATUS_REASONS[status],
        "browser_closed": True,
        "shared_pending_retained": False,
        "close_attempted": True,
        "files_preserved": True,
        "metadata_preserved": True,
        "files_verified": 1,
        "tasks_completed": 1 if status == "batch_finish_completed" else 0,
        "job_counts": {"observed": 1, "completed": 1, "unresolved": 0},
        "saved_files": [
            {
                "saved_filename": "verified.png",
                "detected_format": "PNG",
                "file_size": 125,
                "width": 32,
                "height": 16,
                "frames": 1,
            }
        ],
    }
    if status == "batch_finish_cancelled":
        value["error_type"] = "KeyboardInterrupt"
    if status == "batch_finish_manual_review":
        value["error_type"] = "NativeUIError"
    if status in {"batch_finish_no_pending", "batch_finish_busy"}:
        value.update(
            browser_closed=None,
            close_attempted=False,
            files_verified=0,
            saved_files=[],
        )
        value.pop("job_counts")
    if status == "batch_finish_busy":
        value.update(last_stage="pending_check", shared_pending_retained=None)
    return value


def install_result(monkeypatch, value=None, *, code=0, raw=None, failed=False):
    if raw is None:
        raw = json.dumps(value if value is not None else report()).encode()
    monkeypatch.setattr(action, "_run_child", lambda *args: (code, raw, failed, False))


class FakeProcess:
    def __init__(self, value=None, *, code=0, on_wait=None):
        self.stdout = io.BytesIO(json.dumps(value if value is not None else report()).encode())
        self.stderr = io.BytesIO(b"private diagnostic never exposed")
        self.code = code
        self.on_wait = on_wait
        self.waits = 0

    def wait(self, *, timeout):
        self.waits += 1
        if self.on_wait is not None:
            self.on_wait(self)
        return self.code

    def kill(self):
        pytest.fail("A started finish must never be killed")

    def terminate(self):
        pytest.fail("A started finish must never be terminated")

    def send_signal(self, *_):
        pytest.fail("A started finish must never receive cancellation input")


def test_child_command_has_only_the_three_fixed_roots_and_no_console(tmp_path, monkeypatch):
    process = FakeProcess()
    calls = []

    def popen(arguments, **options):
        calls.append((arguments, options))
        return process

    monkeypatch.setattr(action.subprocess, "Popen", popen)
    monkeypatch.setattr(action.sys, "platform", "win32")
    monkeypatch.setattr(action.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    roots = [tmp_path / name for name in ("watch ; no shell", "legacy", "batch")]
    assert action.run_completed_finish(*roots) == report()
    assert len(calls) == 1
    arguments, options = calls[0]
    assert arguments == [
        sys.executable,
        "-m",
        "image_monitor",
        "monitor-batch-finish",
        "--watch-root",
        str(roots[0]),
        "--legacy-root",
        str(roots[1]),
        "--work-root",
        str(roots[2]),
    ]
    assert options == {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "shell": False,
        "close_fds": True,
        "creationflags": 0x08000000,
    }
    assert process.waits == 1


@pytest.mark.parametrize("stop_on_call", [1, 2, 3])
def test_stop_before_launch_does_not_create_a_child(monkeypatch, stop_on_call):
    calls = 0

    def should_stop():
        nonlocal calls
        calls += 1
        return calls >= stop_on_call

    monkeypatch.setattr(action.subprocess, "Popen", lambda *a, **kw: pytest.fail("No launch"))
    result = action.run_completed_finish("watch", "legacy", "batch", should_stop=should_stop)
    assert result["status"] == "batch_finish_cancelled"
    assert result["reason"] == "cancelled"


def test_late_stop_waits_for_completion_and_preserves_actual_evidence(monkeypatch):
    stopped = threading.Event()

    def on_wait(process):
        if process.waits == 1:
            stopped.set()
            raise subprocess.TimeoutExpired("fixed finish", 0.1)

    process = FakeProcess(on_wait=on_wait)
    monkeypatch.setattr(action.subprocess, "Popen", lambda *a, **kw: process)
    result = action.run_completed_finish("watch", "legacy", "batch", should_stop=stopped.is_set)
    assert stopped.is_set()
    assert process.waits == 2
    assert result == report()


def test_soft_deadline_does_not_kill_or_replace_late_completion(monkeypatch):
    process = FakeProcess()
    monkeypatch.setattr(action.subprocess, "Popen", lambda *a, **kw: process)
    monkeypatch.setattr(action, "_SOFT_TIMEOUT_SECONDS", 0)
    result = action.run_completed_finish("watch", "legacy", "batch")
    assert result.pop("completion_wait_exceeded") is True
    assert result == report()
    assert process.waits == 1


@pytest.mark.parametrize(
    ("status", "code"),
    [
        ("batch_finish_completed", 0),
        ("batch_finish_no_pending", 0),
        ("batch_finish_busy", 0),
        ("batch_finish_manual_review", 2),
        ("batch_finish_cancelled", 130),
    ],
)
def test_legitimate_review_and_cancellation_exit_codes_are_parsed(monkeypatch, status, code):
    value = report(status)
    install_result(monkeypatch, value, code=code)
    assert action.run_completed_finish("watch", "legacy", "batch") == value


@pytest.mark.parametrize("code", [1, 2, 3, 130, -9])
def test_exit_code_must_match_the_claimed_result(monkeypatch, code):
    install_result(monkeypatch, code=code)
    result = action.run_completed_finish("watch", "legacy", "batch")
    assert result["status"] == "batch_finish_manual_review"
    assert result["reason"] == "completed_finish_action_failed"


@pytest.mark.parametrize(
    "raw",
    [
        b"not JSON /private/profile https://private.example",
        b"[]",
        b"{}{}",
        b'\xff{"private":"value"}',
        b'{"schema_version":1,"schema_version":1}',
        json.dumps(report()).replace('"width": 32', '"width": 32.0').encode(),
        json.dumps(report()).replace('"width": 32', '"width": NaN').encode(),
        json.dumps(report()).replace('"width": 32', '"width": Infinity').encode(),
        json.dumps(report()).replace('"width": 32', '"width": 1e3').encode(),
        json.dumps(report()).replace('"width": 32', '"width": 32,"width": 32').encode(),
        b" " * (action._STDOUT_LIMIT + 1),
    ],
)
def test_malformed_ambiguous_and_unbounded_json_fails_closed(monkeypatch, raw):
    install_result(monkeypatch, raw=raw)
    result = action.run_completed_finish("watch", "legacy", "batch")
    assert result == action._fallback()
    assert "private" not in json.dumps(result)


@pytest.mark.parametrize(
    "change",
    [
        {"mode": "monitor_save_batch"},
        {"status": "unknown"},
        {"reason": "https://private.example/reason"},
        {"error_type": "/private/profile"},
        {"last_stage": "https://private.example/stage"},
        {"report_path": "/private/report.json"},
        {"browser_profile": "/private/profile"},
        {"schema_version": True},
        {"browser_closed": 1},
        {"shared_pending_retained": "False"},
        {"close_attempted": 0},
        {"files_preserved": False},
        {"metadata_preserved": 1},
        {"files_verified": True},
        {"files_verified": 3},
        {"tasks_completed": 2},
        {"tasks_completed": 0},
        {"saved_files": [report()["saved_files"][0]] * 3},
        {"job_counts": {"observed": 1, "completed": 1, "unresolved": 1}},
        {"job_counts": {"observed": 1, "completed": True, "unresolved": 0}},
        {"job_counts": {"observed": 1, "completed": 1, "unresolved": 0, "private": 1}},
    ],
)
def test_report_fields_and_counts_are_strict_and_private_values_never_escape(monkeypatch, change):
    install_result(monkeypatch, report() | change)
    assert action.run_completed_finish("watch", "legacy", "batch") == action._fallback()


@pytest.mark.parametrize(
    "change",
    [
        {"saved_filename": "../private.png"},
        {"saved_filename": r"C:\private\image.png"},
        {"saved_filename": "private.png:stream"},
        {"saved_filename": "line\nbreak.png"},
        {"saved_filename": "unpaired\ud800.png"},
        {"saved_filename": ".."},
        {"saved_filename": "x" * 256},
        {"detected_format": "https://private.example/format"},
        {"file_size": -1},
        {"width": 0},
        {"height": True},
        {"frames": 0},
        {"path": "/private/image.png"},
        {"sha256": "private-hash"},
    ],
)
def test_only_safe_file_metadata_crosses_the_process_boundary(monkeypatch, change):
    value = report()
    value["saved_files"][0].update(change)
    install_result(monkeypatch, value)
    assert action.run_completed_finish("watch", "legacy", "batch") == action._fallback()


def test_start_failure_does_not_expose_the_exception_or_retry(monkeypatch):
    calls = []

    def denied(*args, **kwargs):
        calls.append(args)
        raise OSError("/private/profile https://private.example")

    monkeypatch.setattr(action.subprocess, "Popen", denied)
    assert action.run_completed_finish("watch", "legacy", "batch") == action._fallback()
    assert len(calls) == 1


def test_drainer_thread_resource_failure_prevents_launch_and_releases_started_reader(monkeypatch):
    original_thread = threading.Thread
    readers = []

    class ResourceLimitedThread(original_thread):
        def start(self):
            readers.append(self)
            if len(readers) == 2:
                raise RuntimeError("cannot start new thread")
            return super().start()

    monkeypatch.setattr(action.threading, "Thread", ResourceLimitedThread)
    monkeypatch.setattr(action.subprocess, "Popen", lambda *a, **kw: pytest.fail("No launch"))
    assert action.run_completed_finish("watch", "legacy", "batch") == action._fallback()
    assert len(readers) == 2
    assert not readers[0].is_alive()


def test_unexpected_post_launch_failure_still_waits_for_owned_child_cleanup(monkeypatch):
    process = FakeProcess()

    def broken_clock():
        raise RuntimeError("private clock implementation details")

    monkeypatch.setattr(action.subprocess, "Popen", lambda *a, **kw: process)
    monkeypatch.setattr(action.time, "monotonic", broken_clock)
    assert action.run_completed_finish("watch", "legacy", "batch") == action._fallback()
    assert process.waits == 1
    assert process.stdout.closed and process.stderr.closed


def test_real_pipes_are_drained_even_after_both_capture_limits_are_exceeded():
    # Writing more than pipe capacity to each stream catches a reader which
    # stops at its budget and deadlocks the other pipe or process.wait().
    script = (
        "import os\nfor _ in range(128):\n os.write(1, b'x' * 8192)\n os.write(2, b'y' * 8192)\n"
    )
    code, raw, failed, exceeded = action._run_child([sys.executable, "-c", script], None)
    assert code == 0
    assert len(raw) == action._STDOUT_LIMIT
    assert failed is True
    assert exceeded is False
    assert action._STDOUT_LIMIT + action._STDERR_LIMIT <= 128 * 1024


def test_incomplete_capture_fails_closed_even_with_a_valid_json_prefix(monkeypatch):
    install_result(monkeypatch, failed=True)
    assert action.run_completed_finish("watch", "legacy", "batch") == action._fallback()


def test_actual_child_runs_on_its_main_thread_when_called_from_a_monitor_worker(
    tmp_path, monkeypatch
):
    package = tmp_path / "stub" / "image_monitor"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "__main__.py").write_text(
        "import json, os, sys, threading\n"
        "from pathlib import Path\n"
        "assert threading.current_thread() is threading.main_thread()\n"
        "assert len(sys.argv) == 8\n"
        "assert sys.argv[1] == 'monitor-batch-finish'\n"
        "assert sys.argv[2::2] == ['--watch-root', '--legacy-root', '--work-root']\n"
        "proof = {'pid': os.getpid(), 'main_thread': True, 'arguments': sys.argv[1:]}\n"
        "(Path(sys.argv[3]) / 'child-proof.json').write_text(json.dumps(proof))\n"
        f"print({json.dumps(report())!r})\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PYTHONPATH", str(package.parent))
    roots = [tmp_path / name for name in ("watch", "legacy", "batch")]
    roots[0].mkdir()
    with ThreadPoolExecutor(max_workers=1) as worker:
        result = worker.submit(action.run_completed_finish, *roots).result(timeout=15)
    assert result == report()
    proof = json.loads((roots[0] / "child-proof.json").read_text())
    assert proof["main_thread"] is True
    assert proof["pid"] != os.getpid()
    assert proof["arguments"][2::2] == list(map(str, roots))


def test_adapter_import_does_not_import_native_runtime_in_the_worker(tmp_path):
    script = (
        "import sys\n"
        "from image_monitor.monitor_finish_action import run_completed_finish\n"
        "assert callable(run_completed_finish)\n"
        "assert 'image_monitor.monitor_batch_finish' not in sys.modules\n"
        "assert 'image_monitor.native_ui' not in sys.modules\n"
        "assert 'image_monitor.completed_browser_close' not in sys.modules\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        timeout=15,
        check=False,
        cwd=Path(__file__).parents[1],
    )
    assert completed.returncode == 0, completed.stderr.decode()
