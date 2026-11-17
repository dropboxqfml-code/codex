"""Validate completed local images without inventing a pending shutdown failure."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from test_candidate_finish import completed as completed
from test_candidate_finish import finish, preserved
from test_candidate_finish import local_exclusive_digest as local_exclusive_digest
from test_candidate_save_policy import candidate_evidence
from test_monitor_finish_runtime import completed_monitor as completed_monitor
from test_monitor_finish_runtime import preserve as preserve_monitor

from image_monitor import candidate_finish
from image_monitor.candidate_finish import CandidateFinishError, verify_completed_candidate_files
from image_monitor.candidate_save_policy import make_candidate_save_permit
from image_monitor.queue import QueueStore


def verify(value, *, store=None, **options):
    return verify_completed_candidate_files(
        store or value.store, value.permit, base=options.pop("base", value.base), **options
    )


def test_readonly_verifier_needs_no_report_profile_or_pending_run(completed):
    expected_summary = finish(completed)
    shutil.rmtree(completed.base / "runs")
    before = preserved(completed)
    with QueueStore(completed.base / "queue.sqlite", read_only=True) as store:
        summary, proofs = verify(completed, store=store)
        assert store.read_only is True
    assert summary == expected_summary
    assert [proof["saved_filename"] for proof in proofs] == ["001.png", "002.png"]
    assert preserved(completed) == before
    assert not (completed.base / "runs").exists()


def test_private_proofs_bind_exact_final_bytes_without_entering_public_summary(completed):
    before = preserved(completed)
    summary, proofs = verify(completed)
    assert len(proofs) == completed.permit.image_count == 2
    public_fields = {
        "saved_filename",
        "detected_format",
        "file_size",
        "width",
        "height",
        "frames",
    }
    for public, proof in zip(summary["saved_files"], proofs, strict=True):
        assert set(public) == public_fields
        assert set(proof) == public_fields | {"path", "sha256"}
        assert {key: proof[key] for key in public_fields} == public
        assert isinstance(proof["path"], Path) and proof["path"].is_absolute()
        assert proof["path"].is_relative_to(completed.base / "images")
        assert proof["path"].name == proof["saved_filename"]
        data = proof["path"].read_bytes()
        assert proof["file_size"] == len(data)
        assert proof["sha256"] == hashlib.sha256(data).hexdigest()
    encoded = json.dumps(summary)
    assert str(completed.base) not in encoded and "sha256" not in encoded and "path" not in encoded
    assert verify(completed) == (summary, proofs)
    assert preserved(completed) == before


def test_monitor_permit_works_without_finishing_or_rewriting_pending_state(completed_monitor):
    before = preserve_monitor(completed_monitor)
    pending = completed_monitor.marker.read_bytes()
    with QueueStore(completed_monitor.base / "queue.sqlite", read_only=True) as store:
        summary, proofs = verify_completed_candidate_files(
            store, completed_monitor.permit, base=completed_monitor.base
        )
    assert summary["job_counts"] == {"observed": 1, "completed": 1, "unresolved": 0}
    assert len(proofs) == 1 and proofs[0]["saved_filename"] == "001.png"
    assert completed_monitor.permit.watch_name == "목록 감시"
    assert completed_monitor.marker.read_bytes() == pending
    assert preserve_monitor(completed_monitor) == before


@pytest.mark.parametrize(
    "change",
    [
        {"status": "post_completed"},
        {"last_stage": "native_saving"},
        {"browser_closed": True},
        {"shared_pending_retained": False},
    ],
)
def test_original_finish_checks_its_report_before_delegating(completed, monkeypatch, change):
    def no_file_verification(*_args, **_options):
        pytest.fail("An unrelated report must fail before common file verification")

    monkeypatch.setattr(candidate_finish, "verify_completed_candidate_files", no_file_verification)
    before = preserved(completed)
    with pytest.raises(CandidateFinishError, match="report"):
        finish(completed, report=completed.report | change)
    assert preserved(completed) == before


def test_frozen_detail_identity_must_still_match_finalized_sources(completed):
    candidate, baseline, detail = candidate_evidence()
    detail["attempt_id"] = "d" * 32
    other = make_candidate_save_permit(candidate, baseline, detail)
    before = preserved(completed)
    with pytest.raises(CandidateFinishError, match="bound"):
        verify_completed_candidate_files(completed.store, other, base=completed.base)
    assert preserved(completed) == before


@pytest.mark.parametrize(
    "query,parameters",
    [
        ("UPDATE jobs SET status='saving' WHERE job_id=?", ()),
        ("UPDATE jobs SET worker_id='foreign',lease_token='foreign' WHERE job_id=?", ()),
        ("UPDATE artifact_finalizations SET phase='metadata_pending' WHERE job_id=?", ()),
        (
            "UPDATE artifact_finalizations SET final_relative=? WHERE job_id=?",
            ("../unrelated.png",),
        ),
        (
            "UPDATE artifact_finalizations SET save_root=? WHERE job_id=?",
            ("C:/unrelated/images",),
        ),
    ],
)
def test_incomplete_owned_or_escaped_work_is_never_repaired(completed, query, parameters):
    job_id = completed.jobs[0]["job_id"]
    completed.store.connection.execute(query, (*parameters, job_id))
    before = preserved(completed)
    with pytest.raises((ValueError, CandidateFinishError)):
        verify(completed)
    assert preserved(completed) == before


@pytest.mark.parametrize("target", ["image", "metadata", "completion"])
def test_changed_local_evidence_is_preserved_and_not_served(completed, target):
    artifact = completed.artifacts[0]
    if target == "image":
        path = Path(artifact["final_path"])
        path.write_bytes(path.read_bytes() + b"Changed bytes after original completion")
    elif target == "metadata":
        path = Path(artifact["metadata_path"])
        data = json.loads(path.read_bytes())
        data["images"][0]["artifact"]["saved_filename"] = "foreign.png"
        path.write_text(json.dumps(data), encoding="utf-8")
    else:
        metadata = dict(artifact["image_metadata"])
        metadata["completion"] = dict(metadata["completion"]) | {"state": "IN_PROGRESS"}
        completed.store.connection.execute(
            "UPDATE artifact_finalizations SET image_metadata_json=? WHERE job_id=?",
            (json.dumps(metadata), completed.jobs[0]["job_id"]),
        )
    before = preserved(completed)
    with pytest.raises((ValueError, CandidateFinishError)):
        verify(completed)
    assert preserved(completed) == before


def test_native_queue_connection_must_belong_to_the_exact_session_root(completed, tmp_path):
    before = preserved(completed)
    with QueueStore(tmp_path / "other.sqlite") as unrelated:
        unrelated_before = tuple(unrelated.connection.iterdump())
        with pytest.raises(CandidateFinishError, match="does not belong"):
            verify(completed, store=unrelated)
        assert tuple(unrelated.connection.iterdump()) == unrelated_before
    assert preserved(completed) == before


def test_missing_session_directory_is_not_created(completed, tmp_path):
    missing = tmp_path / "session-42"
    before = preserved(completed)
    with pytest.raises(FileNotFoundError):
        verify(completed, base=missing)
    assert not missing.exists()
    assert preserved(completed) == before


def test_other_directory_names_are_not_treated_as_native_sessions(completed, tmp_path):
    other = tmp_path / "images"
    other.mkdir()
    before = preserved(completed)
    with pytest.raises(CandidateFinishError, match="exact local session"):
        verify(completed, base=other)
    assert list(other.iterdir()) == []
    assert preserved(completed) == before


def test_generic_snapshot_dictionary_cannot_replace_a_frozen_permit(completed):
    before = preserved(completed)
    with pytest.raises(CandidateFinishError, match="permit"):
        verify_completed_candidate_files(
            completed.store, completed.permit.reference_snapshot, base=completed.base
        )
    assert preserved(completed) == before
