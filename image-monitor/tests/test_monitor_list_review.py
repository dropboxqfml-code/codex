"""A shareable review may describe only the committed turn and its final report."""

import json
from pathlib import Path

import pytest
from test_watch_runtime import (
    BrowserFactory,
    FakeClock,
    baseline_outcome,
    link,
    new_posts_outcome,
    unverified_second_page,
)

from image_monitor import watch_runtime
from image_monitor.monitor_list_review import (
    current_list_review,
    previous_list_review,
    public_list_review,
)
from image_monitor.queue import QueueStore
from image_monitor.watch_store import MONITOR_SCOPE, WatchStore


def scan(root, clock, outcome):
    return watch_runtime.run_watch_trial(
        root,
        cycles=1,
        clock=clock,
        backend_factory=BrowserFactory(outcome),
        scope=MONITOR_SCOPE,
        follow_up_gaps=True,
        recover_long_gaps=True,
    )


def network_error(_):
    return {
        "status": "network_error",
        "http_status": None,
        "retry_after": None,
        "pages": [],
        "navigation": [{"url": link(1)["canonical_url"], "http_status": None}],
        "error_type": "Error",
        "error_code": "ERR_CONNECTION_RESET",
    }


@pytest.fixture
def run(tmp_path, monkeypatch):
    monkeypatch.setattr(watch_runtime, "require_windows", lambda: None)
    clock = FakeClock()
    assert scan(tmp_path, clock, baseline_outcome)["status"] == "watch_test_completed"
    with QueueStore(tmp_path / "watch.sqlite", read_only=True) as q:
        before = WatchStore(q).get_state(MONITOR_SCOPE)
    clock.wait(60)
    return tmp_path, clock, before


def current(root, before, raw):
    database = root / "watch.sqlite"
    with QueueStore(database, read_only=True) as q:
        after = WatchStore(q).get_state(MONITOR_SCOPE)
        return current_list_review(database, q, before, after, raw, stage="watch_result")


def test_current_and_previous_explain_bound_transport_then_new_success_supersedes(run):
    root, clock, before = run
    raw = scan(root, clock, network_error)
    assert raw["status"] == "watch_test_failed"
    expected = {
        "stage": "watch_result",
        "evidence": "committed_scan",
        "watch_status": "watch_test_failed",
        "watch_stage": "persist_scan",
        "transport": "network_error",
        "error_type": "Error",
        "error_code": "ERR_CONNECTION_RESET",
        "planner_issue": "no_page_evidence",
        "gap_reason": "list_transport_or_inspection_failure",
        "visited_page_numbers": [1],
        "pages": [],
    }
    assert current(root, before, raw) == expected
    files = {p.relative_to(root): p.stat().st_mtime_ns for p in root.rglob("*") if p.is_file()}
    assert previous_list_review(root) == expected
    assert {
        p.relative_to(root): p.stat().st_mtime_ns for p in root.rglob("*") if p.is_file()
    } == files
    assert current(root, before | {"generation": 0}, raw) is None
    clock.wait(60)
    assert scan(root, clock, new_posts_outcome)["status"] == "watch_test_completed"
    assert previous_list_review(root) is None
    assert current(root, before, raw) is None


def test_unsupported_partial_yields_exact_safe_layout_and_page_numbers(run):
    root, clock, before = run
    raw = scan(root, clock, unverified_second_page)
    result = current(root, before, raw)
    assert result["visited_page_numbers"] == [1, 2]
    assert result["planner_issue"] == "snapshot_layout"
    assert [page["layout_status"] for page in result["pages"]] == ["site_verified", "unverified"]
    assert result["gap_reason"] == "list_profile_unverified_or_incomplete"
    assert previous_list_review(root) == result | {"stage": "stored_scan"}
    assert public_list_review(result) == result
    for private in ("post_id", "http://", "https://", str(root), "comic_new6", "source_url"):
        assert private not in json.dumps(result)


@pytest.mark.parametrize(
    "damaged",
    [
        "unclosed",
        "missing",
        "other_run",
        "new_deadline",
        "another_scope",
        "generation",
        "same_run_different_cycle",
        "uncommitted",
    ],
)
def test_missing_or_contradictory_evidence_never_supplies_observation(run, damaged):
    root, clock, before = run
    raw = scan(root, clock, network_error)
    path = Path(raw["report_path"])
    if damaged == "missing":
        path.unlink()
    elif damaged in {"another_scope", "generation", "uncommitted"}:
        with QueueStore(root / "watch.sqlite") as q:
            if damaged == "another_scope":
                q.connection.execute(
                    "UPDATE watch_scans SET watch_name='unrelated' WHERE generation=2"
                )
            elif damaged == "generation":
                q.connection.execute("UPDATE watch_state SET generation=5")
            else:
                q.connection.execute("DELETE FROM watch_gaps WHERE generation=2")
    else:
        modified = json.loads(path.read_text())
        if damaged == "other_run":
            modified["report_path"] = str(root / "runs" / ("0" * 32) / "report.json")
        elif damaged == "unclosed":
            modified["browser_closed"] = False
        elif damaged == "new_deadline":
            modified["next_eligible_at_local"] = clock.now().isoformat()
        else:
            modified["cycles"][0]["generation"] -= 1
        path.write_text(json.dumps(modified))
    assert current(root, before, raw) is None
    assert previous_list_review(root) is None


def test_reproject_filters_private_fields_and_has_stage_only_when_unbound():
    assert public_list_review({"stage": "preflight", "error_type": "Error"}) == {
        "stage": "preflight"
    }
    assert public_list_review({"stage": "not a stage"}) is None
    data = public_list_review(
        {
            "stage": "planner_check",
            "evidence": "committed_scan",
            "transport": "https://private",
            "error_code": "private path",
            "http_status": True,
            "visited_page_numbers": [1, False],
            "pages": [
                {
                    "page": 10001,
                    "status": "arbitrary",
                    "profile_issue": "not safe",
                    "post_id": "123",
                    "ordinary_rows": 0,
                }
            ],
        }
    )
    assert data == {
        "stage": "planner_check",
        "evidence": "committed_scan",
        "pages": [{"ordinary_rows": 0}],
    }


def test_previous_missing_watch_root_never_creates_state(tmp_path):
    root = tmp_path / "absent"
    assert previous_list_review(root) is None
    assert not root.exists()


@pytest.mark.parametrize("stage", ["watch_result", "planner_check"])
def test_uncommitted_worker_report_can_only_explain_the_worker_failure(stage):
    review = public_list_review(
        {
            "stage": stage,
            "evidence": "worker_report",
            "watch_status": "watch_test_failed",
            "watch_stage": "list_observation",
            "error_type": "TimeoutError",
            "http_status": 503,
            "visited_page_numbers": [1],
            "pages": [],
            "gap_reason": "pagination_missing",
            "planner_issue": "snapshot_identity",
            "cause": "private",
        }
    )
    if stage == "watch_result":
        assert review == {
            "stage": "watch_result",
            "evidence": "worker_report",
            "watch_status": "watch_test_failed",
            "watch_stage": "list_observation",
            "error_type": "TimeoutError",
        }
        assert public_list_review(review) == review
    else:
        assert review == {"stage": stage}
