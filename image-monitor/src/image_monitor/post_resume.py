"""Explicit recovery for the legacy reviewed-post failure before native input.

The caller holds NativeSaveLock and opens the existing queue for ``base``. Every
external proof is checked before the queue is changed. Reports, artifacts and
staging directories are preserved, including after a successful recovery.
"""

import json
import re
import sqlite3
import stat
from datetime import datetime
from pathlib import Path

from image_monitor.artifact_files import ArtifactError, _plain_path, _relative_path
from image_monitor.dcinside import SITE_VERIFIED_POST, validate_post_url
from image_monitor.native_state import PendingSave, browser_still_running
from image_monitor.native_ui import NativeUIError
from image_monitor.queue import QueueError, QueueStore

MAX_REPORT_BYTES = 4 * 1024 * 1024
PREINPUT_REASONS = {
    "Foreground focus is outside the bound probe window; input stopped",
    "The probe page itself is not in the foreground",
}
IDENTITY_FIELDS = ("gallery_type", "gallery_id", "post_id")


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise NativeUIError(reason)


def _uuid32(value) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{32}", value) is not None


def _directory(path: Path) -> Path:
    path = _plain_path(path)
    _require(stat.S_ISDIR(path.lstat().st_mode), "Recovery requires an existing plain directory")
    return path


def _unique_object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate report field")
        result[key] = value
    return result


def _read_report(run_directory: Path) -> dict:
    path = _plain_path(run_directory / "report.json")
    info = path.lstat()
    _require(
        stat.S_ISREG(info.st_mode) and info.st_size <= MAX_REPORT_BYTES,
        "The private run report is not a bounded regular file",
    )
    with path.open("rb") as stream:
        raw = stream.read(MAX_REPORT_BYTES + 1)
    _require(len(raw) <= MAX_REPORT_BYTES, "The private run report exceeds the recovery limit")
    report = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    _require(isinstance(report, dict), "The private run report is invalid")
    _require(
        type(report.get("schema_version")) is int
        and report["schema_version"] == 1
        and report.get("mode") == "single_post_native_context_menu"
        and report.get("status") == "manual_review"
        and report.get("error_type") == "NativeUIError"
        and report.get("reason") in PREINPUT_REASONS
        and report.get("last_stage") == "native_saving"
        and report.get("native_stage") == "image_load"
        and report.get("shared_pending_retained") is True,
        "The private report does not prove the supported legacy pre-input failure",
    )
    return report


def _check_store(store: QueueStore, base: Path) -> None:
    database = _plain_path(base / "queue.sqlite")
    _require(
        stat.S_ISREG(database.lstat().st_mode),
        "Recovery requires this root's existing plain queue database",
    )
    main = [row for row in store.connection.execute("PRAGMA database_list") if row[1] == "main"]
    _require(
        len(main) == 1 and main[0][2] and _plain_path(Path(main[0][2])) == database,
        "The open queue database does not belong to this recovery root",
    )


def _check_source(store: QueueStore, job: dict, observation_id: str) -> None:
    source = store.get_job_source(job["job_id"], observation_id)
    _require(
        isinstance(source, dict)
        and source.get("observation_id") == observation_id
        and isinstance(source.get("snapshot"), dict)
        and isinstance(source.get("image"), dict),
        "The attempt has no matching immutable source observation",
    )
    snapshot = source["snapshot"]
    _require(
        tuple(job.get(key) for key in IDENTITY_FIELDS) == SITE_VERIFIED_POST
        and tuple(snapshot.get(key) for key in IDENTITY_FIELDS) == SITE_VERIFIED_POST,
        "Pre-input recovery is limited to the reviewed post",
    )
    target = validate_post_url(snapshot.get("post_url"))
    _require(
        tuple(target.get(key) for key in IDENTITY_FIELDS) == SITE_VERIFIED_POST
        and target["canonical_url"] == snapshot["post_url"],
        "The immutable source does not contain the reviewed canonical post URL",
    )


def _check_empty_job_files(job: dict, stage: Path, save_root: Path) -> None:
    _directory(stage)
    _require(not any(stage.iterdir()), "The reported staging attempt contains entries")
    # Other attempts for this same job may be empty, but any bytes or links leave
    # the operation ambiguous. Other jobs' completed images are never touched.
    for attempt in stage.parent.iterdir():
        _require(_uuid32(attempt.name), "The job staging directory contains an unknown entry")
        _directory(attempt)
        _require(not any(attempt.iterdir()), "Another attempt for this job contains entries")
    plan = job.get("folder_plan")
    _require(isinstance(plan, dict), "The image job has no frozen destination plan")
    _require(
        plan.get("relative_directory") != ".",
        "The image job has an invalid frozen destination plan",
    )
    directory = _relative_path(save_root, plan.get("relative_directory"))
    slot = job.get("file_slot")
    _require(type(slot) is int and slot > 0, "The image job has an invalid destination slot")
    if directory.exists():
        _directory(directory)
        basename = f"{slot:03d}"
        _require(
            not any(
                entry.name == basename or entry.name.startswith(basename + ".")
                for entry in directory.iterdir()
            ),
            "The image job already has a destination entry",
        )


def _legacy_failure(history: dict, job: dict) -> bool:
    return (
        type(history.get("history_id")) is int
        and history["history_id"] > 0
        and history.get("kind") == "ui"
        and history.get("reason") == "NativeUIError"
        and history.get("resulting_status") == "paused_ui"
        and history.get("attempt_count") == job.get("attempt_count")
    )


def resume_preinput_failure(
    store: QueueStore,
    state: PendingSave,
    *,
    base: Path,
    now: datetime,
    is_running=browser_still_running,
) -> dict:
    """Requeue only a proven legacy foreground failure before its first native input.

    A queue commit followed by failure to remove the pending marker is safe to
    repeat: the matching resume history permits only marker cleanup on that run.
    """
    try:
        _plain_path(state.path)
        pending = state.read()
        if pending is None:
            return {"status": "no_pending_save"}
        base = _directory(Path(base))
        _check_store(store, base)
        run_directory = Path(pending["run_directory"])
        _require(
            _uuid32(run_directory.name)
            and pending["run_directory"] == str(base / "runs" / run_directory.name)
            and pending["browser_profile"] == str(run_directory / "browser-profile"),
            "The pending save does not identify this root's exact private run and profile",
        )
        _directory(run_directory)
        _directory(run_directory / "browser-profile")
        _require(
            is_running(pending) is False,
            "Previous browser/profile is still active or could not be verified closed",
        )
        report = _read_report(run_directory)
        attempt = report.get("active_attempt")
        _require(
            isinstance(attempt, dict)
            and set(attempt) == {"job_id", "observation_id", "staging_directory"}
            and _uuid32(attempt.get("job_id"))
            and _uuid32(attempt.get("observation_id"))
            and isinstance(attempt.get("staging_directory"), str),
            "The private report has no unambiguous pre-input image attempt",
        )
        job_id, observation_id = attempt["job_id"], attempt["observation_id"]
        stage = Path(attempt["staging_directory"])
        save_root = _directory(base / "images")
        _require(
            _uuid32(stage.name)
            and attempt["staging_directory"] == str(save_root / "_staging" / job_id / stage.name),
            "The reported attempt does not identify the exact owned staging directory",
        )
        job = store.get_job(job_id)
        _require(isinstance(job, dict), "The reported image job is missing")
        _require(
            job.get("worker_id") is None
            and job.get("lease_token") is None
            and store.get_artifact(job_id) is None,
            "The reported image job has an owner or an artifact journal",
        )
        _check_source(store, job, observation_id)
        _check_empty_job_files(job, stage, save_root)
        history = store.history(job_id)
        _require(bool(history), "The image job has no matching failure history")
        latest = history[-1]
        already_resumed = job.get("status") == "queued"
        if already_resumed:
            _require(
                job.get("last_error") is None
                and latest.get("kind") == "pre_input_resume"
                and latest.get("reason") == "verified_no_input"
                and latest.get("resulting_status") == "queued"
                and latest.get("attempt_count") == job.get("attempt_count")
                and len(history) >= 2
                and _legacy_failure(history[-2], job),
                "The queued image job has no matching pre-input resume history",
            )
        else:
            _require(
                job.get("status") == "paused_ui"
                and job.get("last_error") == "NativeUIError"
                and _legacy_failure(latest, job),
                "The image job is not paused on the supported legacy UI failure",
            )
            store.resume_preinput_failure(
                job_id,
                observation_id=observation_id,
                expected_history_id=latest["history_id"],
                now=now,
                confirm_workers_stopped=True,
                confirmed_no_input=True,
            )
        state.finish(pending)
        return {
            "status": "resumed_preinput_failure",
            "job_id": job_id,
            "files_preserved": True,
            "pending_cleared": True,
            "already_resumed": already_resumed,
        }
    except (
        ArtifactError,
        QueueError,
        sqlite3.Error,
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        KeyError,
        RecursionError,
    ) as error:
        raise NativeUIError(
            "Pre-input recovery could not complete; inspect the preserved pending state"
        ) from error
