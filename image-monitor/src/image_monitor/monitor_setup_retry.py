"""Prove a failed Chrome completion setup stopped before any native image attempt."""

from image_monitor.artifact_files import _plain_path
from image_monitor.browser_completion import completion_setup_reason
from image_monitor.candidate_finish import (
    _paths,
    _read_json,
    _same_json,
    verify_candidate_job_source,
    verify_candidate_queue_jobs,
)
from image_monitor.monitor_save_ledger import is_setup_retry_candidate, task_native_base
from image_monitor.native_state import (
    PendingSave,
    browser_still_running,
    session_id,
    shared_state_path,
)
from image_monitor.queue import QueueError, QueueStore


def verify_setup_retry(ledger, task, permit):
    """Return the original run and safe cause while the caller holds watch and native locks.

    Nothing here claims a job, mutates the ledger or removes a previous report.
    A caller that releases either lock must repeat verification before starting.
    """
    if (
        ledger.get_task(task["task_id"]) != task
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
        or report.get("last_stage") != "completion_setup"
        or report.get("error_type") != "BrowserCompletionError"
        or report.get("browser_closed") is not True
        or report.get("shared_pending_retained") is not False
        or report.get("saved_files") != []
        or report.get("report_path") != str(path)
        or report.get("output_directory") != str(images)
        or not _same_json(
            report.get("job_counts"), {"observed": count, "completed": 0, "unresolved": count}
        )
        or "active_attempt" in report
        or "last_preinput_attempt" in report
    ):
        raise QueueError("The original worker report does not prove a pre-input setup failure")

    with QueueStore(_plain_path(base / "queue.sqlite"), read_only=True) as native:
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
