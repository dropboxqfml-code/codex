"""The continuous monitor and offline diagnosis show physical and logical page positions."""

import io
from copy import deepcopy

import pytest

from image_monitor.auto_monitor_cli import _describe_list_check, _describe_result, _show_progress
from image_monitor.monitor_auto_session import _record_list_pages
from image_monitor.monitor_gap_report import (
    RECOVERY_MESSAGES,
    RECOVERY_REASON_MESSAGES,
    checked_gap_route,
    gap_route_details,
)
from image_monitor.watch_diagnosis import diagnose_list_scan, public_list_diagnosis
from image_monitor.watch_gap_recovery import GAP_RECOVERY_REASONS, GAP_STATUSES


def test_private_recovery_receipts_have_bounded_public_progress_across_a_search_range():
    numbers = [1, 2, 55, 1]
    record = {
        "complete": False,
        "control": {"follow_up_page_limit": 4},
        "private_observation": {
            "pages": [
                {"page": n, "url": "private", "search_pos": "private" if i == 3 else None}
                for i, n in enumerate(numbers)
            ]
        },
        "gap_recovery": {
            "route": "bookmark",
            "status": "advanced",
            "depth": 56,
            "crossed_search_range": True,
            "bookmark": {"url": "private", "head_ids": ["private"]},
        },
    }
    turn = {
        "status": "partial",
        "page_limit": 4,
        "visited_page_numbers": numbers,
        "pages_checked": 4,
        **gap_route_details(record),
    }
    report = {
        "phase": "scanning",
        "cycles_completed": 1,
        "posts_saved": 0,
        "files_verified": 0,
        "last_list": {"status": "partial"},
        "recent_list_checks": [],
        "gap_followup_checks": 0,
        "gap_followups_completed": 0,
    }
    _record_list_pages(report, turn)
    assert report["last_list"]["visited_page_numbers"] == numbers
    assert report["last_list"]["recovery_depth"] == 56
    assert report["recent_list_checks"] == [report["last_list"]]
    assert "private" not in repr(report)
    assert "다음 쪽" in _describe_list_check(report["last_list"])["recovery_status_ko"]
    stream = io.StringIO()
    _show_progress(report, stream)
    assert "복구 위치 56쪽 · 다음 검색 구간 진입" in stream.getvalue()
    assert set(RECOVERY_MESSAGES) == GAP_STATUSES
    assert {
        status: set(reasons) for status, reasons in RECOVERY_REASON_MESSAGES.items()
    } == GAP_RECOVERY_REASONS
    bad = turn | {"recovery_status": "completed"}
    with pytest.raises(ValueError):
        _record_list_pages(report, bad)


def test_old_report_shape_cannot_authorize_deep_pages_and_diagnosis_never_relabels_the_range():
    latest = {
        "complete": False,
        "gap_reason": "list_profile_unverified_or_incomplete",
        "result": {
            "control": {"follow_up_page_limit": 4},
            "private_observation": {
                "pages": [{"page": n} for n in (1, 2, 36, 1)],
                "recovery_page_numbers": [1, 2, 36, 1],
            },
        },
    }
    result = diagnose_list_scan(latest)
    assert [page["page"] for page in result["pages"]] == [1, 2, 36, 1]
    assert result == public_list_diagnosis(result)
    altered = deepcopy(result)
    altered["pages"][2]["page"] = 37
    assert public_list_diagnosis(altered)["pages"][2]["page"] is None
    bad = {
        "page_limit": 4,
        "pages_checked": 4,
        "visited_page_numbers": [1, 2, 36, 1],
        "status": "partial",
    }
    with pytest.raises(ValueError):
        _record_list_pages({"last_list": {}}, bad)


@pytest.mark.parametrize(
    ("numbers", "starts"),
    [([1, 1], [2]), ([1, 1, 2], [2]), ([1, 2, 1, 1], [3, 4])],
)
def test_normal_session_can_display_resets_in_the_first_search_windows(numbers, starts):
    turn = {
        "status": "partial",
        "page_limit": len(numbers),
        "pages_checked": len(numbers),
        "visited_page_numbers": numbers,
        "search_window_start_visits": starts,
    }
    report = {
        "last_list": {"status": "partial"},
        "recent_list_checks": [],
        "gap_followup_checks": 0,
        "gap_followups_completed": 0,
    }
    _record_list_pages(report, turn)
    assert report["last_list"]["search_window_start_visits"] == starts
    assert report["last_list"]["visited_page_numbers"] == numbers
    with pytest.raises(ValueError):
        _record_list_pages(report, turn | {"search_window_start_visits": []})


def recent_record(status, numbers, **marker_fields):
    return {
        "complete": False,
        "control": {"follow_up_page_limit": 4},
        "private_observation": {"pages": [{"page": n, "search_pos": None} for n in numbers]},
        "gap_recovery": {
            "route": "recent",
            "status": status,
            "depth": 4,
            "crossed_search_range": False,
            "bookmark": {"PRIVATE_ID": "PRIVATE_URL"},
            **marker_fields,
        },
    }


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (status, reason)
        for status, reasons in RECOVERY_REASON_MESSAGES.items()
        for reason in reasons
    ],
)
def test_recent_recovery_reason_is_bound_to_its_route_and_survives_report_boundaries(status, code):
    numbers = [1, 2, 3] if code == "recent_page_limit" else [1, 2, 3, 4]
    record = recent_record(status, numbers, recovery_reason=code, raw_message="PRIVATE")
    turn = {
        "status": "partial",
        "page_limit": 4,
        "pages_checked": len(numbers),
        "visited_page_numbers": numbers,
        **gap_route_details(record),
    }
    report = {
        "phase": "scanning",
        "cycles_completed": 1,
        "posts_saved": 0,
        "files_verified": 0,
        "last_list": {"status": "partial"},
        "recent_list_checks": [],
        "previous_list_checks": [turn],
        "gap_followup_checks": 0,
        "gap_followups_completed": 0,
    }
    _record_list_pages(report, turn)
    assert report["last_list"]["recovery_reason"] == code
    public = _describe_result(report)
    phrase = RECOVERY_REASON_MESSAGES[status][code]
    for check in (
        public["last_list"],
        *public["previous_list_checks"],
        *public["recent_list_checks"],
    ):
        assert check["recovery_reason_ko"] == phrase
    assert "PRIVATE" not in repr(public)
    stream = io.StringIO()
    _show_progress(report, stream)
    assert phrase in stream.getvalue()


@pytest.mark.parametrize(
    ("status", "numbers", "code", "route"),
    [
        ("held", [1, 2, 3, 4], "recent_tail_overlap", "recent"),
        ("segment_queued", [1, 2, 3, 4], "deferred_limit", "recent"),
        ("held", [1, 2, 3], "recent_chain_unverified", "recent"),
        ("held", [1, 2, 3, 4], "recent_page_limit", "recent"),
        ("held", [1, 2, 4, 5], "recent_overlap_unconfirmed", "bookmark"),
        ("held", [1, 2, 3, 4], "PRIVATE", "recent"),
        ("held", [1, 2, 3, 4], ["PRIVATE"], "recent"),
    ],
)
def test_mismatched_or_arbitrary_recovery_explanations_cannot_survive_projection(
    status, numbers, code, route
):
    turn = {
        "status": "partial",
        "page_limit": 4,
        "visited_page_numbers": numbers,
        "recovery_status": status,
        "recovery_route": route,
        "recovery_depth": 4,
        "recovery_crossed_search_range": False,
        "recovery_reason": code,
        "recovery_reason_ko": "PRIVATE",
    }
    with pytest.raises(ValueError):
        checked_gap_route(turn, numbers, 4)
    public = _describe_list_check(turn)
    assert "recovery_reason" not in public and "recovery_reason_ko" not in public
    assert "PRIVATE" not in repr(public)


def test_original_held_marker_does_not_imply_a_specific_reason():
    numbers = [1, 2, 3, 4]
    turn = {
        "status": "partial",
        "page_limit": 4,
        "pages_checked": 4,
        "visited_page_numbers": numbers,
        **gap_route_details(recent_record("held", numbers)),
    }
    assert "recovery_reason" not in turn
    described = _describe_list_check(turn)
    assert (
        "recovery_reason_ko" not in described
        and "세부 보류 사유가 없습니다" in described["recovery_status_ko"]
    )
