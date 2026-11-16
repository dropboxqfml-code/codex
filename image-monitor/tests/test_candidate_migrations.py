"""Protect existing watch and native-save state during the detail audit upgrade."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest

from image_monitor import queue as queue_module
from image_monitor.queue import ImageDiscovery, PostDiscovery, QueueError, QueueStore
from image_monitor.watch_store import WatchScope, WatchStore

NOW = datetime(2026, 11, 16, 4, 0, tzinfo=UTC)
SCOPE = WatchScope("invented watch", "normal", "gallery", "ai", "search_subject_memo")


def database_contents(path):
    with closing(sqlite3.connect(path)) as db:
        objects = tuple(
            db.execute(
                "SELECT type,name,tbl_name,sql FROM sqlite_master "
                "WHERE name NOT GLOB 'sqlite_*' ORDER BY type,name"
            )
        )
        tables = [row[1] for row in objects if row[0] == "table"]
        rows = {
            name: tuple(db.execute(f'SELECT * FROM "{name}" ORDER BY rowid')) for name in tables
        }
        return {
            "objects": objects,
            "rows": rows,
            "version": db.execute("PRAGMA user_version").fetchone()[0],
            "application": db.execute("PRAGMA application_id").fetchone()[0],
        }


def legacy_watch_database(path):
    """Retain a real V4 watch and every native-save table, with no image bytes."""
    with QueueStore(path) as queue:
        image = ImageDiscovery("invented-image", 1, "https://example.invalid/image.png")
        observation = queue.persist_post_snapshot(
            watch_name=SCOPE.watch_name,
            gallery_type=SCOPE.gallery_type,
            gallery_id=SCOPE.gallery_id,
            keyword=SCOPE.keyword,
            search_type=SCOPE.search_type,
            post=PostDiscovery("10", "Invented author", None, NOW),
            images=[image],
            snapshot={
                "gallery_type": SCOPE.gallery_type,
                "gallery_id": SCOPE.gallery_id,
                "post_id": "10",
                "images": [
                    {
                        "stable_key": image.stable_key,
                        "body_order": image.body_order,
                        "display_url": image.display_url,
                    }
                ],
            },
            observed_at=NOW,
        )
        claim = queue.claim_next("invented worker", NOW)
        queue.transition(claim["job_id"], claim["lease_token"], "saving")
        queue.transition(claim["job_id"], claim["lease_token"], "verifying")
        queue.prepare_artifact(
            claim["job_id"],
            claim["lease_token"],
            observation_id=observation["observation_id"],
            save_root=str(path.parent / "invented storage"),
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
        watch = WatchStore(queue)
        checkpoint = {
            "anchor_ids": ["100", "99"],
            "observed_at": NOW.isoformat(),
            "source_url": "https://example.invalid/latest",
        }
        watch.persist_scan(
            SCOPE,
            observed_at=NOW,
            expected_generation=0,
            scan_result={"synthetic_fixture": True},
            candidates=[],
            checkpoint=checkpoint,
            complete=True,
            baseline=checkpoint | {"mode": "new"},
        )
        watch.persist_scan(
            SCOPE,
            observed_at=NOW + timedelta(seconds=60),
            expected_generation=1,
            scan_result={"synthetic_fixture": True},
            candidates=[
                {
                    "post_id": "101",
                    "post_url": "https://example.invalid/post/101",
                    "title": "Invented title",
                    "shown_metadata": {"date_display": "13:01"},
                }
            ],
            checkpoint=checkpoint | {"anchor_ids": ["101", "100"]},
            complete=False,
            gap_reason="invented page limit",
        )
        queue.defer_service("dcinside", NOW + timedelta(seconds=120))
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("DROP TABLE IF EXISTS candidate_details")
        db.execute("PRAGMA user_version=4")
        assert queue_module._matches_schema(db, queue_module.V4_SCHEMA)
        assert list(db.execute("PRAGMA foreign_key_check")) == []


def assert_old_state_preserved(before, after):
    assert after["version"] == queue_module.SCHEMA_VERSION == 5
    assert after["application"] == before["application"]
    assert set(before["objects"]) <= set(after["objects"])
    assert {name: after["rows"][name] for name in before["rows"]} == before["rows"]
    assert after["rows"]["candidate_details"] == ()


def test_v4_upgrade_preserves_watch_history_jobs_and_prepared_artifact(tmp_path):
    path = tmp_path / "v4.sqlite"
    legacy_watch_database(path)
    before = database_contents(path)

    with QueueStore(path) as queue:
        assert queue.schema_version == 5
        assert queue.summary()["jobs"] == 1
        assert queue.get_artifact(queue.connection.execute("SELECT job_id FROM jobs").fetchone()[0])
        assert WatchStore(queue).get_state(SCOPE)["generation"] == 2
        assert list(queue.connection.execute("PRAGMA foreign_key_check")) == []

    assert_old_state_preserved(before, database_contents(path))


def test_readonly_v4_inspection_does_not_add_detail_table_or_change_state(tmp_path):
    path = tmp_path / "v4.sqlite"
    legacy_watch_database(path)
    before = database_contents(path)

    with QueueStore(path, read_only=True) as queue:
        assert queue.schema_version == 4
        assert WatchStore(queue).get_state(SCOPE)["generation"] == 2
        assert (
            queue.connection.execute(
                "SELECT name FROM sqlite_master WHERE name='candidate_details'"
            ).fetchone()
            is None
        )
        with pytest.raises(QueueError, match="read-only"):
            queue.defer_service("dcinside", NOW + timedelta(days=1))

    assert database_contents(path) == before


def test_failed_v4_detail_migration_rolls_back_all_new_objects_and_rows(tmp_path, monkeypatch):
    path = tmp_path / "v4.sqlite"
    legacy_watch_database(path)
    before = database_contents(path)
    monkeypatch.setattr(
        queue_module,
        "CANDIDATE_DETAIL_STATEMENTS",
        queue_module.CANDIDATE_DETAIL_STATEMENTS + ("SELECT nonexistent_detail_function()",),
    )

    with pytest.raises(sqlite3.OperationalError, match="nonexistent_detail_function"):
        QueueStore(path)

    assert database_contents(path) == before


@pytest.mark.parametrize("read_only", [False, True])
def test_unknown_object_in_declared_v4_refuses_migration_and_preserves_data(tmp_path, read_only):
    path = tmp_path / "unknown.sqlite"
    legacy_watch_database(path)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE sqlitex_foreign_data(value TEXT)")
        db.execute("INSERT INTO sqlitex_foreign_data VALUES ('preserve owner data')")
    before = database_contents(path)

    with pytest.raises(QueueError, match="migration refused"):
        QueueStore(path, read_only=read_only)

    assert database_contents(path) == before


def test_two_v4_openers_share_one_atomic_detail_upgrade(tmp_path, monkeypatch):
    path = tmp_path / "v4.sqlite"
    legacy_watch_database(path)
    before = database_contents(path)
    barrier = Barrier(2)
    original = QueueStore._write

    @contextmanager
    def concurrent_migration(self):
        barrier.wait(timeout=10)
        with original(self):
            yield

    monkeypatch.setattr(QueueStore, "_write", concurrent_migration)

    def opened_version():
        with QueueStore(path) as queue:
            return queue.schema_version

    with ThreadPoolExecutor(max_workers=2) as pool:
        versions = list(pool.map(lambda _: opened_version(), range(2)))

    assert versions == [5, 5]
    assert_old_state_preserved(before, database_contents(path))
