"""Deterministic, fixture-only list scan plans; no browser or polling loop.

A plan records list evidence and possible detail-inspection candidates. It never
asserts a publication time, creates post folders, or authorizes an image save.
"""

import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from math import isfinite

from image_monitor.dcinside import DCSnapshotError, validate_post_url
from image_monitor.search_list import validate_list_url
from image_monitor.watch_store import WatchScope

_SCOPE_FIELDS = ("gallery_type", "gallery_id", "search_type", "keyword")
_SAFE_EXCLUSIONS = {"ad", "pinned", "non_numeric", "wrong_gallery"}


class WatchPlanError(ValueError):
    """The supplied evidence cannot safely be interpreted as this watch."""


def _time(value, name):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise WatchPlanError(f"{name} must be a timezone-aware datetime")
    return value


def _stored_time(value, name):
    try:
        return _time(datetime.fromisoformat(value), name)
    except (TypeError, ValueError) as error:
        raise WatchPlanError(f"Invalid {name}") from error


def _ids(values):
    if (
        not isinstance(values, list)
        or any(
            not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]{0,19}", value)
            for value in values
        )
        or len(values) != len(set(values))
    ):
        raise WatchPlanError("anchor_ids must be unique canonical positive post IDs")
    return list(values)


def _sequence(value, name):
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise WatchPlanError(f"{name} must be a sequence")
    return value


def _scope(scope):
    if not isinstance(scope, WatchScope):
        raise WatchPlanError("scope must be a WatchScope")
    try:
        scope.key()
    except ValueError as error:
        raise WatchPlanError("Invalid watch scope") from error
    return {field: getattr(scope, field) for field in _SCOPE_FIELDS}


def _list_url(value, expected):
    try:
        parsed = validate_list_url(value)
    except DCSnapshotError as error:
        raise WatchPlanError("Invalid list URL") from error
    if any(parsed[field] != expected[field] for field in _SCOPE_FIELDS):
        raise WatchPlanError("List URL does not match the exact watch scope")
    if parsed["navigation"]:
        raise WatchPlanError("Additional navigation filters require a distinct watch scope")
    if parsed["canonical_url"] != value:
        raise WatchPlanError("Expected a canonical list URL")
    return parsed


def _cursor(page):
    return {"canonical_url": page["url"], "page": page["page"], "search_pos": page["search_pos"]}


def _checkpoint(record, expected, observed_at, name):
    if not isinstance(record, Mapping):
        raise WatchPlanError(f"Invalid {name}")
    anchors = _ids(record.get("anchor_ids"))
    source = _list_url(record.get("source_url"), expected)
    if source["page"] != 1 or source["search_pos"] is not None:
        raise WatchPlanError(f"{name} must describe latest page 1")
    stamp = _stored_time(record.get("observed_at"), f"{name} observed_at")
    if stamp > observed_at:
        raise WatchPlanError("A scan observation cannot precede its baseline or checkpoint")
    return anchors, stamp


def _page(value, expected, observed_at):
    if not isinstance(value, Mapping):
        raise WatchPlanError("Each page must be a list snapshot")
    if (
        value.get("layout_status") != "fixture_validated"
        or value.get("queue_eligible") is not False
    ):
        raise WatchPlanError("Only fixture-validated, non-queueable snapshots are supported")
    target = _list_url(value.get("url"), expected)
    scope = value.get("scope")
    if (
        not isinstance(scope, Mapping)
        or set(scope) - {*_SCOPE_FIELDS, "navigation"}
        or any(scope.get(field) != expected[field] for field in _SCOPE_FIELDS)
        or scope.get("navigation", {}) != {}
        or type(value.get("page")) is not int
        or value["page"] != target["page"]
        or value.get("search_pos") != target["search_pos"]
    ):
        raise WatchPlanError("Snapshot identity does not match its URL and exact watch scope")
    if (
        "observed_at" in value
        and _stored_time(value["observed_at"], "page observed_at") != observed_at
    ):
        raise WatchPlanError("Snapshot observation date differs from the scan")
    if value.get("status") not in {"observed", "empty"}:
        raise WatchPlanError("Missing, ambiguous, or unrecognized list evidence")
    rows = []
    previous_order = -1
    for row in _sequence(value.get("rows"), "rows"):
        if not isinstance(row, Mapping):
            raise WatchPlanError("Invalid list row")
        post_id = row.get("post_id")
        _ids([post_id])
        try:
            post = validate_post_url(row.get("canonical_url"))
        except DCSnapshotError as error:
            raise WatchPlanError("Invalid row post URL") from error
        if (
            post["canonical_url"] != row.get("canonical_url")
            or post["post_id"] != post_id
            or any(post[field] != expected[field] for field in ("gallery_type", "gallery_id"))
        ):
            raise WatchPlanError("Row post URL is not its canonical, in-scope identity")
        order = row.get("row_order")
        if type(order) is not int or order < 0 or order <= previous_order:
            raise WatchPlanError("Rows must retain strictly increasing DOM row_order")
        previous_order = order
        for field in ("title", "author_raw", "published_at_raw"):
            if row.get(field) is not None and not isinstance(row[field], str):
                raise WatchPlanError(f"Invalid row {field}")
        rows.append(
            {
                key: row.get(key)
                for key in (
                    "post_id",
                    "canonical_url",
                    "title",
                    "author_raw",
                    "published_at_raw",
                    "row_order",
                )
            }
        )
    excluded = []
    row_orders = {row["row_order"] for row in rows}
    for exclusion in _sequence(value.get("excluded_rows", []), "excluded_rows"):
        if not isinstance(exclusion, Mapping):
            raise WatchPlanError("Invalid excluded row evidence")
        order, reason = exclusion.get("row_order"), exclusion.get("reason")
        if (
            type(order) is not int
            or order < 0
            or order in row_orders
            or not isinstance(reason, str)
            or not reason
        ):
            raise WatchPlanError("Invalid or conflicting excluded row evidence")
        row_orders.add(order)
        excluded.append({"row_order": order, "reason": reason})
    if (value["status"] == "empty" and (rows or excluded)) or (
        value["status"] == "observed" and not (rows or excluded)
    ):
        raise WatchPlanError("Snapshot status conflicts with the observed rows")
    links = []
    for link in _sequence(value.get("pagination_candidates"), "pagination_candidates"):
        if not isinstance(link, Mapping):
            raise WatchPlanError("Invalid pagination candidate")
        parsed = _list_url(link.get("canonical_url"), expected)
        if (
            type(link.get("page")) is not int
            or link["page"] != parsed["page"]
            or link.get("search_pos") != parsed["search_pos"]
        ):
            raise WatchPlanError("Pagination candidate conflicts with its URL")
        cursor = {key: parsed[key] for key in ("canonical_url", "page", "search_pos")}
        if cursor not in links:
            links.append(cursor)
    terminal = value.get("end_of_results") is True and value.get("pagination_complete") is True
    if terminal and links:
        raise WatchPlanError("Terminal evidence conflicts with pagination candidates")
    return {
        "url": target["canonical_url"],
        "page": target["page"],
        "search_pos": target["search_pos"],
        "rows": rows,
        "excluded_rows": excluded,
        "rows_complete": all(item["reason"] in _SAFE_EXCLUSIONS for item in excluded),
        "links": links,
        "end_of_results": terminal,
    }


def _next(page):
    return [
        link
        for link in page["links"]
        if (link["search_pos"] == page["search_pos"] and link["page"] == page["page"] + 1)
    ]


def plan_scan(
    scope: WatchScope,
    state: Mapping,
    pages: Sequence[dict],
    observed_at: datetime,
    *,
    overlap_pages: int = 1,
    max_pages: int = 5,
    synthetic_fixture: bool = False,
) -> dict:
    """Return keyword arguments for ``WatchStore.persist_scan(scope, **plan)``.

    Every cycle starts at latest page 1. Only exact anchors in the last complete
    checkpoint establish overlap; rows after the first anchor remain observations.
    Explicit fixture terminal evidence can establish full coverage without an
    anchor. Missing links or snapshots never establish end-of-results. Unknown
    ordinary rows block coverage; historical cursor relationships are unverified.
    """
    if synthetic_fixture is not True:
        raise WatchPlanError("Scan planning currently requires synthetic_fixture=True")
    expected = _scope(scope)
    observed_at = _time(observed_at, "observed_at")
    if type(overlap_pages) is not int or overlap_pages < 1:
        raise WatchPlanError("overlap_pages must be an integer of at least 1")
    if type(max_pages) is not int or max_pages < 1:
        raise WatchPlanError("max_pages must be a positive integer")
    if (
        not isinstance(state, Mapping)
        or type(state.get("generation")) is not int
        or state["generation"] < 0
    ):
        raise WatchPlanError("Invalid watch state generation")
    for field in (*_SCOPE_FIELDS, "watch_name"):
        if field in state and state[field] != getattr(scope, field):
            raise WatchPlanError("Watch state belongs to a different scope")
    pages = _sequence(pages, "pages")
    if not pages:
        raise WatchPlanError("A scan requires latest page 1 evidence")
    baseline = state.get("baseline")
    checkpoint = state.get("checkpoint")
    if baseline is None and checkpoint is not None:
        raise WatchPlanError("A checkpoint requires an established baseline")
    if baseline is not None:
        _, baseline_time = _checkpoint(baseline, expected, observed_at, "baseline")
        if (
            baseline.get("mode") != "new"
            or baseline.get("requires_published_at_filter") is not True
        ):
            raise WatchPlanError("Unsupported baseline or missing publication-date filter")
        if checkpoint is None:
            raise WatchPlanError("An established baseline requires a complete checkpoint")
        anchor_ids, checkpoint_time = _checkpoint(checkpoint, expected, observed_at, "checkpoint")
        if checkpoint_time < baseline_time:
            raise WatchPlanError("A complete checkpoint cannot precede the baseline")
    else:
        anchor_ids = []
    if state.get("updated_at") is not None:
        if _stored_time(state["updated_at"], "state updated_at") > observed_at:
            raise WatchPlanError("A scan observation cannot move state backwards")
    stamp = observed_at.isoformat(timespec="microseconds")
    result = {
        "mode": "baseline" if baseline is None else "scan",
        "scope": expected,
        "layout_status": "fixture_validated",
        "synthetic_fixture": True,
        "queue_eligible": False,
        "observed_at": stamp,
        "coverage_anchor_ids": list(anchor_ids),
        "observations": [],
        "pages": [],
        "first_anchor_id": None,
        "last_cursor": None,
        "follow_up": None,
        "unverified_cursor_candidates": [],
    }
    candidates = []
    seen = {}
    last_unique_id = None
    first_anchor_page = None
    visited = set()
    first = _page(pages[0], expected, observed_at)
    if first["page"] != 1 or first["search_pos"] is not None:
        raise WatchPlanError("Every cycle must start at latest page 1 without search_pos")
    new_checkpoint = {
        "anchor_ids": [row["post_id"] for row in first["rows"]],
        "observed_at": stamp,
        "source_url": first["url"],
    }
    new_baseline = None
    complete = False
    gap_reason = None
    current = first
    for index in range(min(len(pages), max_pages)):
        if index:
            current = _page(pages[index], expected, observed_at)
        visited.add(current["url"])
        result["last_cursor"] = _cursor(current)
        result["follow_up"] = None
        result["pages"].append(
            _cursor(current)
            | {
                "end_of_results": current["end_of_results"],
                "excluded_rows": current["excluded_rows"],
                "rows_complete": current["rows_complete"],
                "pagination_candidates": current["links"],
            }
        )
        historical = [
            link for link in current["links"] if link["search_pos"] != current["search_pos"]
        ]
        result["unverified_cursor_candidates"].extend(historical)
        # Validate the whole page before treating any of its rows as candidates.
        local_ids = [int(row["post_id"]) for row in current["rows"]]
        descending = all(
            left > right for left, right in zip(local_ids, local_ids[1:], strict=False)
        )
        pending_last = last_unique_id
        for row in current["rows"]:
            post_id = row["post_id"]
            if post_id in seen:
                if seen[post_id] != row["canonical_url"]:
                    raise WatchPlanError("One post ID has conflicting canonical URLs")
            else:
                if pending_last is not None and int(post_id) >= pending_last:
                    descending = False
                pending_last = int(post_id)
        for row in current["rows"]:
            post_id = row["post_id"]
            metadata = {
                "author_raw": row["author_raw"],
                "published_at_raw": row["published_at_raw"],
                "row_order": row["row_order"],
                "source_url": current["url"],
                "requires_published_at_filter": True,
                "baseline_observed_at": baseline["observed_at"] if baseline else stamp,
                "empty_baseline_ambiguous": baseline is not None and not anchor_ids,
            }
            candidate = {
                "post_id": post_id,
                "post_url": row["canonical_url"],
                "title": row["title"],
                "shown_metadata": metadata,
            }
            if not current["rows_complete"]:
                role = "excluded_rows_unverified"
            elif not descending:
                role = "order_unverified"
            elif baseline is None:
                role = "baseline"
            elif post_id in anchor_ids:
                role = "anchor"
                if first_anchor_page is None:
                    first_anchor_page = index
                    result["first_anchor_id"] = post_id
            elif first_anchor_page is None:
                role = "candidate"
                if post_id not in seen:
                    candidates.append(candidate)
            else:
                role = "overlap_recheck"
            result["observations"].append(
                candidate
                | {"role": role, "page": current["page"], "search_pos": current["search_pos"]}
            )
            seen[post_id] = row["canonical_url"]
        if not current["rows_complete"] or not descending:
            gap_reason = (
                "excluded_rows_unverified" if not current["rows_complete"] else ("order_unverified")
            )
            result["follow_up"] = _cursor(current)
            break
        last_unique_id = pending_last
        if baseline is None:
            new_baseline = new_checkpoint | {"mode": "new", "requires_published_at_filter": True}
            complete = True
            break
        if current["end_of_results"] or (
            first_anchor_page is not None and index - first_anchor_page >= overlap_pages
        ):
            complete = True
            break
        options = _next(current)
        result["follow_up"] = dict(options[0]) if len(options) == 1 else None
        if not options and historical:
            gap_reason = "historical_cursor_unverified"
            result["follow_up"] = _cursor(current)
            break
        if len(options) > 1:
            gap_reason = "pagination_ambiguous"
            break
        if index + 1 >= max_pages:
            gap_reason = "max_pages"
            break
        if index + 1 >= len(pages):
            gap_reason = (
                "pagination_missing"
                if not options
                else "overlap_incomplete"
                if first_anchor_page is not None
                else "empty_baseline_requires_end"
                if not anchor_ids
                else "anchor_not_reached"
            )
            break
        following = _page(pages[index + 1], expected, observed_at)
        if following["url"] in visited:
            gap_reason = "pagination_cycle"
            break
        if following["search_pos"] != current["search_pos"]:
            gap_reason = "historical_cursor_unverified"
            break
        if not options or _cursor(following) not in options:
            gap_reason = "pagination_unverified"
            break
    if complete:
        result["follow_up"] = None
    result["complete"] = complete
    result["gap_reason"] = gap_reason
    return {
        "observed_at": observed_at,
        "expected_generation": state["generation"],
        "scan_result": result,
        "candidates": candidates,
        "checkpoint": new_checkpoint,
        "complete": complete,
        "gap_reason": gap_reason,
        "baseline": new_baseline,
    }


def next_poll_at(
    last_finished_at: datetime,
    interval_seconds: float = 60,
    service_not_before: datetime | None = None,
) -> datetime:
    """Calculate a future eligibility time; this function never runs a scheduler."""
    last_finished_at = _time(last_finished_at, "last_finished_at")
    if (
        isinstance(interval_seconds, bool)
        or not isinstance(interval_seconds, (int, float))
        or not isfinite(interval_seconds)
        or interval_seconds < 60
    ):
        raise WatchPlanError("interval_seconds must be finite and at least 60")
    try:
        eligible = last_finished_at + timedelta(seconds=interval_seconds)
    except OverflowError as error:
        raise WatchPlanError("Poll interval exceeds the supported date range") from error
    if service_not_before is not None:
        eligible = max(eligible, _time(service_not_before, "service_not_before"))
    return eligible
