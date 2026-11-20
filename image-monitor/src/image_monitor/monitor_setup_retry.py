"""Prove a failed Chrome startup or completion setup stopped before the first image attempt."""

from image_monitor.artifact_files import _plain_path
from image_monitor.browser_completion import completion_setup_reason
from image_monitor.candidate_finish import (
    _paths,
    _read_json,
    _same_json,
    verify_candidate_job_source,
    verify_candidate_queue_jobs,
)
from image_monitor.candidate_save_policy import MONITOR_SCOPE
from image_monitor.monitor_save_ledger import is_setup_retry_candidate, task_native_base
from image_monitor.native_state import (
    PendingSave,
    browser_still_running,
    session_id,
    shared_state_path,
)
from image_monitor.queue import SCHEMA_VERSION, QueueError, QueueStore

FOREGROUND_RETRY_REASON = "automatic_foreground_unconfirmed"
FOREGROUND_RETRY_EXHAUSTED = "automatic_foreground_retry_exhausted"

_FOREGROUND_FIELDS = {
    "schema_version",
    "mode",
    "status",
    "browser",
    "last_stage",
    "error_type",
    "browser_closed",
    "shared_pending_retained",
    "saved_files",
    "output_directory",
    "preinput_recovery",
    "recovery",
    "browser_version",
    "reason",
    "focus_at_failure",
    "native_stage",
    "report_path",
}
_FOCUS_FIELDS = {
    "target_hwnd",
    "foreground_hwnd",
    "foreground_pid",
    "foreground_class",
    "target_exists",
    "belongs_to_target",
    "target_foreground",
}


def _valid_focus_snapshot(focus):
    if (
        not isinstance(focus, dict)
        or set(focus) != _FOCUS_FIELDS
        or type(focus["target_hwnd"]) is not int
        or focus["target_hwnd"] <= 0
        or any(
            type(focus[key]) is not bool
            for key in ("target_exists", "belongs_to_target", "target_foreground")
        )
    ):
        return False
    if not focus["target_exists"] and (focus["belongs_to_target"] or focus["target_foreground"]):
        return False
    if focus["foreground_hwnd"] is None:
        return (
            focus["foreground_pid"] is None
            and focus["foreground_class"] is None
            and not focus["belongs_to_target"]
            and not focus["target_foreground"]
        )
    # Windows may have moved focus again before the diagnostic sample was taken.
    return (
        type(focus["foreground_hwnd"]) is int
        and focus["foreground_hwnd"] > 0
        and (
            focus["foreground_pid"] is None
            or type(focus["foreground_pid"]) is int
            and focus["foreground_pid"] > 0
        )
        and (focus["foreground_class"] is None or isinstance(focus["foreground_class"], str))
    )


def _verify_foreground_failure(report, native, run, base):
    # This guard ran immediately after navigation, before inspection, enqueue,
    # claim, or native input. Even zero-valued job_counts would be a later stage.
    if (
        set(report) != _FOREGROUND_FIELDS
        or report["last_stage"] != "automatic_foreground_check"
        or report["native_stage"] != "desktop_guard"
        or report["reason"]
        not in (
            "Foreground focus is outside the bound probe window; input stopped",
            "The probe page itself is not in the foreground",
        )
        or not isinstance(report["browser_version"], str)
        or not report["browser_version"]
        or report["preinput_recovery"] is not None
        or not _same_json(
            report["recovery"],
            {
                "recovered": 0,
                "metadata_written": 0,
                "skipped": 0,
                "manual_review": [],
            },
        )
        or not _valid_focus_snapshot(report["focus_at_failure"])
    ):
        raise QueueError("The original report does not prove an initial foreground check failure")
    if (
        any(child != base for child in base.parent.iterdir())
        or {p.name for p in run.iterdir()} != {"report.json", "browser-profile"}
        or any(
            p.name not in {"runs", "images", "queue.sqlite", "queue.sqlite-shm", "queue.sqlite-wal"}
            for p in base.iterdir()
        )
    ):
        raise QueueError("The prior foreground check contains unexpected output")
    if native.schema_version != SCHEMA_VERSION:
        raise QueueError("The prior foreground check has an unexpected native queue schema")
    # QueueStore has verified the exact known schema. Check *every* application
    # table, including standalone discovery, service, or publication records.
    tables = native.connection.execute(
        "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT GLOB 'sqlite_*'"
    )
    for (name,) in tables:
        if native.connection.execute(f'SELECT 1 FROM "{name}" LIMIT 1').fetchone() is not None:
            raise QueueError("The prior foreground check already contains durable work")


def verify_setup_retry(ledger, task, permit):
    """Return the original run and safe cause while the caller holds watch and native locks.

    Nothing here claims a job, mutates the ledger or removes a previous report.
    A caller that releases either lock must repeat verification before starting.
    """
    if (
        ledger.get_task(task["task_id"]) != task
        or ledger.scope != MONITOR_SCOPE
        or not is_setup_retry_candidate(task)
        or task["native_session"] != session_id()
        or task["permit_fingerprint"] != permit.fingerprint
        or task["detail_attempt_id"] != permit.detail_attempt_id
        or task["post_url"] != permit.post_url
    ):
        raise QueueError("The failed task does not match this session and frozen post")
    identity = task["control"]["browser_identity"]
    base = task_native_base(task, ledger.batch_root, ledger.legacy_root)
    _, run, images = _paths(base, identity)
    PendingSave(shared_state_path()).assert_clear()
    if browser_still_running(identity) is not False:
        raise QueueError("The previous owned Chrome session is not confirmed closed")
    runs = run.parent.iterdir()
    if next(runs, None) != run or next(runs, None) is not None or any(images.iterdir()):
        raise QueueError("The failed task already has another run or image output")

    path = run / "report.json"
    report = _read_json(path)
    count = permit.image_count
    if (
        not isinstance(report, dict)
        or type(report.get("schema_version")) is not int
        or report["schema_version"] != 2
        or report.get("mode") != "reviewed_candidate_native_context_menu"
        or report.get("browser") != "chrome"
        or report.get("status") != "manual_review"
        or report.get("error_type") != task["result"]["error_type"]
        or report.get("browser_closed") is not True
        or report.get("shared_pending_retained") is not False
        or report.get("saved_files") != []
        or report.get("report_path") != str(path)
        or report.get("output_directory") != str(images)
        or "active_attempt" in report
        or "last_preinput_attempt" in report
    ):
        raise QueueError("The original worker report does not prove a pre-input setup failure")

    with QueueStore(_plain_path(base / "queue.sqlite"), read_only=True) as native:
        if report["error_type"] == "NativeFocusError":
            _verify_foreground_failure(report, native, run, base)
            return run.name, FOREGROUND_RETRY_REASON
        if report.get("last_stage") != "completion_setup" or not _same_json(
            report.get("job_counts"), {"observed": count, "completed": 0, "unresolved": count}
        ):
            raise QueueError("The original report does not prove a completion setup failure")
        _, jobs = verify_candidate_queue_jobs(native, permit, base=base)
        if (
            native.list_artifacts()
            or native.connection.execute("SELECT 1 FROM attempts LIMIT 1").fetchone()
        ):
            raise QueueError("The original queue contains image attempts or artifacts")
        for job in jobs:
            if (
                job["status"] != "queued"
                or job["attempt_count"] != 0
                or any(
                    job[key] is not None
                    for key in (
                        "first_failure_at",
                        "next_retry_at",
                        "server_not_before",
                        "last_error",
                    )
                )
            ):
                raise QueueError("A queued image shows an earlier attempt")
            verify_candidate_job_source(permit, native.get_job_source(job["job_id"]))
    return run.name, completion_setup_reason(report.get("reason"))
