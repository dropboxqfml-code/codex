"""Join fresh recent and older list windows to a previously replayed coverage receipt."""

import re

from image_monitor.search_list import MAX_ROWS
from image_monitor.watch_planner import (
    WatchPlanError,
    _cursor,
    _page,
    _page_record,
    _plan_scan,
    _scope,
    _stored_time,
    plan_scan,
)
from image_monitor.watch_store import MONITOR_SCOPE

MAX_HISTORICAL_PAGE = 10
HEAD_JOIN_METHODS = frozenset({"clipped_prefix", "corroborated_suffix"})
_MIN_HEAD_OVERLAP = 3
_GAPS = {"anchor_not_reached", "overlap_incomplete"}
_UNKNOWN_ROUTE = "route_evidence_unverified"
_SUCCESSOR_REASONS = frozenset(
    {"successor_link_missing", "successor_link_ambiguous", "route_not_observed", _UNKNOWN_ROUTE}
)
HISTORICAL_ROUTE_REASONS = {
    "recent_pages_only": frozenset(
        {
            "checkpoint_in_recent_pages",
            "insufficient_recent_pages",
            "recent_chain_unverified",
            "previous_head_not_matched",
            "boundary_link_missing",
            "boundary_link_ambiguous",
            "route_not_observed",
            _UNKNOWN_ROUTE,
        }
    ),
    "extended": _SUCCESSOR_REASONS | {"boundary_extended"},
    "boundary_changed": _SUCCESSOR_REASONS | {"previous_boundary_not_matched"},
}


def _ids(page):
    return [row["post_id"] for row in page["rows"]]


def _descending(ids):
    return (
        isinstance(ids, list)
        and 0 < len(ids) <= MAX_ROWS
        and all(isinstance(item, str) and re.fullmatch(r"[1-9][0-9]{0,19}", item) for item in ids)
        and all(int(left) > int(right) for left, right in zip(ids, ids[1:], strict=False))
    )


def _source_ok(source):
    if not isinstance(source, dict) or source.keys() - {"after_head_id"} != {
        "source_scan_id",
        "boundary_page",
        "head_ids",
        "boundary_ids",
    }:
        return False
    boundary = source["boundary_page"]
    after = source.get("after_head_id")
    return (
        isinstance(source["source_scan_id"], str)
        and re.fullmatch(r"[0-9a-f]{32}", source["source_scan_id"]) is not None
        and type(boundary) is int
        and 4 <= boundary < MAX_HISTORICAL_PAGE
        and _descending(source["head_ids"])
        and _descending(source["boundary_ids"])
        and int(source["head_ids"][-1]) > int(source["boundary_ids"][0])
        and (
            "after_head_id" not in source
            or _descending([source["head_ids"][-1], after, source["boundary_ids"][0]])
        )
    )


def historical_source(latest):
    """Extract the two ordered boundaries from a separately replayed, closed partial scan."""
    if not latest or latest.get("complete") is not False or latest.get("gap_reason") not in _GAPS:
        return None
    result = latest["result"]
    if result["control"].get("follow_up_page_limit") != 4:
        return None
    pages = result["private_observation"]["pages"]
    if len(pages) != 4:
        return None
    positions = [page["page"] for page in pages]
    previous = result.get("historical_follow_up")
    if previous is None:
        if positions != [1, 2, 3, 4]:
            return None
        if any(
            not _joined_rows(_ids(left), _ids(right))
            for left, right in zip(pages, pages[1:], strict=False)
        ):
            return None
    elif previous.get("status") != "extended" or positions != [
        1,
        2,
        previous["boundary_page"],
        previous["boundary_page"] + 1,
    ]:
        return None
    source = {
        "source_scan_id": latest["scan_id"],
        "head_ids": _ids(pages[0]),
        "boundary_page": positions[-1],
        "boundary_ids": _ids(pages[-1]),
    }
    # This row is part of the same replayed source. It corroborates the end
    # of the earlier first page even if page two repeated its last few rows.
    head = source["head_ids"]
    joined = _joined_rows(head, _ids(pages[1]))
    if joined and source["boundary_ids"]:
        after = joined[len(head)]
        if _descending([head[-1], after, source["boundary_ids"][0]]):
            source["after_head_id"] = after
    return source if _source_ok(source) else None


def _joined_rows(first, second):
    """Allow only a shared page edge and require a genuinely older row on the next page."""
    if not _descending(first) or not _descending(second):
        return []
    repeated = len(set(first).intersection(second))
    if repeated and first[-repeated:] != second[:repeated]:
        return []
    if repeated == len(second) or int(first[-1]) <= int(second[repeated]):
        return []
    return first + second[repeated:]


def _contains(rows, previous, *, allow_prefix=False):
    """The entire old row sequence must occur in order; a proper prefix can guide one read."""
    if previous[0] not in rows:
        return False
    tail = rows[rows.index(previous[0]) :][: len(previous)]
    return tail == previous or (allow_prefix and tail == previous[: len(tail)])


def _head_join(rows, source, allow_head_overlap):
    previous = source["head_ids"]
    if _contains(rows, previous):
        return "full"
    if allow_head_overlap is not True or len(previous) <= _MIN_HEAD_OVERLAP:
        return None
    previous_ids = set(previous)
    common = [item for item in rows if item in previous_ids]
    count = len(common)
    if not _MIN_HEAD_OVERLAP <= count < len(previous):
        return None
    # A clipped prefix must reach the very last row we actually observed.
    if common == previous[:count] and rows[-count:] == common:
        return "clipped_prefix"
    # A suffix must continue through the old page break. Any preceding
    # current rows must be newer than the entire earlier first page.
    start = rows.index(common[0])
    if (
        common == previous[-count:]
        and (start == 0 or int(rows[start - 1]) > int(previous[0]))
        and rows[start : start + count + 1] == [*common, source.get("after_head_id")]
    ):
        return "corroborated_suffix"
    return None


def _link(page, raw, number, role):
    counts = raw.get("counts")
    if not isinstance(counts, dict) or type(counts.get("list_containers")) is not int:
        return None, _UNKNOWN_ROUTE
    if counts["list_containers"] != 1:
        return None, _UNKNOWN_ROUTE
    options = [
        link
        for link in raw["pagination_candidates"]
        if link["page"] == number and link.get("search_pos") is None
    ]
    if not options:
        return None, role + "_link_missing"
    if len(options) != 1:
        return None, role + "_link_ambiguous"
    target = {key: options[0].get(key) for key in ("canonical_url", "page", "search_pos")}
    if target in page["links"]:
        return target, None
    return None, _UNKNOWN_ROUTE


def _head(scope, state, pages, observed_at, source, allow_head_overlap):
    if scope != MONITOR_SCOPE or not _source_ok(source):
        raise WatchPlanError("Unconfirmed historical source")
    head = plan_scan(scope, state, pages[:2], observed_at, allow_verified_live=True)
    if head["scan_result"]["first_anchor_id"] is not None:
        return head, None, "checkpoint_in_recent_pages", None
    if len(pages) < 2:
        return head, None, "insufficient_recent_pages", None
    if (
        head["gap_reason"]
        not in {"anchor_not_reached", "pagination_missing", "historical_cursor_unverified"}
        or len(head["scan_result"]["pages"]) != 2
    ):
        return head, None, "recent_chain_unverified", None
    # Page one and its adjacent page must connect to the prior scan's actual head.
    ids = _joined_rows(_ids(pages[0]), _ids(pages[1]))
    if not ids:
        return head, None, "recent_chain_unverified", None
    join = _head_join(ids, source, allow_head_overlap)
    if join is None:
        return head, None, "previous_head_not_matched", None
    expected = _scope(scope)
    first = _page(pages[0], expected, observed_at, "site_verified")
    second = _page(pages[1], expected, observed_at, "site_verified")
    next_page, _ = _link(first, pages[0], 2, "recent")
    if next_page != _cursor(second):
        return head, None, "recent_chain_unverified", None
    target, reason = _link(second, pages[1], source["boundary_page"], "boundary")
    return head, target, reason, join if target is not None else None


def _boundary(scope, raw, observed_at, cursor):
    page = _page(raw, _scope(scope), observed_at, "site_verified")
    if _cursor(page) != cursor:
        raise WatchPlanError("The historical document differs from its fresh link")
    return page


def _successor(head_end, boundary, raw, source):
    rows = _ids(boundary)
    if (
        boundary["rows_complete"]
        and _descending(rows)
        and int(head_end) > int(rows[0])
        and _contains(rows, source["boundary_ids"], allow_prefix=True)
    ):
        target, reason = _link(boundary, raw, boundary["page"] + 1, "successor")
        return True, target, reason
    return False, None, "previous_boundary_not_matched"


def historical_next_url(scope, state, pages, observed_at, source, *, allow_head_overlap=False):
    """Return a fresh DOM link to the older boundary or its verified adjacent successor."""
    if len(pages) not in (2, 3):
        return None
    try:
        _, target, _, _ = _head(scope, state, pages, observed_at, source, allow_head_overlap)
        if target is None:
            return None
        if len(pages) == 2:
            return target["canonical_url"]
        page = _boundary(scope, pages[2], observed_at, target)
        _, link, _ = _successor(_ids(pages[1])[-1], page, pages[2], source)
        return link["canonical_url"] if link else None
    except WatchPlanError:
        pass
    return None


def _tail(scope, pages, observed_at, source, target):
    boundary = _boundary(scope, pages[2], observed_at, target)
    tail_pages = [boundary]
    ids = _ids(boundary)
    initial_match, adjacent, reason = _successor(_ids(pages[1])[-1], boundary, pages[2], source)
    if len(pages) == 4:
        if adjacent is None:
            raise WatchPlanError("The older boundary did not authorize an additional page")
        following = _boundary(scope, pages[3], observed_at, adjacent)
        tail_pages.append(following)
        ids = _joined_rows(ids, _ids(following)) if following["rows_complete"] else []
        matched = _contains(ids, source["boundary_ids"])
        return (
            tail_pages,
            matched,
            "boundary_extended" if matched else "previous_boundary_not_matched",
        )
    matched = initial_match and _contains(ids, source["boundary_ids"])
    return tail_pages, matched, reason or "route_not_observed"


def plan_historical_scan(scope, state, pages, observed_at, source, *, allow_head_overlap=False):
    """Replay physical visits 1, 2, B[, B+1], retaining the head if the older rows moved."""
    if len(pages) not in (3, 4):
        raise WatchPlanError("A historical scan needs three or four visited documents")
    head, target, _, join = _head(scope, state, pages, observed_at, source, allow_head_overlap)
    if target is None:
        raise WatchPlanError("The fresh head does not join the earlier scan")
    tail_pages, matched, _ = _tail(scope, pages, observed_at, source, target)
    mark = {"source_scan_id": source["source_scan_id"], "boundary_page": target["page"]}
    if join in HEAD_JOIN_METHODS:
        mark["head_join"] = join
    if matched:
        plan = _plan_scan(
            scope, state, pages, observed_at, allow_verified_live=True, verified_boundary=target
        )
        plan["scan_result"]["historical_follow_up"] = mark | {"status": "extended"}
        return plan

    # Private observations/visit receipts retain every document. Only rows from
    # the two connected latest pages can create or refresh candidates in this case.
    result = head["scan_result"]
    result["pages"].extend(_page_record(item) for item in tail_pages)
    result["last_cursor"] = _cursor(tail_pages[-1])
    result["follow_up"] = None
    result["historical_follow_up"] = mark | {"status": "boundary_changed"}
    head["gap_reason"] = result["gap_reason"] = "historical_boundary_changed"
    return head


def _route_assessment(scope, state, pages, observed_at, source, status, allow_head_overlap):
    try:
        if status not in HISTORICAL_ROUTE_REASONS or not 1 <= len(pages) <= 4:
            return _UNKNOWN_ROUTE, None
        _, target, reason, join = _head(
            scope, state, pages, observed_at, source, allow_head_overlap
        )
        if status == "recent_pages_only":
            if [page["page"] for page in pages] != list(range(1, len(pages) + 1)):
                return _UNKNOWN_ROUTE, None
            return reason or "route_not_observed", None
        if target is None or len(pages) < 3:
            return _UNKNOWN_ROUTE, None
        _, matched, reason = _tail(scope, pages, observed_at, source, target)
        if matched == (status == "extended"):
            return reason, join if join in HEAD_JOIN_METHODS else None
    except (WatchPlanError, AttributeError, IndexError, KeyError, TypeError):
        pass
    return _UNKNOWN_ROUTE, None


def historical_route_reason(
    scope, state, pages, observed_at, source, status, *, allow_head_overlap=False
):
    """Explain a verified scan using the same observations and checks that chose its route."""
    return _route_assessment(scope, state, pages, observed_at, source, status, allow_head_overlap)[
        0
    ]


def historical_route_details(before, latest, source, *, allow_head_overlap=False):
    """Project the verified route and any partial head match without exposing post identities."""
    if source is None:
        return {}
    if not _source_ok(source):
        raise WatchPlanError("Invalid verified historical source")
    result = latest["result"]
    marker = result.get("historical_follow_up")
    status = "recent_pages_only"
    if marker is not None:
        if (
            not isinstance(marker, dict)
            or marker.get("status") not in ("extended", "boundary_changed")
            or marker.get("source_scan_id") != source["source_scan_id"]
            or marker.get("boundary_page") != source["boundary_page"]
        ):
            raise WatchPlanError("Historical routing marker differs from its verified source")
        status = marker["status"]
    reason, join = _route_assessment(
        MONITOR_SCOPE,
        before,
        result["private_observation"]["pages"],
        _stored_time(latest["observed_at"], "scan observed_at"),
        source,
        status,
        allow_head_overlap,
    )
    details = {
        "historical_boundary_page": source["boundary_page"],
        "historical_status": status,
        "historical_reason": reason,
    }
    if marker is not None:
        if ("head_join" in marker) != (join is not None) or marker.get("head_join") != join:
            raise WatchPlanError("Historical head match differs from the verified observations")
        if join is not None:
            details["head_join"] = join
    return details


def plan_historical_prefix(scope, state, pages, observed_at, source, *, allow_head_overlap=False):
    """Retain only the verified head when its historical route ends at an unverified layout."""
    if len(pages) not in (3, 4) or pages[-1].get("layout_status") != "unverified":
        return None
    target = historical_next_url(
        scope, state, pages[:-1], observed_at, source, allow_head_overlap=allow_head_overlap
    )
    if target is None:
        return None
    try:
        following = _page(pages[-1], _scope(scope), observed_at, "unverified")
        times = [_stored_time(page.get("observed_at"), "page observed_at") for page in pages]
        if following["url"] != target or times != sorted(times):
            return None
        head = plan_scan(scope, state, pages[:2], observed_at, allow_verified_live=True)
    except WatchPlanError:
        return None
    head["gap_reason"] = "list_profile_unverified_or_incomplete"
    head["checkpoint"] = state["checkpoint"]
    head["scan_result"].update(
        layout_status="unverified", gap_reason=head["gap_reason"], verified_prefix_pages=2
    )
    return head
