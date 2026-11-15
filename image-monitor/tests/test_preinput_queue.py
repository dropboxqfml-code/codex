import sqlite3
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

import pytest

from image_monitor.queue import ImageDiscovery, PostDiscovery, QueueError, QueueStore

NOW = datetime(2026, 11, 15, tzinfo=UTC)
IMAGE = ImageDiscovery("stable", 1, "https://images.example.invalid/a.png")
NETWORK_FIELDS = ("attempt_count", "first_failure_at", "next_retry_at", "server_not_before")


def add(store):
    return store.persist_post_snapshot(
        watch_name="watch",
        gallery_type="normal",
        gallery_id="comic_new6",
        keyword="manual",
        search_type="manual",
        post=PostDiscovery("123", "example", None, NOW),
        images=[IMAGE],
        snapshot={
            "gallery_type": "normal",
            "gallery_id": "comic_new6",
            "post_id": "123",
            "images": [asdict(IMAGE)],
        },
        observed_at=NOW,
    )


def loading_after_network_failure(store):
    added = add(store)
    initial = store.claim_next("worker", NOW)
    store.record_failure(
        initial["job_id"], initial["lease_token"], "network", "busy", NOW, server_retry_after="600"
    )
    claim = store.claim_next("worker", NOW + timedelta(seconds=600))
    assert claim["source"]["observation_id"] == added["observation_id"]
    return claim


def paused(store):
    claim = loading_after_network_failure(store)
    store.transition(claim["job_id"], claim["lease_token"], "saving")
    job = store.record_failure(
        claim["job_id"], claim["lease_token"], "ui", "NativeUIError", NOW + timedelta(seconds=601)
    )
    return job, claim["source"]["observation_id"], store.history(job["job_id"])[-1]["history_id"]


def resume(store, job, observation, history_id, **overrides):
    options = {
        "observation_id": observation,
        "expected_history_id": history_id,
        "now": NOW + timedelta(seconds=602),
        "confirm_workers_stopped": True,
        "confirmed_no_input": True,
    }
    return store.resume_preinput_failure(job["job_id"], **(options | overrides))


def test_release_loading_claim_keeps_network_state_and_appends_a_nonnetwork_pause(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        claim = loading_after_network_failure(store)
        prior = store.history(claim["job_id"])
        released = store.release_unstarted_claim(claim["job_id"], claim["lease_token"], now=NOW)
        assert released["status"] == "queued" and released["last_error"] is None
        assert released["worker_id"] is None and released["lease_token"] is None
        assert {key: released[key] for key in NETWORK_FIELDS} == {
            key: claim[key] for key in NETWORK_FIELDS
        }
        assert store.history(claim["job_id"])[:-1] == prior
        last = store.history(claim["job_id"])[-1]
        assert (last["kind"], last["reason"], last["resulting_status"], last["attempt_count"]) == (
            "ui_pause",
            "pre_input_focus_pause",
            "queued",
            1,
        )
        with pytest.raises(QueueError, match="claim"):
            store.release_unstarted_claim(claim["job_id"], claim["lease_token"], now=NOW)


@pytest.mark.parametrize("stage", ["saving", "verifying"])
def test_release_refuses_a_claim_that_may_have_started_native_input(tmp_path, stage):
    with QueueStore(tmp_path / "queue.db") as store:
        claim = loading_after_network_failure(store)
        store.transition(claim["job_id"], claim["lease_token"], "saving")
        if stage == "verifying":
            store.transition(claim["job_id"], claim["lease_token"], "verifying")
        before, history = store.get_job(claim["job_id"]), store.history(claim["job_id"])
        with pytest.raises(QueueError, match="unstarted loading"):
            store.release_unstarted_claim(claim["job_id"], claim["lease_token"], now=NOW)
        assert store.get_job(claim["job_id"]) == before
        assert store.history(claim["job_id"]) == history


def test_release_rejects_a_stale_claim_token(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        claim = loading_after_network_failure(store)
        before = store.get_job(claim["job_id"])
        with pytest.raises(QueueError, match="claim"):
            store.release_unstarted_claim(claim["job_id"], "stale", now=NOW)
        assert store.get_job(claim["job_id"]) == before


def test_resume_only_the_exact_paused_failure_and_keep_network_delays(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        job, observation, history_id = paused(store)
        prior = store.history(job["job_id"])
        resumed = resume(store, job, observation, history_id)
        assert resumed["status"] == "queued" and resumed["last_error"] is None
        assert resumed["worker_id"] is None and resumed["lease_token"] is None
        assert {key: resumed[key] for key in NETWORK_FIELDS} == {
            key: job[key] for key in NETWORK_FIELDS
        }
        assert store.history(job["job_id"])[:-1] == prior
        audit = store.history(job["job_id"])[-1]
        assert (
            audit["kind"],
            audit["reason"],
            audit["resulting_status"],
            audit["attempt_count"],
        ) == (
            "pre_input_resume",
            "verified_no_input",
            "queued",
            1,
        )
        with pytest.raises(QueueError, match="eligible"):
            resume(store, job, observation, history_id)
        assert store.history(job["job_id"])[-1] == audit


@pytest.mark.parametrize(
    ("stopped", "no_input"), [(False, False), (False, True), (True, False), (1, True), (True, 1)]
)
def test_resume_requires_both_exact_confirmations(tmp_path, stopped, no_input):
    with QueueStore(tmp_path / "queue.db") as store:
        job, observation, history_id = paused(store)
        with pytest.raises(QueueError, match="Confirm"):
            resume(
                store,
                job,
                observation,
                history_id,
                confirm_workers_stopped=stopped,
                confirmed_no_input=no_input,
            )
        assert store.get_job(job["job_id"]) == job
        assert len(store.history(job["job_id"])) == 2


@pytest.mark.parametrize(
    "status",
    [
        "manual_review",
        "paused_local",
        "loading",
        "saving",
        "verifying",
        "queued",
        "completed",
        "blocked",
    ],
)
def test_resume_never_resets_unknown_or_other_job_states(tmp_path, status):
    with QueueStore(tmp_path / "queue.db") as store:
        job, observation, history_id = paused(store)
        store.connection.execute("UPDATE jobs SET status=? WHERE job_id=?", (status, job["job_id"]))
        before = store.get_job(job["job_id"])
        with pytest.raises(QueueError, match="eligible"):
            resume(store, job, observation, history_id)
        assert store.get_job(job["job_id"]) == before


@pytest.mark.parametrize("field", ["worker_id", "lease_token"])
def test_resume_refuses_any_retained_worker_or_lease_identity(tmp_path, field):
    with QueueStore(tmp_path / "queue.db") as store:
        job, observation, history_id = paused(store)
        store.connection.execute(
            f"UPDATE jobs SET {field}='still-owned' WHERE job_id=?", (job["job_id"],)
        )
        with pytest.raises(QueueError, match="eligible"):
            resume(store, job, observation, history_id)


@pytest.mark.parametrize("history_id", [0, -1, True, "1", 2**63, 999999])
def test_resume_requires_the_expected_latest_history_id(tmp_path, history_id):
    with QueueStore(tmp_path / "queue.db") as store:
        job, observation, _history_id = paused(store)
        with pytest.raises(QueueError, match="history"):
            resume(store, job, observation, history_id)
        assert store.get_job(job["job_id"]) == job


@pytest.mark.parametrize(
    ("field", "value"),
    [("kind", "local"), ("reason", "OtherError"), ("resulting_status", "manual_review")],
)
def test_resume_checks_history_kind_reason_and_result_not_only_job_status(tmp_path, field, value):
    with QueueStore(tmp_path / "queue.db") as store:
        job, observation, history_id = paused(store)
        store.connection.execute(
            f"UPDATE attempts SET {field}=? WHERE history_id=?", (value, history_id)
        )
        with pytest.raises(QueueError, match="latest job history"):
            resume(store, job, observation, history_id)
        assert store.get_job(job["job_id"]) == job


def test_resume_requires_the_original_observation_to_match_current_url(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        job, observation, history_id = paused(store)
        with pytest.raises(QueueError, match="source"):
            resume(store, job, "missing-observation", history_id)
        store.connection.execute(
            "UPDATE jobs SET display_url='https://other.invalid/a' WHERE job_id=?", (job["job_id"],)
        )
        before = store.get_job(job["job_id"])
        with pytest.raises(QueueError, match="source"):
            resume(store, job, observation, history_id)
        assert store.get_job(job["job_id"]) == before


def test_resume_cannot_use_an_old_failure_after_a_later_attempt_fails(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        job, observation, old_id = paused(store)
        resume(store, job, observation, old_id)
        claim = store.claim_next("worker", NOW + timedelta(seconds=603))
        store.record_failure(
            claim["job_id"],
            claim["lease_token"],
            "ui",
            "NativeUIError",
            NOW + timedelta(seconds=604),
        )
        before = store.get_job(job["job_id"])
        with pytest.raises(QueueError, match="latest job history"):
            resume(store, job, observation, old_id)
        assert store.get_job(job["job_id"]) == before


@pytest.mark.parametrize("mode", ["release", "resume"])
def test_audit_insert_failure_rolls_back_the_requeue(tmp_path, mode):
    with QueueStore(tmp_path / "queue.db") as store:
        if mode == "release":
            claim = loading_after_network_failure(store)
            job_id = claim["job_id"]
        else:
            job, observation, history_id = paused(store)
            job_id = job["job_id"]
        before, history = store.get_job(job_id), store.history(job_id)
        store.connection.execute("""CREATE TRIGGER fail_resume_audit BEFORE INSERT ON attempts
            WHEN NEW.kind IN ('ui_pause','pre_input_resume')
            BEGIN SELECT RAISE(ABORT,'audit unavailable'); END""")
        with pytest.raises(sqlite3.IntegrityError, match="audit unavailable"):
            if mode == "release":
                store.release_unstarted_claim(job_id, claim["lease_token"], now=NOW)
            else:
                resume(store, job, observation, history_id)
        assert store.get_job(job_id) == before
        assert store.history(job_id) == history


@pytest.mark.parametrize("mode", ["release", "resume"])
def test_an_artifact_journal_always_blocks_preinput_requeue(tmp_path, mode):
    with QueueStore(tmp_path / "queue.db") as store:
        claim = loading_after_network_failure(store)
        store.transition(claim["job_id"], claim["lease_token"], "saving")
        store.transition(claim["job_id"], claim["lease_token"], "verifying")
        artifact = store.prepare_artifact(
            claim["job_id"],
            claim["lease_token"],
            observation_id=claim["source"]["observation_id"],
            save_root=str(tmp_path / "images"),
            staging_relative=f"_staging/{claim['job_id']}/attempt/native-image.png",
            final_relative=claim["folder_plan"]["relative_directory"] + "/001.png",
            verification={"sha256": "a" * 64, "detected_format": "PNG", "file_size": 372},
            image_metadata=claim["source"]["image"] | {"saved_filename": "001.png"},
            saved_at=NOW,
        )
        if mode == "release":
            # Even an accidental outside repair to loading cannot bypass the journal.
            store.connection.execute(
                "UPDATE jobs SET status='loading' WHERE job_id=?", (claim["job_id"],)
            )
        else:
            store.record_failure(claim["job_id"], claim["lease_token"], "ui", "NativeUIError", NOW)
        before, history = store.get_job(claim["job_id"]), store.history(claim["job_id"])
        with pytest.raises(QueueError, match="artifact|eligible"):
            if mode == "release":
                store.release_unstarted_claim(claim["job_id"], claim["lease_token"], now=NOW)
            else:
                resume(store, before, claim["source"]["observation_id"], history[-1]["history_id"])
        assert store.get_job(claim["job_id"]) == before
        assert store.history(claim["job_id"]) == history
        assert store.get_artifact(claim["job_id"]) == artifact


def test_resume_refuses_a_changed_current_failure_reason(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        job, observation, history_id = paused(store)
        store.connection.execute(
            "UPDATE jobs SET last_error='OtherError' WHERE job_id=?", (job["job_id"],)
        )
        before = store.get_job(job["job_id"])
        with pytest.raises(QueueError, match="eligible"):
            resume(store, job, observation, history_id)
        assert store.get_job(job["job_id"]) == before


def test_resume_refuses_a_job_without_the_failure_audit(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        job, observation, history_id = paused(store)
        store.connection.execute("DELETE FROM attempts WHERE job_id=?", (job["job_id"],))
        with pytest.raises(QueueError, match="latest job history"):
            resume(store, job, observation, history_id)
        assert store.get_job(job["job_id"]) == job
