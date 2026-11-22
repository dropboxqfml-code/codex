"""Plan a bounded slice of a durable, possibly multi-window search gap."""

from image_monitor.watch_history import _descending, _head_join, _ids, _joined_rows
from image_monitor.watch_planner import (
    WatchPlanError,
    _cursor,
    _list_url,
    _page,
    _page_record,
    _plan_scan,
    _scope,
)
from image_monitor.watch_store import MONITOR_SCOPE

GAP_COVERAGE_REASONS = frozenset({"gap_successor_unconfirmed"})
GAP_RECOVERY_REASONS = {
    "frontier_relocated": frozenset({"frontier_prefix_overlap"}),
    "segment_queued": frozenset({"recent_tail_overlap", "observed_frontier_shift"}),
    "held": frozenset(
        {
            "recent_page_limit",
            "recent_chain_unverified",
            "recent_overlap_unconfirmed",
            "deferred_limit",
            "frontier_rebase_unverified",
            "recent_plan_unconfirmed",
        }
    ),
}
GAP_STATUSES = frozenset(
    {
        "advanced",
        "completed",
        "frontier_changed",
        "frontier_relocated",
        "successor_unconfirmed",
        "overlap_pending",
        "segment_rejoined",
        "head_rejoined",
        "segment_queued",
        "held",
    }
)
_MAX_DEFERRED = 8
_MAX_WINDOWS = 256
_SEGMENT_KEYS = {"head_ids", "frontier", "frontier_ids", "depth"}
_OPTIONAL_SEGMENT_KEYS = {"after_head_id", "search_positions"}


def _segment_valid(expected, segment):
    if not isinstance(segment, dict) or segment.keys() - _OPTIONAL_SEGMENT_KEYS != _SEGMENT_KEYS:
        return False
    head, ids, cursor = segment["head_ids"], segment["frontier_ids"], segment["frontier"]
    if not (
        _descending(head)
        and _descending(ids)
        and int(head[-1]) > int(ids[0])
        and type(segment["depth"]) is int
        and segment["depth"] >= 4
        and isinstance(cursor, dict)
        and cursor.keys() == {"canonical_url", "page", "search_pos"}
        and type(cursor["page"]) is int
    ):
        return False
    if "after_head_id" in segment and not _descending([head[-1], segment["after_head_id"], ids[0]]):
        return False
    parsed = _list_url(cursor["canonical_url"], expected)
    if parsed["page"] != cursor["page"] or parsed["search_pos"] != cursor["search_pos"]:
        return False
    if cursor["search_pos"] is None:
        return cursor["page"] == segment["depth"] and "search_positions" not in segment
    positions = segment.get("search_positions")
    return (
        isinstance(positions, list)
        and 0 < len(positions) <= _MAX_WINDOWS
        and positions[-1] == cursor["search_pos"]
        and all(isinstance(pos, str) for pos in positions)
        and len(positions) == len(set(positions))
        and cursor["page"] < segment["depth"]
    )


def _segment(bookmark):
    return {key: bookmark[key] for key in _SEGMENT_KEYS | _OPTIONAL_SEGMENT_KEYS if key in bookmark}


def valid_gap_bookmark(scope, state, bookmark):
    """Validate the private cursor against the exact scope and active checkpoint."""
    try:
        if scope != MONITOR_SCOPE or not isinstance(bookmark, dict):
            return False
        allowed = (
            _SEGMENT_KEYS
            | _OPTIONAL_SEGMENT_KEYS
            | {"target_ids", "deferred", "source_scan_id", "source_generation"}
        )
        if not bookmark.keys() <= allowed:
            return False
        targets = bookmark["target_ids"]
        expected = _scope(scope)
        deferred = bookmark.get("deferred", [])
        return (
            _descending(targets)
            and targets == state["checkpoint"]["anchor_ids"]
            and _segment_valid(expected, _segment(bookmark))
            and isinstance(deferred, list)
            and len(deferred) <= _MAX_DEFERRED
            and all(_segment_valid(expected, segment) for segment in deferred)
        )
    except (KeyError, ValueError, TypeError, IndexError):
        return False


def _checked(scope, state, pages, at, bookmark):
    if not valid_gap_bookmark(scope, state, bookmark):
        raise WatchPlanError("The stored gap does not describe this checkpoint")
    checked = [_page(raw, _scope(scope), at, "site_verified") for raw in pages]
    return checked


def _link_to(raw, page, cursor):
    if (
        type(raw.get("counts", {}).get("list_containers")) is not int
        or raw["counts"]["list_containers"] != 1
    ):
        return False
    return (
        cursor in page["links"]
        and sum(
            all(item.get(key) == value for key, value in cursor.items())
            for item in raw["pagination_candidates"]
        )
        == 1
    )


def _latest_rows(raw, pages):
    if not 1 <= len(pages) <= 4 or pages[0]["page"] != 1 or pages[0]["search_pos"] is not None:
        return []
    combined = _ids(pages[0])
    positions = []
    for index, page in enumerate(pages):
        if not page["rows_complete"] or not _descending(_ids(page)):
            return []
        if index:
            previous = pages[index - 1]
            prior = _ids(previous)
            joined = _joined_rows(prior, _ids(page))
            target = _successor(raw[index - 1], previous, {"search_positions": positions})
            if not joined or target != _cursor(page):
                return []
            if page["search_pos"] != previous["search_pos"]:
                positions.append(page["search_pos"])
            combined = combined + joined[len(prior) :]
    return combined


def _updated_head(segment, head_pages):
    head = _ids(head_pages[0])
    joined = _joined_rows(head, _ids(head_pages[1]))
    updated = dict(segment, head_ids=head)
    updated.pop("after_head_id", None)
    if joined and _descending([head[-1], joined[len(head)], segment["frontier_ids"][0]]):
        updated["after_head_id"] = joined[len(head)]
    return updated


def new_gap_bookmark(scope, state, pages, observed_at):
    """Seed only from a previously certified partial scan. Its last cursor was actually observed."""
    if scope != MONITOR_SCOPE or len(pages) != 4 or not state.get("checkpoint"):
        return None
    checked = [_page(raw, _scope(scope), observed_at, "site_verified") for raw in pages]
    frontier = checked[-1]
    consecutive = bool(_latest_rows(pages, checked))
    if not consecutive:
        # Earlier alpha releases may have a separately authenticated 1,2,B,B+1 scan.
        if (
            not _latest_rows(pages[:2], checked[:2])
            or not all(p["search_pos"] is None and p["rows_complete"] for p in checked)
            or checked[2]["page"] < 4
            or frontier["page"] != checked[2]["page"] + 1
            or not _joined_rows(_ids(checked[2]), _ids(frontier))
            or not _link_to(pages[2], checked[2], _cursor(frontier))
        ):
            return None
    new = _updated_head(
        {
            "frontier": _cursor(frontier),
            "frontier_ids": _ids(frontier),
            "depth": len(pages) if consecutive else frontier["page"],
            "target_ids": list(state["checkpoint"]["anchor_ids"]),
        },
        checked,
    )
    if frontier["search_pos"] is not None:
        new["search_positions"] = list(
            dict.fromkeys(p["search_pos"] for p in checked if p["search_pos"] is not None)
        )
    return new if valid_gap_bookmark(scope, state, new) else None


def _head_ready(scope, state, raw, checked, at, bookmark):
    rows = _latest_rows(raw[:2], checked[:2])
    if not rows or not _head_join(rows, bookmark, True):
        return False
    # A located global checkpoint needs its physical adjacent page, never a jump.
    head = plan_gap_seed_route(scope, state, raw[:2], at)
    return not head["complete"] and head["scan_result"]["first_anchor_id"] is None


def _successor(raw, page, bookmark):
    options = [
        cursor
        for cursor in page["links"]
        if cursor["search_pos"] == page["search_pos"] and cursor["page"] == page["page"] + 1
    ]
    if options:
        return options[0] if len(options) == 1 and _link_to(raw, page, options[0]) else None
    if len(bookmark.get("search_positions", [])) >= _MAX_WINDOWS:
        return None
    directional = [
        item for item in raw["pagination_candidates"] if item.get("label_kind") == "next_search"
    ]
    if len(directional) != 1:
        return None
    option = {key: directional[0].get(key) for key in ("canonical_url", "page", "search_pos")}
    if (
        option["page"] == 1
        and option["search_pos"] is not None
        and option["search_pos"] != page["search_pos"]
        and option["search_pos"] not in bookmark.get("search_positions", [])
        and _link_to(raw, page, option)
    ):
        return option
    return None


def plan_gap_seed_route(scope, state, pages, observed_at):
    """Replay the connected sequence from latest page one, including observed range breaks."""
    if scope != MONITOR_SCOPE:
        raise WatchPlanError("Unsupported gap scope")
    checked = [_page(raw, _scope(scope), observed_at, "site_verified") for raw in pages]
    if not _latest_rows(pages, checked):
        raise WatchPlanError("Unverified recent pagination or row ordering")
    hops = {i - 1: _cursor(page) for i, page in enumerate(checked) if i}
    plan = _plan_scan(
        scope, state, pages, observed_at, allow_verified_live=True, verified_hops=hops
    )
    if plan["gap_reason"] == "historical_cursor_unverified":
        positions = list(
            dict.fromkeys(p["search_pos"] for p in checked if p["search_pos"] is not None)
        )
        if _successor(pages[-1], checked[-1], {"search_positions": positions}) is not None:
            _partial_reason(
                plan,
                "overlap_incomplete"
                if plan["scan_result"]["first_anchor_id"]
                else "anchor_not_reached",
            )
    return plan


def seed_next_url(scope, state, pages, observed_at):
    """Select a unique directional successor in the currently observed recent sequence."""
    if not state.get("baseline") or not 1 <= len(pages) <= 3:
        return None
    try:
        plan = plan_gap_seed_route(scope, state, pages, observed_at)
        if plan["complete"] or len(plan["scan_result"]["pages"]) != len(pages):
            return None
        page = _page(pages[-1], _scope(scope), observed_at, "site_verified")
        positions = list(
            dict.fromkeys(p["search_pos"] for p in pages if p["search_pos"] is not None)
        )
        target = _successor(pages[-1], page, {"search_positions": positions})
        return target["canonical_url"] if target else None
    except (WatchPlanError, KeyError, TypeError, IndexError):
        return None


def _surviving_window(rows, previous):
    """Require a whole old window or three adjacent survivors after at most two deletions."""
    old = set(previous)
    common = [value for value in rows if value in old]
    if not common or (common != previous and (len(common) < 3 or len(previous) - len(common) > 2)):
        return False
    start = rows.index(common[0])
    return rows[start : start + len(common)] == common


def _probe_allowed(rows, previous):
    # The bookmark may have moved partly or entirely into the adjacent document.
    # A read alone cannot advance or register the unproven historical rows.
    if not _descending(rows):
        return False
    return _surviving_window(rows, previous) or int(rows[-1]) >= int(previous[-1])


def gap_next_url(scope, state, pages, observed_at, bookmark):
    """Return an exact previously checked bookmark or a unique observed successor."""
    if len(pages) not in (2, 3):
        return None
    try:
        checked = _checked(scope, state, pages, observed_at, bookmark)
        if not _head_ready(scope, state, pages, checked, observed_at, bookmark):
            return None
        if len(pages) == 2:
            if any(page["url"] == bookmark["frontier"]["canonical_url"] for page in checked):
                return None
            return bookmark["frontier"]["canonical_url"]
        frontier = checked[2]
        if (
            _cursor(frontier) != bookmark["frontier"]
            or not frontier["rows_complete"]
            or not _descending(_ids(frontier))
            or int(_ids(checked[1])[-1]) <= int(_ids(frontier)[0])
            or not _probe_allowed(_ids(frontier), bookmark["frontier_ids"])
        ):
            return None
        target = _successor(pages[2], frontier, bookmark)
        return target["canonical_url"] if target else None
    except (KeyError, TypeError, IndexError, WatchPlanError):
        return None


def _mark(plan, status, depth, eligible, route, *, next_bookmark=None, crossed=False):
    plan["scan_result"]["gap_recovery"] = {
        "status": status,
        "depth": depth,
        "eligible_pages": eligible,
        "route": route,
        "bookmark": next_bookmark,
        "crossed_search_range": crossed,
    }
    return plan


def _confirmed_completion(plan, bookmark):
    if plan["scan_result"]["first_anchor_id"] not in bookmark["target_ids"]:
        raise WatchPlanError("Gap completion requires an observed covered anchor")


def _partial_reason(plan, reason):
    plan["gap_reason"] = plan["scan_result"]["gap_reason"] = reason


def _held_head(scope, state, pages, checked, at, bookmark, status):
    plan = plan_gap_seed_route(scope, state, pages[:2], at)
    result = plan["scan_result"]
    result["pages"].extend(_page_record(page) for page in checked[2:])
    result["last_cursor"] = _cursor(checked[-1])
    result["follow_up"] = None
    plan["gap_reason"] = result["gap_reason"] = "historical_boundary_changed"
    return _mark(plan, status, bookmark["depth"], 2, "bookmark")


def _advance(bookmark, head, frontier):
    next_bookmark = _updated_head(
        bookmark
        | {
            "frontier": _cursor(frontier),
            "frontier_ids": _ids(frontier),
            "depth": bookmark["depth"] + 1,
        },
        head,
    )
    if frontier["search_pos"] != bookmark["frontier"]["search_pos"]:
        next_bookmark["search_positions"] = [
            *bookmark.get("search_positions", []),
            frontier["search_pos"],
        ]
    next_bookmark.pop("source_scan_id", None)
    next_bookmark.pop("source_generation", None)
    return next_bookmark


def plan_gap_scan(scope, state, pages, observed_at, bookmark, *, allow_frontier_overlap=False):
    """Replay 1, 2, exact bookmarked frontier and, when observed, its linked successor."""
    if len(pages) not in (3, 4):
        raise WatchPlanError("Expected a revisited gap frontier")
    checked = _checked(scope, state, pages, observed_at, bookmark)
    if gap_next_url(scope, state, pages[:2], observed_at, bookmark) != checked[2]["url"] or (
        len(pages) == 4
        and gap_next_url(scope, state, pages[:3], observed_at, bookmark) != checked[3]["url"]
    ):
        raise WatchPlanError("Historical pages do not follow the verified bookmark and successor")
    frontier = checked[2]
    tail = _ids(frontier)
    if len(pages) == 4:
        tail = _joined_rows(tail, _ids(checked[3]))
    if (
        not tail
        or not _descending(_ids(frontier))
        or not all(page["rows_complete"] for page in checked[2:])
        or int(_ids(checked[1])[-1]) <= int(tail[0])
    ):
        return _held_head(scope, state, pages, checked, observed_at, bookmark, "frontier_changed")
    previous = bookmark["frontier_ids"]
    relocated = not _surviving_window(tail, previous)
    if relocated and not (
        allow_frontier_overlap is True
        and len(pages) == 4
        and checked[3]["search_pos"] == frontier["search_pos"]
        and int(_ids(frontier)[-1]) > int(previous[0])
        and _clipped_prefix_at_end(tail, _ids(frontier)[-1], previous)
    ):
        return _held_head(scope, state, pages, checked, observed_at, bookmark, "frontier_changed")
    hops = {index - 1: _cursor(checked[index]) for index in range(1, len(pages))}
    plan = _plan_scan(
        scope,
        state,
        pages,
        observed_at,
        allow_verified_live=True,
        verified_hops=hops,
    )
    if len(plan["scan_result"]["pages"]) != len(pages):
        raise WatchPlanError("Stored recovery pages differ from the replayed route")
    advanced = len(pages) == 4
    depth = bookmark["depth"] + int(advanced)
    crossed = advanced and checked[3]["search_pos"] != frontier["search_pos"]
    if plan["complete"]:
        if relocated:
            return _held_head(
                scope, state, pages, checked, observed_at, bookmark, "frontier_changed"
            )
        _confirmed_completion(plan, bookmark)
        return _mark(plan, "completed", depth, len(pages), "bookmark", crossed=crossed)
    anchor_seen = plan["scan_result"]["first_anchor_id"] is not None
    if not advanced:
        status = "overlap_pending" if anchor_seen else "successor_unconfirmed"
        _partial_reason(plan, "overlap_incomplete" if anchor_seen else "gap_successor_unconfirmed")
        return _mark(plan, status, depth, 3, "bookmark")
    updated = _advance(bookmark, checked, checked[-1])
    if not valid_gap_bookmark(scope, state, updated):
        return _held_head(scope, state, pages, checked, observed_at, bookmark, "frontier_changed")
    # A directional range change may be available where the ordinary planner
    # correctly reports that it cannot infer one from the cursor alone.
    successor = _successor(pages[-1], checked[-1], updated)
    if relocated and successor is None:
        return _held_head(scope, state, pages, checked, observed_at, bookmark, "frontier_changed")
    _partial_reason(
        plan,
        "overlap_incomplete"
        if anchor_seen
        else "anchor_not_reached"
        if successor
        else "gap_successor_unconfirmed",
    )
    if relocated:
        # The fourth document ends inside the former frontier. Reopen it next
        # turn to verify the remaining rows; every deferred segment stays open.
        _mark(plan, "frontier_relocated", depth, 4, "bookmark", next_bookmark=updated)
        plan["scan_result"]["gap_recovery"]["recovery_reason"] = "frontier_prefix_overlap"
        return plan
    deferred = bookmark.get("deferred", [])
    if deferred:
        earlier = deferred[0]
        if set(_ids(frontier)).intersection(earlier["head_ids"]) and _surviving_window(
            tail, earlier["head_ids"]
        ):
            # Latest-range page numbers can move dozens of pages during an
            # outage. Continue at the successor actually reached, rather than
            # returning to an ordinal whose old rows have shifted. Distinct
            # cursor windows may reuse their own stored URL and must recheck it.
            old_cursor = earlier["frontier"]["search_pos"]
            if old_cursor is None or old_cursor == updated["frontier"]["search_pos"]:
                restored = updated
            else:
                restored = _updated_head(earlier, checked) | {
                    "target_ids": bookmark["target_ids"],
                }
            restored["deferred"] = deferred[1:]
            if not valid_gap_bookmark(scope, state, restored):
                return _held_head(
                    scope, state, pages, checked, observed_at, bookmark, "frontier_changed"
                )
            return _mark(
                plan,
                "segment_rejoined",
                restored["depth"],
                4,
                "bookmark",
                next_bookmark=restored,
                crossed=crossed,
            )
    status = (
        "overlap_pending" if anchor_seen else "advanced" if successor else "successor_unconfirmed"
    )
    return _mark(plan, status, depth, 4, "bookmark", next_bookmark=updated, crossed=crossed)


def _clipped_prefix_at_end(rows, earlier_floor, previous):
    """Match a terminal run after an earlier document to a proper prefix of a prior window."""
    floor = rows[-1]
    if floor not in previous or floor == previous[-1]:
        return False
    prefix = previous[: previous.index(floor) + 1]
    old_ids = set(prefix)
    common = [post_id for post_id in rows if post_id in old_ids]
    if len(common) < 3 or len(prefix) - len(common) > 2:
        return False
    # Every row before the shared run must be newer than the entire prior window.
    start = len(rows) - len(common)
    return (
        start > 0
        and int(common[0]) < int(earlier_floor)
        and int(rows[start - 1]) > int(previous[0])
        and rows[start:] == common
    )


def _observed_frontier_shift(rows, recent_floor, checked, bookmark):
    """Require a full displaced head and different, strictly newer rows at the exact old URL."""
    head = bookmark["head_ids"]
    if int(head[0]) >= int(recent_floor) or head[0] not in rows:
        return False
    start = rows.index(head[0])
    if rows[start : start + len(head)] != head:
        return False
    return any(
        _cursor(page) == bookmark["frontier"]
        and int(_ids(page)[-1]) > int(bookmark["frontier_ids"][0])
        for page in checked
    )


def _recent_rebase(scope, state, pages, observed_at, bookmark, allow_partial_overlap):
    if len(pages) != 4:
        return None, "recent_page_limit"
    checked = _checked(scope, state, pages, observed_at, bookmark)
    rows = _latest_rows(pages, checked)
    if not rows:
        return None, "recent_chain_unverified"
    previous = bookmark["head_ids"]
    queue_reason = None
    if allow_partial_overlap:
        recent_floor = _ids(checked[1])[-1]
        if _clipped_prefix_at_end(rows, recent_floor, previous):
            queue_reason = "recent_tail_overlap"
        elif _observed_frontier_shift(rows, recent_floor, checked, bookmark):
            queue_reason = "observed_frontier_shift"
    if queue_reason is None:
        if _head_join(rows, bookmark, True) or _surviving_window(rows, previous):
            updated = _updated_head(bookmark, checked)
            updated.pop("source_scan_id", None)
            updated.pop("source_generation", None)
            if valid_gap_bookmark(scope, state, updated):
                return updated, None
            return None, "frontier_rebase_unverified"
        if int(rows[-1]) <= int(previous[0]):
            return None, "recent_overlap_unconfirmed"
    if len(bookmark.get("deferred", [])) >= _MAX_DEFERRED:
        return None, "deferred_limit"
    # The old rows can now be several pages deeper. Continue from the fourth
    # document actually read and retain the entire previous route until rejoined.
    fresh = new_gap_bookmark(scope, state, pages, observed_at)
    if fresh is None:
        return None, "frontier_rebase_unverified"
    fresh["deferred"] = [_segment(bookmark), *bookmark.get("deferred", [])]
    return fresh, queue_reason


def rebase_gap_bookmark(scope, state, pages, observed_at, bookmark):
    """Return the original recent-route bookmark for callers replaying earlier scans."""
    return _recent_rebase(scope, state, pages, observed_at, bookmark, False)[0]


def plan_gap_seed(scope, state, pages, observed_at, plan):
    """Recognize a verified recent prefix ending at an explicit forward search link."""
    if (
        plan["gap_reason"] != "historical_cursor_unverified"
        or not 2 <= len(pages) <= 4
        or len(plan["scan_result"]["pages"]) != len(pages)
    ):
        return plan
    try:
        verified = plan_gap_seed_route(scope, state, pages, observed_at)
    except WatchPlanError:
        return plan
    if verified["gap_reason"] in {"anchor_not_reached", "overlap_incomplete"}:
        _partial_reason(plan, verified["gap_reason"])
    return plan


def plan_gap_fallback(
    scope, state, pages, observed_at, bookmark, plan, *, allow_partial_overlap=False
):
    """Record an ordinary recent scan while a gap is open. A failure keeps the earlier bookmark."""
    if not valid_gap_bookmark(scope, state, bookmark):
        raise WatchPlanError("Unconfirmed gap for ordinary scan")
    plan = plan_gap_seed(scope, state, pages, observed_at, plan)
    eligible = len(plan["scan_result"]["pages"])
    if plan["complete"]:
        _confirmed_completion(plan, bookmark)
        return _mark(plan, "completed", bookmark["depth"], eligible, "recent")
    status, reason, updated = "held", "recent_plan_unconfirmed", None
    if eligible == len(pages) and plan["gap_reason"] in {
        "anchor_not_reached",
        "overlap_incomplete",
    }:
        updated, reason = _recent_rebase(
            scope, state, pages, observed_at, bookmark, allow_partial_overlap
        )
        if updated is not None:
            status = (
                "segment_queued"
                if len(updated.get("deferred", [])) > len(bookmark.get("deferred", []))
                else "head_rejoined"
            )
    plan = _mark(
        plan, status, (updated or bookmark)["depth"], eligible, "recent", next_bookmark=updated
    )
    if allow_partial_overlap and reason:
        plan["scan_result"]["gap_recovery"]["recovery_reason"] = reason
    return plan
