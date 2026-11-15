import errno
import json
import os
import sqlite3
import uuid
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta

import pytest
from PIL import Image

from image_monitor import artifact_files
from image_monitor.artifact_files import (
    APP_MARKER,
    ArtifactError,
    finalize_saved_image,
    recover_finalizations,
)
from image_monitor.paths import FolderPlan, destination
from image_monitor.queue import ImageDiscovery, PostDiscovery, QueueStore
from image_monitor.validation import verify_image

NOW = datetime(2026, 11, 15, tzinfo=UTC)
POST = PostDiscovery(
    "123",
    "public author",
    "123.45",
    NOW,
    title="public title",
    post_url="https://example.invalid/post/123",
)
IMAGE = ImageDiscovery("file-a", 1, "https://images.example.invalid/a.png")


def persist(store, *, images=None, observed_at=NOW):
    images = [IMAGE] if images is None else images
    snapshot = {
        "schema_version": 1,
        "gallery_type": "normal",
        "gallery_id": "comic_new6",
        "post_id": "123",
        "title": POST.title,
        "nickname": POST.nickname,
        "ip_display": POST.ip_display,
        "post_url": POST.post_url,
        "published_at": None,
        "cookies": {"secret": "NEVER_METADATA"},
        "images": [
            asdict(image)
            | {
                "original_attachment_filename": f"original-{image.body_order}.png",
                "original_filename_match_status": "matched",
                "original_filename_source": "attachment_list_dom",
                "cookies": "NEVER_METADATA",
            }
            for image in images
        ],
    }
    return store.persist_post_snapshot(
        watch_name="watch",
        gallery_type="normal",
        gallery_id="comic_new6",
        keyword="ai",
        search_type="search_subject_memo",
        post=POST,
        images=images,
        snapshot=snapshot,
        observed_at=observed_at,
    )


def prepared(store, root, *, images=None):
    persist(store, images=images)
    claim = store.claim_next("native-worker", NOW)
    store.transition(claim["job_id"], claim["lease_token"], "saving")
    store.transition(claim["job_id"], claim["lease_token"], "verifying")
    staging = root / "_staging" / claim["job_id"] / uuid.uuid4().hex / "native-image.png"
    staging.parent.mkdir(parents=True)
    # Deliberately disagree with both the browser and original filename suffixes.
    Image.new("RGB", (17, 11), "red").save(staging, format="WEBP")
    verification = verify_image(staging, writer_finished=True).to_dict()
    return {
        "store": store,
        "job_id": claim["job_id"],
        "token": claim["lease_token"],
        "observation_id": claim["source"]["observation_id"],
        "save_root": root,
        "staging_file": staging,
        "verification": verification,
        "completion_evidence": {
            "state": "COMPLETE",
            "destination_confirmed": True,
            "source_confirmed": True,
            "destination": str(staging),
            "source_url": IMAGE.display_url,
            "exclusive_sha256": verification["sha256"],
        },
        "browser_suggested_filename": "browser-name.jpeg",
        "saved_at": NOW,
    }


def final_path(options):
    job = options["store"].get_job(options["job_id"])
    return destination(options["save_root"], FolderPlan(**job["folder_plan"])) / "001.webp"


def test_finalization_keeps_bytes_names_frozen_source_and_all_job_states(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        options = prepared(
            store,
            tmp_path / "images",
            images=[IMAGE, ImageDiscovery("file-b", 2, "https://images.example.invalid/b.png")],
        )
        original = options["staging_file"].read_bytes()
        result = finalize_saved_image(**options)
        assert result["phase"] == "finalized"
        assert final_path(options).read_bytes() == original
        assert not options["staging_file"].exists()
        assert store.get_job(options["job_id"])["status"] == "completed"
        metadata = json.loads(final_path(options).with_name("metadata.json").read_text())
        assert metadata["application"] == APP_MARKER
        assert metadata["folder_plan"] == store.get_job(options["job_id"])["folder_plan"]
        assert [image["status"] for image in metadata["images"]] == ["completed", "queued"]
        image = metadata["images"][0]["artifact"]
        assert image["original_attachment_filename"] == "original-1.png"
        assert image["browser_suggested_filename"] == "browser-name.jpeg"
        assert image["saved_filename"] == "001.webp"
        assert image["save_method"] == "native_context_menu_save_image_as"
        assert image["verification"] == options["verification"]
        assert image["frozen_post"]["title"] == "public title"
        assert "NEVER_METADATA" not in json.dumps(metadata)
        assert "cookies" not in json.dumps(metadata)


@pytest.mark.parametrize(
    "change",
    [
        {"state": "IN_PROGRESS"},
        {"destination_confirmed": False},
        {"source_confirmed": False},
        {"destination": "some-other-file"},
        {"source_url": "https://images.example.invalid/wrong.png"},
    ],
)
def test_unproven_completion_never_reads_file_or_prepares_journal(tmp_path, monkeypatch, change):
    with QueueStore(tmp_path / "queue.db") as store:
        options = prepared(store, tmp_path / "images")
        options["completion_evidence"].update(change)
        monkeypatch.setattr(
            artifact_files,
            "verify_image",
            lambda *_args, **_kwargs: pytest.fail("Unproven writer cannot be verified"),
        )
        with pytest.raises(ArtifactError, match="completion_unproven"):
            finalize_saved_image(**options)
        assert store.list_artifacts() == []
        assert options["staging_file"].exists()


@pytest.mark.parametrize("field", ["sha256", "file_size", "extension", "width", "frames"])
def test_verification_disagreement_preserves_staging_and_has_no_journal(tmp_path, field):
    with QueueStore(tmp_path / "queue.db") as store:
        options = prepared(store, tmp_path / "images")
        options["verification"][field] = "wrong"
        with pytest.raises(ArtifactError, match="verification_mismatch"):
            finalize_saved_image(**options)
        assert options["staging_file"].exists()
        assert store.list_artifacts() == []


def test_exclusive_hash_disagreement_is_rejected(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        options = prepared(store, tmp_path / "images")
        options["completion_evidence"]["exclusive_sha256"] = "0" * 64
        with pytest.raises(ArtifactError, match="exclusive_verification_mismatch"):
            finalize_saved_image(**options)
        assert store.list_artifacts() == []


def test_database_refusal_before_prepare_preserves_staging_and_does_not_publish(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        options = prepared(store, tmp_path / "images")
        store.connection.execute("""CREATE TRIGGER fail_prepare BEFORE INSERT
            ON artifact_finalizations BEGIN SELECT RAISE(ABORT,'journal unavailable'); END""")
        with pytest.raises(ValueError, match="already reserved"):
            finalize_saved_image(**options)
        assert options["staging_file"].exists()
        assert not final_path(options).exists()
        assert store.list_artifacts() == []


def test_database_refusal_after_publication_recovers_without_native_retry(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        options = prepared(store, tmp_path / "images")
        store.connection.execute("""CREATE TRIGGER fail_completion BEFORE UPDATE
            ON jobs WHEN NEW.status='completed'
            BEGIN SELECT RAISE(ABORT,'completion unavailable'); END""")
        with pytest.raises(sqlite3.IntegrityError, match="completion unavailable"):
            finalize_saved_image(**options)
        assert final_path(options).exists()
        assert not options["staging_file"].exists()
        assert store.get_artifact(options["job_id"])["phase"] == "prepared"
        assert store.claim_next("must-not-repeat", NOW) is None
        store.connection.execute("DROP TRIGGER fail_completion")
        assert recover_finalizations(store, confirm_workers_stopped=True)["recovered"] == 1


def test_cross_device_publication_failure_keeps_journal_and_original_file(tmp_path, monkeypatch):
    if os.name == "nt":
        pytest.skip("POSIX hardlink publication failure")
    with QueueStore(tmp_path / "queue.db") as store:
        options = prepared(store, tmp_path / "images")
        original = options["staging_file"].read_bytes()

        def cross_device(*_args, **_kwargs):
            raise OSError(errno.EXDEV, "simulated cross-device failure")

        monkeypatch.setattr(artifact_files.os, "link", cross_device)
        with pytest.raises(OSError, match="cross-device"):
            finalize_saved_image(**options)
        assert options["staging_file"].read_bytes() == original
        assert not final_path(options).exists()
        assert store.get_artifact(options["job_id"])["phase"] == "prepared"
        assert store.claim_next("must-not-repeat", NOW) is None


@pytest.mark.parametrize("location", ["unexpected.png", "_staging/wrong/native-image.png"])
def test_unexpected_staging_layout_is_rejected(tmp_path, location):
    with QueueStore(tmp_path / "queue.db") as store:
        options = prepared(store, tmp_path / "images")
        bad = options["save_root"] / location
        bad.parent.mkdir(parents=True, exist_ok=True)
        options["staging_file"].rename(bad)
        options["staging_file"] = bad
        options["completion_evidence"]["destination"] = str(bad)
        with pytest.raises(ArtifactError, match="unexpected_staging_layout"):
            finalize_saved_image(**options)
        assert bad.exists()
        assert store.list_artifacts() == []


def test_existing_image_never_overwritten_even_with_identical_bytes(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        options = prepared(store, tmp_path / "images")
        target = final_path(options)
        target.parent.mkdir(parents=True)
        target.write_bytes(options["staging_file"].read_bytes())
        with pytest.raises(ArtifactError, match="destination_exists"):
            finalize_saved_image(**options)
        assert target.exists() and options["staging_file"].exists()
        assert store.list_artifacts() == []


@pytest.mark.parametrize("stage", ["prepare", "publish", "complete", "metadata", "finalized"])
def test_crashes_resume_local_journal_once_without_reclaiming_or_saving(
    tmp_path,
    monkeypatch,
    stage,
):
    path = tmp_path / "queue.db"
    with QueueStore(path) as store:
        options = prepared(store, tmp_path / "images")
        job_id = options["job_id"]
        target = final_path(options)
        if stage in {"prepare", "complete", "finalized"}:
            name = {
                "prepare": "prepare_artifact",
                "complete": "complete_artifact",
                "finalized": "mark_metadata_written",
            }[stage]
            original = getattr(store, name)

            def crash(*args, **kwargs):
                original(*args, **kwargs)
                raise RuntimeError("simulated crash")

            monkeypatch.setattr(store, name, crash)
        else:
            name = "_publish" if stage == "publish" else "_write_metadata"
            original = getattr(artifact_files, name)

            def crash(*args, **kwargs):
                original(*args, **kwargs)
                raise RuntimeError("simulated crash")

            monkeypatch.setattr(artifact_files, name, crash)
        with pytest.raises(RuntimeError, match="simulated crash"):
            finalize_saved_image(**options)
        monkeypatch.undo()
    with QueueStore(path) as store:
        assert store.claim_next("must-not-save-again", NOW + timedelta(hours=1)) is None
        summary = recover_finalizations(store, confirm_workers_stopped=True)
        assert summary["manual_review"] == []
        assert store.get_artifact(job_id)["phase"] == "finalized"
        assert store.get_job(job_id)["status"] == "completed"
        verified = verify_image(target, writer_finished=True)
        assert verified.sha256 == options["verification"]["sha256"]
        assert (
            json.loads(target.with_name("metadata.json").read_text())["images"][0]["status"]
            == "completed"
        )
        assert recover_finalizations(store, confirm_workers_stopped=True) == {
            "recovered": 0,
            "metadata_written": 0,
            "skipped": 1,
            "manual_review": [],
        }


def interrupt_before_publish(options, monkeypatch):
    def crash(*_args, **_kwargs):
        raise RuntimeError("before publication")

    with monkeypatch.context() as patch:
        patch.setattr(artifact_files, "_publish", crash)
        with pytest.raises(RuntimeError, match="before publication"):
            finalize_saved_image(**options)


def test_recovery_requires_workers_stopped_before_any_file_or_database_work(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        with pytest.raises(ArtifactError, match="confirm_workers_stopped_required"):
            recover_finalizations(store)


@pytest.mark.parametrize("problem", ["missing", "changed", "conflicting"])
def test_recovery_preserves_uncertain_files_and_prevents_native_requeue(
    tmp_path,
    monkeypatch,
    problem,
):
    with QueueStore(tmp_path / "queue.db") as store:
        options = prepared(store, tmp_path / "images")
        interrupt_before_publish(options, monkeypatch)
        staging, target = options["staging_file"], final_path(options)
        if problem == "missing":
            staging.unlink()
        elif problem == "changed":
            Image.new("RGB", (19, 13), "blue").save(staging, format="PNG")
        else:
            target.parent.mkdir(parents=True)
            target.write_bytes(staging.read_bytes())  # Same bytes do not establish ownership.
        before = {p: p.read_bytes() for p in (staging, target) if p.exists()}
        summary = recover_finalizations(store, confirm_workers_stopped=True)
        assert len(summary["manual_review"]) == 1
        assert store.get_job(options["job_id"])["status"] == "manual_review"
        assert store.get_artifact(options["job_id"])["phase"] == "prepared"
        assert store.claim_next("no-native-retry", NOW + timedelta(hours=1)) is None
        assert {p: p.read_bytes() for p in before} == before


@pytest.mark.skipif(os.name == "nt", reason="Only POSIX publishes using hardlinks")
def test_recovery_finishes_interrupted_hardlink_publication(tmp_path, monkeypatch):
    with QueueStore(tmp_path / "queue.db") as store:
        options = prepared(store, tmp_path / "images")
        interrupt_before_publish(options, monkeypatch)
        target = final_path(options)
        target.parent.mkdir(parents=True)
        os.link(options["staging_file"], target)
        assert recover_finalizations(store, confirm_workers_stopped=True)["manual_review"] == []
        assert target.exists() and not options["staging_file"].exists()
        assert store.get_job(options["job_id"])["status"] == "completed"


@pytest.mark.parametrize("existing", ["unrelated", "other_post", "other_plan", "invalid_json"])
def test_unowned_metadata_is_preserved_and_completed_image_waits_for_review(tmp_path, existing):
    with QueueStore(tmp_path / "queue.db") as store:
        options = prepared(store, tmp_path / "images")
        target = final_path(options)
        target.parent.mkdir(parents=True)
        sidecar = target.with_name("metadata.json")
        payload = {
            "application": APP_MARKER,
            "schema_version": 1,
            "post": {"gallery_type": "normal", "gallery_id": "comic_new6", "post_id": "123"},
            "folder_plan": store.get_job(options["job_id"])["folder_plan"],
        }
        if existing == "unrelated":
            payload["application"] = "someone else"
        elif existing == "other_post":
            payload["post"]["post_id"] = "999"
        elif existing == "other_plan":
            payload["folder_plan"] = {}
        before = "not json" if existing == "invalid_json" else json.dumps(payload)
        sidecar.write_text(before)
        with pytest.raises(ArtifactError, match="unowned_metadata"):
            finalize_saved_image(**options)
        assert sidecar.read_text() == before
        assert target.exists()
        assert store.get_job(options["job_id"])["status"] == "completed"
        assert store.get_artifact(options["job_id"])["phase"] == "metadata_pending"
        summary = recover_finalizations(store, confirm_workers_stopped=True)
        assert summary["manual_review"][0]["reason"] == "unowned_metadata"
        assert sidecar.read_text() == before


def make_symlink(path, target, *, directory=False):
    try:
        path.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError) as error:
        if (
            isinstance(error, NotImplementedError)
            or getattr(error, "winerror", None) == 1314
            or (getattr(error, "errno", None) in {errno.EPERM, errno.EACCES, errno.ENOSYS})
        ):
            pytest.skip("Symlinks are unavailable")
        raise


def test_symlink_within_root_is_rejected_even_when_it_does_not_escape(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        options = prepared(store, tmp_path / "images")
        staging = options["staging_file"]
        actual = staging.with_name("real.png")
        staging.rename(actual)
        make_symlink(staging, actual)
        with pytest.raises(ArtifactError, match="symlink_or_reparse_path"):
            finalize_saved_image(**options)
        assert actual.exists()
        assert store.list_artifacts() == []


def test_metadata_symlink_never_changes_target(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        options = prepared(store, tmp_path / "images")
        target = final_path(options)
        target.parent.mkdir(parents=True)
        unrelated = tmp_path / "unrelated.txt"
        unrelated.write_text("preserve")
        make_symlink(target.with_name("metadata.json"), unrelated)
        with pytest.raises(ArtifactError, match="symlink_or_reparse_path"):
            finalize_saved_image(**options)
        assert unrelated.read_text() == "preserve"


def test_artifact_source_stays_frozen_after_completed_url_changes(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        options = prepared(store, tmp_path / "images")
        result = finalize_saved_image(**options)
        original_observation = result["observation_id"]
        updated = replace(IMAGE, display_url="https://images.example.invalid/refreshed.png")
        persist(store, images=[updated], observed_at=NOW + timedelta(seconds=1))
        # Rebuild a pending sidecar from the frozen artifact, not the current URL.
        store.connection.execute(
            "UPDATE artifact_finalizations SET phase='metadata_pending' WHERE job_id=?",
            (options["job_id"],),
        )
        assert recover_finalizations(store, confirm_workers_stopped=True)["manual_review"] == []
        metadata = json.loads(final_path(options).with_name("metadata.json").read_text())
        artifact = metadata["images"][0]["artifact"]
        assert artifact["observation_id"] == original_observation
        assert artifact["display_url"] == IMAGE.display_url
        assert store.get_job(options["job_id"])["display_url"] == updated.display_url


def test_newer_same_url_observation_cannot_replace_the_claimed_source(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        options = prepared(store, tmp_path / "images")
        original_observation = options["observation_id"]
        newer_snapshot = store.get_observation(original_observation)["snapshot"]
        newer_snapshot["title"] = "new title after native claim"
        newer_snapshot["images"][0]["original_attachment_filename"] = "new-name-after-claim.png"
        store.persist_post_snapshot(
            watch_name="watch",
            gallery_type="normal",
            gallery_id="comic_new6",
            keyword="ai",
            search_type="search_subject_memo",
            post=replace(POST, title="new title after native claim"),
            images=[IMAGE],
            snapshot=newer_snapshot,
            observed_at=NOW + timedelta(seconds=1),
        )
        assert store.get_job_source(options["job_id"])["observation_id"] != original_observation
        result = finalize_saved_image(**options)
        assert result["observation_id"] == original_observation
        metadata = json.loads(final_path(options).with_name("metadata.json").read_text())
        frozen = metadata["images"][0]["artifact"]
        assert frozen["original_attachment_filename"] == "original-1.png"
        assert frozen["frozen_post"]["title"] == "public title"
