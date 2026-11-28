"""Verify which frozen image jobs can safely be retried after a closed Chrome run."""

from image_monitor.artifact_files import _plain_path
from image_monitor.browser_completion import completion_setup_reason
from image_monitor.candidate_finish import (
    _paths,
    _read_json,
    _same_json,
    verify_candidate_job_source,
    verify_candidate_queue_jobs,
    verify_partial_candidate_files,
)
from image_monitor.candidate_save_policy import MONITOR_SCOPE
from image_monitor.monitor_foreground import WAIT_CANCELLED
from image_monitor.monitor_save_ledger import (
    is_exhausted_foreground_task,
    is_setup_retry_candidate,
    task_native_base,
)
from image_monitor.native_state import (
    PendingSave,
    browser_still_running,
    session_id,
    shared_state_path,
)
from image_monitor.queue import SCHEMA_VERSION, QueueError, QueueStore

FOREGROUND_RETRY_REASON = "automatic_foreground_unconfirmed"
FOREGROUND_RETRY_EXHAUSTED = "automatic_foreground_retry_exhausted"
PARTIAL_RETRY_REASON = "between_images_foreground_lost"
PARTIAL_RETRY_EXHAUSTED = "between_images_retry_exhausted"

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


def _verify_focus_run(report, native, run, base):
    """Require one clean run, session and native schema from the automatic worker."""
    if (
        not isinstance(report["browser_version"], str)
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
        raise QueueError("The original Chrome run has incomplete focus or recovery evidence")
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
            WAIT_CANCELLED,
        )
    ):
        raise QueueError("The original report does not prove an initial foreground check failure")
    _verify_focus_run(report, native, run, base)
    # QueueStore has verified the exact known schema. Check *every* application
    # table, including standalone discovery, service, or publication records.
    tables = native.connection.execute(
        "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT GLOB 'sqlite_*'"
    )
    for (name,) in tables:
        if native.connection.execute(f'SELECT 1 FROM "{name}" LIMIT 1').fetchone() is not None:
            raise QueueError("The prior foreground check already contains durable work")


def _partial_completed_count(report, native, permit, run, base):
    # On alpha.6 the UI still names the previous successful save dialog. The
    # worker records pre_input_check before claiming the next image in the loop.
    if (
        set(report) != _FOREGROUND_FIELDS | {"focus_pauses", "focus_at_pause", "job_counts"}
        or report["reason"] != "Automatic saving stopped when the dedicated window lost focus"
        or report["native_stage"] != "save_dialog"
        or type(report["focus_pauses"]) is not int
        or report["focus_pauses"] != 1
        or not _valid_focus_snapshot(report["focus_at_pause"])
        or not isinstance(report["saved_files"], list)
        or not 0 < len(report["saved_files"]) < permit.image_count
    ):
        raise QueueError("The original report does not prove a stop between saved images")
    _verify_focus_run(report, native, run, base)
    if report["focus_at_pause"]["target_hwnd"] != report["focus_at_failure"]["target_hwnd"]:
        raise QueueError("The focus evidence identifies different Chrome windows")
    summary, proofs = verify_partial_candidate_files(native, permit, base=base)
    files = [
        {
            "job_id": proof["job_id"],
            "saved_filename": proof["saved_filename"],
            **proof["verification"],
        }
        for proof in proofs
    ]
    if not _same_json(report["job_counts"], summary["job_counts"]) or not _same_json(
        report["saved_files"], files
    ):
        raise QueueError("The prior report and the verified saved image prefix disagree")
    return len(proofs)


def verify_setup_retry(ledger, task, permit, *, manual_foreground=False):
    """Return the original run, safe cause and preserved file count under watch and native locks.

    Nothing here claims a job, mutates the ledger or removes a previous report.
    A caller that releases either lock must repeat verification before starting.
    """
    if (
        ledger.get_task(task["task_id"]) != task
        or ledger.scope != MONITOR_SCOPE
        or not (
            is_exhausted_foreground_task(task)
            if manual_foreground
            else is_setup_retry_candidate(task)
        )
        or task["native_session"] != session_id()
        or task["permit_fingerprint"] != permit.fingerprint
        or task["detail_attempt_id"] != permit.detail_attempt_id
        or task["post_url"] != permit.post_url
    ):
        raise QueueError("The failed task does not match this session and frozen post")
    base = task_native_base(task, ledger.batch_root, ledger.legacy_root)
    PendingSave(shared_state_path()).assert_clear()
    controls = [task["control"]]
    if manual_foreground:
        receipt = task["control"]["setup_retry"]
        controls = [receipt["prior_control"], *receipt.get("manual_prior_controls", []), *controls]
    seen = set()
    for control in controls:
        if (
            control.get("blocked") is not False
            or control.get("in_flight") is not False
            or control.get("http_status") != 200
        ):
            raise QueueError("The prior browser navigation was not confirmed")
        identity = control["browser_identity"]
        _, run, images = _paths(base, identity)
        if run in seen or (manual_foreground and not seen and run.name != receipt["prior_run"]):
            raise QueueError("The foreground retry history does not match the owned runs")
        seen.add(run)
        if browser_still_running(identity) is not False:
            raise QueueError("The previous owned Chrome session is not confirmed closed")
        result = _verify_run(base, run, images, permit, task["result"]["error_type"])
        if manual_foreground and result[1:] != (FOREGROUND_RETRY_REASON, 0):
            raise QueueError("Manual foreground resume requires only closed pre-input failures")
    if set((base / "runs").iterdir()) != seen:
        raise QueueError("The failed task contains an unbound native run")
    return result


def _verify_run(base, run, images, permit, error_type):
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
        or report.get("error_type") != error_type
        or report.get("browser_closed") is not True
        or report.get("shared_pending_retained") is not False
        or report.get("report_path") != str(path)
        or report.get("output_directory") != str(images)
        or "active_attempt" in report
        or "last_preinput_attempt" in report
    ):
        raise QueueError("The original worker report does not prove a closed pre-input failure")

    with QueueStore(_plain_path(base / "queue.sqlite"), read_only=True) as native:
        if (
            report["error_type"] == "NativeFocusError"
            and report.get("last_stage") == "pre_input_check"
        ):
            prefix = _partial_completed_count(report, native, permit, run, base)
            return run.name, PARTIAL_RETRY_REASON, prefix
        if report.get("saved_files") != [] or any(images.iterdir()):
            raise QueueError("The failed setup already has image output")
        if report["error_type"] == "NativeFocusError":
            _verify_foreground_failure(report, native, run, base)
            return run.name, FOREGROUND_RETRY_REASON, 0
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
    return run.name, completion_setup_reason(report.get("reason")), 0
