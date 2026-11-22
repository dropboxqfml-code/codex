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


def ordinary(rows, count=4):
    return [document(i, rows[(i - 1) * 5 : i * 5], i + 1) for i in range(1, count + 1)]


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
