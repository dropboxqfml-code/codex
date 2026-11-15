import json
import sqlite3
import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from image_monitor.artifact_files import finalize_saved_image
from image_monitor.native_state import PendingSave
from image_monitor.native_ui import NativeUIError
from image_monitor.post_resume import MAX_REPORT_BYTES, resume_preinput_failure
from image_monitor.queue import ImageDiscovery, PostDiscovery, QueueError, QueueStore
from image_monitor.site_inspection import DEFAULT_POST_URL
from image_monitor.validation import verify_image

NOW = datetime(2026, 11, 15, 12, tzinfo=UTC)
REASON = "Foreground focus is outside the bound probe window; input stopped"


def image_files(root):
    return {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }


@pytest.fixture
def legacy(tmp_path):
    base = tmp_path / "session-1"
    run = base / "runs" / uuid.uuid4().hex
    run.mkdir(parents=True)
    (run / "browser-profile").mkdir()
    state = PendingSave(tmp_path / "shared.json")
    pending = state.begin(run)
    state.update_browser(pending, 12345, 123.0)
    with QueueStore(base / "queue.sqlite") as store:
        images = [
            ImageDiscovery("fixture-first", 1, "https://images.example.invalid/first"),
            ImageDiscovery("fixture-second", 2, "https://images.example.invalid/second"),
        ]
        snapshot = {
            "schema_version": 1,
            "gallery_type": "normal",
            "gallery_id": "comic_new6",
            "post_id": "7036949",
            "post_url": DEFAULT_POST_URL,
            "title": "Synthetic recovery fixture",
            "nickname": "fixture author",
            "ip_display": None,
            "published_at": None,
            "images": [asdict(image) for image in images],
        }
        result = store.persist_post_snapshot(
            watch_name="fixture",
            gallery_type="normal",
            gallery_id="comic_new6",
            keyword="fixture",
            search_type="search_subject_memo",
            post=PostDiscovery(
                "7036949",
                "fixture author",
                None,
                NOW,
                title=snapshot["title"],
                post_url=DEFAULT_POST_URL,
            ),
            images=images,
            snapshot=snapshot,
            observed_at=NOW,
        )
        first = store.claim_next("fixture-worker", NOW)
        store.transition(first["job_id"], first["lease_token"], "saving")
        store.transition(first["job_id"], first["lease_token"], "verifying")
        first_path = (
            base / "images" / "_staging" / first["job_id"] / uuid.uuid4().hex / "native-image.webp"
        )
        first_path.parent.mkdir(parents=True)
        Image.new("RGB", (4, 3), "blue").save(first_path, format="WEBP")
        verification = verify_image(first_path, writer_finished=True).to_dict()
        artifact = finalize_saved_image(
            store,
            first["job_id"],
            first["lease_token"],
            observation_id=result["observation_id"],
            save_root=base / "images",
            staging_file=first_path,
            verification=verification,
            completion_evidence={
                "state": "COMPLETE",
                "destination_confirmed": True,
                "source_confirmed": True,
                "destination": str(first_path),
                "source_url": images[0].display_url,
                "exclusive_sha256": verification["sha256"],
            },
            browser_suggested_filename="fixture-first.webp",
            saved_at=NOW,
        )
        second = store.claim_next("fixture-worker", NOW)
        store.transition(second["job_id"], second["lease_token"], "saving")
        # Exercise preservation of prior network retry accounting and both delays.
        store.connection.execute(
            "UPDATE jobs SET attempt_count=2,first_failure_at=?,next_retry_at=?,"
            "server_not_before=? WHERE job_id=?",
            tuple(
                value.isoformat(timespec="microseconds")
                for value in (
                    NOW - timedelta(hours=1),
                    NOW + timedelta(minutes=3),
                    NOW + timedelta(minutes=4),
                )
            )
            + (second["job_id"],),
        )
        store.defer_service("default", NOW + timedelta(minutes=5))
        store.record_failure(second["job_id"], second["lease_token"], "ui", "NativeUIError", NOW)
        stage = base / "images" / "_staging" / second["job_id"] / uuid.uuid4().hex
        stage.mkdir(parents=True)
        report = {
            "schema_version": 1,
            "mode": "single_post_native_context_menu",
            "status": "manual_review",
            "error_type": "NativeUIError",
            "reason": REASON,
            "last_stage": "native_saving",
            "native_stage": "image_load",
            "shared_pending_retained": True,
            "saved_files": [{"job_id": first["job_id"], "saved_filename": "001.webp"}],
            "active_attempt": {
                "job_id": second["job_id"],
                "observation_id": result["observation_id"],
                "staging_directory": str(stage),
            },
        }
        values = SimpleNamespace(
            base=base,
            run=run,
            state=state,
            pending=pending,
            store=store,
            first_id=first["job_id"],
            job_id=second["job_id"],
            artifact=artifact,
            observation_id=result["observation_id"],
            stage=stage,
            report=report,
        )
        write_report(values)
        yield values


def write_report(values):
    (values.run / "report.json").write_text(json.dumps(values.report), encoding="utf-8")


def resume(values, **kwargs):
    return resume_preinput_failure(
        values.store,
        values.state,
        base=values.base,
        now=NOW,
        is_running=kwargs.pop("is_running", lambda _pending: False),
        **kwargs,
    )


def unchanged_failure(values, **kwargs):
    jobs = values.store.list_jobs()
    history = values.store.history(values.job_id)
    artifacts = values.store.list_artifacts()
    marker = values.state.path.read_bytes()
    files = image_files(values.base / "images")
    with pytest.raises(NativeUIError):
        resume(values, **kwargs)
    assert values.store.list_jobs() == jobs
    assert values.store.history(values.job_id) == history
    assert values.store.list_artifacts() == artifacts
    assert values.state.path.read_bytes() == marker
    assert image_files(values.base / "images") == files


@pytest.mark.parametrize("reason", [REASON, "The probe page itself is not in the foreground"])
def test_resume_preserves_completed_artifact_bytes_report_and_retry_limits(legacy, reason):
    legacy.report["reason"] = reason
    write_report(legacy)
    first = legacy.store.get_job(legacy.first_id)
    artifact = legacy.store.get_artifact(legacy.first_id)
    second = legacy.store.get_job(legacy.job_id)
    files = image_files(legacy.base / "images")
    report = (legacy.run / "report.json").read_bytes()
    history = legacy.store.history(legacy.job_id)
    limits = list(legacy.store.connection.execute("SELECT * FROM service_limits"))
    result = resume(legacy)
    assert result == {
        "status": "resumed_preinput_failure",
        "job_id": legacy.job_id,
        "files_preserved": True,
        "pending_cleared": True,
        "already_resumed": False,
    }
    assert not legacy.state.path.exists()
    assert legacy.store.get_job(legacy.first_id) == first
    assert legacy.store.get_artifact(legacy.first_id) == artifact
    assert legacy.store.get_job(legacy.job_id) == second | {"status": "queued", "last_error": None}
    assert image_files(legacy.base / "images") == files
    assert (legacy.run / "report.json").read_bytes() == report
    assert legacy.stage.is_dir() and not list(legacy.stage.iterdir())
    assert len(legacy.store.history(legacy.job_id)) == len(history) + 1
    assert legacy.store.history(legacy.job_id)[-1] | {"history_id": 0} == {
        "history_id": 0,
        "job_id": legacy.job_id,
        "at": NOW.isoformat(timespec="microseconds"),
        "kind": "pre_input_resume",
        "reason": "verified_no_input",
        "attempt_count": 2,
        "resulting_status": "queued",
    }
    assert list(legacy.store.connection.execute("SELECT * FROM service_limits")) == limits
    assert legacy.store.claim_next("fixture-again", NOW) is None


def test_no_pending_marker_does_not_infer_recovery_from_an_old_report(legacy):
    legacy.state.finish(legacy.pending)
    before = legacy.store.get_job(legacy.job_id)
    assert resume(legacy, is_running=lambda _: pytest.fail("No browser check needed")) == {
        "status": "no_pending_save"
    }
    assert legacy.store.get_job(legacy.job_id) == before


@pytest.mark.parametrize("running", [True, None, 0])
def test_browser_and_profile_must_be_verified_dead(legacy, running):
    unchanged_failure(legacy, is_running=lambda _: running)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 2),
        ("schema_version", True),
        ("mode", "native_probe"),
        ("status", "post_completed"),
        ("error_type", "NativeFocusError"),
        ("reason", REASON + "."),
        ("reason", "Save Image As menu could not be identified"),
        ("last_stage", "download_completion"),
        ("native_stage", "context_menu"),
        ("native_stage", "save_dialog"),
        ("shared_pending_retained", False),
    ],
)
def test_legacy_report_must_match_every_preinput_proof(legacy, field, value):
    legacy.report[field] = value
    write_report(legacy)
    unchanged_failure(legacy)


@pytest.mark.parametrize("bad_report", [b"not json", b"[]", b"\xff", b'{"x":1,"x":2}'])
def test_malformed_report_is_preserved(legacy, bad_report):
    (legacy.run / "report.json").write_bytes(bad_report)
    unchanged_failure(legacy)
    assert (legacy.run / "report.json").read_bytes() == bad_report


def test_report_size_is_bounded(legacy):
    (legacy.run / "report.json").write_bytes(b" " * (MAX_REPORT_BYTES + 1))
    unchanged_failure(legacy)


@pytest.mark.parametrize("field", ["job_id", "observation_id", "staging_directory"])
def test_report_attempt_must_match_existing_frozen_job(legacy, field):
    legacy.report["active_attempt"][field] = uuid.uuid4().hex
    write_report(legacy)
    unchanged_failure(legacy)


@pytest.mark.parametrize("field", ["completion", "verification", "staging_path"])
def test_later_save_evidence_conflicts_with_preinput_report(legacy, field):
    legacy.report["active_attempt"][field] = {}
    write_report(legacy)
    unchanged_failure(legacy)


@pytest.mark.parametrize("field", ["run_directory", "browser_profile"])
def test_pending_run_and_profile_must_belong_to_the_exact_base(legacy, field):
    pending = legacy.state.read()
    pending[field] = str(legacy.base / "different")
    legacy.state.path.write_text(json.dumps(pending))
    unchanged_failure(legacy)


def test_traversal_alias_for_staging_is_rejected(legacy):
    legacy.report["active_attempt"]["staging_directory"] = str(
        legacy.stage.parent / ".." / legacy.job_id / legacy.stage.name
    )
    write_report(legacy)
    unchanged_failure(legacy)


@pytest.mark.parametrize("kind", ["file", "directory"])
def test_any_reported_attempt_entry_blocks_resume(legacy, kind):
    entry = legacy.stage / "fixture-entry"
    entry.write_bytes(b"preserve") if kind == "file" else entry.mkdir()
    unchanged_failure(legacy)


def test_nonempty_other_attempt_for_same_job_blocks_resume(legacy):
    other = legacy.stage.parent / uuid.uuid4().hex
    other.mkdir()
    (other / "native-image.webp").write_bytes(b"preserve uncertain bytes")
    unchanged_failure(legacy)


def test_empty_other_attempt_is_preserved(legacy):
    other = legacy.stage.parent / uuid.uuid4().hex
    other.mkdir()
    resume(legacy)
    assert other.is_dir()


@pytest.mark.parametrize("suffix", ["", ".webp", ".png", ".crdownload"])
def test_any_existing_destination_slot_blocks_resume(legacy, suffix):
    parent = Path(legacy.artifact["final_path"]).parent
    (parent / f"002{suffix}").write_bytes(b"preserve destination")
    unchanged_failure(legacy)


@pytest.mark.parametrize("kind", ["report", "stage", "profile", "destination", "descendant"])
def test_links_cannot_supply_recovery_proofs(legacy, tmp_path, kind):
    target = tmp_path / "link-target"
    if kind == "report":
        link = legacy.run / "report.json"
        target.write_bytes(link.read_bytes())
        link.unlink()
    elif kind == "destination":
        target.write_bytes(b"uncertain")
        link = Path(legacy.artifact["final_path"]).with_name("002.webp")
    elif kind == "descendant":
        target.mkdir()
        link = legacy.stage / "linked-directory"
    else:
        target.mkdir()
        link = legacy.stage if kind == "stage" else legacy.run / "browser-profile"
        link.rmdir()
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except OSError as error:
        pytest.skip(f"Symlinks unavailable: {error}")
    unchanged_failure(legacy)
    assert link.is_symlink()


def test_windows_reparse_attribute_blocks_staging_proof(legacy, monkeypatch):
    original = Path.lstat

    def lstat(path, *args, **kwargs):
        info = original(path, *args, **kwargs)
        if path == legacy.stage:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info

    monkeypatch.setattr(Path, "lstat", lstat)
    unchanged_failure(legacy)


@pytest.mark.parametrize(
    "sql,parameters",
    [
        ("UPDATE jobs SET status='manual_review' WHERE job_id=?", ()),
        ("UPDATE jobs SET last_error='different' WHERE job_id=?", ()),
        ("UPDATE jobs SET lease_token='claimed' WHERE job_id=?", ()),
        ("UPDATE jobs SET worker_id='claimed' WHERE job_id=?", ()),
        ("UPDATE attempts SET kind='local' WHERE job_id=?", ()),
        ("UPDATE attempts SET reason='different' WHERE job_id=?", ()),
        ("UPDATE attempts SET resulting_status='queued' WHERE job_id=?", ()),
        ("UPDATE attempts SET attempt_count=0 WHERE job_id=?", ()),
    ],
)
def test_job_and_latest_history_must_match_the_failure(legacy, sql, parameters):
    legacy.store.connection.execute(sql, parameters + (legacy.job_id,))
    unchanged_failure(legacy)


@pytest.mark.parametrize("post_url", [DEFAULT_POST_URL + "&page=2", "https://example.invalid/123"])
def test_frozen_post_url_must_be_exactly_canonical(legacy, post_url):
    row = legacy.store.connection.execute(
        "SELECT snapshot_json FROM post_observations WHERE observation_id=?",
        (legacy.observation_id,),
    ).fetchone()
    snapshot = json.loads(row[0])
    snapshot["post_url"] = post_url
    legacy.store.connection.execute(
        "UPDATE post_observations SET snapshot_json=? WHERE observation_id=?",
        (json.dumps(snapshot), legacy.observation_id),
    )
    unchanged_failure(legacy)


@pytest.mark.parametrize("change", ["identity", "image_url", "association"])
def test_frozen_source_must_still_identify_this_job(legacy, change):
    if change == "image_url":
        legacy.store.connection.execute(
            "UPDATE jobs SET display_url='https://images.example.invalid/changed' WHERE job_id=?",
            (legacy.job_id,),
        )
    elif change == "association":
        legacy.store.connection.execute(
            "DELETE FROM observation_jobs WHERE observation_id=? AND job_id=?",
            (legacy.observation_id, legacy.job_id),
        )
    else:
        row = legacy.store.connection.execute(
            "SELECT snapshot_json FROM post_observations WHERE observation_id=?",
            (legacy.observation_id,),
        ).fetchone()
        snapshot = json.loads(row[0])
        snapshot["post_id"] = "42"
        legacy.store.connection.execute(
            "UPDATE post_observations SET snapshot_json=? WHERE observation_id=?",
            (json.dumps(snapshot), legacy.observation_id),
        )
    unchanged_failure(legacy)


def test_artifact_journal_for_failed_job_blocks_recovery(legacy, monkeypatch):
    original = legacy.store.get_artifact
    monkeypatch.setattr(
        legacy.store,
        "get_artifact",
        lambda job_id: legacy.artifact if job_id == legacy.job_id else original(job_id),
    )
    unchanged_failure(legacy)


def test_a_store_for_another_database_cannot_resume_the_pending_job(legacy, tmp_path):
    jobs = legacy.store.list_jobs()
    history = legacy.store.history(legacy.job_id)
    marker = legacy.state.path.read_bytes()
    files = image_files(legacy.base / "images")
    with QueueStore(tmp_path / "other.sqlite") as other:
        with pytest.raises(NativeUIError, match="does not belong"):
            resume_preinput_failure(
                other, legacy.state, base=legacy.base, now=NOW, is_running=lambda _: False
            )
        assert other.list_jobs() == []
    assert legacy.store.list_jobs() == jobs
    assert legacy.store.history(legacy.job_id) == history
    assert legacy.state.path.read_bytes() == marker
    assert image_files(legacy.base / "images") == files


def test_queue_database_symlink_is_refused(legacy, tmp_path):
    legacy.store.close()
    original = legacy.base / "queue.sqlite"
    target = tmp_path / "original-queue.sqlite"
    original.rename(target)
    try:
        original.symlink_to(target)
    except OSError as error:
        pytest.skip(f"Symlinks unavailable: {error}")
    with QueueStore(original) as linked:
        legacy.store = linked
        unchanged_failure(legacy)
        assert original.is_symlink()


@pytest.mark.parametrize("error_type", [QueueError, sqlite3.OperationalError])
def test_queue_refusal_leaves_pending_and_files_unchanged(legacy, monkeypatch, error_type):
    def refuse(*_args, **_kwargs):
        raise error_type("Synthetic queue refusal")

    monkeypatch.setattr(legacy.store, "resume_preinput_failure", refuse)
    unchanged_failure(legacy)


def test_marker_cleanup_after_commit_is_idempotent_without_another_history_entry(
    legacy, monkeypatch
):
    finish = legacy.state.finish

    def fail_finish(_pending):
        raise OSError("Synthetic marker cleanup failure")

    monkeypatch.setattr(legacy.state, "finish", fail_finish)
    with pytest.raises(NativeUIError):
        resume(legacy)
    assert legacy.state.read() == legacy.pending
    assert legacy.store.get_job(legacy.job_id)["status"] == "queued"
    history = legacy.store.history(legacy.job_id)
    files = image_files(legacy.base / "images")
    monkeypatch.setattr(legacy.state, "finish", finish)
    monkeypatch.setattr(
        legacy.store,
        "resume_preinput_failure",
        lambda *_args, **_kwargs: pytest.fail("A committed resume must not be repeated"),
    )
    assert resume(legacy)["already_resumed"] is True
    assert not legacy.state.path.exists()
    assert legacy.store.history(legacy.job_id) == history
    assert image_files(legacy.base / "images") == files


def test_ordinary_queued_job_is_not_treated_as_a_committed_resume(legacy):
    legacy.store.connection.execute(
        "UPDATE jobs SET status='queued',last_error=NULL WHERE job_id=?", (legacy.job_id,)
    )
    unchanged_failure(legacy)


def test_crash_gap_with_new_uncertain_bytes_retains_pending(legacy, monkeypatch):
    monkeypatch.setattr(legacy.state, "finish", lambda _: None)
    resume(legacy)
    (legacy.stage / "native-image.webp").write_bytes(b"uncertain")
    unchanged_failure(legacy)
