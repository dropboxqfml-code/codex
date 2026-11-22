"""Retrospective diagnosis must survive later candidate refreshes without trusting them."""

import json
from pathlib import Path

import pytest
from test_watch_historical_receipt import history as history
from test_watch_historical_receipt import listing

from image_monitor.monitor_list_history import previous_list_checks
from image_monitor.queue import QueueStore
from image_monitor.watch_lock import watch_run_lock
from image_monitor.watch_runtime import DEFAULT_SCOPE
from image_monitor.watch_store import MONITOR_SCOPE, WatchStore


def _edit(path, patch):
    receipt = json.loads(path.read_bytes())
    receipt.update(patch)
    path.write_text(json.dumps(receipt), encoding="utf-8")


@pytest.fixture
def two_checks(tmp_path, history):
    run, seed = history
    assert previous_list_checks(tmp_path) == []
    first = run(listing([1, 2, 4, 5], [130, 120, 110, 100]))
    second = run(listing([1, 2, 5, 6], [130, 120, 100, 98]))
    assert first["status"] == "watch_test_partial" and second["status"] == "watch_test_completed"
    return run, seed, Path(first["report_path"]), Path(second["report_path"])


def test_diagnoses_two_original_generations_after_checkpoint_advances(tmp_path, two_checks):
    assert previous_list_checks(tmp_path) == [
        {
            "status": "partial",
            "reason": "overlap_incomplete",
            "pages_checked": 4,
            "page_limit": 4,
            "visited_page_numbers": [1, 2, 4, 5],
            "historical_boundary_page": 4,
            "historical_status": "extended",
            "historical_reason": "boundary_extended",
        },
        {
            "status": "complete",
            "reason": None,
            "pages_checked": 4,
            "page_limit": 4,
            "visited_page_numbers": [1, 2, 5, 6],
            "historical_boundary_page": 5,
            "historical_status": "extended",
            "historical_reason": "boundary_extended",
        },
    ]
    run, *_ = two_checks
    for _ in range(2):
        assert run(listing([1, 2], [130, 120]))["status"] == "watch_test_completed"
    assert previous_list_checks(tmp_path) == []


@pytest.mark.parametrize("fault", ["cleanup", "generation", "summary", "candidate", "baseline"])
def test_unverifiable_old_source_or_scan_suppresses_the_explanation(tmp_path, two_checks, fault):
    _, seed, first, second = two_checks
    if fault == "cleanup":
        _edit(seed, {"browser_closed": False})
    elif fault == "generation":
        manifest = json.loads(first.read_bytes())
        manifest["cycles"][0]["generation"] -= 1
        _edit(first, manifest)
    elif fault == "summary":
        record = json.loads(second.read_bytes())
        record["cycles"][0]["page_count"] = 3
        _edit(second, record)
        assert [c["status"] for c in previous_list_checks(tmp_path)] == ["partial"]
        return
    else:
        with QueueStore(tmp_path / "watch.sqlite") as queue:
            if fault == "candidate":
                # A same-count swap of an old post skipped by later scans.
                queue.connection.execute(
                    "UPDATE watch_candidates SET post_id='119' WHERE post_id='115'"
                )
            else:
                baseline = WatchStore(queue).get_state(MONITOR_SCOPE)["baseline"]
                baseline["anchor_ids"].pop()
                queue.connection.execute(
                    "UPDATE watch_state SET baseline_json=?", (json.dumps(baseline),)
                )
    assert previous_list_checks(tmp_path) == []


@pytest.mark.parametrize(
    ("version", "capability", "expected"),
    [
        ("0.5.0-alpha.8", None, 1),
        ("0.5.0-alpha.8", 1, 1),
        ("0.5.0-alpha.9", None, 2),
        ("0.5.0-alpha.9", 1, 1),
        ("0.6.0", 1, 2),
        ("0.6.0", None, 1),
        ("0.6.0", True, 1),
        (None, 1, 1),
    ],
)
def test_receipts_distinguish_old_contiguous_scans_from_historical_navigation(
    tmp_path, two_checks, version, capability, expected
):
    last = two_checks[-1]
    receipt = json.loads(last.read_bytes())
    assert receipt.pop("historical_route_schema") == 1
    receipt["program_version"] = version
    if capability is not None:
        receipt["historical_route_schema"] = capability
    last.write_text(json.dumps(receipt), encoding="utf-8")
    assert len(previous_list_checks(tmp_path)) == expected


def test_missing_or_busy_history_causes_no_file_changes(tmp_path):
    missing = tmp_path / "missing"
    assert previous_list_checks(missing) == [] and not missing.exists()
    database = tmp_path / "watch.sqlite"
    with QueueStore(database), watch_run_lock(database, DEFAULT_SCOPE):
        names = sorted(tmp_path.iterdir())
        assert previous_list_checks(tmp_path) == []
        assert sorted(tmp_path.iterdir()) == names
