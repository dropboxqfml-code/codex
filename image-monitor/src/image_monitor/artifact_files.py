"""Publish verified native saves and recover their journal without browser activity.

The caller must hold NativeSaveLock throughout finalization and recovery. Recovery
also requires confirmation that every previous native worker has stopped. Nothing
here downloads, re-encodes, overwrites image files, or schedules native retries.
"""

import json
import os
import re
import stat
import uuid
from datetime import datetime
from pathlib import Path, PurePosixPath

from image_monitor.paths import FolderPlan, aware, destination
from image_monitor.validation import verify_image

APP_MARKER = "image-monitor/native-context-menu"
METADATA_SCHEMA_VERSION = 1
IDENTITY_FIELDS = ("gallery_type", "gallery_id", "post_id")
SOURCE_FIELDS = (
    "stable_key",
    "display_url",
    "body_order",
    "occurrences",
    "natural_width",
    "natural_height",
    "original_attachment_filename",
    "original_filename_source",
    "original_filename_match_status",
    "original_filename_match_method",
    "original_filename_match_reason",
    "stable_key_source",
    "resource_identity",
)
POST_FIELDS = (*IDENTITY_FIELDS, "title", "nickname", "ip_display", "post_url", "published_at")


class ArtifactError(ValueError):
    """A local artifact requires review; its files must be preserved."""


def _plain_path(path: Path) -> Path:
    path = path.absolute()
    if ".." in path.parts:
        raise ArtifactError("unsafe_path")
    for part in [*reversed(path.parents), path]:
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ArtifactError("symlink_or_reparse_path")
        if part != path and not stat.S_ISDIR(info.st_mode):
            raise ArtifactError("non_directory_ancestor")
    return path


def _relative_path(root: Path, relative: str) -> Path:
    value = PurePosixPath(relative)
    if (
        not isinstance(relative, str)
        or not relative
        or str(value) != relative
        or value.is_absolute()
        or any(
            part in {".", ".."} or any(c in part for c in "\\:") or any(ord(c) < 32 for c in part)
            for part in value.parts
        )
    ):
        raise ArtifactError("unsafe_relative_path")
    return _plain_path(root.joinpath(*value.parts))


def _staging_relative(root: Path, path: Path, job_id: str) -> str:
    path = _plain_path(path)
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise ArtifactError("staging_outside_root") from error
    parts = relative.parts
    if len(parts) != 4 or parts[:2] != ("_staging", job_id):
        raise ArtifactError("unexpected_staging_layout")
    try:
        if str(uuid.UUID(parts[1])).replace("-", "") != parts[1].replace("-", ""):
            raise ValueError
        if str(uuid.UUID(parts[2])).replace("-", "") != parts[2].replace("-", ""):
            raise ValueError
    except ValueError as error:
        raise ArtifactError("unexpected_staging_identity") from error
    if not re.fullmatch(r"native-image\.[a-z0-9]{1,12}", parts[3]):
        raise ArtifactError("unexpected_staging_filename")
    return relative.as_posix()


def _verified(path: Path, expected: dict) -> dict:
    _plain_path(path)
    actual = verify_image(path, writer_finished=True).to_dict()
    if actual != expected:
        raise ArtifactError("verification_mismatch")
    return actual


def _sync_directory(path: Path) -> None:
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _publish(staging: Path, final: Path, expected: dict) -> None:
    _verified(staging, expected)
    _plain_path(final)
    final.parent.mkdir(parents=True, exist_ok=True)
    _plain_path(final)
    if staging.stat().st_dev != final.parent.stat().st_dev:
        raise ArtifactError("cross_volume_publication")
    if os.path.lexists(final):
        raise ArtifactError("destination_exists")
    # The browser's exclusive completion check has already closed its writer.
    # Windows FlushFileBuffers (used by CRT commit/fsync) requires write access.
    # Opening the already completed, owned staging file for update changes no bytes.
    with staging.open("r+b") as stream:
        os.fsync(stream.fileno())
    if os.name == "nt":
        os.rename(staging, final)  # Windows rename refuses an existing target.
    else:
        os.link(staging, final, follow_symlinks=False)  # Exclusive target creation.
        _sync_directory(final.parent)
        _verified(final, expected)
        staging.unlink()
    _sync_directory(final.parent)
    _sync_directory(staging.parent)


def _source_metadata(source: dict) -> dict:
    # Whitelist public DOM fields; never copy a browser context or attachment URL.
    return {key: source["image"].get(key) for key in SOURCE_FIELDS}


def _post_identity(job: dict) -> dict:
    return {key: job[key] for key in IDENTITY_FIELDS}


def _metadata(store, job: dict) -> dict:
    identity = _post_identity(job)
    post = store.get_post(**identity)
    images = []
    for image_job in store.list_jobs():
        if _post_identity(image_job) != identity:
            continue
        artifact = store.get_artifact(image_job["job_id"])
        entry = {
            "job_id": image_job["job_id"],
            "file_slot": image_job["file_slot"],
            "status": image_job["status"],
            "stable_key": image_job["stable_key"],
            "retry": {
                key: image_job[key]
                for key in (
                    "attempt_count",
                    "first_failure_at",
                    "next_retry_at",
                    "server_not_before",
                )
            },
            "retry_history": [
                {key: attempt[key] for key in ("at", "kind", "attempt_count", "resulting_status")}
                for attempt in store.history(image_job["job_id"])
            ],
        }
        if artifact is not None:
            observation = store.get_observation(artifact["observation_id"])
            if observation is None:
                raise ArtifactError("frozen_observation_missing")
            entry["artifact"] = {
                "artifact_id": artifact["artifact_id"],
                "observation_id": artifact["observation_id"],
                "saved_at": artifact["saved_at"],
                "final_relative": artifact["final_relative"],
                "verification": artifact["verification"],
                **artifact["image_metadata"],
                "frozen_post": {key: observation["snapshot"].get(key) for key in POST_FIELDS},
            }
        images.append(entry)
    return {
        "application": APP_MARKER,
        "schema_version": METADATA_SCHEMA_VERSION,
        "post": identity,
        "folder_plan": job["folder_plan"],
        "post_metadata": {key: post.get(key) for key in POST_FIELDS},
        "images": images,
    }


def _owned_metadata(path: Path, payload: dict) -> None:
    _plain_path(path)
    if not os.path.lexists(path):
        return
    if not stat.S_ISREG(path.lstat().st_mode) or path.stat().st_size > 4 * 1024 * 1024:
        raise ArtifactError("unowned_metadata")
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        raise ArtifactError("unowned_metadata") from error
    if not isinstance(previous, dict) or any(
        previous.get(key) != payload[key]
        for key in ("application", "schema_version", "post", "folder_plan")
    ):
        raise ArtifactError("unowned_metadata")


def _write_metadata(store, job: dict, root: Path) -> Path:
    directory = destination(root, FolderPlan(**job["folder_plan"]))
    path = _plain_path(directory / "metadata.json")
    payload = _metadata(store, job)
    _owned_metadata(path, payload)
    temporary = path.with_name(f".metadata-{uuid.uuid4().hex}.tmp")
    created = False
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            created = True
            json.dump(payload, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        _owned_metadata(path, payload)
        # A first sidecar uses exclusive publication too. Replacements are only
        # allowed after validating our application/post/frozen folder markers.
        if not os.path.lexists(path):
            if os.name == "nt":
                os.rename(temporary, path)
            else:
                os.link(temporary, path, follow_symlinks=False)
                temporary.unlink()
        else:
            os.replace(temporary, path)
        _sync_directory(directory)
    finally:
        if created and temporary.exists():
            temporary.unlink()  # Only this invocation's exclusive temporary file.
    return path


def finalize_saved_image(
    store,
    job_id: str,
    token: str,
    *,
    observation_id: str,
    save_root: Path,
    staging_file: Path,
    verification: dict,
    completion_evidence: dict,
    browser_suggested_filename: str | None,
    saved_at: datetime,
) -> dict:
    """Journal and publish one proven native save while holding NativeSaveLock."""
    aware(saved_at)
    root = _plain_path(save_root)
    source = store.get_job_source(job_id, observation_id)
    job = store.get_job(job_id)
    if source is None or job is None:
        raise ArtifactError("frozen_source_missing")
    if (
        completion_evidence.get("state") != "COMPLETE"
        or completion_evidence.get("destination_confirmed") is not True
        or completion_evidence.get("source_confirmed") is not True
        or completion_evidence.get("destination") != str(staging_file)
        or completion_evidence.get("source_url") != source["image"]["display_url"]
    ):
        raise ArtifactError("completion_unproven")
    staging_relative = _staging_relative(root, staging_file, job_id)
    staging = _relative_path(root, staging_relative)
    actual = _verified(staging, verification)
    if completion_evidence.get("exclusive_sha256") != actual["sha256"]:
        raise ArtifactError("exclusive_verification_mismatch")
    directory = destination(root, FolderPlan(**job["folder_plan"]))
    final = _plain_path(directory / f"{job['file_slot']:03d}.{actual['extension']}")
    final_relative = final.relative_to(root).as_posix()
    if os.path.lexists(final):
        raise ArtifactError("destination_exists")
    metadata = {
        **_source_metadata(source),
        "browser_suggested_filename": browser_suggested_filename,
        "saved_filename": final.name,
        "save_method": "native_context_menu_save_image_as",
        "completion": {
            "state": "COMPLETE",
            "destination_confirmed": True,
            "source_confirmed": True,
            "exclusive_sha256": actual["sha256"],
        },
    }
    store.prepare_artifact(
        job_id,
        token,
        observation_id=source["observation_id"],
        save_root=str(root),
        staging_relative=staging_relative,
        final_relative=final_relative,
        verification=actual,
        image_metadata=metadata,
        saved_at=saved_at,
    )
    _publish(staging, final, actual)
    _verified(final, actual)
    store.complete_artifact(job_id, token)
    metadata_path = _write_metadata(store, store.get_job(job_id), root)
    store.mark_metadata_written(job_id)
    return store.get_artifact(job_id) | {
        "final_path": str(final),
        "metadata_path": str(metadata_path),
    }


def _resume_files(artifact: dict) -> None:
    root = _plain_path(Path(artifact["save_root"]))
    staging = _relative_path(root, artifact["staging_relative"])
    _staging_relative(root, staging, artifact["job_id"])
    final = _relative_path(root, artifact["final_relative"])
    expected = artifact["verification"]
    staged, published = os.path.lexists(staging), os.path.lexists(final)
    if staged:
        _verified(staging, expected)
    if published:
        _verified(final, expected)
    if staged and published:
        # Only an interrupted POSIX hardlink publication can own both names.
        if os.name == "nt" or not os.path.samefile(staging, final):
            raise ArtifactError("conflicting_artifact_files")
        staging.unlink()
        _sync_directory(staging.parent)
    elif staged:
        _publish(staging, final, expected)
    elif not published:
        raise ArtifactError("artifact_files_missing")
    _verified(final, expected)


def recover_finalizations(store, *, confirm_workers_stopped: bool = False) -> dict:
    """Resume only verified local journals; never claim jobs or open a browser."""
    if confirm_workers_stopped is not True:
        raise ArtifactError("confirm_workers_stopped_required")
    result = {"recovered": 0, "metadata_written": 0, "skipped": 0, "manual_review": []}
    for artifact in store.list_artifacts():
        job_id = artifact["job_id"]
        if artifact["phase"] == "finalized":
            result["skipped"] += 1
            continue
        try:
            _resume_files(artifact)
            if artifact["phase"] == "prepared":
                store.recover_artifact_complete(job_id, confirm_workers_stopped=True)
                result["recovered"] += 1
            _write_metadata(store, store.get_job(job_id), Path(artifact["save_root"]))
            store.mark_metadata_written(job_id)
            result["metadata_written"] += 1
        except (OSError, ValueError) as error:
            reason = str(error) if isinstance(error, ArtifactError) else "local_recovery_failed"
            store.mark_artifact_manual_review(job_id, reason, confirm_workers_stopped=True)
            result["manual_review"].append({"job_id": job_id, "reason": reason})
    return result
