"""The persisted four-page source must still support a jump when its result is committed."""

import json
from pathlib import Path

import pytest
from test_watch_runtime import BrowserFactory, FakeClock, baseline_outcome, link, observed, snapshot

from image_monitor import watch_runtime
from image_monitor.queue import QueueStore
from image_monitor.watch_store import MONITOR_SCOPE, WatchStore


def listing(page_numbers, ids):
    def page(stamp, number, post_id):
        links = [link(number + 1)]
        if number == 2:
            links.extend([link(4), link(5), link(6), link(7), link(8), link(9)])
        return snapshot(
            post_id if isinstance(post_id, list) else [post_id],
            stamp,
            page=number,
            links=links,
            counts={"list_containers": 1},
        )

    return observed(
        *[
            lambda stamp, n=n, post=post: page(stamp, n, post)
            for n, post in zip(page_numbers, ids, strict=True)
        ]
    )


@pytest.fixture
def history(tmp_path, monkeypatch):
    monkeypatch.setattr(watch_runtime, "require_windows", lambda: None)
    clock = FakeClock()

    def run(outcome):
        report = watch_runtime.run_watch_trial(
            tmp_path,
            scope=MONITOR_SCOPE,
            cycles=1,
            clock=clock,
            backend_factory=BrowserFactory(outcome),
            follow_up_gaps=True,
        )
        clock.wait(60)
        return report

    assert run(baseline_outcome)["status"] == "watch_test_completed"
    for depth in (2, 3, 4):
        seed = run(listing(range(1, depth + 1), (130, 120, 115, 110)[:depth]))
        assert seed["recent_pages_verified"] is True
    return run, Path(seed["report_path"])


def test_parent_receipt_changed_during_navigation_cannot_advance_the_checkpoint(tmp_path, history):
    run, receipt = history
    initial = json.loads(receipt.read_bytes())
    # The old global anchor appears at the bottom of the fifth page. One more
    # adjacent page would normally finish this scope on the next scan.
    assert run(listing([1, 2, 4, 5], [130, 120, 110, 100]))["reason"] == "overlap_incomplete"

    def during_scan(stamp):
        receipt.write_text(json.dumps(initial | {"browser_closed": False}))
        return listing([1, 2, 5, 6], [130, 120, 100, 98])(stamp)

    result = run(during_scan)
    assert result["status"] == "watch_test_partial"
    assert result["reason"] == "historical_source_unverified"
    assert "closed_monitor_scan" not in result
    with QueueStore(tmp_path / "watch.sqlite", read_only=True) as queue:
        state = WatchStore(queue).get_state(MONITOR_SCOPE)
        assert state["checkpoint"]["anchor_ids"] == ["100", "99"]
        assert state["latest_scan"]["complete"] is False


@pytest.mark.parametrize("fault", ["closed_marker", "candidate_identity"])
def test_reopen_replays_parent_evidence_before_allowing_next_boundary(tmp_path, history, fault):
    run, receipt = history
    result = run(listing([1, 2, 4, 5], [130, 120, 110, 108]))
    assert result["cycles"][0]["visited_page_numbers"] == [1, 2, 4, 5]
    database = tmp_path / "watch.sqlite"
    with QueueStore(database) as queue:
        state = WatchStore(queue).get_state(MONITOR_SCOPE)
        assert watch_runtime.monitor_scan_policy(database, queue, state)[1]["boundary_page"] == 5
        if fault == "closed_marker":
            record = json.loads(receipt.read_bytes())
            del record["closed_monitor_scan"]
            receipt.write_text(json.dumps(record))
        else:
            # Page 3 did not appear in the new scan. Swapping its identity keeps
            # the count unchanged but breaks the historical coverage evidence.
            queue.connection.execute(
                "UPDATE watch_candidates SET post_id='114' WHERE post_id='115'"
            )
        assert watch_runtime.verified_recent_plan(queue, MONITOR_SCOPE, state) is None
        assert watch_runtime.monitor_scan_policy(database, queue, state) == (2, None)


def test_finishing_page_ten_keeps_partial_coverage_without_authorizing_page_eleven(
    tmp_path, history
):
    run, _ = history
    for boundary in range(4, 10):
        page_numbers = [1, 2, boundary, boundary + 1]
        result = run(listing(page_numbers, [130, 120, 114 - boundary, 113 - boundary]))
        assert result["recent_pages_verified"] and result["cycles"][0]["page_count"] == 4
        assert result["cycles"][0]["visited_page_numbers"] == page_numbers
    database = tmp_path / "watch.sqlite"
    with QueueStore(database, read_only=True) as queue:
        state = WatchStore(queue).get_state(MONITOR_SCOPE)
        assert state["checkpoint"]["anchor_ids"] == ["100", "99"]
        assert watch_runtime.monitor_scan_policy(database, queue, state) == (4, None)


@pytest.fixture
def clipped_run(tmp_path, history):
    run, _ = history
    run(listing([1, 2, 3, 4], [[150, 149, 148, 147, 146], [145, 144, 143], 129, 110]))
    database = tmp_path / "watch.sqlite"
    with QueueStore(database) as queue:
        # The alpha.10 receipt had the strict policy in the final report only.
        # Rebuild those original shapes so the new rule starts on the next run.
        for previous in WatchStore(queue).list_scans(MONITOR_SCOPE):
            record = previous["result"]
            control = record["control"]
            del control["historical_route_schema"]
            receipt_path = tmp_path / "runs" / control["monitor_run_id"] / "report.json"
            receipt = json.loads(receipt_path.read_bytes())
            receipt.update(program_version="0.5.0-alpha.10", historical_route_schema=1)
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            queue.connection.execute(
                "UPDATE watch_scans SET result_json=? WHERE scan_id=?",
                (json.dumps(record), previous["scan_id"]),
            )
    result = run(listing([1, 2, 4, 5], [[170, 168, 166], [150, 149, 148], 110, 108]))
    assert result["recent_pages_verified"] is True
    assert result["cycles"][0]["head_join"] == "clipped_prefix"
    assert result["historical_route_schema"] == watch_runtime.HEAD_OVERLAP_SCHEMA
    return run, Path(result["report_path"])


@pytest.mark.parametrize(
    "fault",
    ["report_schema", "db_schema", "downgrade", "report_join", "db_join", "proof"],
)
def test_current_and_child_scan_reject_changed_overlap_proof(tmp_path, clipped_run, fault):
    run, receipt_path = clipped_run
    database = tmp_path / "watch.sqlite"
    with QueueStore(database) as queue:
        parent = WatchStore(queue).get_state(MONITOR_SCOPE)
        assert watch_runtime.verified_recent_plan(queue, MONITOR_SCOPE, parent) is not None
    child_report = run(listing([1, 2, 5, 6], [[170, 168, 166], [150, 149, 148], 108, 106]))
    assert child_report["recent_pages_verified"] is True
    latest = parent["latest_scan"]
    record = latest["result"]
    receipt = json.loads(receipt_path.read_bytes())
    if fault == "report_schema":
        del receipt["historical_route_schema"]
    elif fault == "db_schema":
        record["control"]["historical_route_schema"] = True
    elif fault == "downgrade":
        del record["control"]["historical_route_schema"]
        receipt.update(program_version="0.5.0-alpha.10", historical_route_schema=1)
        del record["historical_follow_up"]["head_join"]
        del receipt["cycles"][0]["head_join"]
    elif fault == "report_join":
        del receipt["cycles"][0]["head_join"]
    elif fault == "db_join":
        record["historical_follow_up"]["head_join"] = "corroborated_suffix"
    else:
        rows = record["private_observation"]["pages"][1]["rows"]
        rows[-1]["post_id"] = "147"
        rows[-1]["canonical_url"] = rows[-1]["canonical_url"].replace("no=148", "no=147")
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    with QueueStore(database) as queue:
        queue.connection.execute(
            "UPDATE watch_scans SET result_json=? WHERE scan_id=?",
            (json.dumps(record), latest["scan_id"]),
        )
        child = WatchStore(queue).get_state(MONITOR_SCOPE)
        assert watch_runtime.verified_recent_plan(queue, MONITOR_SCOPE, parent) is None
        assert watch_runtime.verified_recent_plan(queue, MONITOR_SCOPE, child) is None
        assert watch_runtime.monitor_scan_policy(database, queue, child) == (2, None)


@pytest.mark.parametrize("last_page", [4, 5])
def test_unverified_historical_layout_keeps_only_the_verified_recent_rows(
    tmp_path, history, last_page
):
    run, _ = history

    def during_scan(stamp):
        route = [1, 2, 4, 5] if last_page == 5 else [1, 2, 4]
        result = listing(route, [135, 130, 110, 105][: len(route)])(stamp)
        result["historical_boundary_page"] = 4
        result["pages"][-1]["layout_status"] = "unverified"
        return result

    result = run(during_scan)
    assert result["reason"] == "list_profile_unverified_or_incomplete"
    assert result["new_candidates"] == 1
    assert "closed_monitor_scan" not in result
    with QueueStore(tmp_path / "watch.sqlite", read_only=True) as queue:
        store = WatchStore(queue)
        state = store.get_state(MONITOR_SCOPE)
        assert state["checkpoint"]["anchor_ids"] == ["100", "99"]
        assert state["latest_scan"]["result"]["verified_prefix_pages"] == 2
        posts = {row["post_id"]: row for row in store.list_candidates(MONITOR_SCOPE)}
        latest = state["latest_scan"]["scan_id"]
        assert {key for key in posts if posts[key]["latest_scan_id"] == latest} == {"135", "130"}


@pytest.mark.parametrize(
    "version,receipt_schema,control_schema,accepted",
    [
        ("0.5.0-alpha.12", 3, 3, 3),
        ("0.5.0-alpha.15", 3, 3, 3),
        ("0.5.0-alpha.15", 4, 4, None),
        ("0.5.0-alpha.16", 4, 4, 4),
        ("0.5.0-alpha.16", 3, 4, None),
        ("0.5.0-alpha.16", 4, 3, None),
        ("0.5.0-alpha.16", 4, 4.0, None),
        ("0.5.0-alpha.16", 5, 5, None),
        ("0.6.0", 3, 3, 3),
        ("0.6.0", 4, 4, 4),
        ("0.6.0", 5, 5, None),
    ],
)
def test_bookmarked_route_version_requires_compatible_matching_capability(
    version, receipt_schema, control_schema, accepted
):
    assert (
        watch_runtime.historical_route_policy(
            {"program_version": version, "historical_route_schema": receipt_schema},
            {"historical_route_schema": control_schema},
        )
        == accepted
    )


@pytest.mark.parametrize("fault", ["missing_bookmark", "new_reason_on_old_schema"])
def test_partial_overlap_claim_requires_its_bookmark_and_schema(tmp_path, monkeypatch, fault):
    from test_watch_runtime import BrowserFactory, FakeClock, baseline_outcome

    from image_monitor.monitor_gap_store import bookmark_seal

    monkeypatch.setattr(watch_runtime, "require_windows", lambda: None)
    report = watch_runtime.run_watch_trial(
        tmp_path,
        "chrome",
        cycles=1,
        clock=FakeClock(),
        backend_factory=BrowserFactory(baseline_outcome),
        scope=MONITOR_SCOPE,
        follow_up_gaps=True,
        recover_long_gaps=True,
    )
    database = tmp_path / "watch.sqlite"
    with QueueStore(database) as queue:
        scan = WatchStore(queue).get_state(MONITOR_SCOPE)["latest_scan"]
    assert watch_runtime.confirmed_monitor_scan(database, scan)
    receipt = Path(report["report_path"])
    public = json.loads(receipt.read_bytes())
    if fault == "missing_bookmark":
        public.update(program_version="0.5.0-alpha.16", historical_route_schema=4)
    else:
        public.update(program_version="0.5.0-alpha.15", historical_route_schema=3)
        scan["result"]["gap_recovery"] = {"recovery_reason": "recent_page_limit"}
    scan["result"]["control"]["historical_route_schema"] = public["historical_route_schema"]
    if fault == "new_reason_on_old_schema":
        public["gap_bookmark_digest"] = bookmark_seal(scan)
    receipt.write_text(json.dumps(public), encoding="utf-8")
    assert not watch_runtime.confirmed_monitor_scan(database, scan)
