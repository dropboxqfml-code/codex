"""Retrospective diagnosis must survive later candidate refreshes without trusting them."""

import json
from functools import partial
from pathlib import Path

import pytest
from test_watch_historical_receipt import history as history
from test_watch_historical_receipt import listing
from test_watch_runtime import link, observed, snapshot

from image_monitor.monitor_list_history import previous_list_checks
from image_monitor.queue import QueueStore
from image_monitor.watch_lock import watch_run_lock
from image_monitor.watch_runtime import DEFAULT_SCOPE, HEAD_OVERLAP_SCHEMA
from image_monitor.watch_store import MONITOR_SCOPE, WatchStore


def _edit(path, patch):
    receipt = json.loads(path.read_bytes())
    receipt.update(patch)
    path.write_text(json.dumps(receipt), encoding="utf-8")


def _set_route_format(root, path, version, capability, control_schema):
    """Reproduce each release's persisted schema, or damage one side for a negative case."""
    receipt = json.loads(path.read_bytes())
    assert receipt.pop("historical_route_schema") == HEAD_OVERLAP_SCHEMA
    receipt["program_version"] = version
    if capability is not None:
        receipt["historical_route_schema"] = capability
    path.write_text(json.dumps(receipt), encoding="utf-8")
    scan_id = receipt["closed_monitor_scan"]["scan_id"]
    with QueueStore(root / "watch.sqlite") as queue:
        row = queue.connection.execute(
            "SELECT result_json FROM watch_scans WHERE scan_id=?", (scan_id,)
        ).fetchone()
        result = json.loads(row[0])
        assert result["control"].pop("historical_route_schema") == HEAD_OVERLAP_SCHEMA
        if control_schema is not None:
            result["control"]["historical_route_schema"] = control_schema
        queue.connection.execute(
            "UPDATE watch_scans SET result_json=? WHERE scan_id=?", (json.dumps(result), scan_id)
        )


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
    ("version", "capability", "control_schema", "expected"),
    [
        ("0.5.0-alpha.8", None, None, 1),
        ("0.5.0-alpha.8", 1, None, 1),
        ("0.5.0-alpha.9", None, None, 2),
        ("0.5.0-alpha.9", 1, None, 1),
        ("0.5.0-alpha.10", 1, None, 2),
        ("0.5.0-alpha.10", 2, 2, 1),
        ("0.5.0-alpha.11", 1, 2, 1),
        ("0.5.0-alpha.11", 2, None, 1),
        ("0.6.0", 1, None, 2),
        ("0.6.0", 2, 2, 2),
        ("0.6.0", None, None, 1),
        ("0.6.0", True, None, 1),
        (None, 1, None, 1),
    ],
)
def test_receipts_distinguish_old_contiguous_scans_from_historical_navigation(
    tmp_path, two_checks, version, capability, control_schema, expected
):
    _set_route_format(tmp_path, two_checks[-1], version, capability, control_schema)
    assert len(previous_list_checks(tmp_path)) == expected


def _listing_with_rows(documents):
    builders = [
        partial(
            snapshot,
            rows,
            page=number,
            links=[link(p) for p in links],
            counts={"list_containers": 1},
        )
        for number, rows, links in documents
    ]
    return observed(*builders)


@pytest.fixture
def shifted_history(history):
    run, _ = history
    seed = [
        (1, [150, 149, 148, 147], [2]),
        (2, [146, 145], [3]),
        (3, [144, 143], [4]),
        (4, [142, 141], [5]),
    ]
    assert run(_listing_with_rows(seed))["status"] == "watch_test_partial"
    return run


@pytest.mark.parametrize(
    ("version", "capability", "control_schema", "reason"),
    [
        ("0.5.0-alpha.9", None, None, "previous_head_not_matched"),
        ("0.5.0-alpha.10", 1, None, "previous_head_not_matched"),
        ("0.5.0-alpha.11", 2, 2, "boundary_link_missing"),
    ],
)
def test_same_stored_pages_keep_the_route_reason_of_the_original_release(
    tmp_path, shifted_history, version, capability, control_schema, reason
):
    # Only the first three rows of the old head reach the end of the current
    # second page. The link to page 4 is absent, so all releases visit 1,2,3,4.
    shifted = [
        (1, [160, 159, 158], [2]),
        (2, [157, 150, 149, 148], [3]),
        (3, [147, 146], [4]),
        (4, [145, 144], [5]),
    ]
    report = shifted_history(_listing_with_rows(shifted))
    _set_route_format(tmp_path, Path(report["report_path"]), version, capability, control_schema)
    last = previous_list_checks(tmp_path)[-1]
    assert last["visited_page_numbers"] == [1, 2, 3, 4]
    assert last["historical_status"] == "recent_pages_only" and last["historical_reason"] == reason
    assert "head_join" not in last


@pytest.mark.parametrize(
    ("current_second_page", "expected_join"),
    [([157, 150, 149, 148], "clipped_prefix"), ([157, 149, 148, 147, 146], "corroborated_suffix")],
)
def test_reopen_only_describes_the_head_join_proved_by_the_closed_scan(
    tmp_path, shifted_history, current_second_page, expected_join
):
    report = shifted_history(
        _listing_with_rows(
            [
                (1, [160, 159, 158], [2]),
                (2, current_second_page, [3, 4]),
                (4, [142, 141], [5]),
                (5, [140, 139], [6]),
            ]
        )
    )
    assert report["status"] == "watch_test_partial"
    checks = previous_list_checks(tmp_path)
    assert checks[-1]["visited_page_numbers"] == [1, 2, 4, 5]
    assert checks[-1]["historical_reason"] == "boundary_extended"
    assert checks[-1]["head_join"] == expected_join

    # The legacy policy cannot justify the same recorded jump with these rows.
    _set_route_format(tmp_path, Path(report["report_path"]), "0.5.0-alpha.10", 1, None)
    assert previous_list_checks(tmp_path) == checks[:-1]


def test_missing_or_busy_history_causes_no_file_changes(tmp_path):
    missing = tmp_path / "missing"
    assert previous_list_checks(missing) == [] and not missing.exists()
    database = tmp_path / "watch.sqlite"
    with QueueStore(database), watch_run_lock(database, DEFAULT_SCOPE):
        names = sorted(tmp_path.iterdir())
        assert previous_list_checks(tmp_path) == []
        assert sorted(tmp_path.iterdir()) == names
