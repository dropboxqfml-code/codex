import sqlite3
from contextlib import closing
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta

import pytest

from image_monitor import queue as queue_module
from image_monitor.queue import (
    SCHEMA_VERSION,
    ImageDiscovery,
    PostDiscovery,
    QueueError,
    QueueStore,
)

NOW = datetime(2026, 11, 15, tzinfo=UTC)
IMAGE = ImageDiscovery("stable-a", 1, "https://images.example.invalid/a.png")
POST = PostDiscovery("123", "example", None, NOW)
VERIFIED = {
    "sha256": "a" * 64,
    "detected_format": "PNG",
    "extension": "png",
    "file_size": 372,
    "width": 96,
    "height": 64,
    "frames": 1,
}


def add_post(store, *, image=IMAGE, post=POST, gallery_type="normal", observed_at=NOW, **extra):
    return store.persist_post_snapshot(
        watch_name="watch",
        gallery_type=gallery_type,
        gallery_id="comic_new6",
        keyword="ai",
        search_type="search_subject_memo",
        post=post,
        images=[image],
        observed_at=observed_at,
        snapshot={
            "gallery_type": gallery_type,
            "gallery_id": "comic_new6",
            "post_id": post.post_id,
            "images": [asdict(image) | extra],
        },
    )


def verifying(store, **options):
    added = add_post(store, **options)
    claim = store.claim_next("worker", NOW + timedelta(days=1))
    store.transition(claim["job_id"], claim["lease_token"], "saving")
    store.transition(claim["job_id"], claim["lease_token"], "verifying")
    assert claim["job_id"] == added["jobs"][0]["job_id"]
    return claim


def prepare(store, claim, tmp_path, **overrides):
    filename = f"{claim['file_slot']:03d}.png"
    options = {
        "observation_id": claim["source"]["observation_id"],
        "save_root": str(tmp_path / "storage"),
        "staging_relative": f"_staging/{claim['job_id']}/attempt/native-image.png",
        "final_relative": claim["folder_plan"]["relative_directory"] + "/" + filename,
        "verification": VERIFIED,
        "image_metadata": claim["source"]["image"] | {"saved_filename": filename},
        "saved_at": NOW + timedelta(hours=1),
    }
    return store.prepare_artifact(claim["job_id"], claim["lease_token"], **(options | overrides))


def downgrade(path, version):
    with closing(sqlite3.connect(path)) as db, db:
        for table in (
            "candidate_details",
            "watch_gaps",
            "watch_candidates",
            "watch_scans",
            "watch_state",
        ):
            db.execute(f"DROP TABLE {table}")
        if version < 3:
            db.execute("DROP TABLE artifact_finalizations")
        if version == 1:
            db.execute("DROP TABLE observation_jobs")
            db.execute("DROP TABLE post_observations")
        db.execute(f"PRAGMA user_version={version}")


def database_state(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        return {
            "dump": tuple(db.iterdump()),
            "schema": db.execute(
                "SELECT type,name,sql FROM sqlite_master ORDER BY type,name"
            ).fetchall(),
            "version": db.execute("PRAGMA user_version").fetchone()[0],
            "application": db.execute("PRAGMA application_id").fetchone()[0],
            "integrity": db.execute("PRAGMA integrity_check").fetchall(),
        }


def test_claim_captures_latest_matching_immutable_source_inside_its_transaction(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        first = add_post(store, caption="old")
        second = add_post(store, observed_at=NOW + timedelta(seconds=1), caption="claimed")
        claim = store.claim_next("worker", NOW + timedelta(seconds=2))
        assert claim["source"]["observation_id"] == second["observation_id"]
        add_post(store, observed_at=NOW + timedelta(seconds=3), caption="newer")
        assert claim["source"]["image"]["caption"] == "claimed"
        assert store.get_job_source(claim["job_id"])["image"]["caption"] == "newer"
        assert (
            store.get_job_source(claim["job_id"], first["observation_id"])["image"]["caption"]
            == "old"
        )
        claim["source"]["image"]["caption"] = "external mutation"
        assert (
            store.get_observation(second["observation_id"])["snapshot"]["images"][0]["caption"]
            == "claimed"
        )


def test_source_requires_association_and_exact_current_display_url(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        one = add_post(store)
        other = add_post(store, post=replace(POST, post_id="124"))
        job_id = one["jobs"][0]["job_id"]
        assert store.get_job_source(job_id, other["observation_id"]) is None
        store.queue_images(
            gallery_type="normal",
            gallery_id="comic_new6",
            post_id="123",
            images=[replace(IMAGE, display_url="https://changed.example.invalid/image")],
        )
        assert store.get_job_source(job_id) is None
        assert (
            store.get_observation(one["observation_id"])["snapshot"]["images"][0]["display_url"]
            == IMAGE.display_url
        )


def test_artifact_lifecycle_is_separate_from_external_file_and_metadata_work(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        claim = verifying(store)
        prepared = prepare(store, claim, tmp_path)
        assert prepared["phase"] == "prepared"
        assert prepared["verification"] == VERIFIED
        assert prepared["image_metadata"]["saved_filename"] == "001.png"
        assert store.get_job(claim["job_id"])["status"] == "verifying"
        assert not (tmp_path / "storage").exists()  # Queue APIs never create artifact files.
        assert prepare(store, claim, tmp_path) == prepared
        assert store.list_artifacts() == [prepared]
        complete = store.complete_artifact(claim["job_id"], claim["lease_token"])
        assert complete["phase"] == "metadata_pending"
        job = store.get_job(claim["job_id"])
        assert (
            job["status"] == "completed" and job["worker_id"] is None and job["lease_token"] is None
        )
        assert store.claim_next("another", NOW + timedelta(days=2)) is None
        finalized = store.mark_metadata_written(claim["job_id"])
        assert finalized["phase"] == "finalized"
        assert store.mark_metadata_written(claim["job_id"]) == finalized
        assert store.list_artifacts() == [finalized]


@pytest.mark.parametrize("stage", ["loading", "saving"])
def test_only_verifying_claim_can_prepare_a_journal(tmp_path, stage):
    with QueueStore(tmp_path / "queue.db") as store:
        add_post(store)
        claim = store.claim_next("worker", NOW)
        if stage == "saving":
            store.transition(claim["job_id"], claim["lease_token"], "saving")
        with pytest.raises(QueueError, match="verifying"):
            prepare(store, claim, tmp_path)
        assert store.list_artifacts() == []


def test_stale_token_and_unassociated_source_cannot_prepare(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        claim = verifying(store)
        with pytest.raises(QueueError, match="claim"):
            prepare(store, claim | {"lease_token": "stale"}, tmp_path)
        with pytest.raises(QueueError, match="associated"):
            prepare(store, claim, tmp_path, observation_id="not-observed")
        assert store.list_artifacts() == []


@pytest.mark.parametrize(
    "change",
    [
        {"sha256": "bad"},
        {"sha256": "x" * 64},
        {"detected_format": "SVG"},
        {"file_size": 0},
        {"file_size": True},
        {"extension": "jpg"},
        {"width": False},
    ],
)
def test_invalid_verification_cannot_be_journalled(tmp_path, change):
    with QueueStore(tmp_path / "queue.db") as store:
        claim = verifying(store)
        with pytest.raises(QueueError, match="verification"):
            prepare(store, claim, tmp_path, verification=VERIFIED | change)
        assert store.list_artifacts() == []


@pytest.mark.parametrize(
    "relative",
    [
        "../escape.png",
        "/absolute.png",
        "C:/absolute.png",
        "a/../escape.png",
        "a/CON.png",
        "a/unsafe:stream",
        "a/trailing. ",
        "_staging/another-job/attempt/image.png",
    ],
)
def test_unsafe_or_wrong_job_staging_paths_are_rejected(tmp_path, relative):
    with QueueStore(tmp_path / "queue.db") as store:
        claim = verifying(store)
        with pytest.raises(QueueError):
            prepare(store, claim, tmp_path, staging_relative=relative)
        assert store.list_artifacts() == []


@pytest.mark.parametrize("suffix", ["002.png", "001.jpg", "../001.png"])
def test_final_name_must_use_frozen_file_slot_and_detected_extension(tmp_path, suffix):
    with QueueStore(tmp_path / "queue.db") as store:
        claim = verifying(store)
        with pytest.raises(QueueError):
            prepare(
                store,
                claim,
                tmp_path,
                final_relative=claim["folder_plan"]["relative_directory"] + "/" + suffix,
            )
        assert store.list_artifacts() == []


@pytest.mark.parametrize(
    "root", ["relative", "C:relative", "C:/parent/../escape", "//server/share"]
)
def test_storage_root_must_be_absolute_local_and_without_parent_traversal(tmp_path, root):
    with QueueStore(tmp_path / "queue.db") as store:
        claim = verifying(store)
        with pytest.raises(QueueError, match="root"):
            prepare(store, claim, tmp_path, save_root=root)
        assert store.list_artifacts() == []


@pytest.mark.parametrize(
    "change",
    [
        {"stable_key": "other"},
        {"display_url": "https://other.invalid"},
        {"saved_filename": "other.png"},
    ],
)
def test_metadata_identity_and_final_filename_must_match_the_frozen_source(tmp_path, change):
    with QueueStore(tmp_path / "queue.db") as store:
        claim = verifying(store)
        meta = claim["source"]["image"] | {"saved_filename": "001.png"} | change
        with pytest.raises(QueueError, match="metadata|filename"):
            prepare(store, claim, tmp_path, image_metadata=meta)
        assert store.list_artifacts() == []


def test_prepared_journal_is_immutable_even_while_its_lease_is_valid(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        claim = verifying(store)
        before = prepare(store, claim, tmp_path)
        with pytest.raises(QueueError, match="immutable"):
            prepare(store, claim, tmp_path, verification=VERIFIED | {"file_size": 999})
        assert store.get_artifact(claim["job_id"]) == before
        before["verification"]["sha256"] = "external mutation"
        assert store.get_artifact(claim["job_id"])["verification"]["sha256"] == VERIFIED["sha256"]


def test_distinct_jobs_cannot_reserve_the_same_windows_target_with_different_root_spelling(
    tmp_path,
):
    with QueueStore(tmp_path / "queue.db") as store:
        first = verifying(store)
        prepare(store, first, tmp_path, save_root="C:/IMages")
        second = verifying(store, gallery_type="minor")
        assert first["folder_plan"] == second["folder_plan"]
        with pytest.raises(QueueError, match="reserved"):
            prepare(store, second, tmp_path, save_root="c:\\images")
        assert len(store.list_artifacts()) == 1
        assert store.get_job(second["job_id"])["status"] == "verifying"


def test_completion_failure_rolls_back_both_job_and_journal_phase(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        claim = verifying(store)
        artifact = prepare(store, claim, tmp_path)
        before = store.get_job(claim["job_id"])
        store.connection.execute("""CREATE TRIGGER fail_phase
            BEFORE UPDATE ON artifact_finalizations
            BEGIN SELECT RAISE(ABORT,'phase unavailable'); END""")
        with pytest.raises(sqlite3.IntegrityError, match="phase unavailable"):
            store.complete_artifact(claim["job_id"], claim["lease_token"])
        assert store.get_job(claim["job_id"]) == before
        assert store.get_artifact(claim["job_id"]) == artifact


def test_journal_prevents_native_reclaim_even_if_a_failure_handler_releases_the_lease(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        claim = verifying(store)
        prepare(store, claim, tmp_path)
        failure = store.record_failure(
            claim["job_id"], claim["lease_token"], "network", "busy", NOW
        )
        assert failure["status"] == "retry_wait"
        assert store.claim_next("worker", NOW + timedelta(days=1)) is None
        assert store.get_artifact(claim["job_id"])["phase"] == "prepared"


@pytest.mark.parametrize("status", ["verifying", "manual_review", "paused_local"])
def test_explicit_stopped_worker_recovery_finishes_prepared_files_without_old_token(
    tmp_path, status
):
    with QueueStore(tmp_path / "queue.db") as store:
        claim = verifying(store)
        prepare(store, claim, tmp_path)
        if status == "manual_review":
            store.recover_interrupted(confirm_workers_stopped=True)
        elif status == "paused_local":
            store.record_failure(claim["job_id"], claim["lease_token"], "local", "disk", NOW)
        with pytest.raises(QueueError, match="workers stopped"):
            store.recover_artifact_complete(claim["job_id"])
        before = store.get_job(claim["job_id"])
        recovered = store.recover_artifact_complete(claim["job_id"], confirm_workers_stopped=True)
        assert recovered["phase"] == "metadata_pending"
        after = store.get_job(claim["job_id"])
        assert after["status"] == "completed"
        assert after["attempt_count"] == before["attempt_count"]
        assert store.claim_next("worker", NOW + timedelta(days=1)) is None
        with pytest.raises(QueueError, match="claim"):
            store.complete_artifact(claim["job_id"], claim["lease_token"])


def test_manual_review_preserves_completed_file_and_metadata_phase(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        claim = verifying(store)
        prepare(store, claim, tmp_path)
        with pytest.raises(QueueError, match="workers stopped"):
            store.mark_artifact_manual_review(claim["job_id"], "conflict")
        store.mark_artifact_manual_review(claim["job_id"], "conflict", confirm_workers_stopped=True)
        assert store.get_job(claim["job_id"])["status"] == "manual_review"
        store.recover_artifact_complete(claim["job_id"], confirm_workers_stopped=True)
        store.mark_artifact_manual_review(
            claim["job_id"], "metadata_conflict", confirm_workers_stopped=True
        )
        assert store.get_job(claim["job_id"])["status"] == "completed"
        assert store.get_job(claim["job_id"])["last_error"] == "metadata_conflict"
        assert store.get_artifact(claim["job_id"])["phase"] == "metadata_pending"
        store.mark_metadata_written(claim["job_id"])
        assert store.get_job(claim["job_id"])["last_error"] is None


def test_completed_artifact_retains_its_original_observation_after_job_url_updates(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        claim = verifying(store)
        artifact = prepare(store, claim, tmp_path)
        store.complete_artifact(claim["job_id"], claim["lease_token"])
        changed = replace(IMAGE, display_url="https://images.example.invalid/new.png")
        add_post(store, image=changed, observed_at=NOW + timedelta(days=2))
        assert store.get_job_source(claim["job_id"], artifact["observation_id"]) is None
        old = store.get_observation(artifact["observation_id"])
        assert old["snapshot"]["images"][0]["display_url"] == IMAGE.display_url
        assert store.get_artifact(claim["job_id"]) == artifact | {"phase": "metadata_pending"}


@pytest.mark.parametrize("version", [1, 2, 3])
def test_legacy_readonly_and_writable_migration_preserve_existing_sources_and_jobs(
    tmp_path, version
):
    path = tmp_path / "legacy.db"
    with QueueStore(path) as store:
        initial = add_post(store)
    downgrade(path, version)
    before = database_state(path)
    with QueueStore(path, read_only=True) as store:
        assert store.summary()["schema_version"] == version
        assert store.get_artifact(initial["jobs"][0]["job_id"]) is None
        assert store.list_artifacts() == []
        assert (store.get_job_source(initial["jobs"][0]["job_id"]) is not None) == (version >= 2)
    assert database_state(path) == before
    with QueueStore(path) as store:
        assert store.summary()["schema_version"] == SCHEMA_VERSION
        assert store.get_job(initial["jobs"][0]["job_id"]) == initial["jobs"][0]
        assert (store.get_observation(initial["observation_id"]) is not None) == (version >= 2)


@pytest.mark.parametrize("version", [1, 2])
def test_artifact_schema_failure_rolls_back_the_entire_legacy_upgrade(
    tmp_path, monkeypatch, version
):
    path = tmp_path / "legacy.db"
    with QueueStore(path) as store:
        add_post(store)
    downgrade(path, version)
    before = database_state(path)
    monkeypatch.setattr(
        queue_module,
        "ARTIFACT_STATEMENTS",
        queue_module.ARTIFACT_STATEMENTS + ("SELECT nonexistent_artifact_function()",),
    )
    with pytest.raises(sqlite3.OperationalError, match="nonexistent_artifact_function"):
        QueueStore(path)
    assert database_state(path) == before


def test_filtered_claim_does_not_take_an_older_unapproved_job_or_other_post(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        unapproved = add_post(store)["jobs"][0]
        approved = add_post(store, post=replace(POST, post_id="124"))["jobs"][0]
        claim = store.claim_next("worker", NOW, job_ids=[approved["job_id"]])
        assert claim["job_id"] == approved["job_id"]
        assert store.get_job(unapproved["job_id"]) == unapproved
        assert claim["source"]["snapshot"]["post_id"] == "124"


def test_empty_approval_is_a_noop_including_retry_expiry(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        add_post(store)
        claim = store.claim_next("worker", NOW)
        before = store.record_failure(claim["job_id"], claim["lease_token"], "network", "busy", NOW)
        assert store.claim_next("worker", NOW + timedelta(days=2), job_ids=[]) is None
        assert store.get_job(claim["job_id"]) == before


def test_filtered_claim_does_not_expire_unapproved_retries(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        add_post(store)
        claim = store.claim_next("worker", NOW)
        before = store.record_failure(claim["job_id"], claim["lease_token"], "network", "busy", NOW)
        approved = add_post(store, post=replace(POST, post_id="124"))["jobs"][0]
        assert (
            store.claim_next("worker", NOW + timedelta(days=2), job_ids=[approved["job_id"]])[
                "job_id"
            ]
            == approved["job_id"]
        )
        assert store.get_job(claim["job_id"]) == before


@pytest.mark.parametrize("job_ids", ["not-a-list", b"bytes", [""], [" "], [None], [1], ["x"] * 501])
def test_malformed_or_oversized_approval_lists_fail_before_queue_mutation(tmp_path, job_ids):
    with QueueStore(tmp_path / "queue.db") as store:
        before = add_post(store)["jobs"][0]
        with pytest.raises(QueueError, match="job ID"):
            store.claim_next("worker", NOW, job_ids=job_ids)
        assert store.get_job(before["job_id"]) == before


def test_approved_ids_are_bound_values_not_sql_fragments(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        job = add_post(store)["jobs"][0]
        assert store.claim_next("worker", NOW, job_ids=["'); DROP TABLE jobs; --"]) is None
        assert store.get_job(job["job_id"]) == job
        assert (
            store.claim_next("worker", NOW, job_ids=[job["job_id"], job["job_id"]])["job_id"]
            == job["job_id"]
        )


def test_a_journal_created_after_approval_still_prevents_filtered_native_reclaim(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        claim = verifying(store)
        approved_ids = [claim["job_id"]]
        prepare(store, claim, tmp_path)
        store.record_failure(claim["job_id"], claim["lease_token"], "network", "busy", NOW)
        assert store.claim_next("worker", NOW + timedelta(minutes=1), job_ids=approved_ids) is None
        assert store.get_artifact(claim["job_id"])["phase"] == "prepared"
