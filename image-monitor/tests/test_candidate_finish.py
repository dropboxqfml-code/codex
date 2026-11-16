"""Verify an already completed candidate using only its owned local evidence."""

import copy
import hashlib
import json
import os
import sys
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from test_candidate_save_policy import candidate_evidence, snapshot_from

from image_monitor.artifact_files import finalize_saved_image
from image_monitor.candidate_save_policy import make_candidate_save_permit
from image_monitor.native_ui import NativeUIError
from image_monitor.post_pipeline import enqueue_candidate_snapshot
from image_monitor.queue import QueueStore
from image_monitor.validation import verify_image


@pytest.fixture(autouse=True)
def local_exclusive_digest(monkeypatch):
    if sys.platform == "win32":
        return
    from image_monitor import candidate_finish

    monkeypatch.setattr(
        candidate_finish,
        "exclusive_digest",
        lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest(),
    )


@pytest.fixture
def completed():
    directory = tempfile.TemporaryDirectory(
        prefix="imf-", dir=os.environ.get("RUNNER_TEMP", tempfile.gettempdir())
    )
    store = None
    try:
        base = Path(directory.name) / "session-1"
        run = base / "runs" / uuid.uuid4().hex
        (run / "browser-profile").mkdir(parents=True)
        candidate, baseline, detail = candidate_evidence()
        permit = make_candidate_save_permit(candidate, baseline, detail)
        snapshot = copy.deepcopy(snapshot_from(detail))
        now = datetime(2026, 11, 16, 9, tzinfo=UTC)
        snapshot["observed_at"] = now.isoformat()
        store = QueueStore(base / "queue.sqlite")
        queued = enqueue_candidate_snapshot(store, snapshot, permit=permit)
        files = []
        artifacts = []
        for order in range(2):
            claim = store.claim_next("finish-fixture", now)
            store.transition(claim["job_id"], claim["lease_token"], "saving")
            store.transition(claim["job_id"], claim["lease_token"], "verifying")
            source = claim["source"]
            staging = (
                base
                / "images"
                / "_staging"
                / claim["job_id"]
                / uuid.uuid4().hex
                / "native-image.png"
            )
            staging.parent.mkdir(parents=True)
            Image.new("RGB", (96, 64), "red" if order == 0 else "navy").save(staging)
            verified = verify_image(staging, writer_finished=True).to_dict()
            artifact = finalize_saved_image(
                store,
                claim["job_id"],
                claim["lease_token"],
                observation_id=source["observation_id"],
                save_root=base / "images",
                staging_file=staging,
                verification=verified,
                completion_evidence={
                    "state": "COMPLETE",
                    "destination_confirmed": True,
                    "source_confirmed": True,
                    "destination": str(staging),
                    "source_url": source["image"]["display_url"],
                    "exclusive_sha256": verified["sha256"],
                },
                browser_suggested_filename="invented-browser-name.png",
                saved_at=now + timedelta(seconds=order),
            )
            artifacts.append(artifact)
            files.append(
                {
                    "job_id": claim["job_id"],
                    "saved_filename": Path(artifact["final_path"]).name,
                    **verified,
                }
            )
        pending = {
            "schema_version": 1,
            "run_id": uuid.uuid4().hex,
            "run_directory": str(run),
            "browser_profile": str(run / "browser-profile"),
            "browser_pid": 4242,
            "browser_create_time": 123456.5,
        }
        report = {
            "schema_version": 2,
            "mode": "reviewed_candidate_native_context_menu",
            "status": "manual_review",
            "browser": "chrome",
            "last_stage": "browser_shutdown",
            "error_type": "NativeUIError",
            "reason": "Dedicated browser did not close; inspect it manually",
            "browser_closed": False,
            "shared_pending_retained": True,
            "output_directory": str(base / "images"),
            "job_counts": {"observed": 2, "completed": 2, "unresolved": 0},
            "saved_files": files,
            "report_path": str(run / "report.json"),
        }
        (run / "report.json").write_text(json.dumps(report), encoding="utf-8")
        value = SimpleNamespace(
            base=base,
            run=run,
            permit=permit,
            store=store,
            pending=pending,
            report=report,
            artifacts=artifacts,
            jobs=queued["jobs"],
        )
        yield value
    finally:
        if store is not None:
            store.close()
        directory.cleanup()


def finish(value, **overrides):
    from image_monitor.candidate_finish import finish_completed_candidate

    options = {"base": value.base, "pending": value.pending, "report": value.report}
    return finish_completed_candidate(value.store, value.permit, **(options | overrides))


def preserved(value):
    files = {
        str(path): path.read_bytes()
        for path in value.base.rglob("*")
        if path.is_file()
        and path.suffix not in {".sqlite", ".sqlite-wal", ".sqlite-shm"}
        and ".sqlite-" not in path.name
    }
    return (
        value.store.list_jobs(),
        value.store.list_artifacts(),
        list(value.store.connection.iterdump()),
        files,
    )


def test_completed_candidate_is_verified_without_mutating_database_or_any_file(completed):
    before = preserved(completed)
    result = finish(completed)
    assert result["job_counts"] == {"observed": 2, "completed": 2, "unresolved": 0}
    assert result["files_preserved"] is True
    assert result["metadata_preserved"] is True
    assert [item["saved_filename"] for item in result["saved_files"]] == ["001.png", "002.png"]
    assert all(item["detected_format"] == "PNG" for item in result["saved_files"])
    assert "sha256" not in json.dumps(result["saved_files"])
    assert preserved(completed) == before
    assert finish(completed) == result
    assert preserved(completed) == before


@pytest.mark.parametrize(
    "change",
    [
        {"last_stage": "native_saving"},
        {"active_attempt": {"phase": "input_armed"}},
        {"status": "post_completed"},
        {"mode": "single_post_native_context_menu"},
        {"error_type": "VerificationError"},
        {"reason": "An unrelated UI error"},
        {"job_counts": {"observed": 2, "completed": 1, "unresolved": 1}},
        {"output_directory": "C:/other/images"},
    ],
)
def test_nonterminal_or_unrelated_report_is_refused_without_mutation(completed, change):
    before = preserved(completed)
    with pytest.raises((ValueError, NativeUIError)):
        finish(completed, report=completed.report | change)
    assert preserved(completed) == before


@pytest.mark.parametrize("key", ["run_directory", "browser_profile"])
def test_pending_cannot_point_to_another_private_run_or_profile(completed, key):
    before = preserved(completed)
    with pytest.raises((ValueError, NativeUIError)):
        finish(completed, pending=completed.pending | {key: str(completed.base / "foreign")})
    assert preserved(completed) == before


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": 2},
        {"run_id": "not-a-run-identity"},
        {"browser_pid": True},
        {"browser_create_time": float("nan")},
    ],
)
def test_invalid_pending_process_identity_is_refused_without_cleanup(completed, change):
    before = preserved(completed)
    with pytest.raises((ValueError, NativeUIError)):
        finish(completed, pending=completed.pending | change)
    assert preserved(completed) == before


def test_unfinished_image_job_is_never_recovered_or_requeued(completed):
    job_id = completed.jobs[0]["job_id"]
    completed.store.connection.execute("UPDATE jobs SET status='saving' WHERE job_id=?", (job_id,))
    before = preserved(completed)
    with pytest.raises((ValueError, NativeUIError)):
        finish(completed)
    assert preserved(completed) == before


def test_changed_source_permit_is_refused_even_when_files_remain_valid(completed):
    candidate, baseline, detail = candidate_evidence()
    candidate["first_seen_at"] = (
        datetime.fromisoformat(candidate["first_seen_at"]) - timedelta(seconds=1)
    ).isoformat()
    other = make_candidate_save_permit(candidate, baseline, detail)
    from image_monitor.candidate_finish import finish_completed_candidate

    before = preserved(completed)
    with pytest.raises((ValueError, NativeUIError)):
        finish_completed_candidate(
            completed.store,
            other,
            base=completed.base,
            pending=completed.pending,
            report=completed.report,
        )
    assert preserved(completed) == before


def test_corrupt_saved_file_does_not_clear_or_change_completed_state(completed):
    path = Path(completed.artifacts[0]["final_path"])
    path.write_bytes(b"This is not an image")
    before = preserved(completed)
    with pytest.raises((ValueError, NativeUIError)):
        finish(completed)
    assert preserved(completed) == before


def test_replaced_metadata_is_not_silently_rebuilt(completed):
    path = Path(completed.artifacts[0]["metadata_path"])
    data = json.loads(path.read_text())
    data["images"][0]["artifact"]["original_attachment_filename"] = "forged.png"
    path.write_text(json.dumps(data))
    before = preserved(completed)
    with pytest.raises((ValueError, NativeUIError)):
        finish(completed)
    assert preserved(completed) == before


def test_artifact_root_cannot_escape_the_owned_images_directory(completed):
    job_id = completed.jobs[0]["job_id"]
    completed.store.connection.execute(
        "UPDATE artifact_finalizations SET save_root=? WHERE job_id=?",
        (str(completed.base / "foreign-images"), job_id),
    )
    before = preserved(completed)
    with pytest.raises((ValueError, NativeUIError)):
        finish(completed)
    assert preserved(completed) == before


def test_bounded_private_report_reader_preserves_duplicate_json(completed):
    from image_monitor.candidate_finish import read_completed_report

    assert read_completed_report(completed.base, completed.pending) == completed.report
    path = completed.run / "report.json"
    content = '{"schema_version":2,"schema_version":2}'
    path.write_text(content)
    with pytest.raises((ValueError, NativeUIError)):
        read_completed_report(completed.base, completed.pending)
    assert path.read_text() == content
