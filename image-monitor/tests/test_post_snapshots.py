import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest

from image_monitor import queue as queue_module
from image_monitor.queue import (
    APPLICATION_ID,
    SCHEMA_VERSION,
    ImageDiscovery,
    PostDiscovery,
    QueueError,
    QueueStore,
)

NOW = datetime(2026, 11, 15, 0, 0, tzinfo=UTC)
POST = PostDiscovery("123", "example", None, NOW, title="first title")
IMAGE = ImageDiscovery("file-a", 1, "https://images.example.invalid/a.png")


def snapshot(images=None):
    return {
        "schema_version": 1,
        "gallery_type": "normal",
        "gallery_id": "comic_new6",
        "post_id": "123",
        "attachment_inventory": [{"filename": "original.png", "identity": "a"}],
        "images": [asdict(image) for image in (images if images is not None else [IMAGE])],
    }


def persist(store, *, images=None, **overrides):
    images = [IMAGE] if images is None else images
    options = {
        "watch_name": "watch",
        "gallery_type": "normal",
        "gallery_id": "comic_new6",
        "keyword": "ai",
        "search_type": "search_subject_memo",
        "post": POST,
        "images": images,
        "snapshot": snapshot(images),
        "observed_at": NOW,
    }
    return store.persist_post_snapshot(**(options | overrides))


def snapshots(store):
    return store.list_post_snapshots("normal", "comic_new6", "123")


def make_legacy_database(path):
    # Keep real data created through the existing API, then remove only the
    # additive v2 objects to reproduce the app's exact previous v1 format.
    with QueueStore(path) as store:
        store.discover_batch(
            watch_name="watch",
            gallery_type="normal",
            gallery_id="comic_new6",
            keyword="ai",
            search_type="search_subject_memo",
            posts=[POST],
            checked_at=NOW,
            cursor="list-cursor",
            complete=True,
        )
        job = store.queue_images(
            gallery_type="normal", gallery_id="comic_new6", post_id="123", images=[IMAGE]
        )[0]
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE observation_jobs")
        db.execute("DROP TABLE post_observations")
        db.execute("PRAGMA user_version=1")
    return job


def test_snapshot_and_associations_survive_reopen_without_a_list_checkpoint(tmp_path):
    path = tmp_path / "queue.db"
    data = snapshot()
    with QueueStore(path) as store:
        result = persist(store, snapshot=data)
        assert store.summary()["posts"] == 1
        assert store.summary()["jobs"] == 1
        assert store.connection.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0] == 0
    data["attachment_inventory"][0]["filename"] = "changed-after-write.png"
    with QueueStore(path, read_only=True) as store:
        records = snapshots(store)
        assert len(records) == 1
        assert records[0]["observation_id"] == result["observation_id"]
        assert records[0]["snapshot"]["attachment_inventory"][0]["filename"] == "original.png"
        assert records[0]["jobs"] == [
            {
                "job_id": result["jobs"][0]["job_id"],
                "body_order": 1,
                "stable_key": "file-a",
                "file_slot": 1,
            }
        ]
        records[0]["snapshot"]["images"].clear()
        assert len(snapshots(store)[0]["snapshot"]["images"]) == 1


def test_body_inspection_never_advances_or_invents_list_scan_state(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        store.discover_batch(
            watch_name="watch",
            gallery_type="normal",
            gallery_id="comic_new6",
            keyword="ai",
            search_type="search_subject_memo",
            posts=[POST],
            checked_at=NOW,
            cursor="unfinished-list-page",
            complete=False,
            gap_reason="page_limit",
        )
        before = [tuple(row) for row in store.connection.execute("SELECT * FROM checkpoints")]
        gaps = store.list_gaps()
        persist(store, observed_at=NOW + timedelta(hours=1))
        assert [
            tuple(row) for row in store.connection.execute("SELECT * FROM checkpoints")
        ] == before
        assert store.list_gaps() == gaps


def test_rediscovery_keeps_frozen_folder_job_slot_attempts_and_old_observations(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        first = persist(store)
        initial = first["jobs"][0]
        claim = store.claim_next("worker", NOW)
        failed = store.record_failure(
            initial["job_id"], claim["lease_token"], "network", "busy", NOW
        )
        old = snapshots(store)[0]
        images = [
            ImageDiscovery("file-new", 1, "https://images.example.invalid/new.png"),
            replace(
                IMAGE, body_order=2, display_url="https://images.example.invalid/refreshed.png"
            ),
        ]
        newer = persist(
            store,
            images=images,
            observed_at=NOW + timedelta(days=1),
            post=replace(
                POST,
                first_seen_at=NOW + timedelta(days=1),
                nickname="new display name",
                published_at=NOW - timedelta(days=3),
            ),
            folder_date_basis="first_seen_at",
        )
        existing = newer["jobs"][1]
        assert existing["job_id"] == initial["job_id"]
        assert existing["file_slot"] == 1
        assert existing["folder_plan"] == initial["folder_plan"]
        assert existing["attempt_count"] == failed["attempt_count"]
        assert existing["status"] == failed["status"]
        assert existing["body_order"] == 2
        assert newer["jobs"][0]["file_slot"] == 2
        records = snapshots(store)
        assert [record["observation_id"] for record in records] == [
            newer["observation_id"],
            first["observation_id"],
        ]
        assert records[1] == old
        assert store.get_post("normal", "comic_new6", "123")["first_seen_at"] == NOW.isoformat(
            timespec="microseconds"
        )


def test_active_job_keeps_claimed_url_but_new_observation_retains_the_new_source(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        initial = persist(store)["jobs"][0]
        claim = store.claim_next("worker", NOW)
        updated = replace(IMAGE, display_url="https://images.example.invalid/refreshed.png")
        result = persist(store, images=[updated], observed_at=NOW + timedelta(seconds=1))
        assert result["jobs"][0]["display_url"] == initial["display_url"]
        assert result["jobs"][0]["lease_token"] == claim["lease_token"]
        assert snapshots(store)[0]["snapshot"]["images"][0]["display_url"] == updated.display_url


def test_repeated_body_occurrences_share_a_job_and_remain_in_the_snapshot(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        data = snapshot()
        data["images"].append(asdict(replace(IMAGE, body_order=3)))
        result = persist(store, snapshot=data)
        assert len(result["jobs"]) == 1
        assert [image["body_order"] for image in snapshots(store)[0]["snapshot"]["images"]] == [
            1,
            3,
        ]


def test_text_only_post_preserves_empty_inventory_without_inventing_an_image_job(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        result = persist(store, images=[])
        assert result["jobs"] == []
        assert snapshots(store)[0]["snapshot"]["images"] == []


def test_failed_job_association_rolls_back_post_match_jobs_and_snapshot(tmp_path):
    path = tmp_path / "queue.db"
    with QueueStore(path) as store:
        store.connection.execute("""CREATE TRIGGER fail_second_association
            BEFORE INSERT ON observation_jobs WHEN NEW.body_order=2
            BEGIN SELECT RAISE(ABORT,'simulated observation write failure'); END""")
        with pytest.raises(sqlite3.IntegrityError, match="simulated"):
            persist(
                store,
                images=[IMAGE, ImageDiscovery("file-b", 2, "https://images.example.invalid/b.png")],
            )
        for table in ("posts", "matches", "jobs", "post_observations", "observation_jobs"):
            assert store.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        store.connection.execute("DROP TRIGGER fail_second_association")
    with QueueStore(path, read_only=True) as store:
        assert store.summary()["posts"] == 0
        assert snapshots(store) == []


def test_failure_during_rediscovery_restores_previous_job_and_snapshot(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        initial = persist(store)
        before = snapshots(store)
        store.connection.execute("""CREATE TRIGGER fail_observation
            BEFORE INSERT ON post_observations
            BEGIN SELECT RAISE(ABORT,'observation unavailable'); END""")
        with pytest.raises(sqlite3.IntegrityError, match="unavailable"):
            persist(
                store, images=[replace(IMAGE, body_order=2)], observed_at=NOW + timedelta(days=1)
            )
        assert store.get_job(initial["jobs"][0]["job_id"]) == initial["jobs"][0]
        assert snapshots(store) == before


@pytest.mark.parametrize(
    "change",
    [
        {"post_id": "wrong"},
        {"gallery_type": "minor"},
        {"images": [{"stable_key": "unknown", "body_order": 1, "display_url": IMAGE.display_url}]},
        {
            "images": [
                {
                    "stable_key": IMAGE.stable_key,
                    "body_order": True,
                    "display_url": IMAGE.display_url,
                }
            ]
        },
        {
            "images": [
                {"stable_key": IMAGE.stable_key, "body_order": 2, "display_url": IMAGE.display_url}
            ]
        },
        {
            "images": [
                {
                    "stable_key": IMAGE.stable_key,
                    "body_order": 1,
                    "display_url": "https://wrong.invalid/a",
                }
            ]
        },
        {"images": []},
        {"extra": object()},
        {"extra": float("nan")},
    ],
)
def test_invalid_identity_image_alignment_or_json_has_no_persistent_side_effects(tmp_path, change):
    with QueueStore(tmp_path / "queue.db") as store:
        with pytest.raises(QueueError):
            persist(store, snapshot=snapshot() | change)
        assert store.summary()["posts"] == 0
        assert store.summary()["jobs"] == 0
        assert snapshots(store) == []


def test_stale_observation_does_not_regress_job_or_latest_metadata(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        initial = persist(store)
        with pytest.raises(QueueError, match="stale"):
            persist(
                store,
                post=replace(POST, first_seen_at=NOW - timedelta(days=1)),
                observed_at=NOW - timedelta(hours=1),
            )
        assert store.get_job(initial["jobs"][0]["job_id"]) == initial["jobs"][0]
        assert len(snapshots(store)) == 1


def test_exact_v1_migration_preserves_jobs_checkpoints_and_frozen_folder(tmp_path):
    path = tmp_path / "legacy.db"
    legacy = make_legacy_database(path)
    with QueueStore(path) as store:
        assert store.summary()["schema_version"] == SCHEMA_VERSION
        assert store.get_job(legacy["job_id"]) == legacy
        before = list(store.connection.execute("SELECT * FROM checkpoints"))
        persist(store)
        assert list(store.connection.execute("SELECT * FROM checkpoints")) == before
        assert len(snapshots(store)) == 1
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA application_id").fetchone()[0] == APPLICATION_ID
        assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_readonly_v1_status_never_migrates_or_writes_the_file(tmp_path):
    path = tmp_path / "legacy.db"
    legacy = make_legacy_database(path)
    before = path.read_bytes()
    with QueueStore(path, read_only=True) as store:
        assert store.summary()["schema_version"] == 1
        assert store.get_job(legacy["job_id"]) == legacy
        assert snapshots(store) == []
        with pytest.raises(QueueError, match="read-only"):
            persist(store)
    assert path.read_bytes() == before
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
        assert (
            db.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE name='post_observations'"
            ).fetchone()[0]
            == 0
        )


def test_migration_failure_rolls_back_all_new_objects_and_version(tmp_path, monkeypatch):
    path = tmp_path / "legacy.db"
    legacy = make_legacy_database(path)
    before = path.read_bytes()
    monkeypatch.setattr(
        queue_module,
        "OBSERVATION_STATEMENTS",
        queue_module.OBSERVATION_STATEMENTS + ("SELECT nonexistent_function()",),
    )
    with pytest.raises(sqlite3.OperationalError, match="nonexistent_function"):
        QueueStore(path)
    assert path.read_bytes() == before
    with QueueStore(path, read_only=True) as store:
        assert store.summary()["schema_version"] == 1
        assert store.get_job(legacy["job_id"]) == legacy
        assert snapshots(store) == []


def test_declared_v1_with_unrecognized_object_is_not_modified(tmp_path):
    path = tmp_path / "modified-v1.db"
    make_legacy_database(path)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE foreign_data(value TEXT)")
    before = path.read_bytes()
    with pytest.raises(QueueError, match="migration refused"):
        QueueStore(path)
    assert path.read_bytes() == before


def test_two_connections_can_open_a_legacy_queue_during_the_same_migration(tmp_path, monkeypatch):
    path = tmp_path / "legacy.db"
    legacy = make_legacy_database(path)
    original_write = QueueStore._write
    barrier = Barrier(2)

    @contextmanager
    def concurrent_migration(self):
        barrier.wait(timeout=5)
        with original_write(self):
            yield

    monkeypatch.setattr(QueueStore, "_write", concurrent_migration)

    def open_queue(_worker):
        with QueueStore(path) as store:
            return store.summary()["schema_version"], store.get_job(legacy["job_id"])

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(open_queue, [0, 1]))
    assert results == [(SCHEMA_VERSION, legacy), (SCHEMA_VERSION, legacy)]


def test_sqlitex_user_table_is_not_mistaken_for_an_empty_database(tmp_path):
    path = tmp_path / "unrelated.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE sqlitex_user_data(value TEXT)")
        db.execute("INSERT INTO sqlitex_user_data VALUES ('preserve')")
    before = path.read_bytes()
    with pytest.raises(QueueError, match="schema"):
        QueueStore(path)
    assert path.read_bytes() == before
    assert not path.with_name(path.name + "-wal").exists()
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT * FROM sqlitex_user_data").fetchall() == [("preserve",)]
        assert db.execute("PRAGMA application_id").fetchone()[0] == 0
        assert db.execute("PRAGMA user_version").fetchone()[0] == 0
        assert (
            db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='posts'").fetchone()[0] == 0
        )


def test_sqlitex_object_in_declared_v1_prevents_migration_without_changes(tmp_path):
    path = tmp_path / "unrecognized-v1.db"
    legacy = make_legacy_database(path)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE sqlitex_user_data(value TEXT)")
        db.execute("INSERT INTO sqlitex_user_data VALUES ('preserve')")
    before = path.read_bytes()
    with pytest.raises(QueueError, match="migration refused"):
        QueueStore(path)
    assert path.read_bytes() == before
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT * FROM sqlitex_user_data").fetchall() == [("preserve",)]
        assert db.execute("SELECT job_id FROM jobs").fetchall() == [(legacy["job_id"],)]
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
        assert (
            db.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE name='post_observations'"
            ).fetchone()[0]
            == 0
        )
