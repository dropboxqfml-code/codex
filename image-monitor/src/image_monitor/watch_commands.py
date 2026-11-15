"""Local synthetic list-watch demonstration; never navigate or save images."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from image_monitor.queue import QueueStore
from image_monitor.search_list import build_list_url
from image_monitor.watch_planner import next_poll_at, plan_scan
from image_monitor.watch_store import WatchScope, WatchStore


def _fixture_page(scope, identifiers, observed_at, *, page=1, next_page=None, terminal=False):
    url = build_list_url(scope.gallery_type, scope.gallery_id, scope.keyword, page=page)
    return {
        "schema_version": 1,
        "scope": {
            "gallery_type": scope.gallery_type,
            "gallery_id": scope.gallery_id,
            "keyword": scope.keyword,
            "search_type": scope.search_type,
            "navigation": {},
        },
        "url": url,
        "page": page,
        "search_pos": None,
        "observed_at": observed_at.isoformat(),
        "layout_status": "fixture_validated",
        "queue_eligible": False,
        "status": "observed" if identifiers else "empty",
        "rows": [
            {
                "post_id": str(identifier),
                "canonical_url": (
                    f"https://gall.dcinside.com/board/view/?id={scope.gallery_id}&no={identifier}"
                ),
                "title": f"Synthetic post {identifier}",
                "author_raw": "fixture author",
                "published_at_raw": "13:00",
                "row_order": index,
            }
            for index, identifier in enumerate(identifiers, 1)
        ],
        "pagination_candidates": [
            {
                "canonical_url": build_list_url(
                    scope.gallery_type, scope.gallery_id, scope.keyword, page=next_page
                ),
                "page": next_page,
                "search_pos": None,
            }
        ]
        if next_page is not None
        else [],
        "pagination_complete": terminal,
        "end_of_results": terminal,
    }


def watch_demo(database: Path) -> dict:
    """Prove baseline/partial/restart behavior in a new database using fixed rows."""
    database = Path(database)
    database.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(database, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    scope = WatchScope("감시 시험", "normal", "watch_fixture", "synthetic", "search_subject_memo")
    now = datetime.now(UTC)
    cycles = []
    with QueueStore(database) as queue:
        store = WatchStore(queue)
        baseline_page = _fixture_page(scope, [100, 99], now, next_page=2)
        baseline_plan = plan_scan(
            scope, store.get_state(scope), [baseline_page], now, synthetic_fixture=True
        )
        cycles.append(store.persist_scan(scope, **baseline_plan))
        original_checkpoint = store.get_state(scope)["checkpoint"]
        partial_time = now + timedelta(seconds=60)
        partial_page = _fixture_page(scope, [104, 103], partial_time, next_page=2)
        partial_plan = plan_scan(
            scope,
            store.get_state(scope),
            [partial_page],
            partial_time,
            max_pages=1,
            synthetic_fixture=True,
        )
        cycles.append(store.persist_scan(scope, **partial_plan))
        if partial_plan["complete"] or store.get_state(scope)["checkpoint"] != original_checkpoint:
            raise RuntimeError("Synthetic partial scan incorrectly advanced complete coverage")
    # A fresh connection must retain both discovered candidates and the old coverage.
    complete_time = now + timedelta(seconds=120)
    with QueueStore(database) as queue:
        store = WatchStore(queue)
        if store.get_state(scope)["checkpoint"] != original_checkpoint:
            raise RuntimeError("Synthetic coverage did not survive reopening the queue")
        pages = [
            _fixture_page(scope, [104, 103], complete_time, next_page=2),
            _fixture_page(scope, [100, 99], complete_time, page=2, next_page=3),
            _fixture_page(scope, [98], complete_time, page=3, terminal=True),
        ]
        complete_plan = plan_scan(
            scope, store.get_state(scope), pages, complete_time, synthetic_fixture=True
        )
        if not complete_plan["complete"]:
            raise RuntimeError("Synthetic exact-anchor overlap scan did not complete")
        cycles.append(store.persist_scan(scope, **complete_plan))
    with QueueStore(database, read_only=True) as queue:
        store = WatchStore(queue)
        state = store.get_state(scope)
        candidates = store.list_candidates(scope)
        return {
            "synthetic_only": True,
            "browser_started": False,
            "images_saved": False,
            "periodic_monitoring_started": False,
            "summary": queue.summary(),
            "watch_state": state,
            "candidate_post_ids": [candidate["post_id"] for candidate in candidates],
            "scan_count": len(store.list_scans(scope)),
            "historical_gap_count": len(store.list_gaps(scope)),
            "baseline_skipped_existing_rows": True,
            "partial_preserved_complete_checkpoint": True,
            "reopen_verified": True,
            "cycles": cycles,
            "next_normal_poll_at": next_poll_at(complete_time).isoformat(),
        }
