"""The continuous monitor and offline diagnosis show physical and logical page positions."""

import io
import json
from copy import deepcopy

import pytest
from test_monitor_long_gap import starting_watch as starting_watch  # noqa: PLC0414

from image_monitor.auto_monitor_cli import _describe_list_check, _describe_result, _show_progress
from image_monitor.monitor_auto_session import _record_list_pages
from image_monitor.monitor_gap_report import (
    RECOVERY_MESSAGES,
    RECOVERY_OBSERVATION_MESSAGES,
    RECOVERY_REASON_MESSAGES,
    checked_gap_route,
    gap_route_details,
)
from image_monitor.monitor_list_history import previous_list_checks
from image_monitor.queue import QueueStore
from image_monitor.watch_diagnosis import diagnose_list_scan, public_list_diagnosis
from image_monitor.watch_gap_recovery import GAP_RECOVERY_REASONS, GAP_STATUSES
from image_monitor.watch_store import MONITOR_SCOPE, WatchStore


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
def test_recovery_reason_is_bound_to_its_route_and_survives_report_boundaries(status, code):
    numbers = [1, 2, 3] if code == "recent_page_limit" else [1, 2, 3, 4]
    if status == "frontier_relocated":
        numbers = [1, 2, 5, 6]
    route = "bookmark" if status == "frontier_relocated" else "recent"
    record = recent_record(
        status,
        numbers,
        route=route,
        recovery_reason=code,
        eligible_pages=len(numbers),
        raw_message="PRIVATE",
    )
    if status == "frontier_relocated":
        record["control"]["historical_route_schema"] = 5
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


def test_disjoint_segment_checked_from_live_and_reopened_unchanged_receipt(
    tmp_path, starting_watch
):
    feed, clock, _ = starting_watch
    feed.ids[:0] = range(1150, 1000, -1)
    for _ in range(3):
        assert feed.run(tmp_path, clock)["status"] == "partial"
    # Every ordinary post on the next four pages is newer than the previous head.
    feed.ids[:0] = range(1260, 1150, -1)
    turn = feed.run(tmp_path, clock)
    assert turn["recovery_status"] == "segment_queued"
    assert turn["recovery_observation"] == "disjoint_recent_rows" and "recovery_reason" not in turn
    files = {f: (f.read_bytes(), f.stat().st_mtime_ns) for f in tmp_path.rglob("*") if f.is_file()}
    previous = previous_list_checks(tmp_path)[-1]
    assert previous["recovery_observation"] == turn["recovery_observation"]
    assert (
        _describe_list_check(previous)["recovery_observation_ko"]
        == RECOVERY_OBSERVATION_MESSAGES["disjoint_recent_rows"]
    )
    assert files == {
        f: (f.read_bytes(), f.stat().st_mtime_ns) for f in tmp_path.rglob("*") if f.is_file()
    }
    with QueueStore(tmp_path / "watch.sqlite", read_only=True) as queue:
        record = WatchStore(queue).get_state(MONITOR_SCOPE)["latest_scan"]["result"]
    assert "recovery_observation" not in record["gap_recovery"]
    assert "recovery_reason" not in record["gap_recovery"]
    assert "1260" not in repr(_describe_list_check(turn))
    for damage in (
        "same_floor",
        "missing_prior",
        "different_cursor",
        "middle_order",
        "missing_rows",
    ):
        altered = deepcopy(record)
        bookmark = altered["gap_recovery"]["bookmark"]
        pages = altered["private_observation"]["pages"]
        if damage == "same_floor":
            bookmark["deferred"][0]["head_ids"] = [pages[-1]["rows"][-1]["post_id"]]
        elif damage == "missing_prior":
            del bookmark["deferred"]
        elif damage == "different_cursor":
            bookmark["frontier"]["canonical_url"] += "PRIVATE"
        elif damage == "middle_order":
            pages[1]["rows"].reverse()
        else:
            altered["pages"][2]["rows_complete"] = False
        details = gap_route_details(altered)
        assert details["recovery_status"] == "segment_queued"
        assert "recovery_observation" not in details

    # Even a structurally plausible replacement is outside the original sealed receipt.
    record["gap_recovery"]["bookmark"]["deferred"][0]["head_ids"] = ["1149", "1148"]
    with QueueStore(tmp_path / "watch.sqlite") as queue:
        scan = WatchStore(queue).get_state(MONITOR_SCOPE)["latest_scan"]
        queue.connection.execute(
            "UPDATE watch_scans SET result_json=? WHERE scan_id=?",
            (json.dumps(record), scan["scan_id"]),
        )
    assert all(
        check.get("recovery_status") != "segment_queued" for check in previous_list_checks(tmp_path)
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "complete"},
        {"recovery_reason": "recent_tail_overlap"},
        {"recovery_route": "bookmark"},
        {"visited_page_numbers": [1, 2, 3]},
        {"recovery_depth": 5},
        {"recovery_status": "held"},
        {"recovery_observation": "PRIVATE"},
    ],
)
def test_unverified_or_conflicting_observation_is_not_displayed(changes):
    turn = {
        "status": "partial",
        "page_limit": 4,
        "visited_page_numbers": [1, 2, 3, 4],
        "recovery_route": "recent",
        "recovery_status": "segment_queued",
        "recovery_depth": 4,
        "recovery_crossed_search_range": False,
        "recovery_observation": "disjoint_recent_rows",
        "recovery_observation_ko": "PRIVATE",
    } | changes
    public = _describe_list_check(turn)
    assert "recovery_observation" not in public and "recovery_observation_ko" not in public
    assert "PRIVATE" not in repr(public)
    marker = recent_record(
        "segment_queued", [1, 2, 3, 4], recovery_observation="disjoint_recent_rows"
    )
    assert "recovery_observation" not in gap_route_details(marker)


def saved_frontier_sample():
    numbers = [1, 2, 5, 6]
    record = recent_record("frontier_changed", numbers, route="bookmark", eligible_pages=2)
    ref = {"scan_id": "a" * 32, "generation": 5}
    record["control"].update(historical_route_schema=4, gap_bookmark_before=ref)
    record["pages"] = []
    pages = record["private_observation"]["pages"]
    for page, ids in zip(pages, ([120, 119], [118, 117], [112, 111], [110, 109, 108]), strict=True):
        url = f"PRIVATE-URL-{page['page']}"
        page.update(url=url, rows=[{"post_id": str(i)} for i in ids])
        record["pages"].append(
            {"canonical_url": url, "page": page["page"], "search_pos": None, "rows_complete": True}
        )
    prior = {
        "source_scan_id": ref["scan_id"],
        "source_generation": ref["generation"],
        "frontier": {"canonical_url": pages[2]["url"], "page": 5, "search_pos": None},
        "frontier_ids": ["109", "108", "107", "106"],
    }
    return record, prior, numbers


@pytest.mark.parametrize(
    ("ids", "matched", "shape"),
    [
        (["109", "108", "107", "106"], 2, "prefix_at_end"),
        (["114", "111", "108", "101"], 2, "other"),
        (["98", "97", "96"], 0, "none"),
    ],
)
def test_recorded_hold_can_report_physical_overlap_without_altering_its_status(ids, matched, shape):
    record, prior, numbers = saved_frontier_sample()
    prior["frontier_ids"] = ids
    original = deepcopy(record)
    details = gap_route_details(record, prior_bookmark=prior)
    expected = {"previous_rows": len(ids), "matched_rows": matched, "shape": shape}
    assert details["frontier_overlap"] == expected and record == original
    assert details["recovery_status"] == "frontier_changed"
    assert "recovery_reason" not in details and "frontier_overlap" not in gap_route_details(record)
    check = _describe_list_check(
        {"status": "partial", "visited_page_numbers": numbers, "page_limit": 4, **details}
    )
    assert check["frontier_overlap"] == expected
    assert f"{len(ids)}개 중 {matched}개" in check["frontier_overlap_ko"]
    assert ("첫머리" in check["frontier_overlap_ko"]) == (shape == "prefix_at_end")
    assert "PRIVATE" not in repr(check) and prior["source_scan_id"] not in repr(check)


@pytest.mark.parametrize(
    "damaged",
    [
        "other_generation",
        "another_source",
        "unproven_page",
        "another_cursor",
        "contradictory_check",
        "broken_order",
        "not_four_visits",
    ],
)
def test_missing_or_inconsistent_frontier_evidence_keeps_original_hold_generic(damaged):
    record, prior, _ = saved_frontier_sample()
    if damaged == "other_generation":
        prior["source_generation"] -= 1
    elif damaged == "another_source":
        prior["source_scan_id"] = "b" * 32
    elif damaged == "unproven_page":
        record["pages"][-1]["rows_complete"] = False
    elif damaged == "another_cursor":
        prior["frontier"]["search_pos"] = "PRIVATE"
    elif damaged == "contradictory_check":
        record["pages"][2]["canonical_url"] = "PRIVATE"
    elif damaged == "broken_order":
        record["private_observation"]["pages"][3]["rows"].reverse()
    else:
        record["private_observation"]["pages"].pop()
        record["pages"].pop()
    details = gap_route_details(record, prior_bookmark=prior)
    assert details["recovery_status"] == "frontier_changed" and "frontier_overlap" not in details


@pytest.mark.parametrize(
    "changes",
    [
        {"matched_rows": True},
        {"matched_rows": 5},
        {"previous_rows": 201},
        {"shape": "PRIVATE"},
        {"shape": "none"},
        {"matched_rows": 4},
        {"shape": []},
    ],
)
def test_contradictory_frontier_counts_and_untrusted_text_never_render(changes):
    record, prior, numbers = saved_frontier_sample()
    details = gap_route_details(record, prior_bookmark=prior)
    details["frontier_overlap"].update(changes)
    check = _describe_list_check(
        {
            "status": "partial",
            "visited_page_numbers": numbers,
            "page_limit": 4,
            **details,
            "frontier_overlap_ko": "PRIVATE",
        }
    )
    assert "frontier_overlap" not in check and "PRIVATE" not in repr(check)


@pytest.mark.parametrize("schema", [None, True, 4, 5.0, "5"])
def test_unconfirmed_schema_cannot_label_an_old_frontier_as_relocated(schema):
    record, prior, _ = saved_frontier_sample()
    record["control"]["historical_route_schema"] = schema
    record["gap_recovery"].update(
        status="frontier_relocated", recovery_reason="frontier_prefix_overlap", eligible_pages=4
    )
    with pytest.raises(ValueError):
        gap_route_details(record, prior_bookmark=prior)
