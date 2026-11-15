"""Synthetic end-to-end post inspection and queue persistence diagnostics."""

import os
from datetime import UTC, datetime
from pathlib import Path

from image_monitor.dcinside import parse_snapshot
from image_monitor.post_pipeline import enqueue_snapshot
from image_monitor.queue import QueueStore


def fixture_raw() -> dict:
    def image(order, resource, **extra):
        return {
            "body_order": order,
            "display_url": "https://example.invalid/" + resource,
            "complete": True,
            "natural_width": 96,
            "natural_height": 64,
            "decode_ok": True,
            **extra,
        }

    return {
        "body_count": 1,
        "title": "합성 게시글: 첨부 순서와 본문 순서가 다른 예제",
        "nickname": "시험 작성자",
        "ip_display": None,
        "published_at_raw": "2026.11.14 23:59:00",
        "attachments": [
            {"key": "att-b", "filename": "둘째.gif", "filename_complete": True, "identity": "b"},
            {"key": "att-a", "filename": "첫째.png", "filename_complete": True, "identity": "a"},
            {"key": "att-only", "filename": "본문에 없는 파일.png", "filename_complete": True},
        ],
        "images": [
            image(1, "a.png", identity="a"),
            image(2, "dccon.gif", excluded_reason="body_dccon"),
            image(3, "b.gif", attachment_key="att-b", identity="b"),
            image(4, "a.png", identity="a"),
            image(5, "unknown.png"),
        ],
    }


def post_demo(database: Path) -> dict:
    snapshot = parse_snapshot(
        fixture_raw(),
        expected_url="https://gall.dcinside.com/board/view/?id=monitor_fixture&no=1",
        observed_at=datetime.now(UTC),
        layout_status="fixture_validated",
    )
    database.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(database, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    with QueueStore(database) as store:
        result = enqueue_snapshot(
            store,
            snapshot,
            watch_name="합성 본문 시험",
            keyword="synthetic",
            synthetic_fixture=True,
        )
    with QueueStore(database, read_only=True) as store:
        observations = store.list_post_snapshots("normal", "monitor_fixture", "1")
        summary = store.summary()
    return {
        "synthetic_only": True,
        "browser_started": False,
        "files_downloaded": 0,
        "native_save_started": False,
        "observation_id": result["observation_id"],
        "snapshot": observations[0]["snapshot"],
        "jobs": [
            {key: job[key] for key in ("job_id", "stable_key", "file_slot", "body_order", "status")}
            for job in result["jobs"]
        ],
        "queue_summary": summary,
    }
