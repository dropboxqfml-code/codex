"""Keep an unattended list-only catch-up bounded by actual verified recovery progress."""

from datetime import timedelta

import pytest
from test_monitor_auto_session import scan
from test_monitor_long_gap import starting_watch as starting_watch

from image_monitor.monitor_auto_session import run_auto_monitor
from image_monitor.monitor_settings import MAX_CATCH_UP_SCANS, save_monitor_settings


def recovery(status, depth, *, pages=None, candidates=0):
    recent = status in {"segment_queued", "head_rejoined", "held"}
    pages = pages or ([1, 2, 3, 4] if recent else [1, 2, 4, 5])
    return scan("complete" if status == "completed" else "partial", candidates=candidates) | {
        "page_limit": 4,
        "pages_checked": len(pages),
        "visited_page_numbers": pages,
        "recovery_route": "recent" if recent else "bookmark",
        "recovery_depth": depth,
        "recovery_crossed_search_range": False,
        "recovery_status": status,
    }


def waiting(reason, seconds, closed=True):
    def wait(clock):
        return scan(
            "waiting",
            reason=reason,
            closed=closed,
            due=(clock.now() + timedelta(seconds=seconds)).isoformat(),
        ) | ({"review": {"stage": "watch_result"}} if reason == "inspection_retry_due" else {})

    return wait


def run_catch_up(path, clock, turns, *, stop=None):
    calls = []
    start = clock.now()
    turns = iter(turns)

    def check(*roots, **options):
        assert roots == (path,) and options["clock"] is clock
        calls.append((clock.now() - start).total_seconds())
        turn = next(turns, None)
        assert turn is not None, "The session issued an additional list check"
        return turn(clock) if callable(turn) else turn

    def collect(*args, **kwargs):
        pytest.fail("List catch-up started collection")

    report = run_auto_monitor(
        path,
        None,
        None,
        max_cycles=MAX_CATCH_UP_SCANS,
        list_only=True,
        clock=clock,
        should_stop=stop,
        scan_runner=check,
        collect_runner=collect,
    )
    return report, calls


def test_catch_up_keeps_eight_verified_checks_at_the_saved_interval(tmp_path, starting_watch):
    _, clock, _ = starting_watch
    save_monitor_settings(tmp_path, 300)
    turns = [recovery("segment_queued", 4, candidates=28)]
    turns.extend(recovery("advanced", depth, candidates=int(depth == 5)) for depth in range(5, 12))
    report, times = run_catch_up(tmp_path, clock, turns)
    assert times == list(range(0, 8 * 300, 300))
    assert (
        report["status"] == "auto_monitor_completed" and report["reason"] == "cycle_limit_reached"
    )
    assert report["list_checks"] == report["cycles_completed"] == report["partial_list_checks"] == 8
    assert report["new_candidates"] == 29
    assert [c["new_candidates"] for c in report["recent_list_checks"]] == [28, 1, 0, 0, 0, 0, 0, 0]
    assert [c["recovery_depth"] for c in report["recent_list_checks"]] == list(range(4, 12))
    assert (
        report["new_details_checked"]
        == report["native_save_tasks_started"]
        == report["files_verified"]
        == 0
    )


def test_rejoined_segment_can_reset_depth_and_cross_a_search_window(tmp_path, starting_watch):
    _, clock, _ = starting_watch
    crossing = recovery("advanced", 14, pages=[1, 2, 10, 1]) | {
        "recovery_crossed_search_range": True,
        "search_window_start_visits": [4],
    }
    turns = [
        recovery("advanced", 12),
        recovery("head_rejoined", 12),
        recovery("advanced", 13),
        crossing,
        recovery("segment_rejoined", 5),
        recovery("overlap_pending", 6),
        recovery("completed", 7),
    ]
    report, times = run_catch_up(tmp_path, clock, turns)
    assert times == list(range(0, 7 * 60, 60))
    assert report["reason"] == "list_coverage_confirmed" and report["cycles_completed"] == 7
    assert report["recent_list_checks"][3]["visited_page_numbers"] == [1, 2, 10, 1]
    assert report["last_list"]["status"] == "complete"


@pytest.mark.parametrize(
    "turns,reason",
    [
        (
            [recovery("head_rejoined", 9), recovery("segment_queued", 4)],
            "recovery_progress_stalled",
        ),
        (
            [recovery("segment_queued", 4), recovery("head_rejoined", 4)],
            "recovery_progress_stalled",
        ),
        ([recovery("advanced", 9), recovery("advanced", 9)], "recovery_progress_stalled"),
        ([recovery("advanced", 9), recovery("overlap_pending", 8)], "recovery_progress_stalled"),
        ([recovery("overlap_pending", 9, pages=[1, 2, 4])], "recovery_followup_deferred"),
        ([recovery("head_rejoined", 9, pages=[1, 2, 3])], "recovery_followup_deferred"),
        ([recovery("successor_unconfirmed", 9)], "recovery_followup_deferred"),
        ([recovery("frontier_changed", 9)], "recovery_followup_deferred"),
        ([recovery("held", 9)], "recovery_followup_deferred"),
        ([scan("partial", reason="anchor_not_reached")], "recovery_followup_deferred"),
    ],
)
def test_no_more_browser_turns_on_stalled_or_unconfirmed_routes(
    tmp_path, starting_watch, turns, reason
):
    _, clock, _ = starting_watch
    report, times = run_catch_up(tmp_path, clock, turns)
    assert times == list(range(0, len(turns) * 60, 60))
    assert report["status"] == "auto_monitor_completed" and report["reason"] == reason
    assert report["list_checks"] == len(turns)


def test_cooldown_costs_no_attempt_but_a_document_timeout_uses_one(tmp_path, starting_watch):
    _, clock, _ = starting_watch
    turns = [
        waiting("persisted_cooldown", 10, closed=None),
        recovery("advanced", 5),
        waiting("inspection_retry_due", 60),
        *[recovery("advanced", n) for n in range(6, 12)],
    ]
    report, times = run_catch_up(tmp_path, clock, turns)
    assert times == [0, *range(10, 10 + 8 * 60, 60)]
    assert report["reason"] == "cycle_limit_reached"
    assert report["list_checks"] == len(report["recent_list_checks"]) == 7
    assert report["inspection_retries_scheduled"] == 1
    assert report["last_inspection_retry"] == {"stage": "watch_result"}


def test_timeout_on_eighth_actual_attempt_does_not_launch_ninth(tmp_path, starting_watch):
    _, clock, _ = starting_watch
    turns = [recovery("advanced", n) for n in range(5, 12)] + [waiting("inspection_retry_due", 60)]
    report, times = run_catch_up(tmp_path, clock, turns)
    assert times == list(range(0, 8 * 60, 60))
    assert (report["status"], report["reason"]) == ("auto_monitor_waiting", "inspection_retry_due")
    assert report["next_eligible_at"] == (clock.now() + timedelta(seconds=60)).isoformat(
        timespec="microseconds"
    )
    assert report["list_checks"] == 7 and report["inspection_retries_scheduled"] == 0
    assert report["last_list"]["review"] == {"stage": "watch_result"}


@pytest.mark.parametrize(
    "turns,status,reason",
    [
        (
            [waiting("inspection_retry_due", 60), waiting("inspection_retry_due", 60)],
            "review",
            "list_scan_requires_review",
        ),
        ([waiting("service_wait", 180)], "waiting", "service_wait"),
        ([waiting("persisted_cooldown", 61, closed=None)], "waiting", "persisted_cooldown"),
        (
            [scan("blocked", reason="access_block_requires_review")],
            "blocked",
            "access_block_requires_review",
        ),
        ([scan("busy", reason="another_worker_active")], "busy", "another_worker_active"),
        (
            [scan("review", reason="list_scan_requires_review")],
            "review",
            "list_scan_requires_review",
        ),
        ([scan("complete", closed=False)], "review", "owned_browser_cleanup_unconfirmed"),
    ],
)
def test_catch_up_ends_on_review_or_long_wait(tmp_path, starting_watch, turns, status, reason):
    _, clock, _ = starting_watch
    report, times = run_catch_up(tmp_path, clock, turns)
    assert len(times) == len(turns)
    assert (report["status"], report["reason"]) == (f"auto_monitor_{status}", reason)


def test_stop_during_catch_up_wait_preserves_one_verified_turn(tmp_path, starting_watch):
    _, clock, _ = starting_watch
    start = clock.now()
    report, times = run_catch_up(
        tmp_path,
        clock,
        [recovery("advanced", 5)],
        stop=lambda: clock.now() >= start + timedelta(seconds=1),
    )
    assert times == [0] and (report["status"], report["reason"]) == (
        "auto_monitor_stopped",
        "requested_stop",
    )
    assert report["cycles_completed"] == 1 and len(report["recent_list_checks"]) == 1


def test_catch_up_follows_verified_relocated_frontier_once_the_saved_interval_elapses(
    tmp_path, starting_watch
):
    _, clock, _ = starting_watch
    # The moved frontier is an intermediate position even when no new candidates were needed.
    shifted = recovery("frontier_relocated", 6, pages=[1, 2, 5, 6]) | {
        "recovery_reason": "frontier_prefix_overlap",
        "candidate_eligible_visits": 4,
    }
    report, times = run_catch_up(
        tmp_path,
        clock,
        [
            shifted,
            recovery("advanced", 7, pages=[1, 2, 6, 7]),
            recovery("completed", 8, pages=[1, 2, 7, 8]),
        ],
    )
    assert times == [0, 60, 120] and report["reason"] == "list_coverage_confirmed"
    assert report["recent_list_checks"][0]["status"] == "partial"
    assert report["recent_list_checks"][0]["candidate_eligible_visits"] == 4
    assert report["new_candidates"] == report["files_verified"] == 0
    assert report["gap_followups_completed"] == 1
