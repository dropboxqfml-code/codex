import json

import pytest

from image_monitor.queue import SCHEMA_VERSION, QueueStore
from image_monitor.watch_commands import watch_demo
from image_monitor.watch_store import WatchScope, WatchStore


def test_synthetic_watch_baseline_partial_reopen_and_overlap_never_create_image_jobs(tmp_path):
    path = tmp_path / "watch.sqlite"
    result = watch_demo(path)
    assert result["synthetic_only"]
    assert not result["browser_started"] and not result["images_saved"]
    assert not result["periodic_monitoring_started"]
    assert result["summary"]["schema_version"] == SCHEMA_VERSION
    assert result["summary"]["posts"] == result["summary"]["jobs"] == 0
    assert set(result["candidate_post_ids"]) == {"104", "103"}
    assert result["watch_state"]["generation"] == 3
    assert result["watch_state"]["baseline"]["anchor_ids"] == ["100", "99"]
    assert result["watch_state"]["checkpoint"]["anchor_ids"] == ["104", "103"]
    assert result["scan_count"] == 3 and result["historical_gap_count"] == 1
    assert result["reopen_verified"] and result["partial_preserved_complete_checkpoint"]
    scope = WatchScope("감시 시험", "normal", "watch_fixture", "synthetic", "search_subject_memo")
    with QueueStore(path, read_only=True) as queue:
        rows = WatchStore(queue).list_candidates(scope)
        assert all(row["shown_metadata"]["requires_published_at_filter"] for row in rows)
        assert all(row["shown_metadata"]["published_at_raw"] == "13:00" for row in rows)
        assert queue.list_jobs() == []
    json.dumps(result)


def test_demo_refuses_an_existing_database_without_changing_it(tmp_path):
    path = tmp_path / "preserve.sqlite"
    path.write_bytes(b"Owner data must remain unchanged")
    with pytest.raises(FileExistsError):
        watch_demo(path)
    assert path.read_bytes() == b"Owner data must remain unchanged"
