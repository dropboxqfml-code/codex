"""Local-only queue diagnostics. These commands never start a browser or collect files."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from image_monitor.queue import ImageDiscovery, PostDiscovery, QueueStore


def queue_status(database: Path) -> dict:
    with QueueStore(database, read_only=True) as store:
        return store.summary()


def queue_demo(database: Path) -> dict:
    """Create a new synthetic database without adding fixtures to an existing database."""
    database.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(database, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    now = datetime.now(UTC)
    with QueueStore(database) as store:
        store.discover_batch(
            watch_name="시험 감시",
            gallery_type="normal",
            gallery_id="monitor_fixture",
            keyword="synthetic",
            search_type="search_subject_memo",
            posts=[
                PostDiscovery(
                    post_id="1",
                    nickname="시험 작성자",
                    ip_display=None,
                    first_seen_at=now,
                    published_at=now - timedelta(days=1),
                    title="합성 대기열 시험",
                    post_url="https://example.invalid/post/1",
                )
            ],
            checked_at=now,
            cursor="fixture-page-1",
            complete=True,
        )
        store.queue_images(
            gallery_type="normal",
            gallery_id="monitor_fixture",
            post_id="1",
            images=[
                ImageDiscovery("fixture-image-a", 1, "https://example.invalid/a.png", "fixture"),
                ImageDiscovery("fixture-image-b", 2, "https://example.invalid/b.png", "fixture"),
            ],
        )
        claim = store.claim_next("synthetic-demo", now)
        if claim is None:
            raise RuntimeError("Synthetic queued job could not be claimed")
        store.record_failure(
            claim["job_id"],
            claim["lease_token"],
            "network",
            "synthetic_network_failure",
            now,
            server_retry_after="600",
        )
        store.defer_service("fixture", now + timedelta(seconds=600))
    # Inspect through a fresh read-only connection: retained SQLite state is the evidence.
    return {
        "synthetic_only": True,
        "browser_started": False,
        "files_downloaded": 0,
        "summary": queue_status(database),
    }
