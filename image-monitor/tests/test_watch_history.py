"""A rolling gap can be bridged only by the current head, frontier and observed links."""

from datetime import UTC, datetime, timedelta

import pytest
from test_watch_runtime import link, snapshot

from image_monitor.watch_history import (
    historical_next_url,
    historical_source,
    plan_historical_prefix,
    plan_historical_scan,
)
from image_monitor.watch_planner import WatchPlanError, plan_scan
from image_monitor.watch_store import MONITOR_SCOPE

START = datetime(2026, 5, 3, tzinfo=UTC)
NOW = START + timedelta(hours=1)
SOURCE_ID = "a" * 32


def document(number, ids, *targets):
    return snapshot(
        ids,
        NOW,
        page=number,
        links=[link(index) for index in targets],
        counts={"list_containers": 1},
    )


@pytest.fixture
def state():
    base = plan_scan(
        MONITOR_SCOPE,
        {"generation": 0, "baseline": None, "checkpoint": None},
        [snapshot([100, 99], START)],
        START,
        allow_verified_live=True,
    )
    return {"generation": 3, "baseline": base["baseline"], "checkpoint": base["checkpoint"]}


def latest(pages, *, source=None):
    result = {
        "control": {"follow_up_page_limit": 4},
        "private_observation": {"pages": pages},
    }
    if source:
        result["historical_follow_up"] = source
    return {
        "scan_id": SOURCE_ID,
        "complete": False,
        "gap_reason": "anchor_not_reached",
        "result": result,
    }


@pytest.fixture
def source():
    receipt = latest(
        [
            document(1, [144, 143, 142], 2),
            document(2, [141, 140], 3),
            document(3, [135, 131], 4),
            document(4, [129, 128, 127], 5),
        ]
    )
    return historical_source(receipt)


def head():
    return [document(1, [146, 145, 144], 2), document(2, [143, 142, 141], 3, 4)]


def test_old_seed_requires_strictly_connected_adjacent_row_windows():
    pages = [
        document(1, [145, 144, 143], 2),
        document(2, [144, 143, 142], 3),
        document(3, [143, 142, 141], 4),
        document(4, [141, 140, 139], 5),
    ]
    assert historical_source(latest(pages)) is not None
    pages[2] = document(3, [144, 142, 141], 4)
    assert historical_source(latest(pages)) is None


def test_ordered_boundaries_may_shift_onto_next_fresh_page_and_old_rows_are_not_replayed(
    state, source
):
    pages = [*head(), document(4, [130, 129, 128], 5), document(5, [127, 126, 100], 6)]
    assert (
        historical_next_url(MONITOR_SCOPE, state, pages[:2], NOW, source)
        == link(4)["canonical_url"]
    )
    assert (
        historical_next_url(MONITOR_SCOPE, state, pages[:3], NOW, source)
        == link(5)["canonical_url"]
    )
    plan = plan_historical_scan(MONITOR_SCOPE, state, pages, NOW, source)
    result = plan["scan_result"]
    assert plan["complete"] is False and plan["gap_reason"] == "overlap_incomplete"
    assert [p["page"] for p in result["pages"]] == [1, 2, 4, 5]
    assert [c["post_id"] for c in plan["candidates"]] == [
        "146",
        "145",
        "144",
        "143",
        "142",
        "141",
        "130",
        "129",
        "128",
        "127",
        "126",
    ]
    assert result["first_anchor_id"] == "100"
    assert result["historical_follow_up"] == {
        "source_scan_id": SOURCE_ID,
        "boundary_page": 4,
        "status": "extended",
    }
    next_source = historical_source(latest(pages, source=result["historical_follow_up"]))
    assert next_source["boundary_page"] == 5 and next_source["head_ids"] == ["146", "145", "144"]
    next_pages = [
        document(1, [147, 146, 145], 2),
        document(2, [144, 143, 142], 5),
        document(5, [127, 126, 100], 6),
        document(6, [99, 98, 97], 7),
    ]
    done = plan_historical_scan(MONITOR_SCOPE, state, next_pages, NOW, next_source)
    assert done["complete"] and done["checkpoint"]["anchor_ids"] == ["147", "146", "145"]
    assert "99" not in [c["post_id"] for c in done["candidates"]]


@pytest.mark.parametrize(
    "fault",
    [
        "missing_head",
        "head_reordered",
        "global_anchor_in_head",
        "duplicate_first_link",
        "duplicate_link",
        "no_current_link",
    ],
)
def test_changed_head_and_unproven_current_link_cannot_jump(state, source, fault):
    pages = head()
    if fault == "missing_head":
        pages[1] = document(2, [143, 141], 3, 4)
    elif fault == "head_reordered":
        pages[1] = document(2, [142, 143, 141], 3, 4)
    elif fault == "global_anchor_in_head":
        pages[1] = document(2, [143, 142, 100], 3, 4)
    elif fault == "duplicate_first_link":
        pages[0]["pagination_candidates"].append(link(2))
    elif fault == "duplicate_link":
        pages[1]["pagination_candidates"].append(link(4))
    else:
        pages[1] = document(2, [143, 142, 141], 3)
    assert historical_next_url(MONITOR_SCOPE, state, pages, NOW, source) is None
    with pytest.raises(WatchPlanError):
        plan_historical_scan(
            MONITOR_SCOPE, state, [*pages, document(4, [129, 128, 127], 5)], NOW, source
        )


@pytest.mark.parametrize(
    "documents",
    [
        [document(4, [130, 128, 127], 5)],
        [document(4, [130, 129, 128], 5), document(5, [126, 100], 6)],
        [document(4, [131, 130, 129], 5), document(5, [129, 100], 6)],
    ],
)
def test_changed_frontier_retains_only_current_head_candidates(state, source, documents):
    observations = head() + documents
    plan = plan_historical_scan(MONITOR_SCOPE, state, observations, NOW, source)
    assert plan["gap_reason"] == "historical_boundary_changed" and not plan["complete"]
    assert plan["scan_result"]["historical_follow_up"]["status"] == "boundary_changed"
    assert [p["page"] for p in plan["scan_result"]["pages"]] == [p["page"] for p in observations]
    assert {item["post_id"] for item in plan["candidates"]} == {
        "146",
        "145",
        "144",
        "143",
        "142",
        "141",
    }
    assert {row["page"] for row in plan["scan_result"]["observations"]} == {1, 2}
    assert (
        historical_source(latest(observations, source=plan["scan_result"]["historical_follow_up"]))
        is None
    )


def test_frontier_may_not_authorize_guessed_page_or_exceed_ceiling(state, source):
    pages = [*head(), document(4, [129, 128, 127], 6)]
    assert historical_next_url(MONITOR_SCOPE, state, pages, NOW, source) is None
    with pytest.raises(WatchPlanError):
        plan_historical_scan(
            MONITOR_SCOPE, state, [*pages, document(5, [126, 100], 6)], NOW, source
        )
    end = latest(
        [*head(), document(9, [110, 109], 10), document(10, [108, 107], 11)],
        source={"status": "extended", "boundary_page": 9},
    )
    assert historical_source(end) is None


@pytest.mark.parametrize("length", [3, 4])
def test_unverified_document_keeps_only_the_fresh_verified_head(state, source, length):
    pages = [*head(), document(4, [130, 129, 128], 5), document(5, [127, 126, 100], 6)][:length]
    pages[-1]["layout_status"] = "unverified"
    result = plan_historical_prefix(MONITOR_SCOPE, state, pages, NOW, source)
    assert result["complete"] is False and result["checkpoint"] == state["checkpoint"]
    assert result["gap_reason"] == "list_profile_unverified_or_incomplete"
    assert result["scan_result"]["verified_prefix_pages"] == 2
    assert {item["page"] for item in result["scan_result"]["observations"]} == {1, 2}
    assert [page["page"] for page in result["scan_result"]["pages"]] == [1, 2]

    pages[-1]["url"] = link(9)["canonical_url"]
    assert plan_historical_prefix(MONITOR_SCOPE, state, pages, NOW, source) is None
