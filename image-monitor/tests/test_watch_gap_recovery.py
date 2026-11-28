"""Durable gap routes navigate only stored exact documents or observed successors."""

from copy import deepcopy

import pytest
from test_watch_history import NOW, START, document
from test_watch_runtime import snapshot

from image_monitor.list_links import build_list_url
from image_monitor.watch_gap_recovery import (
    gap_next_url,
    new_gap_bookmark,
    plan_gap_fallback,
    plan_gap_scan,
    plan_gap_seed,
    plan_gap_seed_route,
    seed_next_url,
    valid_gap_bookmark,
)
from image_monitor.watch_planner import WatchPlanError, plan_scan
from image_monitor.watch_store import MONITOR_SCOPE as SCOPE


def cursor(page, window=None):
    return {
        "page": page,
        "search_pos": window,
        "canonical_url": build_list_url("normal", "comic_new6", "ai", page, window),
    }


def page(number, ids, *, window=None, links=()):
    url = cursor(number, window)
    return snapshot(
        ids,
        NOW,
        page=number,
        links=links,
        url=url["canonical_url"],
        search_pos=window,
        counts={"list_containers": 1},
    )


def ordinary(rows, count=4, *, size=5):
    return [document(i, rows[(i - 1) * size : i * size], i + 1) for i in range(1, count + 1)]


@pytest.fixture
def state():
    seed = plan_scan(
        SCOPE,
        {"generation": 0, "baseline": None, "checkpoint": None},
        [snapshot([101, 100], START)],
        START,
        allow_verified_live=True,
    )
    return {"generation": 4, "baseline": seed["baseline"], "checkpoint": seed["checkpoint"]}


def start(state, rows):
    p = ordinary(rows)
    bookmark = new_gap_bookmark(SCOPE, state, p, NOW)
    assert valid_gap_bookmark(SCOPE, state, bookmark)
    return bookmark


def run(state, rows, b):
    current = b["frontier"]["page"]
    p = ordinary(rows, 2)
    assert gap_next_url(SCOPE, state, p, NOW, b) == cursor(current)["canonical_url"]
    p.append(document(current, rows[(current - 1) * 5 : current * 5], current + 1))
    assert gap_next_url(SCOPE, state, p, NOW, b) == cursor(current + 1)["canonical_url"]
    p.append(document(current + 1, rows[current * 5 : (current + 1) * 5], current + 2))
    result = plan_gap_scan(SCOPE, state, p, NOW, b)
    return result, result["scan_result"]["gap_recovery"]


@pytest.mark.parametrize("old_distance", [30, 60])
def test_long_outage_with_growing_head_reads_the_entire_candidate_set_once_in_union(
    state, old_distance
):
    rows = list(range(5 * old_distance + 101, 69, -1))
    b = start(state, rows)
    found = set(rows[:20])
    for i in range(3 * old_distance):
        if i % 2 == 0:
            rows.insert(0, rows[0] + 1)
        plan, mark = run(state, rows, b)
        found.update(int(row["post_id"]) for row in plan["candidates"])
        assert mark["eligible_pages"] == 4 and mark["route"] == "bookmark"
        if plan["complete"]:
            assert mark["status"] == "completed"
            break
        b = mark["bookmark"]
        assert valid_gap_bookmark(SCOPE, state, b)
    else:
        pytest.fail("The frontier never reached the checkpoint")
    assert found == {r for r in rows if r > 101}
    assert mark["depth"] > old_distance


def test_second_disjoint_outage_rejoins_without_returning_to_stale_page_ordinal(state):
    rows = list(range(190, 69, -1))
    b = start(state, rows)
    for _ in range(4):
        _, mark = run(state, rows, b)
        b = mark["bookmark"]
    assert b["depth"] == 8
    rows = list(range(340, 190, -1)) + rows
    p = ordinary(rows)
    assert gap_next_url(SCOPE, state, p[:2], NOW, b) is None
    recent = plan_scan(SCOPE, state, p, NOW, allow_verified_live=True)
    m = plan_gap_fallback(SCOPE, state, p, NOW, b, recent)["scan_result"]["gap_recovery"]
    assert m["status"] == "segment_queued" and m["bookmark"]["deferred"][0]["depth"] == 8
    b = m["bookmark"]
    seen_rejoin = False
    for _ in range(65):
        plan, m = run(state, rows, b)
        if m["status"] == "segment_rejoined":
            assert m["bookmark"]["depth"] > 30 and m["bookmark"]["deferred"] == []
            seen_rejoin = True
        if plan["complete"]:
            break
        b = m["bookmark"]
    else:
        pytest.fail("Jumped back into a stale page ordinal after the second outage")
    assert seen_rejoin and m["status"] == "completed"


def recent_fallback(state, pages, bookmark, *, allow_partial_overlap, allow_recent_recovery=False):
    recent = plan_scan(SCOPE, state, pages, NOW, allow_verified_live=True)
    return plan_gap_fallback(
        SCOPE,
        state,
        pages,
        NOW,
        bookmark,
        recent,
        allow_partial_overlap=allow_partial_overlap,
        allow_recent_recovery=allow_recent_recovery,
    )["scan_result"]["gap_recovery"]


@pytest.fixture
def shifting_head(state):
    old = list(range(600, 101, -2)) + [101, 100, *range(99, 60, -1)]
    active = new_gap_bookmark(SCOPE, state, ordinary(old, size=20), NOW)
    earlier = new_gap_bookmark(SCOPE, state, ordinary(old[80:], size=20), NOW)
    earlier.pop("target_ids")
    active["deferred"] = [earlier]
    return old, active


@pytest.mark.parametrize(
    ("removed", "old_status"), [(set(), "head_rejoined"), ({600, 588}, "held")]
)
def test_clipped_tail_after_69_arrivals_reopens_only_the_newly_checked_frontier(
    state, shifting_head, removed, old_status
):
    old, active = shifting_head
    fresh = [*range(800, 731, -1), *(post_id for post_id in old if post_id not in removed)]
    docs = ordinary(fresh, 6, size=20)
    legacy = recent_fallback(state, docs[:4], active, allow_partial_overlap=False)
    assert legacy["status"] == old_status and "recovery_reason" not in legacy
    if legacy["bookmark"]:
        stale = plan_gap_scan(
            SCOPE, state, [docs[0], docs[1], docs[3], docs[4]], NOW, legacy["bookmark"]
        )
        assert stale["scan_result"]["gap_recovery"]["status"] == "frontier_changed"
    new = recent_fallback(state, docs[:4], active, allow_partial_overlap=True)
    assert (new["status"], new["recovery_reason"]) == ("segment_queued", "recent_tail_overlap")
    next_book = new["bookmark"]
    assert next_book["target_ids"] == active["target_ids"]
    assert next_book["frontier_ids"] == [str(i) for i in fresh[60:80]]
    assert next_book["deferred"][0]["frontier_ids"] == active["frontier_ids"]
    assert next_book["deferred"][1:] == active["deferred"]
    for offset, expected in ((3, "segment_rejoined"), (4, "advanced")):
        pages = [*docs[:2], docs[offset], docs[offset + 1]]
        for n in (2, 3):
            assert gap_next_url(SCOPE, state, pages[:n], NOW, next_book) == pages[n]["url"]
        following = plan_gap_scan(SCOPE, state, pages, NOW, next_book)
        assert not following["complete"]
        marker = following["scan_result"]["gap_recovery"]
        assert marker["status"] == expected
        next_book = marker["bookmark"]
        assert next_book["deferred"] == active["deferred"]


@pytest.mark.parametrize("arrivals", [40, 60])
def test_full_head_on_page_three_or_four_can_relocate_a_directly_observed_stale_frontier(
    state, shifting_head, arrivals
):
    old, active = shifting_head
    fresh = [*range(800, 800 - arrivals, -1), *old]
    docs = ordinary(fresh, 5, size=20)
    old_result = recent_fallback(state, docs[:4], active, allow_partial_overlap=False)
    assert old_result["status"] == "head_rejoined"
    later = [docs[0], docs[1], docs[3], docs[4]]
    for _ in range(2):
        legacy = plan_gap_scan(SCOPE, state, later, NOW, old_result["bookmark"])
        marker = legacy["scan_result"]["gap_recovery"]
        assert marker["status"] == "frontier_changed" and marker["bookmark"] is None
    new = recent_fallback(state, docs[:4], active, allow_partial_overlap=True)
    assert (new["status"], new["recovery_reason"]) == ("segment_queued", "observed_frontier_shift")
    assert new["bookmark"]["frontier_ids"] == [str(i) for i in fresh[60:80]]
    assert new["bookmark"]["deferred"][0]["frontier_ids"] == active["frontier_ids"]
    assert new["bookmark"]["deferred"][1:] == active["deferred"]
    next_plan = plan_gap_scan(SCOPE, state, later, NOW, new["bookmark"])
    assert not next_plan["complete"] and next_plan["scan_result"]["gap_recovery"]["depth"] == 5


@pytest.mark.parametrize(
    "case", ["head_on_second_page", "unobserved_frontier", "frontier_still_matches"]
)
def test_full_head_keeps_prior_route_unless_its_deep_shift_is_fully_observed(
    state, shifting_head, case
):
    old, active = shifting_head
    arrivals = 20 if case == "head_on_second_page" else 40
    fresh = [*range(800, 800 - arrivals, -1), *old]
    pages = ordinary(fresh, size=20)
    if case == "unobserved_frontier":
        active.update(frontier=cursor(8), frontier_ids=list(map(str, old[140:160])), depth=8)
    elif case == "frontier_still_matches":
        # The previously checked fourth URL contains its original ordered window.
        pages[3] = document(4, list(map(int, active["frontier_ids"])), 5)
    legacy = recent_fallback(state, pages, active, allow_partial_overlap=False)
    assert legacy["status"] == "head_rejoined"
    assert recent_fallback(state, pages, active, allow_partial_overlap=True) == legacy


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ("third_missing", "recent_overlap_unconfirmed"),
        ("interleaved", "recent_overlap_unconfirmed"),
        ("unmatched_before", "recent_overlap_unconfirmed"),
        ("too_few", "recent_overlap_unconfirmed"),
        ("unlinked", "recent_chain_unverified"),
        ("deferred_full", "deferred_limit"),
        ("reordered", "recent_plan_unconfirmed"),
    ],
)
def test_unproven_tail_does_not_replace_the_active_or_deferred_bookmarks(
    state, shifting_head, change, reason
):
    old, active = shifting_head
    removed = {600, 588}
    if change == "third_missing":
        removed.add(586)
    count = 78 if change == "too_few" else 69
    fresh = [*range(800, 800 - count, -1), *(n for n in old if n not in removed)]
    if change == "interleaved":
        fresh.insert(fresh.index(590), 591)
    elif change == "unmatched_before":
        fresh.insert(fresh.index(598), 599)  # Still older than the missing old first ID, 600.
    elif change == "reordered":
        fresh[70], fresh[71] = fresh[71], fresh[70]
    elif change == "deferred_full":
        active["deferred"] *= 8
    pages = ordinary(fresh, size=20)
    if change == "unlinked":
        pages[2]["pagination_candidates"] *= 2
    before = deepcopy(active)
    marker = recent_fallback(state, pages, active, allow_partial_overlap=True)
    assert (marker["status"], marker["recovery_reason"]) == ("held", reason)
    assert marker["bookmark"] is None and active == before
    if reason != "recent_overlap_unconfirmed":
        assert (
            recent_fallback(
                state, pages, active, allow_partial_overlap=True, allow_recent_recovery=True
            )
            == marker
        )


def test_clipped_overlap_across_ranges_keeps_the_exact_observed_cursor(state, shifting_head):
    old, active = shifting_head
    fresh = [*range(800, 731, -1), *(n for n in old if n not in {600, 588})]
    window = "-4097"
    crossing = cursor(1, window) | {"label_kind": "next_search"}
    docs = [
        page(1, fresh[:20], links=[cursor(2)]),
        page(2, fresh[20:40], links=[crossing]),
        page(1, fresh[40:60], window=window, links=[cursor(2, window)]),
        page(2, fresh[60:80], window=window, links=[cursor(3, window)]),
    ]
    recent = plan_gap_seed_route(SCOPE, state, docs, NOW)
    result = plan_gap_fallback(
        SCOPE, state, docs, NOW, active, deepcopy(recent), allow_partial_overlap=True
    )
    marker = result["scan_result"]["gap_recovery"]
    assert marker["recovery_reason"] == "recent_tail_overlap"
    assert marker["bookmark"]["depth"] == 4 and marker["bookmark"]["frontier"] == cursor(2, window)
    docs[1]["pagination_candidates"].append(cursor(1, "-5099") | {"label_kind": "next_search"})
    ambiguous = plan_gap_fallback(
        SCOPE, state, docs, NOW, active, deepcopy(recent), allow_partial_overlap=True
    )["scan_result"]["gap_recovery"]
    assert (
        ambiguous["recovery_reason"] == "recent_chain_unverified" and ambiguous["bookmark"] is None
    )
    docs[3]["scope"] = docs[3]["scope"] | {"keyword": "different"}
    with pytest.raises(WatchPlanError):
        plan_gap_fallback(SCOPE, state, docs, NOW, active, recent, allow_partial_overlap=True)


def test_foreign_or_ambiguous_range_link_and_range_cycles_do_not_advance(state):
    rows = list(range(190, 69, -1))
    b = start(state, rows)
    head = ordinary(rows, 2)
    first_old = cursor(1, "-4523")
    next_search = first_old | {"label_kind": "next_search"}

    def observed(*links):
        return [*head, page(4, rows[15:20], links=links)]

    for raw_link in (
        first_old,
        next_search | {"label_kind": "next"},
        cursor(2, "-4523") | {"label_kind": "next_search"},
    ):
        p = observed(raw_link)
        assert gap_next_url(SCOPE, state, p, NOW, b) is None
        plan = plan_gap_scan(SCOPE, state, p, NOW, b)
        assert plan["gap_reason"] == "gap_successor_unconfirmed" and not plan["complete"]
    assert gap_next_url(SCOPE, state, observed(next_search, next_search), NOW, b) is None
    p = observed(next_search)
    assert gap_next_url(SCOPE, state, p, NOW, b) == first_old["canonical_url"]
    with pytest.raises(WatchPlanError):
        plan_gap_scan(SCOPE, state, [*p, page(1, rows[20:25], window="-105")], NOW, b)
    plan = plan_gap_scan(
        SCOPE, state, [*p, page(1, rows[20:25], window="-4523", links=[cursor(2, "-4523")])], NOW, b
    )
    m = plan["scan_result"]["gap_recovery"]
    assert m["crossed_search_range"] and m["bookmark"]["depth"] == 5
    assert valid_gap_bookmark(SCOPE, state, m["bookmark"])
    cross_back = cursor(1, "-4523") | {"label_kind": "next_search"}
    p = [*head, page(1, rows[20:25], window="-4523", links=[cross_back])]
    assert gap_next_url(SCOPE, state, p, NOW, m["bookmark"]) is None
    p = ordinary(rows)
    p[-1] = observed(next_search)[-1]
    plan = plan_scan(SCOPE, state, p, NOW, allow_verified_live=True)
    assert plan["gap_reason"] == "historical_cursor_unverified"
    assert plan_gap_seed(SCOPE, state, p, NOW, plan)["gap_reason"] == "anchor_not_reached"


def test_two_removed_frontier_rows_require_three_survivors_and_physical_checkpoint_overlap(state):
    rows = list(range(120, 69, -1))
    b = start(state, rows)
    rows.remove(104)
    rows.remove(102)
    plan, m = run(state, rows, b)
    assert m["status"] == "completed" and plan["scan_result"]["first_anchor_id"] == "101"
    rows = list(range(127, 69, -1))
    b = start(state, rows)
    rows.remove(101)
    _, m = run(state, rows, b)
    plan, m = run(state, rows, m["bookmark"])
    assert not plan["complete"] and m["status"] == "overlap_pending"
    plan, m = run(state, rows, m["bookmark"])
    assert plan["complete"] and plan["scan_result"]["first_anchor_id"] == "100"
    rows.remove(100)
    no_witness = start(state, rows)
    for _ in range(4):
        plan, m = run(state, rows, no_witness)
        assert not plan["complete"]
        no_witness = m["bookmark"]


def test_replaced_frontier_never_registers_its_unproven_older_candidates(state):
    rows = list(range(190, 69, -1))
    b = start(state, rows)
    pages = [*ordinary(rows, 2), document(4, [167, 165, 163, 161, 159], 5)]
    result = plan_gap_scan(SCOPE, state, pages, NOW, b)
    assert not result["complete"]
    assert result["scan_result"]["gap_recovery"]["eligible_pages"] == 2
    assert set(int(row["post_id"]) for row in result["candidates"]) == set(rows[:10])
    corrupt = deepcopy(b)
    corrupt["target_ids"] = ["105"]
    assert not valid_gap_bookmark(SCOPE, state, corrupt)
    corrupt = deepcopy(b)
    corrupt["frontier"]["canonical_url"] = cursor(8)["canonical_url"]
    assert not valid_gap_bookmark(SCOPE, state, corrupt)


@pytest.fixture
def fifth_page_frontier(state, shifting_head):
    old, active = shifting_head
    docs = ordinary(old, 5, size=20)
    result = plan_gap_scan(SCOPE, state, [*docs[:2], *docs[3:]], NOW, active)
    bookmark = result["scan_result"]["gap_recovery"]["bookmark"]
    assert bookmark["depth"] == 5 and bookmark["deferred"] == active["deferred"]
    return old, bookmark


@pytest.mark.parametrize("removed_offsets", [(), (0, 7)])
def test_clipped_fifth_frontier_after_26_new_posts_resumes_without_skipping_its_remainder(
    state, fifth_page_frontier, removed_offsets
):
    old, bookmark = fifth_page_frontier
    removed = {old[80 + offset] for offset in removed_offsets}
    fresh = [*range(800, 774, -1), *(i for i in old if i not in removed)]
    docs = ordinary(fresh, 7, size=20)
    route = [*docs[:2], *docs[4:6]]
    legacy = plan_gap_scan(SCOPE, state, route, NOW, bookmark)["scan_result"]["gap_recovery"]
    assert (legacy["status"], legacy["eligible_pages"]) == ("frontier_changed", 2)
    before = deepcopy(bookmark)
    plan = plan_gap_scan(SCOPE, state, route, NOW, bookmark, allow_frontier_overlap=True)
    marker = plan["scan_result"]["gap_recovery"]
    assert not plan["complete"] and plan["gap_reason"] == "anchor_not_reached"
    assert (marker["status"], marker["recovery_reason"]) == (
        "frontier_relocated",
        "frontier_prefix_overlap",
    )
    assert (marker["depth"], marker["eligible_pages"], marker["crossed_search_range"]) == (
        6,
        4,
        False,
    )
    moved = marker["bookmark"]
    assert moved["frontier"] == cursor(6) and moved["frontier_ids"] == list(
        map(str, fresh[100:120])
    )
    assert moved["target_ids"] == before["target_ids"] and moved["deferred"] == before["deferred"]
    assert bookmark == before and valid_gap_bookmark(SCOPE, state, moved)
    next_route = [*docs[:2], *docs[5:7]]
    assert gap_next_url(SCOPE, state, next_route[:3], NOW, moved) == docs[6]["url"]
    next_plan = plan_gap_scan(SCOPE, state, next_route, NOW, moved, allow_frontier_overlap=True)
    assert next_plan["scan_result"]["gap_recovery"]["depth"] == 7
    observed = {r["post_id"] for p in [plan, next_plan] for r in p["scan_result"]["observations"]}
    assert set(bookmark["frontier_ids"]) - set(map(str, removed)) <= observed


@pytest.mark.parametrize(
    "fault",
    [
        "absent",
        "two_matches",
        "three_missing",
        "intrusion",
        "reordered",
        "unknown_before",
        "unknown_floor",
        "no_onward",
        "duplicate_onward",
        "other_range",
    ],
)
def test_ambiguous_or_unlinked_fourth_page_cannot_relocate_an_old_frontier(
    state, fifth_page_frontier, fault
):
    old, bookmark = fifth_page_frontier
    fresh = [*range(800, 774, -1), *old]
    if fault == "three_missing":
        for offset in (0, 3, 8):
            fresh.remove(old[80 + offset])
    ids = fresh[100:120]
    if fault == "absent":
        ids = ids[:6]
    elif fault == "two_matches":
        ids = ids[:8]
    elif fault == "intrusion":
        ids[9] += 1
    elif fault == "reordered":
        ids[9], ids[10] = ids[10], ids[9]
    elif fault == "unknown_before":
        ids[6] -= 1
    elif fault == "unknown_floor":
        ids[-1] += 1
    recent = ordinary(fresh, 5, size=20)
    route = [*recent[:2], recent[4], page(6, ids, links=[cursor(7)])]
    if fault == "no_onward":
        route[-1]["pagination_candidates"] = []
    elif fault == "duplicate_onward":
        route[-1]["pagination_candidates"] *= 2
    elif fault == "other_range":
        other = "-923"
        route[2]["pagination_candidates"] = [cursor(1, other) | {"label_kind": "next_search"}]
        route[3] = page(1, ids, window=other, links=[cursor(2, other)])
    current = plan_gap_scan(SCOPE, state, route, NOW, bookmark, allow_frontier_overlap=True)
    marker = current["scan_result"]["gap_recovery"]
    assert not current["complete"] and current["gap_reason"] == "historical_boundary_changed"
    assert (marker["status"], marker["depth"], marker["eligible_pages"]) == (
        "frontier_changed",
        5,
        2,
    )
    assert marker["bookmark"] is None and "recovery_reason" not in marker
    assert {r["post_id"] for r in current["candidates"]} == set(map(str, fresh[:40]))


def test_partial_frontier_proof_cannot_complete_or_use_a_foreign_scope(state, fifth_page_frontier):
    old, bookmark = fifth_page_frontier
    fresh = [*range(800, 774, -1), *old]
    docs = ordinary(fresh, 6, size=20)
    route = [*docs[:2], *docs[4:]]
    # A checkpoint on the first history page plus its adjacent visit would
    # formally complete the inner plan. A partial frontier proof cannot do so.
    target = [str(fresh[81])]
    current_state = state | {"checkpoint": state["checkpoint"] | {"anchor_ids": target}}
    active = bookmark | {"target_ids": target}
    plan = plan_gap_scan(SCOPE, current_state, route, NOW, active, allow_frontier_overlap=True)
    assert not plan["complete"] and plan["scan_result"]["gap_recovery"]["bookmark"] is None
    route[-1]["scope"] = route[-1]["scope"] | {"keyword": "different"}
    with pytest.raises(WatchPlanError):
        plan_gap_scan(SCOPE, state, route, NOW, bookmark, allow_frontier_overlap=True)


def test_checkpoint_seen_at_relocated_frontier_requires_a_later_physical_overlap(
    state, shifting_head
):
    old, _ = shifting_head
    target = [str(old[80])]
    state = state | {"checkpoint": state["checkpoint"] | {"anchor_ids": target}}
    docs = ordinary(old, 5, size=20)
    initial = new_gap_bookmark(SCOPE, state, docs[:4], NOW)
    first = plan_gap_scan(SCOPE, state, [*docs[:2], *docs[3:5]], NOW, initial)
    previous = first["scan_result"]["gap_recovery"]
    assert previous["status"] == "overlap_pending"
    # A retained segment's head happens to coincide with the relocated page 5.
    # It must remain open through the provisional move.
    deferred = new_gap_bookmark(SCOPE, state, ordinary(old[54:], size=20), NOW)
    deferred.pop("target_ids")
    bookmark = previous["bookmark"] | {"deferred": [deferred]}
    fresh = ordinary([*range(800, 774, -1), *old], 7, size=20)
    route = [*fresh[:2], *fresh[4:6]]
    current = plan_gap_scan(SCOPE, state, route, NOW, bookmark, allow_frontier_overlap=True)
    marker = current["scan_result"]["gap_recovery"]
    assert marker["status"] == "frontier_relocated" and marker["bookmark"]["deferred"] == [deferred]
    assert current["gap_reason"] == "overlap_incomplete" and not current["complete"]
    route = [*fresh[:2], *fresh[5:7]]
    legacy = plan_gap_scan(SCOPE, state, route, NOW, marker["bookmark"])
    confirmed = plan_gap_scan(
        SCOPE, state, route, NOW, marker["bookmark"], allow_frontier_overlap=True
    )
    assert legacy == confirmed
    assert confirmed["complete"] and confirmed["scan_result"]["first_anchor_id"] == target[0]


@pytest.mark.parametrize("first_window", [1, 2, 3])
def test_earlier_short_search_window_can_seed_and_resume_from_the_fourth_document(
    state, first_window
):
    rows = list(range(126, 69, -1))

    def doc(index, number, window, successor):
        return page(number, rows[5 * index : 5 * index + 5], window=window, links=[successor])

    raw = []
    for n in range(1, first_window + 1):
        target = (
            cursor(n + 1) if n < first_window else cursor(1, "-712") | {"label_kind": "next_search"}
        )
        raw.append(doc(n - 1, n, None, target))
        assert seed_next_url(SCOPE, state, raw, NOW) == target["canonical_url"]
    for n in range(1, 4 - first_window + 1):
        raw.append(doc(first_window + n - 1, n, "-712", cursor(n + 1, "-712")))
    plan = plan_gap_seed_route(SCOPE, state, raw, NOW)
    assert len(plan["scan_result"]["pages"]) == 4 and not plan["complete"]
    b = new_gap_bookmark(SCOPE, state, raw, NOW)
    assert b["depth"] == 4 and b["frontier"] == cursor(4 - first_window, "-712")
    assert valid_gap_bookmark(SCOPE, state, b)
    p = [*raw[:2], raw[-1], doc(4, 5 - first_window, "-712", cursor(6 - first_window, "-712"))]
    for n in (2, 3):
        assert gap_next_url(SCOPE, state, p[:n], NOW, b) == p[n]["url"]
    later = plan_gap_scan(SCOPE, state, p, NOW, b)["scan_result"]["gap_recovery"]
    assert later["depth"] == 5 and later["status"] == "advanced"
    broken = list(raw)
    broken[first_window - 1] = page(
        first_window, rows[(first_window - 1) * 5 : first_window * 5], links=[cursor(1, "-712")]
    )
    assert seed_next_url(SCOPE, state, broken[:first_window], NOW) is None
    with pytest.raises(WatchPlanError):
        plan_gap_seed_route(SCOPE, state, broken, NOW)
