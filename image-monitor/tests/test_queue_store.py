import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest

from image_monitor.queue import (
    SCHEMA_VERSION,
    ImageDiscovery,
    PostDiscovery,
    QueueError,
    QueueStore,
)

NOW = datetime(2026, 11, 14, 14, 59, tzinfo=UTC)


def discovery(post_id="1", **overrides):
    return PostDiscovery(
        **(
            {
                "post_id": post_id,
                "nickname": "example",
                "ip_display": None,
                "first_seen_at": NOW,
            }
            | overrides
        )
    )


def discover(store, posts=None, **overrides):
    return store.discover_batch(
        **(
            {
                "watch_name": "watch",
                "gallery_type": "normal",
                "gallery_id": "gallery",
                "keyword": "ai",
                "search_type": "search_subject_memo",
                "posts": posts or [discovery()],
                "checked_at": NOW,
                "cursor": "first",
                "complete": True,
            }
            | overrides
        )
    )


def queue(store, images=None, **overrides):
    return store.queue_images(
        **(
            {
                "gallery_type": "normal",
                "gallery_id": "gallery",
                "post_id": "1",
                "images": images
                or [ImageDiscovery("file-key-a", 1, "https://example.invalid/a.png")],
            }
            | overrides
        )
    )


def checkpoint(store, **overrides):
    return store.get_checkpoint(
        **(
            {
                "watch_name": "watch",
                "gallery_type": "normal",
                "gallery_id": "gallery",
                "keyword": "ai",
                "search_type": "search_subject_memo",
            }
            | overrides
        )
    )


def test_discovery_checkpoint_and_date_survive_reopen(tmp_path):
    path = tmp_path / "queue.db"
    with QueueStore(path) as store:
        assert discover(store) == {"posts_added": 1, "matches_added": 1}
        folder = store.get_post("normal", "gallery", "1")["folder_plan"]
        assert folder["folder_date_basis"] == "first_seen_at"
    with QueueStore(path) as store:
        discover(
            store,
            [discovery(published_at=NOW - timedelta(days=3))],
            checked_at=NOW + timedelta(days=1),
            folder_date_basis="first_seen_at",
            cursor="later",
        )
        post = store.get_post("normal", "gallery", "1")
        assert post["folder_plan"] == folder
        assert post["first_seen_at"] == NOW.isoformat(timespec="microseconds")
        assert post["published_at"] is not None
        assert checkpoint(store)["cursor"] == "later"


def test_invalid_second_post_rolls_back_first_post_and_checkpoint(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        discover(store)
        before = checkpoint(store)
        with pytest.raises(ValueError):
            discover(store, [discovery("2"), discovery("bad/id")], cursor="must-not-commit")
        assert store.get_post("normal", "gallery", "2") is None
        assert checkpoint(store) == before
        assert store.summary()["posts"] == 1


def test_gallery_type_and_search_matches_are_separate(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        discover(store)
        discover(store, gallery_type="minor")
        assert discover(store, keyword="other") == {"posts_added": 0, "matches_added": 1}
        assert store.summary()["posts"] == 2
        assert checkpoint(store, gallery_type="minor") is not None
        assert checkpoint(store, keyword="other") is not None
        assert store.connection.execute("SELECT COUNT(*) FROM matches").fetchone()[0] == 3


def test_incomplete_scan_preserves_gap_and_rejects_stale_checkpoint(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        discover(store, complete=False, gap_reason="page_limit", cursor="remaining")
        assert store.list_gaps()[0]["reason"] == "page_limit"
        assert checkpoint(store)["complete"] == 0
        with pytest.raises(QueueError, match="stale"):
            discover(store, checked_at=NOW - timedelta(seconds=1))
        assert checkpoint(store)["cursor"] == "remaining"


def test_stable_key_reordering_keeps_job_slot_and_counters(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        discover(store)
        original = queue(store)[0]
        claim = store.claim_next("worker", NOW)
        store.record_failure(claim["job_id"], claim["lease_token"], "network", "busy", NOW)
        reordered = queue(
            store,
            [
                ImageDiscovery("new-key", 1, "https://example.invalid/new.png"),
                ImageDiscovery("file-key-a", 2, "https://example.invalid/refreshed.png"),
            ],
        )
        assert reordered[1]["job_id"] == original["job_id"]
        assert reordered[1]["file_slot"] == 1
        assert reordered[1]["body_order"] == 2
        assert reordered[1]["attempt_count"] == 1
        assert reordered[1]["display_url"].endswith("refreshed.png")
        assert reordered[0]["job_id"] != original["job_id"]
        assert reordered[0]["file_slot"] == 2


def test_active_job_retains_claimed_url_and_cannot_change_service_scope(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        discover(store)
        original = queue(store)[0]
        claim = store.claim_next("worker", NOW)
        refreshed = queue(store, [ImageDiscovery("file-key-a", 2, "https://example.invalid/new")])[
            0
        ]
        assert refreshed["display_url"] == original["display_url"]
        assert refreshed["lease_token"] == claim["lease_token"]
        with pytest.raises(QueueError, match="scope"):
            queue(store, [ImageDiscovery("file-key-a", 2, "https://example.invalid/new", "other")])


def test_two_connections_cannot_claim_same_job(tmp_path):
    path = tmp_path / "queue.db"
    with QueueStore(path) as store:
        discover(store)
        queue(store)
    barrier = Barrier(2)

    def claim(worker):
        with QueueStore(path) as store:
            barrier.wait(timeout=5)
            return store.claim_next(worker, NOW)

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(claim, ["first", "second"]))
    assert sum(result is not None for result in results) == 1


@pytest.mark.parametrize(
    "failure,status", [("ui", "paused_ui"), ("local", "paused_local"), ("access", "blocked")]
)
def test_nonnetwork_failures_do_not_consume_attempts(tmp_path, failure, status):
    with QueueStore(tmp_path / "queue.db") as store:
        discover(store)
        queue(store)
        claim = store.claim_next("worker", NOW)
        result = store.record_failure(claim["job_id"], claim["lease_token"], failure, "reason", NOW)
        assert result["status"] == status
        assert result["attempt_count"] == 0
        assert result["first_failure_at"] is None
        assert result["lease_token"] is None
        assert store.claim_next("other", NOW + timedelta(days=1)) is None


def test_server_wait_is_shared_across_galleries_and_persists(tmp_path):
    path = tmp_path / "queue.db"
    with QueueStore(path) as store:
        discover(store)
        queue(store)
        discover(store, gallery_id="other_gallery")
        queue(store, gallery_id="other_gallery")
        claim = store.claim_next("worker", NOW)
        result = store.record_failure(
            claim["job_id"], claim["lease_token"], "network", "busy", NOW, server_retry_after="600"
        )
        assert result["next_retry_at"] == (NOW + timedelta(seconds=600)).isoformat(
            timespec="microseconds"
        )
        store.defer_service("default", NOW + timedelta(seconds=30))
    with QueueStore(path) as store:
        assert store.claim_next("second", NOW + timedelta(seconds=599)) is None
        assert (
            store.claim_next("second", NOW + timedelta(seconds=600))["gallery_id"]
            == "other_gallery"
        )


def test_retry_count_and_first_failure_persist_until_eight_attempt_limit(tmp_path):
    path = tmp_path / "queue.db"
    with QueueStore(path) as store:
        discover(store)
        job_id = queue(store)[0]["job_id"]
    now = NOW
    for attempt in range(1, 9):
        with QueueStore(path) as store:
            claim = store.claim_next("worker", now)
            assert claim["job_id"] == job_id
            result = store.record_failure(job_id, claim["lease_token"], "network", "busy", now)
            assert result["attempt_count"] == attempt
            assert result["first_failure_at"] == NOW.isoformat(timespec="microseconds")
            assert len(store.history(job_id)) == attempt
            if attempt < 8:
                now = datetime.fromisoformat(result["next_retry_at"])
            else:
                assert result["status"] == "manual_review"
                assert store.claim_next("worker", now + timedelta(days=1)) is None


def test_offline_past_24_hours_never_claims_expired_retry(tmp_path):
    path = tmp_path / "queue.db"
    with QueueStore(path) as store:
        discover(store)
        queue(store)
        claim = store.claim_next("worker", NOW)
        failed = store.record_failure(claim["job_id"], claim["lease_token"], "network", "busy", NOW)
    with QueueStore(path) as store:
        assert store.claim_next("worker", NOW + timedelta(hours=24)) is None
        result = store.get_job(claim["job_id"])
        assert result["status"] == "manual_review"
        assert result["attempt_count"] == 1
        assert result["next_retry_at"] == failed["next_retry_at"]


def test_older_due_retry_is_not_starved_by_newly_discovered_jobs(tmp_path):
    with QueueStore(tmp_path / "queue.db") as store:
        discover(store)
        original = queue(store)[0]
        claim = store.claim_next("worker", NOW)
        store.record_failure(claim["job_id"], claim["lease_token"], "network", "busy", NOW)
        later = NOW + timedelta(seconds=60)
        discover(store, [discovery("2", first_seen_at=later)], checked_at=later)
        queue(store, post_id="2")
        next_job = store.claim_next("worker", later)
        assert next_job["job_id"] == original["job_id"]


@pytest.mark.parametrize("status", ["loading", "saving", "verifying"])
def test_interrupted_jobs_require_review_and_stale_claim_cannot_write(tmp_path, status):
    path = tmp_path / "queue.db"
    with QueueStore(path) as store:
        discover(store)
        queue(store)
        claim = store.claim_next("worker", NOW)
        if status in {"saving", "verifying"}:
            store.transition(claim["job_id"], claim["lease_token"], "saving")
        if status == "verifying":
            store.transition(claim["job_id"], claim["lease_token"], "verifying")
    with QueueStore(path) as store:
        with pytest.raises(QueueError, match="Confirm"):
            store.recover_interrupted()
        assert store.recover_interrupted(confirm_workers_stopped=True) == 1
        assert store.get_job(claim["job_id"])["status"] == "manual_review"
        assert store.claim_next("other", NOW + timedelta(days=2)) is None
        with pytest.raises(QueueError, match="Stale"):
            store.transition(claim["job_id"], claim["lease_token"], "saving")


def test_readonly_status_does_not_create_or_write_database(tmp_path):
    path = tmp_path / "queue.db"
    with pytest.raises(sqlite3.OperationalError):
        QueueStore(path, read_only=True)
    assert not path.exists()
    with QueueStore(path) as store:
        discover(store)
    with QueueStore(path, read_only=True) as store:
        assert store.summary()["posts"] == 1
        with pytest.raises(QueueError, match="read-only"):
            discover(store)


def test_unknown_and_newer_schemas_are_left_unchanged(tmp_path):
    path = tmp_path / "unknown.db"
    with sqlite3.connect(path) as database:
        database.execute("CREATE TABLE unrelated(value TEXT)")
        database.execute("INSERT INTO unrelated VALUES ('preserve')")
    original = path.read_bytes()
    with pytest.raises(QueueError, match="schema"):
        QueueStore(path)
    assert path.read_bytes() == original
    path = tmp_path / "newer.db"
    with QueueStore(path) as store:
        store.connection.execute(f"PRAGMA user_version={SCHEMA_VERSION + 1}")
    original = path.read_bytes()
    with pytest.raises(QueueError, match="schema"):
        QueueStore(path)
    assert path.read_bytes() == original


def test_unrelated_view_only_database_is_not_initialized_or_changed(tmp_path):
    path = tmp_path / "unrelated-view.db"
    with sqlite3.connect(path) as database:
        database.execute("CREATE VIEW user_data AS SELECT 1 AS value")
        before_pragmas = (
            database.execute("PRAGMA application_id").fetchone()[0],
            database.execute("PRAGMA user_version").fetchone()[0],
            database.execute("PRAGMA journal_mode").fetchone()[0],
        )
    original = path.read_bytes()
    with pytest.raises(QueueError, match="schema"):
        QueueStore(path)
    assert path.read_bytes() == original
    assert not path.with_name(path.name + "-wal").exists()
    with sqlite3.connect(path) as database:
        after_pragmas = (
            database.execute("PRAGMA application_id").fetchone()[0],
            database.execute("PRAGMA user_version").fetchone()[0],
            database.execute("PRAGMA journal_mode").fetchone()[0],
        )
        assert database.execute("SELECT * FROM user_data").fetchall() == [(1,)]
        assert (
            database.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
            == 0
        )
    assert after_pragmas == before_pragmas == (0, 0, "delete")
    assert path.read_bytes() == original
