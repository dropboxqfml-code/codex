"""Keep individually observed candidates usable without claiming historical coverage."""

import json
from datetime import timedelta

import pytest
from test_monitor_controller import NOW, AutoClock
from test_monitor_details_controller import record_detail
from test_watch_runtime import ScriptedBrowser, baseline_outcome, link, observed, snapshot

from image_monitor import candidate_runtime, watch_runtime
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.monitor_controller import MONITOR_SCOPE, MonitorController
from image_monitor.queue import QueueStore
from image_monitor.watch_store import WatchStore


@pytest.fixture(autouse=True)
def allow_fixture_backends(monkeypatch):
    monkeypatch.setattr(watch_runtime, "require_windows", lambda: None)
    monkeypatch.setattr(candidate_runtime, "require_windows", lambda: None)


partial_pages = observed(
    lambda stamp: snapshot(range(142, 122, -1), stamp, links=[link(2)]),
    lambda stamp: snapshot(range(122, 102, -1), stamp, page=2, links=[link(3)]),
)


def run_scan(root, clock, outcome, **options):
    return watch_runtime.run_watch_trial(
        root,
        clock=clock,
        backend_factory=lambda *_args, **_kwargs: ScriptedBrowser([outcome]),
        scope=MONITOR_SCOPE,
        cycles=1,
        **options,
    )


def seed_baseline(root, clock):
    baseline = run_scan(root, clock, baseline_outcome)
    assert baseline["status"] == "watch_test_completed"
    clock.advance(60)


def run_controller(root, clock, cycle, detail):
    controller = MonitorController(root, clock=clock, run_cycle=cycle, run_details=detail)
    try:
        controller.start()
        assert controller.wait_stopped(4), "The bounded scenario did not reach its endpoint"
        return controller.status()
    finally:
        controller.stop()
        assert controller.wait_stopped(4)


def test_restart_with_older_partial_scan_keeps_gap_and_can_inspect_deduplicated_candidates(
    tmp_path,
):
    clock = AutoClock()
    seed_baseline(tmp_path, clock)
    first = run_scan(tmp_path, clock, partial_pages)
    assert first["status"] == "watch_test_partial"
    assert first["reason"] == "anchor_not_reached" and first["new_candidates"] == 40
    with QueueStore(tmp_path / "watch.sqlite", read_only=True) as queue:
        before = WatchStore(queue).get_state(MONITOR_SCOPE)
        first_gap = WatchStore(queue).list_gaps(MONITOR_SCOPE)[0]

    calls = []
    deadline = NOW + timedelta(minutes=10)

    def cycle(root, _browser, **kwargs):
        calls.append(("list", clock.now()))
        assert len(calls) <= 3
        report = run_scan(root, clock, partial_pages, should_stop=kwargs["should_stop"])
        assert report["new_candidates"] == 0
        if len(calls) == 1:
            with QueueStore(root / "watch.sqlite") as queue:
                queue.defer_service("dcinside", deadline)
        return report

    def detail(root, _browser, **kwargs):
        calls.append(("detail", clock.now()))
        with QueueStore(root / "watch.sqlite", read_only=True) as queue:
            state = WatchStore(queue).get_state(MONITOR_SCOPE)
        assert kwargs["expected_scan_id"] == state["latest_scan"]["scan_id"]
        assert state["latest_scan"]["complete"] is False
        report = record_detail(root, clock)
        if len(calls) == 4:
            controller.stop()
        return report

    controller = MonitorController(tmp_path, run_cycle=cycle, run_details=detail, clock=clock)
    try:
        controller.start()
        assert controller.wait_stopped(4)
    finally:
        controller.stop()
        assert controller.wait_stopped(4)
    status = controller.status()
    assert status["phase"] == "stopped", status
    assert status["gap_reason"] == "anchor_not_reached"
    assert status["partial_cycles"] == status["auto_details_checked"] == 2
    assert status["completed_cycles"] == status["new_candidates"] == 0
    assert status["candidate_count"] == 40 and status["detail_pending_count"] == 38
    assert calls == [
        ("list", NOW + timedelta(seconds=120)),
        ("detail", deadline),
        ("list", deadline + timedelta(seconds=60)),
        ("detail", deadline + timedelta(seconds=120)),
    ]
    with QueueStore(tmp_path / "watch.sqlite", read_only=True) as queue:
        store = WatchStore(queue)
        after = store.get_state(MONITOR_SCOPE)
        assert after["checkpoint"] == before["checkpoint"]
        assert after["baseline"] == before["baseline"]
        gaps = store.list_gaps(MONITOR_SCOPE)
        assert len(gaps) == 3 and gaps[-1] == first_gap
        assert all(row["reason"] == "anchor_not_reached" for row in gaps)
        attempts = CandidateDetailStore(queue).list_details(MONITOR_SCOPE)
        assert {row["post_id"] for row in attempts} == {"103", "104"}
        assert queue.summary()["posts"] == queue.summary()["jobs"] == 0


@pytest.mark.parametrize(
    "invalid",
    [
        "incomplete_navigation",
        "missing_follow_up",
        "second_page_anchor_without_next_link",
        "missing_gap_record",
        "out_of_order",
        "wrong_generation",
        "shortened_deadline",
        "browser_cleanup",
    ],
)
def test_partial_scan_with_unproven_evidence_cannot_schedule_details(tmp_path, invalid):
    clock = AutoClock()
    seed_baseline(tmp_path, clock)
    calls = []

    def outcome(stamp):
        if invalid == "second_page_anchor_without_next_link":
            return observed(
                lambda t: snapshot([104], t, links=[link(2)]),
                lambda t: snapshot([103, 100], t, page=2, links=[]),
            )(stamp)
        result = partial_pages(stamp)
        if invalid == "incomplete_navigation":
            result["navigation"].pop()
        if invalid == "out_of_order":
            result["pages"][0]["rows"].reverse()
        return result

    def cycle(root, _browser, **kwargs):
        calls.append("list")
        assert len(calls) == 1
        report = run_scan(root, clock, outcome, should_stop=kwargs["should_stop"])
        if invalid == "wrong_generation":
            report["cycles"][0]["generation"] += 1
        if invalid == "shortened_deadline":
            report["next_eligible_at_local"] = clock.now().isoformat()
        if invalid == "browser_cleanup":
            report["browser_closed"] = False
        if invalid in {"missing_follow_up", "missing_gap_record"}:
            with QueueStore(root / "watch.sqlite") as queue:
                scan = WatchStore(queue).get_state(MONITOR_SCOPE)["latest_scan"]
                with queue.connection:
                    if invalid == "missing_follow_up":
                        scan["result"]["follow_up"] = None
                        queue.connection.execute(
                            "UPDATE watch_scans SET result_json=? WHERE scan_id=?",
                            (json.dumps(scan["result"]), scan["scan_id"]),
                        )
                    else:
                        queue.connection.execute(
                            "DELETE FROM watch_gaps WHERE scan_id=?", (scan["scan_id"],)
                        )
        return report

    def detail(*_args, **_options):
        calls.append("unexpected detail")

    status = run_controller(tmp_path, clock, cycle, detail)
    assert calls == ["list"]
    assert status["phase"] == "needs_review"
    if invalid == "second_page_anchor_without_next_link":
        assert status["gap_reason"] == "pagination_missing"
    assert status["auto_details_checked"] == status["partial_cycles"] == 0
    with QueueStore(tmp_path / "watch.sqlite", read_only=True) as queue:
        assert WatchStore(queue).get_state(MONITOR_SCOPE)["checkpoint"]["anchor_ids"] == [
            "100",
            "99",
        ]
        assert CandidateDetailStore(queue).list_details(MONITOR_SCOPE) == []


def test_replaced_gap_during_handoff_cannot_enter_candidate_browser(tmp_path):
    clock = AutoClock()
    seed_baseline(tmp_path, clock)
    calls = []

    def cycle(root, _browser, **kwargs):
        calls.append("list")
        assert len(calls) == 1
        return run_scan(root, clock, partial_pages, should_stop=kwargs["should_stop"])

    def refuse_browser(*_args, **_options):
        calls.append("unexpected browser")
        raise RuntimeError("Candidate browser opened after scan identity changed")

    def detail(root, browser, **options):
        calls.append("detail handoff")
        replacement = run_scan(root, clock, partial_pages)
        assert replacement["status"] == "watch_test_partial"
        # A different, equally well-formed generation now owns the latest observation.
        # Advance beyond its fresh cooldown to isolate the identity check inside the lease.
        clock.advance(60)
        return candidate_runtime.run_candidate_trial(
            root, browser, backend_factory=refuse_browser, **options
        )

    status = run_controller(tmp_path, clock, cycle, detail)
    assert calls == ["list", "detail handoff"]
    assert status["phase"] == "needs_review"
    assert status["auto_details_checked"] == 0
    with QueueStore(tmp_path / "watch.sqlite", read_only=True) as queue:
        assert CandidateDetailStore(queue).list_details(MONITOR_SCOPE) == []
        assert len(WatchStore(queue).list_gaps(MONITOR_SCOPE)) == 2
