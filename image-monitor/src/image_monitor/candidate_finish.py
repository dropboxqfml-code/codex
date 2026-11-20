"""Recheck an already completed candidate's local files without changing them.

The caller holds the watch and native locks. Frozen sources and finalized journals
must prove every image completed before these read-only checks. Finishing a pending
save additionally requires its exact shutdown-failure report, and clearing its
marker requires separate proof that the old browser/profile stopped.
This module never opens a browser, edits a queue, deletes a marker, or retries an image.
"""

import json
import math
import os
import re
import stat
from datetime import datetime
from pathlib import Path

from image_monitor.artifact_files import (
    SOURCE_FIELDS,
    _metadata,
    _plain_path,
    _relative_path,
    _source_metadata,
)
from image_monitor.candidate_save_policy import MAX_SAVE_IMAGES, CandidateSavePermit
from image_monitor.native_probe import exclusive_digest
from image_monitor.native_ui import NativeUIError
from image_monitor.paths import FolderPlan, destination, plan_folder
from image_monitor.queue import QueueStore
from image_monitor.validation import verify_image

MAX_REPORT_BYTES = 4 * 1024 * 1024
SHUTDOWN_REASONS = {
    "Dedicated browser did not close; inspect it manually",
    "The dedicated profile remains active",
}
IDENTITY_FIELDS = ("gallery_type", "gallery_id", "post_id")
PENDING_FIELDS = {
    "schema_version",
    "run_id",
    "run_directory",
    "browser_profile",
    "browser_pid",
    "browser_create_time",
}


class CandidateFinishError(NativeUIError):
    """Completed-file evidence is incomplete; leave every marker and file intact."""


def _require(value, message):
    if not value:
        raise CandidateFinishError(message)


def _uuid(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{32}", value) is not None


def _directory(value):
    path = _plain_path(Path(value))
    _require(stat.S_ISDIR(path.lstat().st_mode), "Candidate finish requires a plain directory")
    return path


def _paths(base, pending):
    base = _directory(base)
    _require(
        not str(base).startswith("\\\\") and re.fullmatch(r"session-[0-9]+", base.name),
        "Candidate finish requires this session's exact local save root",
    )
    _require(
        isinstance(pending, dict)
        and set(pending) == PENDING_FIELDS
        and type(pending.get("schema_version")) is int
        and pending["schema_version"] == 1
        and _uuid(pending.get("run_id"))
        and type(pending.get("browser_pid")) is int
        and pending["browser_pid"] > 0
        and type(pending.get("browser_create_time")) in {int, float}
        and math.isfinite(pending["browser_create_time"])
        and pending["browser_create_time"] > 0,
        "The pending candidate browser identity is incomplete",
    )
    raw_directory = pending.get("run_directory")
    _require(isinstance(raw_directory, str), "The pending candidate run is invalid")
    run_name = Path(raw_directory).name
    _require(
        _uuid(run_name)
        and raw_directory == str(base / "runs" / run_name)
        and pending.get("browser_profile") == str(base / "runs" / run_name / "browser-profile"),
        "The pending candidate run/profile does not belong to this save root",
    )
    run_directory = _directory(base / "runs" / run_name)
    _directory(run_directory / "browser-profile")
    save_root = _directory(base / "images")
    return base, run_directory, save_root


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CandidateFinishError("Completed candidate JSON has duplicate fields")
        result[key] = value
    return result


def _read_json(path):
    path = _plain_path(path)
    before = path.lstat()
    _require(
        stat.S_ISREG(before.st_mode) and before.st_size <= MAX_REPORT_BYTES,
        "Completed candidate JSON must be a bounded plain file",
    )
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(MAX_REPORT_BYTES + 1)
        finished = os.fstat(stream.fileno())
    after = path.lstat()
    _require(
        len(raw) <= MAX_REPORT_BYTES
        and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        == (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
        == (finished.st_dev, finished.st_ino, finished.st_size, finished.st_mtime_ns)
        == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
        "Completed candidate JSON changed while being read",
    )
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)


def _report(report, run_directory, save_root, permit=None):
    _require(
        isinstance(report, dict)
        and type(report.get("schema_version")) is int
        and report["schema_version"] == 2
        and report.get("mode") == "reviewed_candidate_native_context_menu"
        and report.get("browser") == "chrome"
        and report.get("status") == "manual_review"
        and report.get("last_stage") == "browser_shutdown"
        and report.get("error_type") == "NativeUIError"
        and report.get("reason") in SHUTDOWN_REASONS
        and report.get("browser_closed") is False
        and report.get("shared_pending_retained") is True
        and "active_attempt" not in report
        and report.get("output_directory") == str(save_root),
        "The private report does not prove a completed candidate shutdown failure",
    )
    _require(
        "report_path" not in report or report["report_path"] == str(run_directory / "report.json"),
        "The private candidate report identifies another run",
    )
    if permit is None:
        image_counts = range(1, MAX_SAVE_IMAGES + 1)
    else:
        _require(isinstance(permit, CandidateSavePermit), "A frozen candidate permit is required")
        image_counts = (permit.image_count,)
    counts = report.get("job_counts")
    _require(
        isinstance(counts, dict)
        and set(counts) == {"observed", "completed", "unresolved"}
        and all(type(value) is int for value in counts.values())
        and counts["observed"] in image_counts
        and counts["observed"] == counts["completed"]
        and counts["unresolved"] == 0,
        "The candidate report does not show every image completed",
    )


def read_completed_report(
    base: Path, pending: dict, *, permit: CandidateSavePermit | None = None
) -> dict:
    """Read the pending run's exact bounded worker report, without writing it."""
    _, run_directory, save_root = _paths(base, pending)
    report = _read_json(run_directory / "report.json")
    _report(report, run_directory, save_root, permit)
    return report


def _same_json(left, right):
    return json.dumps(left, sort_keys=True, allow_nan=False, separators=(",", ":")) == json.dumps(
        right, sort_keys=True, allow_nan=False, separators=(",", ":")
    )


def _same_save_root(value, expected):
    # QueueStore serializes Windows roots with forward slashes. Path comparison
    # preserves Windows identity rules without depending on the stored spelling.
    if not isinstance(value, str):
        return False
    path = Path(value)
    return path.is_absolute() and not str(path).startswith("\\\\") and _plain_path(path) == expected


def finish_completed_candidate(
    store: QueueStore,
    permit: CandidateSavePermit,
    *,
    base: Path,
    pending: dict,
    report: dict,
) -> dict:
    """Verify frozen sources, finished files and sidecars; make no changes.

    A pending marker must only be cleared by the caller after this succeeds and
    the previous browser/profile is independently confirmed stopped.
    """
    _require(isinstance(permit, CandidateSavePermit), "A frozen candidate permit is required")
    permit.validate()
    base, run_directory, save_root = _paths(base, pending)
    _report(report, run_directory, save_root, permit)
    summary, _ = verify_completed_candidate_files(store, permit, base=base)
    return summary


def verify_candidate_queue_jobs(store, permit, *, base):
    """Verify the native queue's identity, frozen plan, slots and unleased jobs."""
    _require(isinstance(permit, CandidateSavePermit), "A frozen candidate permit is required")
    permit.validate()
    base = _directory(base)
    _require(
        base.is_absolute()
        and not str(base).startswith("\\\\")
        and re.fullmatch(r"session-[0-9]+", base.name),
        "Completed candidate files require an exact local session save root",
    )
    save_root = _directory(base / "images")
    database = _plain_path(base / "queue.sqlite")
    _require(stat.S_ISREG(database.lstat().st_mode), "The existing native queue is missing")
    main = [row for row in store.connection.execute("PRAGMA database_list") if row[1] == "main"]
    _require(
        len(main) == 1 and main[0][2] and _plain_path(Path(main[0][2])) == database,
        "The native queue does not belong to this candidate save root",
    )
    reference = permit.reference_snapshot
    identity = {key: reference[key] for key in IDENTITY_FIELDS}
    post = store.get_post(**identity)
    _require(
        post is not None
        and post["watch_name"] == permit.watch_name
        and datetime.fromisoformat(post["first_seen_at"]) == permit.first_seen_at
        and all(
            post.get(key) == reference.get(key)
            for key in ("title", "nickname", "ip_display", "post_url")
        )
        and datetime.fromisoformat(post["published_at"])
        == datetime.fromisoformat(reference["published_at"]),
        "The native post no longer matches the frozen candidate",
    )
    expected_plan = plan_folder(
        watch_name=permit.watch_name,
        gallery_id=reference["gallery_id"],
        post_id=reference["post_id"],
        nickname=reference["nickname"],
        ip_display=reference.get("ip_display"),
        first_seen_at=permit.first_seen_at,
        published_at=datetime.fromisoformat(reference["published_at"]),
    ).to_dict()
    _require(post["folder_plan"] == expected_plan, "The frozen candidate folder plan changed")
    match = store.connection.execute(
        "SELECT first_seen_at FROM matches WHERE watch_name=? AND gallery_type=? AND gallery_id=? "
        "AND post_id=? AND keyword=? AND search_type=?",
        (permit.watch_name, *identity.values(), permit.keyword, permit.search_type),
    ).fetchone()
    _require(
        match is not None and datetime.fromisoformat(match[0]) == permit.first_seen_at,
        "The native queue lost its original candidate discovery scope",
    )
    jobs = store.list_jobs()
    _require(
        store.summary()["posts"] == 1
        and len(jobs) == permit.image_count
        and {job["file_slot"] for job in jobs} == set(range(1, permit.image_count + 1)),
        "The native queue contains missing or unrelated candidate work",
    )
    expected_sources = {image["stable_key"] for image in reference["images"]}
    _require(
        {job["stable_key"] for job in jobs} == expected_sources,
        "The native image jobs differ from the frozen candidate",
    )
    for job in jobs:
        _require(
            all(job.get(key) == value for key, value in identity.items())
            and job["worker_id"] is None
            and job["lease_token"] is None
            and job["folder_plan"] == expected_plan,
            "A candidate image is incomplete, changed, or still owned by a worker",
        )
    return save_root, jobs


def verify_candidate_job_source(permit, source):
    """Bind the exact native source snapshot to the permit that authorized these jobs."""
    _require(isinstance(source, dict), "A candidate image lost its frozen source")
    snapshot = source["snapshot"]
    evidence = snapshot.get("profile_evidence", {}).get("pilot_scope", {})
    _require(
        snapshot.get("layout_status") == "candidate_reviewed"
        and snapshot.get("queue_eligible") is True
        and evidence.get("detail_attempt_id") == permit.detail_attempt_id
        and evidence.get("permit_fingerprint") == permit.fingerprint,
        "The native source is not bound to this reviewed candidate permit",
    )
    permit.authorize_snapshot(snapshot)


def verify_completed_candidate_files(
    store: QueueStore,
    permit: CandidateSavePermit,
    *,
    base: Path,
) -> tuple[dict, list[dict]]:
    """Read completed journals and files without needing or changing a pending save.

    The caller must hold the shared watch and native locks. The public summary
    excludes source identities and paths. Private proofs pair each exact local
    file with its verified digest so a viewer can check its bounded byte buffer
    before caching it; these proofs must never be included in a shared report.
    """
    save_root, jobs = verify_candidate_queue_jobs(store, permit, base=base)
    _require(
        len(store.list_artifacts()) == permit.image_count,
        "The native queue contains missing or unrelated candidate work",
    )
    files = []
    proofs = []
    metadata_paths = set()
    for job in jobs:
        _require(job["status"] == "completed", "A candidate image is incomplete")
        artifact = store.get_artifact(job["job_id"])
        _require(
            isinstance(artifact, dict)
            and artifact.get("phase") == "finalized"
            and _same_save_root(artifact.get("save_root"), save_root)
            and _uuid(artifact.get("observation_id")),
            "A candidate image has no finalized owned artifact journal",
        )
        source = store.get_job_source(job["job_id"], artifact["observation_id"])
        verify_candidate_job_source(permit, source)
        verification = artifact["verification"]
        directory = _directory(destination(save_root, FolderPlan(**job["folder_plan"])))
        final = _relative_path(save_root, artifact["final_relative"])
        _require(
            final == directory / f"{job['file_slot']:03d}.{verification['extension']}"
            and stat.S_ISREG(final.lstat().st_mode),
            "The finalized candidate image is outside its frozen file slot",
        )
        actual = verify_image(final, writer_finished=True).to_dict()
        _require(
            _same_json(actual, verification)
            and exclusive_digest(final) == actual["sha256"]
            and (actual["width"], actual["height"])
            == (source["image"]["natural_width"], source["image"]["natural_height"]),
            "A completed candidate file changed or remains in use",
        )
        image_metadata = artifact["image_metadata"]
        _require(
            image_metadata.get("save_method") == "native_context_menu_save_image_as"
            and image_metadata.get("saved_filename") == final.name
            and _same_json(
                {key: image_metadata.get(key) for key in SOURCE_FIELDS}, _source_metadata(source)
            ),
            "The finalized candidate metadata no longer matches its frozen image source",
        )
        completion = image_metadata.get("completion", {})
        _require(
            completion.get("state") == "COMPLETE"
            and completion.get("destination_confirmed") is True
            and completion.get("source_confirmed") is True
            and completion.get("exclusive_sha256") == actual["sha256"],
            "A candidate artifact lacks its proven native completion",
        )
        metadata_path = directory / "metadata.json"
        if metadata_path not in metadata_paths:
            metadata = _read_json(metadata_path)
            _require(
                _same_json(metadata, _metadata(store, job)),
                "The completed candidate metadata differs from its frozen journals",
            )
            metadata_paths.add(metadata_path)
        public_file = {"saved_filename": final.name} | {
            key: actual[key]
            for key in ("detected_format", "file_size", "width", "height", "frames")
        }
        files.append(public_file)
        proofs.append({"path": final, "sha256": actual["sha256"]} | public_file)
    return (
        {
            "job_counts": {"observed": len(jobs), "completed": len(jobs), "unresolved": 0},
            "saved_files": files,
            "files_preserved": True,
            "metadata_preserved": True,
        },
        proofs,
    )
