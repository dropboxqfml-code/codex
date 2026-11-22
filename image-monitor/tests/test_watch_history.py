"""A rolling gap can be bridged only by the current head, frontier and observed links."""

from datetime import UTC, datetime, timedelta

import pytest
from test_watch_runtime import link, snapshot

from image_monitor.watch_history import (
    HISTORICAL_ROUTE_REASONS,
    historical_next_url,
    historical_route_details,
    historical_route_reason,
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
        "observed_at": NOW.isoformat(),
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
    assert historical_route_details(
        state, latest(pages, source=result["historical_follow_up"]), source
    ) == {
        "historical_boundary_page": 4,
        "historical_status": "extended",
        "historical_reason": "boundary_extended",
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
    ("fault", "reason"),
    [
        ("missing_head", "previous_head_not_matched"),
        ("head_reordered", "recent_chain_unverified"),
        ("global_anchor_in_head", "checkpoint_in_recent_pages"),
        ("duplicate_first_link", "recent_chain_unverified"),
        ("duplicate_link", "boundary_link_ambiguous"),
        ("no_current_link", "boundary_link_missing"),
    ],
)
def test_changed_head_and_unproven_current_link_cannot_jump(state, source, fault, reason):
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
    assert historical_route_details(state, latest(pages), source) == {
        "historical_boundary_page": 4,
        "historical_status": "recent_pages_only",
        "historical_reason": reason,
    }
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
    assert (
        historical_route_reason(MONITOR_SCOPE, state, observations, NOW, source, "boundary_changed")
        == "previous_boundary_not_matched"
    )
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


@pytest.mark.parametrize(
    ("targets", "reason"),
    [
        ([], "successor_link_missing"),
        ([5, 5], "successor_link_ambiguous"),
        ([5], "route_not_observed"),
    ],
)
@pytest.mark.parametrize(
    ("boundary_rows", "status"),
    [
        ([129, 128, 127], "extended"),
        ([130, 129, 128], "boundary_changed"),
    ],
)
def test_partial_boundary_observation_does_not_claim_an_unvisited_successor(
    state, source, targets, reason, boundary_rows, status
):
    pages = [*head(), document(4, boundary_rows, *targets)]
    plan = plan_historical_scan(MONITOR_SCOPE, state, pages, NOW, source)
    marker = plan["scan_result"]["historical_follow_up"]
    assert marker["status"] == status
    assert (
        historical_route_details(state, latest(pages, source=marker), source)["historical_reason"]
        == reason
    )
    assert reason in HISTORICAL_ROUTE_REASONS[status]


def test_limited_or_inconsistent_route_evidence_yields_only_bounded_reasons(state, source):
    pages = head()
    assert historical_route_details(state, latest(pages), None) == {}
    assert (
        historical_route_details(state, latest(pages[:1]), source)["historical_reason"]
        == "insufficient_recent_pages"
    )
    assert (
        historical_route_details(state, latest(pages), source)["historical_reason"]
        == "route_not_observed"
    )
    pages[1]["counts"]["list_containers"] = 2
    assert (
        historical_route_details(state, latest(pages), source)["historical_reason"]
        == "route_evidence_unverified"
    )
    raw = latest(pages, source={"status": "https://untrusted.example"})
    with pytest.raises(WatchPlanError):
        historical_route_details(state, raw, source)
    assert (
        historical_route_reason(MONITOR_SCOPE, state, pages, NOW, source, "extended")
        == "route_evidence_unverified"
    )


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


@pytest.fixture
def rolling_source():
    return historical_source(
        latest(
            [
                document(1, [160, 158, 156, 154, 152], 2),
                document(2, [154, 152, 150, 148], 3),
                document(3, [145, 143], 4),
                document(4, [139, 137, 135], 5),
            ]
        )
    )


def overlap_pages(first, second, targets=(3, 4)):
    return [
        document(1, first, 2),
        document(2, second, *targets),
        document(4, [139, 137, 135], 5),
        document(5, [133, 132, 131], 6),
    ]


@pytest.mark.parametrize(
    ("first", "second", "join"),
    [
        ([169, 166, 164], [160, 158, 156], "clipped_prefix"),
        ([169, 168, 160], [160, 158, 156, 154], "clipped_prefix"),
        ([169, 168, 156], [154, 152, 150], "corroborated_suffix"),
        ([158, 156, 154], [154, 152, 150, 148], "corroborated_suffix"),
    ],
)
def test_confirmed_partial_head_guides_only_an_opted_in_historical_route(
    state, rolling_source, first, second, join
):
    assert rolling_source["after_head_id"] == "150"
    pages = overlap_pages(first, second)
    allow = {"allow_head_overlap": True}
    assert historical_next_url(MONITOR_SCOPE, state, pages[:2], NOW, rolling_source) is None
    with pytest.raises(WatchPlanError):
        plan_historical_scan(MONITOR_SCOPE, state, pages, NOW, rolling_source)
    for length, target in [(2, 4), (3, 5)]:
        assert (
            historical_next_url(MONITOR_SCOPE, state, pages[:length], NOW, rolling_source, **allow)
            == link(target)["canonical_url"]
        )
    plan = plan_historical_scan(MONITOR_SCOPE, state, pages, NOW, rolling_source, **allow)
    assert not plan["complete"] and plan["gap_reason"] == "anchor_not_reached"
    marker = plan["scan_result"]["historical_follow_up"]
    assert marker["status"] == "extended" and marker["head_join"] == join
    assert historical_route_details(
        state, latest(pages, source=marker), rolling_source, **allow
    ) == {
        "historical_status": "extended",
        "historical_boundary_page": 4,
        "historical_reason": "boundary_extended",
        "head_join": join,
    }
    with pytest.raises(WatchPlanError):
        historical_route_details(state, latest(pages, source=marker), rolling_source)
    for replacement in [
        None,
        "corroborated_suffix" if join == "clipped_prefix" else "clipped_prefix",
    ]:
        wrong_marker = marker.copy()
        if replacement is None:
            del wrong_marker["head_join"]
        else:
            wrong_marker["head_join"] = replacement
        with pytest.raises(WatchPlanError):
            historical_route_details(
                state, latest(pages, source=wrong_marker), rolling_source, **allow
            )


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ([190, 188], [160, 158]),  # two observed rows
        ([190, 160, 158], [156, 155]),  # previous prefix ends before fresh page two ends
        ([190, 160, 158], [157, 156]),  # new row inside common block
        ([190, 160, 158], [154, 152]),  # old row missing from inside common block
        ([190, 158], [156, 154]),  # middle of old first page only
        ([190, 156], [154, 152]),  # old second-page witness outside observed head
        ([190, 156], [154, 152, 148]),  # wrong old second-page witness
        ([190, 156], [154, 152, 151, 150]),  # later witness, with new intervening row
        ([190, 157, 156], [154, 152, 150]),  # different post inside old numeric range above suffix
        ([190, 152], [150, 148]),  # corroborating row does not count towards the three posts
        ([190, 158, 156], [158, 154, 152, 150]),  # non-edge duplicate across recent pages
    ],
)
def test_unconfirmed_partial_heads_cannot_navigate_or_contribute_older_rows(
    state, rolling_source, first, second
):
    pages = overlap_pages(first, second)
    assert (
        historical_next_url(
            MONITOR_SCOPE, state, pages[:2], NOW, rolling_source, allow_head_overlap=True
        )
        is None
    )
    with pytest.raises(WatchPlanError):
        plan_historical_scan(
            MONITOR_SCOPE, state, pages, NOW, rolling_source, allow_head_overlap=True
        )


def test_optional_corroboration_and_actual_boundary_navigation_are_independent(
    state, rolling_source
):
    allow = {"allow_head_overlap": True}
    source = rolling_source.copy()
    del source["after_head_id"]
    prefix = overlap_pages([190, 189, 188], [160, 158, 156])
    suffix = overlap_pages([190, 189, 156], [154, 152, 150])
    assert historical_next_url(MONITOR_SCOPE, state, prefix[:2], NOW, source, **allow)
    assert historical_next_url(MONITOR_SCOPE, state, suffix[:2], NOW, source, **allow) is None
    for targets, reason in [
        ((3,), "boundary_link_missing"),
        ((3, 4, 4), "boundary_link_ambiguous"),
    ]:
        pages = overlap_pages([190, 189, 188], [160, 158, 156], targets=targets)[:2]
        assert historical_next_url(MONITOR_SCOPE, state, pages, NOW, source, **allow) is None
        details = historical_route_details(state, latest(pages), source, **allow)
        assert details["historical_reason"] == reason and "head_join" not in details
    # No partial-head path can override a changed frontier.
    prefix[2] = document(4, [136, 134, 131], 5)
    assert historical_next_url(MONITOR_SCOPE, state, prefix[:3], NOW, source, **allow) is None
    changed = plan_historical_scan(MONITOR_SCOPE, state, prefix[:3], NOW, source, **allow)
    marker = changed["scan_result"]["historical_follow_up"]
    assert marker["status"] == "boundary_changed" and marker["head_join"] == "clipped_prefix"
    assert {row["page"] for row in changed["scan_result"]["observations"]} == {1, 2}
    assert changed["gap_reason"] == "historical_boundary_changed" and not changed["complete"]


def test_overlap_keeps_exact_matches_preferred_and_requires_an_adjacent_page_after_global_anchor(
    state, rolling_source
):
    full = overlap_pages([190, 160, 158], [156, 154, 152, 150])
    legacy = plan_historical_scan(MONITOR_SCOPE, state, full, NOW, rolling_source)
    assert (
        plan_historical_scan(
            MONITOR_SCOPE, state, full, NOW, rolling_source, allow_head_overlap=True
        )
        == legacy
    )
    assert "head_join" not in legacy["scan_result"]["historical_follow_up"]
    pages = overlap_pages([190, 160, 158], [156, 154])
    pages[3] = document(5, [133, 100, 99], 6)
    scan = plan_historical_scan(
        MONITOR_SCOPE, state, pages, NOW, rolling_source, allow_head_overlap=True
    )
    assert not scan["complete"] and scan["gap_reason"] == "overlap_incomplete"
    pages[3]["layout_status"] = "unverified"
    prefix = plan_historical_prefix(
        MONITOR_SCOPE, state, pages, NOW, rolling_source, allow_head_overlap=True
    )
    assert prefix["scan_result"]["verified_prefix_pages"] == 2 and not prefix["complete"]
    assert plan_historical_prefix(MONITOR_SCOPE, state, pages, NOW, rolling_source) is None
