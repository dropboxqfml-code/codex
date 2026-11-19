"""Run the existing completed-only finish command on a child main thread.

The monitor worker never imports or calls Windows native UI code. Once the
child starts, stopping the monitor waits for its existing completion and cleanup;
neither cancellation nor the soft deadline terminates a native operation.
"""

import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

FINISH_ACTION_STATUSES = frozenset(
    {
        "batch_finish_completed",
        "batch_finish_no_pending",
        "batch_finish_busy",
        "batch_finish_manual_review",
        "batch_finish_cancelled",
    }
)
FINISH_ACTION_REASONS = frozenset(
    {
        "no_unfinished_batch_tasks",
        "completed_files_reverified_and_batch_resolved",
        "another_scan_owns_this_scope",
        "cancelled",
        "completed_batch_requires_review",
        "completed_finish_action_failed",
    }
)

_MODE = "completed_monitor_batch_local_finish"
_SOFT_TIMEOUT_SECONDS = 120
_WAIT_INTERVAL_SECONDS = 0.1
_READER_JOIN_SECONDS = 2
_STDOUT_LIMIT = 96 * 1024
_STDERR_LIMIT = 32 * 1024
_STAGES = frozenset(
    {
        "pending_check",
        "completed_report_check",
        "local_file_verification",
        "owned_browser_close",
        "final_local_file_verification",
        "clear_completed_pending",
        "complete",
    }
)
_FIELDS = frozenset(
    {
        "schema_version",
        "mode",
        "status",
        "last_stage",
        "error_type",
        "reason",
        "browser_closed",
        "shared_pending_retained",
        "close_attempted",
        "files_preserved",
        "metadata_preserved",
        "files_verified",
        "tasks_completed",
        "saved_files",
    }
)
_FILE_FIELDS = frozenset(
    {"saved_filename", "detected_format", "file_size", "width", "height", "frames"}
)
_STATUS_REASONS = {
    "batch_finish_completed": "completed_files_reverified_and_batch_resolved",
    "batch_finish_no_pending": "no_unfinished_batch_tasks",
    "batch_finish_busy": "another_scan_owns_this_scope",
    "batch_finish_manual_review": "completed_batch_requires_review",
    "batch_finish_cancelled": "cancelled",
}


class _StoppedBeforeLaunch(Exception):
    pass


def _fallback(*, cancelled=False):
    return {
        "schema_version": 1,
        "mode": _MODE,
        "status": "batch_finish_cancelled" if cancelled else "batch_finish_manual_review",
        "last_stage": "pending_check",
        "error_type": None,
        "reason": "cancelled" if cancelled else "completed_finish_action_failed",
        "browser_closed": None,
        "shared_pending_retained": None,
        "close_attempted": False,
        "files_preserved": True,
        "metadata_preserved": True,
        "files_verified": 0,
        "tasks_completed": 0,
        "saved_files": [],
    }


def _requested(should_stop):
    if should_stop is None:
        return False
    try:
        return bool(should_stop())
    except Exception:
        # A broken cancellation source cannot authorize starting more work.
        return True


class _Capture:
    """Keep a fixed prefix while continuing to drain a child's entire pipe."""

    def __init__(self, limit):
        self.limit = limit
        self.data = bytearray()
        self.failed = False
        self.complete = threading.Event()

    def drain(self, pipe):
        try:
            while chunk := pipe.read(8192):
                remaining = self.limit - len(self.data)
                self.data.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    self.failed = True
        except Exception:
            self.failed = True
        finally:
            try:
                pipe.close()
            except Exception:
                self.failed = True
            finally:
                self.complete.set()


def _run_child(arguments, should_stop, *, start_line=None):
    options = {
        "stdin": subprocess.DEVNULL if start_line is None else subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "shell": False,
        "close_fds": True,
    }
    if sys.platform == "win32":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    stdout = _Capture(_STDOUT_LIMIT)
    stderr = _Capture(_STDERR_LIMIT)
    ready = threading.Event()
    pipes = [None, None]

    def drain_when_ready(capture, index):
        ready.wait()
        pipe = pipes[index]
        if pipe is None:
            capture.complete.set()
        else:
            capture.drain(pipe)

    readers = [
        threading.Thread(target=drain_when_ready, args=(stdout, 0), daemon=True),
        threading.Thread(target=drain_when_ready, args=(stderr, 1), daemon=True),
    ]
    started = []
    process = None
    returncode = None
    control = None
    try:
        # Establish both drainers before starting an owned operation. If thread
        # creation fails, no child can fill a pipe and deadlock its cleanup.
        for reader in readers:
            reader.start()
            started.append(reader)
        if _requested(should_stop):
            raise _StoppedBeforeLaunch
        process = subprocess.Popen(arguments, **options)
        pipes[:] = [process.stdout, process.stderr]
        ready.set()
        if start_line is not None:
            control = process.stdin
            if _requested(should_stop):
                control.close()
                control = None
            else:
                control.write(start_line)
                control.flush()
        deadline = time.monotonic() + _SOFT_TIMEOUT_SECONDS
        exceeded = False
        while True:
            # Closing the dashboard control pipe requests stop before the first
            # native commit. An active child keeps ownership of its cleanup.
            if _requested(should_stop) and control is not None:
                control.close()
                control = None
            exceeded = exceeded or time.monotonic() >= deadline
            try:
                returncode = process.wait(timeout=_WAIT_INTERVAL_SECONDS)
                break
            except subprocess.TimeoutExpired:
                continue
            except KeyboardInterrupt:
                # An interrupt after launch has deferred-stop semantics.
                continue
    finally:
        ready.set()
        if control is not None:
            try:
                control.close()
            except OSError:
                pass
        # Every post-launch failure still owns its child's lifetime. Drainers
        # are already running, so waiting cannot deadlock on full output pipes.
        if process is not None and returncode is None:
            while True:
                try:
                    returncode = process.wait(timeout=_WAIT_INTERVAL_SECONDS)
                    break
                except (subprocess.TimeoutExpired, KeyboardInterrupt):
                    continue
        for reader in started:
            reader.join(timeout=_READER_JOIN_SECONDS)
    complete = stdout.complete.is_set() and stderr.complete.is_set()
    failed = not complete or stdout.failed or stderr.failed
    # A descendant retaining a pipe must not hold up the monitor after its
    # completion process exited. Readers retain at most the fixed budgets.
    return returncode, bytes(stdout.data), failed, exceeded


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate report field")
        result[key] = value
    return result


def _reject_number(value):
    raise ValueError("Nonintegral report number")


def _integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def _valid_file(item):
    if not isinstance(item, dict) or set(item) != _FILE_FIELDS:
        return False
    name = item["saved_filename"]
    return (
        isinstance(name, str)
        and 1 <= len(name) <= 255
        and name not in {".", ".."}
        and not any(character in name for character in "/\\:")
        and not any(
            ord(character) < 32
            or 127 <= ord(character) <= 159
            or 0xD800 <= ord(character) <= 0xDFFF
            for character in name
        )
        and item["detected_format"] in {"JPEG", "PNG", "WEBP", "GIF", "BMP", "TIFF"}
        and _integer(item["file_size"], 1, 2**63 - 1)
        and all(_integer(item[key], 1, 2**31 - 1) for key in ("width", "height", "frames"))
    )


def _parse_report(raw, returncode):
    if len(raw) > _STDOUT_LIMIT:
        raise ValueError("Oversize report")
    report = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_unique_object,
        parse_float=_reject_number,
        parse_constant=_reject_number,
    )
    if not isinstance(report, dict) or not _FIELDS <= set(report) <= _FIELDS | {"job_counts"}:
        raise ValueError("Unexpected report fields")
    status = report["status"]
    expected_codes = {
        "batch_finish_completed": 0,
        "batch_finish_no_pending": 0,
        "batch_finish_busy": 0,
        "batch_finish_manual_review": 2,
        "batch_finish_cancelled": 130,
    }
    if (
        type(report["schema_version"]) is not int
        or report["schema_version"] != 1
        or report["mode"] != _MODE
        or not isinstance(status, str)
        or status not in FINISH_ACTION_STATUSES
        or report["reason"] != _STATUS_REASONS[status]
        or type(returncode) is not int
        or returncode != expected_codes[status]
        or report["last_stage"] not in _STAGES
        or not (
            report["error_type"] is None
            or isinstance(report["error_type"], str)
            and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}", report["error_type"])
        )
        or not all(
            report[key] is None or type(report[key]) is bool
            for key in ("browser_closed", "shared_pending_retained")
        )
        or type(report["close_attempted"]) is not bool
        or report["files_preserved"] is not True
        or report["metadata_preserved"] is not True
        or not _integer(report["files_verified"], 0, 2)
        or not _integer(report["tasks_completed"], 0, 1)
        or not isinstance(report["saved_files"], list)
        or len(report["saved_files"]) > 2
        or not all(_valid_file(item) for item in report["saved_files"])
    ):
        raise ValueError("Invalid report values")
    if "job_counts" in report:
        counts = report["job_counts"]
        if (
            not isinstance(counts, dict)
            or set(counts) != {"observed", "completed", "unresolved"}
            or not all(_integer(value, 0, 2) for value in counts.values())
            or counts["observed"] < 1
            or counts["completed"] != counts["observed"]
            or counts["unresolved"] != 0
        ):
            raise ValueError("Invalid completion counts")
    if status == "batch_finish_completed" and (
        report["last_stage"] != "complete"
        or report["tasks_completed"] != 1
        or report["browser_closed"] is not True
        or report["shared_pending_retained"] is not False
        or report["files_verified"] != len(report["saved_files"])
        or report["files_verified"] < 1
        or "job_counts" not in report
        or report["job_counts"]["completed"] != report["files_verified"]
        or report["error_type"] is not None
    ):
        raise ValueError("Incomplete completion evidence")
    if status != "batch_finish_completed" and report["tasks_completed"] != 0:
        raise ValueError("Unexpected completed task")
    if status in {"batch_finish_no_pending", "batch_finish_busy"} and (
        report["files_verified"] != 0
        or report["saved_files"]
        or "job_counts" in report
        or report["error_type"] is not None
        or report["close_attempted"] is not False
    ):
        raise ValueError("Unexpected work in an inert finish")
    if status == "batch_finish_no_pending" and (
        report["last_stage"] != "complete" or report["shared_pending_retained"] is not False
    ):
        raise ValueError("Unconfirmed absence of unfinished work")
    if status == "batch_finish_cancelled" and report["error_type"] != "KeyboardInterrupt":
        raise ValueError("Unexpected child cancellation")
    if status == "batch_finish_manual_review" and report["error_type"] == "KeyboardInterrupt":
        raise ValueError("Child cancellation requires its cancellation status")
    return report


def run_completed_finish(watch_root, legacy_root, batch_root, *, should_stop=None):
    """Finish existing completed work once, preserving a late child's result.

    Only the three configured roots reach the fixed CLI. Output and exception
    messages never escape this boundary. A soft deadline records slow cleanup;
    it cannot interrupt a child which may already be committing completion.
    """
    if _requested(should_stop):
        return _fallback(cancelled=True)
    try:
        arguments = [
            sys.executable,
            "-m",
            "image_monitor",
            "monitor-batch-finish",
            "--watch-root",
            str(Path(watch_root).absolute()),
            "--legacy-root",
            str(Path(legacy_root).absolute()),
            "--work-root",
            str(Path(batch_root).absolute()),
        ]
        # Recheck immediately before launch, after constructing the fixed argv.
        if _requested(should_stop):
            return _fallback(cancelled=True)
        code, raw, failed, exceeded = _run_child(arguments, should_stop)
        report = _fallback() if failed else _parse_report(raw, code)
        if exceeded:
            report["completion_wait_exceeded"] = True
        return report
    except _StoppedBeforeLaunch:
        return _fallback(cancelled=True)
    except Exception:
        return _fallback()
