"""Exercise the atomic hand-off between a stored scan and closed Chrome evidence."""

import json
from copy import deepcopy

import pytest
from test_monitor_long_gap import OLD_HEAD
from test_monitor_long_gap import starting_watch as starting_watch

from image_monitor.monitor_gap_store import bookmark_seal, load_bookmark
from image_monitor.queue import QueueError, QueueStore
from image_monitor.watch_runtime import verified_recent_plan
from image_monitor.watch_store import MONITOR_SCOPE, WatchStore


def persisted(root):
    with QueueStore(root / "watch.sqlite", read_only=True) as queue:
        state = WatchStore(queue).get_state(MONITOR_SCOPE)
        return state, load_bookmark(queue, state)


@pytest.fixture
def advancing(tmp_path, starting_watch):
    feed, clock, checkpoint = starting_watch
    clock.wait(86400)
    feed.ids[:0] = range(OLD_HEAD + 300, OLD_HEAD, -1)
    books = []
    for _ in range(8):
        result = feed.run(tmp_path, clock)
        assert result["status"] == "partial", result
        state, book = persisted(tmp_path)
        if book is not None and book["source_scan_id"] == state["latest_scan"]["scan_id"]:
            books.append(book)
            if len(books) == 2:
                return clock, checkpoint, state["latest_scan"], books
    pytest.fail("The scan never committed two verified gap advances")


def record_failure(root, clock, *, active_bookmark=None, candidate=False, gap_marker=None):
    with QueueStore(root / "watch.sqlite") as queue:
        store = WatchStore(queue)
        state = store.get_state(MONITOR_SCOPE)
        failed = {"control": {"transport_status": "http_error"}}
        if gap_marker is not None:
            failed["gap_recovery"] = gap_marker
        store.persist_scan(
            MONITOR_SCOPE,
            observed_at=clock.now(),
            expected_generation=state["generation"],
            scan_result=failed,
            complete=False,
            checkpoint=state["checkpoint"],
            candidates=[{"post_id": "999999"}] if candidate else [],
            gap_reason="list_transport_or_inspection_failure",
            active_bookmark=active_bookmark,
        )
    clock.wait(60)


@pytest.mark.parametrize("receipt_fault", ["missing", "digest_mismatch"])
def test_unconfirmed_new_frontier_retains_last_closed_one_through_failed_turns(
    tmp_path, advancing, receipt_fault
):
    clock, target, latest, (prior, current) = advancing
    path = tmp_path / "runs" / latest["result"]["control"]["monitor_run_id"] / "report.json"
    receipt = json.loads(path.read_bytes())
    assert receipt["gap_bookmark_digest"] == bookmark_seal(latest)
    assert current["depth"] > prior["depth"]
    if receipt_fault == "missing":
        path.rename(path.with_suffix(".interrupted"))
    else:
        receipt["gap_bookmark_digest"] = "0" * 64
        path.write_text(json.dumps(receipt), encoding="utf-8")

    for _ in range(3):
        state, book = persisted(tmp_path)
        assert state["checkpoint"] == target and book == prior
        record_failure(tmp_path, clock)
    assert persisted(tmp_path)[1] == prior


def test_stale_frontier_and_its_candidates_are_rejected_together(tmp_path, advancing):
    clock, _, latest, (prior, current) = advancing
    with pytest.raises(QueueError, match="frontier"):
        record_failure(tmp_path, clock, active_bookmark=prior, candidate=True)
    state, bookmark = persisted(tmp_path)
    assert bookmark == current and state["latest_scan"]["scan_id"] == latest["scan_id"]
    with QueueStore(tmp_path / "watch.sqlite", read_only=True) as queue:
        assert (
            queue.connection.execute(
                "SELECT 1 FROM watch_candidates WHERE post_id='999999'"
            ).fetchone()
            is None
        )


def test_failure_cannot_substitute_a_genuine_but_superseded_frontier(tmp_path, advancing):
    clock, _, _, (prior, current) = advancing
    record_failure(tmp_path, clock)
    state, verified = persisted(tmp_path)
    assert verified == current
    latest = state["latest_scan"]
    result = latest["result"]
    result["control"]["gap_bookmark_before"] = {
        "scan_id": prior["source_scan_id"],
        "generation": prior["source_generation"],
    }
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        queue.connection.execute(
            "UPDATE watch_scans SET result_json=? WHERE scan_id=?",
            (json.dumps(result), latest["scan_id"]),
        )
    assert persisted(tmp_path)[1] is None


@pytest.mark.parametrize("corruption", ["target", "url", "identity"])
def test_invalid_successor_is_rejected_before_candidate_commit(tmp_path, advancing, corruption):
    clock, _, latest, (_, current) = advancing
    marker = deepcopy(latest["result"]["gap_recovery"])
    if corruption == "target":
        marker["bookmark"]["target_ids"] = ["123"]
    elif corruption == "url":
        marker["bookmark"]["frontier"]["canonical_url"] = "https://example.test/wrong-scope"
    else:
        marker["bookmark"]["source_generation"] = 1
    with pytest.raises(QueueError, match="successor"):
        record_failure(tmp_path, clock, active_bookmark=current, candidate=True, gap_marker=marker)
    state, book = persisted(tmp_path)
    assert book == current and state["latest_scan"]["scan_id"] == latest["scan_id"]
    with QueueStore(tmp_path / "watch.sqlite", read_only=True) as queue:
        assert (
            queue.connection.execute(
                "SELECT COUNT(*) FROM watch_candidates WHERE post_id='999999'"
            ).fetchone()[0]
            == 0
        )


@pytest.mark.parametrize("fault", ["unclosed_parent", "raised_limit", "missing_transition"])
def test_early_window_replay_requires_original_transition_and_closed_budget(
    tmp_path, starting_watch, fault
):
    feed, clock, _ = starting_watch
    feed.window_size = 1
    feed.ids[:0] = range(OLD_HEAD + 50, OLD_HEAD, -1)
    assert feed.run(tmp_path, clock)["status"] == "partial"
    parent = persisted(tmp_path)[0]["latest_scan"]
    assert feed.run(tmp_path, clock)["status"] == "partial"
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        store = WatchStore(queue)
        current = store.get_state(MONITOR_SCOPE)
        assert verified_recent_plan(queue, MONITOR_SCOPE, current)
        latest = current["latest_scan"]
        result = latest["result"]
        assert result["control"]["follow_up_page_limit"] == 3
        assert result["private_observation"]["gap_seed_route"] is True
        if fault == "unclosed_parent":
            run_id = parent["result"]["control"]["monitor_run_id"]
            receipt = tmp_path / "runs" / run_id / "report.json"
            report = json.loads(receipt.read_bytes())
            report["browser_closed"] = False
            receipt.write_text(json.dumps(report), encoding="utf-8")
        else:
            if fault == "raised_limit":
                result["control"]["follow_up_page_limit"] = 4
            else:
                del result["private_observation"]["gap_seed_route"]
            queue.connection.execute(
                "UPDATE watch_scans SET result_json=? WHERE scan_id=?",
                (json.dumps(result), latest["scan_id"]),
            )
        assert verified_recent_plan(queue, MONITOR_SCOPE, store.get_state(MONITOR_SCOPE)) is None
