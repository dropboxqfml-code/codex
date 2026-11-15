import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest

from image_monitor import queue as queue_module
from image_monitor.queue import (
    APPLICATION_ID,
    BASE_SCHEMA,
    SCHEMA_VERSION,
    V2_SCHEMA,
    V3_SCHEMA,
    ImageDiscovery,
    PostDiscovery,
    QueueError,
    QueueStore,
)
from image_monitor.watch_store import WatchScope, WatchStore

NOW = datetime(2026, 11, 15, tzinfo=UTC)
SCOPE = WatchScope("watch", "normal", "gallery", "ai", "search_subject_memo")
BASELINE = {"mode": "new", "anchor_ids": ["100", "99"]}
CHECKPOINT = {"anchor_ids": ["101", "100"], "source_url": "https://example.invalid/latest"}


def persist(watch, **overrides):
    options = {
        "observed_at": NOW,
        "expected_generation": 0,
        "scan_result": {"evidence_status": "synthetic_fixture", "next_cursor": None},
        "candidates": [],
        "checkpoint": CHECKPOINT,
        "complete": True,
        "baseline": BASELINE,
    }
    return watch.persist_scan(SCOPE, **(options | overrides))


def candidate(post_id="101", **overrides):
    return {
        "post_id": post_id,
        "post_url": f"https://example.invalid/post/{post_id}",
        "title": "synthetic title",
        "shown_metadata": {"author_display": "list-only name", "date_display": "11.15"},
    } | overrides


def test_baseline_and_candidates_survive_reopen_without_freezing_post_folders(tmp_path):
    path = tmp_path / "queue.db"
    baseline = {"mode": "new", "anchor_ids": ["100", "99"]}
    with QueueStore(path) as queue:
        watch = WatchStore(queue)
        assert watch.get_state(SCOPE)["generation"] == 0
        persist(watch, baseline=baseline)
        baseline["anchor_ids"].append("98")
        result = persist(
            watch,
            expected_generation=1,
            observed_at=NOW + timedelta(seconds=1),
            candidates=[candidate()],
        )
        assert result["candidates_added"] == 1
        assert queue.summary()["posts"] == 0
        assert queue.summary()["jobs"] == 0
        assert queue.connection.execute("SELECT COUNT(*) FROM matches").fetchone()[0] == 0
        assert queue.connection.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0] == 0
    with QueueStore(path) as queue:
        watch = WatchStore(queue)
        state = watch.get_state(SCOPE)
        assert state["generation"] == 2
        assert state["baseline"] == BASELINE
        assert state["checkpoint"] == CHECKPOINT
        row = watch.list_candidates(SCOPE)[0]
        assert row["shown_metadata"]["author_display"] == "list-only name"
        assert "folder_plan" not in row
        assert len(watch.list_scans(SCOPE)) == 2
        assert watch.list_gaps(SCOPE) == []


def test_partial_scan_keeps_complete_coverage_and_persists_pending_resume_and_gap(tmp_path):
    with QueueStore(tmp_path / "queue.db") as queue:
        watch = WatchStore(queue)
        persist(watch)
        partial = {"anchor_ids": ["102", "101"], "next_cursor": "follow-up"}
        result = persist(
            watch,
            expected_generation=1,
            observed_at=NOW + timedelta(seconds=1),
            candidates=[candidate("102")],
            checkpoint=partial,
            scan_result={"next_cursor": "follow-up", "reason": "page_limit"},
            complete=False,
            gap_reason="page_limit",
        )
        state = watch.get_state(SCOPE)
        assert state["checkpoint"] == CHECKPOINT
        assert state["latest_scan"]["checkpoint"] == partial
        assert state["latest_scan"]["result"]["next_cursor"] == "follow-up"
        assert state["latest_scan"]["complete"] is False
        assert watch.list_gaps(SCOPE)[0]["scan_id"] == result["scan_id"]
        persist(
            watch,
            expected_generation=2,
            observed_at=NOW + timedelta(seconds=2),
            checkpoint=partial,
        )
        assert watch.get_state(SCOPE)["checkpoint"] == partial
        assert len(watch.list_gaps(SCOPE)) == 1


def test_first_partial_has_no_coverage_and_repeated_candidates_keep_first_seen(tmp_path):
    with QueueStore(tmp_path / "queue.db") as queue:
        watch = WatchStore(queue)
        persist(watch, candidates=[candidate()], complete=False, gap_reason="page_limit")
        original = watch.list_candidates(SCOPE)[0]
        assert watch.get_state(SCOPE)["checkpoint"] is None
        result = persist(
            watch,
            expected_generation=1,
            observed_at=NOW + timedelta(days=1),
            candidates=[candidate(title="updated list title", shown_metadata={"date": "later"})],
        )
        repeated = watch.list_candidates(SCOPE)[0]
        assert result["candidates_added"] == 0
        assert repeated["first_seen_at"] == original["first_seen_at"]
        assert repeated["first_scan_id"] == original["first_scan_id"]
        assert repeated["last_seen_at"] > original["last_seen_at"]
        assert repeated["latest_scan_id"] != original["latest_scan_id"]
        assert repeated["title"] == "updated list title"
        assert len(watch.list_candidates(SCOPE)) == 1


def test_stale_generation_observation_and_changed_baseline_leave_everything_unchanged(tmp_path):
    with QueueStore(tmp_path / "queue.db") as queue:
        watch = WatchStore(queue)
        persist(watch)
        state = watch.get_state(SCOPE)
        for override, message in (
            ({"expected_generation": 0}, "generation"),
            ({"expected_generation": 1, "observed_at": NOW - timedelta(seconds=1)}, "observation"),
            ({"expected_generation": 1, "baseline": {"anchor_ids": ["1"]}}, "baseline"),
        ):
            with pytest.raises(QueueError, match=message):
                persist(watch, candidates=[candidate()], **override)
            assert watch.get_state(SCOPE) == state
            assert watch.list_candidates(SCOPE) == []
            assert len(watch.list_scans(SCOPE)) == 1


def test_failure_after_candidate_writes_rolls_back_scan_candidate_checkpoint_and_gap(tmp_path):
    with QueueStore(tmp_path / "queue.db") as queue:
        watch = WatchStore(queue)
        persist(watch)
        state = watch.get_state(SCOPE)
        queue.connection.execute(
            "CREATE TEMP TRIGGER reject_gap BEFORE INSERT ON watch_gaps "
            "BEGIN SELECT RAISE(ABORT, 'synthetic gap failure'); END"
        )
        with pytest.raises(sqlite3.IntegrityError, match="synthetic gap failure"):
            persist(
                watch,
                expected_generation=1,
                candidates=[candidate()],
                complete=False,
                gap_reason="page_limit",
            )
        assert watch.get_state(SCOPE) == state
        assert watch.list_candidates(SCOPE) == []
        assert len(watch.list_scans(SCOPE)) == 1
        assert watch.list_gaps(SCOPE) == []


def test_two_connections_cannot_commit_plans_from_the_same_generation(tmp_path):
    path = tmp_path / "queue.db"
    with QueueStore(path) as queue:
        persist(WatchStore(queue))
    barrier = Barrier(2)

    def commit(post_id):
        with QueueStore(path) as queue:
            watch = WatchStore(queue)
            generation = watch.get_state(SCOPE)["generation"]
            barrier.wait(timeout=5)
            try:
                return persist(
                    watch, expected_generation=generation, candidates=[candidate(post_id)]
                )
            except QueueError as error:
                assert "generation" in str(error)
                return None

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(commit, ["101", "102"]))
    assert sum(result is not None for result in results) == 1
    with QueueStore(path) as queue:
        watch = WatchStore(queue)
        assert watch.get_state(SCOPE)["generation"] == 2
        assert len(watch.list_candidates(SCOPE)) == 1
        assert len(watch.list_scans(SCOPE)) == 2


def test_every_scope_dimension_is_independent_and_queries_are_bounded(tmp_path):
    scopes = [SCOPE] + [
        replace(SCOPE, **{name: value})
        for name, value in (
            ("watch_name", "other"),
            ("gallery_type", "minor"),
            ("gallery_id", "other"),
            ("keyword", "other"),
            ("search_type", "search_subject"),
        )
    ]
    with QueueStore(tmp_path / "queue.db") as queue:
        watch = WatchStore(queue)
        for scope in scopes:
            watch.persist_scan(
                scope,
                observed_at=NOW,
                expected_generation=0,
                scan_result={},
                candidates=[candidate("101"), candidate("102")],
                checkpoint={},
                complete=False,
                gap_reason="synthetic gap",
            )
        for scope in scopes:
            assert watch.get_state(scope)["generation"] == 1
            assert len(watch.list_candidates(scope, limit=1)) == 1
            assert len(watch.list_candidates(scope)) == 2
            assert len(watch.list_scans(scope)) == 1
            assert len(watch.list_gaps(scope)) == 1
        for limit in (True, 0, 1001):
            with pytest.raises(QueueError, match="limit"):
                watch.list_candidates(SCOPE, limit=limit)


@pytest.mark.parametrize(
    "override",
    [
        {"expected_generation": True},
        {"expected_generation": -1},
        {"complete": 1},
        {"complete": False},
        {"gap_reason": "unexpected gap"},
        {"scan_result": {"invalid": float("nan")}},
        {"checkpoint": []},
        {"baseline": []},
        {"candidates": [candidate("001")]},
        {"candidates": [candidate(), candidate()]},
        {"candidates": [candidate(shown_metadata={"invalid": float("inf")})]},
        {"candidates": [candidate(nickname="must await detail inspection")]},
    ],
)
def test_invalid_batch_never_writes_state(tmp_path, override):
    with QueueStore(tmp_path / "queue.db") as queue:
        watch = WatchStore(queue)
        with pytest.raises(QueueError):
            persist(watch, **override)
        assert watch.get_state(SCOPE)["generation"] == 0
        assert watch.list_scans(SCOPE) == []
        assert watch.list_candidates(SCOPE) == []


def database_state(path):
    with closing(sqlite3.connect(path)) as db:
        return tuple(db.iterdump())


@pytest.mark.parametrize("version,schema", [(1, BASE_SCHEMA), (2, V2_SCHEMA), (3, V3_SCHEMA)])
def test_known_legacy_readonly_and_atomic_writable_migration(
    tmp_path, monkeypatch, version, schema
):
    path = tmp_path / "legacy.db"
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript(schema)
        db.execute(f"PRAGMA application_id={APPLICATION_ID}")
        db.execute(f"PRAGMA user_version={version}")
    before = database_state(path)
    with QueueStore(path, read_only=True) as queue:
        watch = WatchStore(queue)
        assert queue.schema_version == version
        assert watch.get_state(SCOPE)["generation"] == 0
        assert watch.list_candidates(SCOPE) == []
        assert watch.list_scans(SCOPE) == []
        assert watch.list_gaps(SCOPE) == []
        with pytest.raises(QueueError, match="read-only"):
            persist(watch)
    assert database_state(path) == before
    with monkeypatch.context() as patch:
        patch.setattr(
            queue_module,
            "WATCH_STATEMENTS",
            queue_module.WATCH_STATEMENTS + ("SELECT nonexistent_watch_function()",),
        )
        with pytest.raises(sqlite3.OperationalError, match="nonexistent_watch_function"):
            QueueStore(path)
    assert database_state(path) == before
    with QueueStore(path) as queue:
        assert queue.schema_version == SCHEMA_VERSION
        assert persist(WatchStore(queue))["generation"] == 1


def test_v3_migration_preserves_existing_jobs_sources_and_prepared_artifacts(tmp_path):
    path = tmp_path / "legacy.db"
    with QueueStore(path) as queue:
        image = ImageDiscovery("synthetic-key", 1, "https://example.invalid/image.png")
        observation = queue.persist_post_snapshot(
            watch_name=SCOPE.watch_name,
            gallery_type=SCOPE.gallery_type,
            gallery_id=SCOPE.gallery_id,
            keyword=SCOPE.keyword,
            search_type=SCOPE.search_type,
            post=PostDiscovery("10", "detail author", None, NOW),
            images=[image],
            snapshot={
                "gallery_type": "normal",
                "gallery_id": "gallery",
                "post_id": "10",
                "images": [
                    {
                        "stable_key": image.stable_key,
                        "body_order": 1,
                        "display_url": image.display_url,
                    }
                ],
            },
            observed_at=NOW,
        )
        claim = queue.claim_next("worker", NOW)
        queue.transition(claim["job_id"], claim["lease_token"], "saving")
        queue.transition(claim["job_id"], claim["lease_token"], "verifying")
        artifact = queue.prepare_artifact(
            claim["job_id"],
            claim["lease_token"],
            observation_id=observation["observation_id"],
            save_root=str(tmp_path / "storage"),
            staging_relative=f"_staging/{claim['job_id']}/attempt/native.png",
            final_relative=claim["folder_plan"]["relative_directory"] + "/001.png",
            verification={
                "sha256": "a" * 64,
                "detected_format": "PNG",
                "extension": "png",
                "file_size": 100,
                "width": 10,
                "height": 10,
                "frames": 1,
            },
            image_metadata={"stable_key": image.stable_key, "display_url": image.display_url},
            saved_at=NOW,
        )
        job = queue.get_job(claim["job_id"])
        source = queue.get_job_source(claim["job_id"])
        post = queue.get_post("normal", "gallery", "10")
    with closing(sqlite3.connect(path)) as db, db:
        for table in ("watch_gaps", "watch_candidates", "watch_scans", "watch_state"):
            db.execute(f"DROP TABLE {table}")
        db.execute("PRAGMA user_version=3")
    before = database_state(path)
    with QueueStore(path, read_only=True) as queue:
        assert queue.get_artifact(job["job_id"]) == artifact
    assert database_state(path) == before
    with QueueStore(path) as queue:
        assert queue.get_job(job["job_id"]) == job
        assert queue.get_job_source(job["job_id"]) == source
        assert queue.get_post("normal", "gallery", "10") == post
        assert queue.get_artifact(job["job_id"]) == artifact
        persist(WatchStore(queue))
        assert queue.get_job(job["job_id"]) == job


def test_declared_v3_with_unknown_object_refuses_migration_without_changes(tmp_path):
    path = tmp_path / "unknown.db"
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript(V3_SCHEMA)
        db.execute(f"PRAGMA application_id={APPLICATION_ID}")
        db.execute("PRAGMA user_version=3")
        db.execute("CREATE TABLE foreign_data(value TEXT)")
    before = database_state(path)
    for read_only in (False, True):
        with pytest.raises(QueueError, match="migration refused"):
            QueueStore(path, read_only=read_only)
        assert database_state(path) == before
