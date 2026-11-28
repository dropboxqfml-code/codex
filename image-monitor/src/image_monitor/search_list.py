"""Read-only search-list observations with one narrowly reviewed DOM structure.

The reviewed title/body search structure never grants permission to queue posts
or establishes pagination completeness. Other scopes remain unverified.
"""

import re
import time
import unicodedata
from datetime import datetime
from urllib.parse import urljoin

from image_monitor.dcinside import DCSnapshotError, validate_post_url
from image_monitor.list_inspection_failure import list_snapshot_error
from image_monitor.list_links import (
    LIST_PATHS as LIST_PATHS,
)
from image_monitor.list_links import (
    SEARCH_TYPE as SEARCH_TYPE,
)
from image_monitor.list_links import (
    build_list_url as build_list_url,
)
from image_monitor.list_links import (
    classify_rejected_list_link,
    validate_list_url,
)
from image_monitor.paths import aware

MAX_ROWS = 200
MAX_PAGINATION = 200
MAX_LINKS_PER_ROW = 8
SELECTORS = {
    "list": ".gall_list",
    "rows": ".gall_list tbody tr.ub-content",
    "number": ".gall_num",
    "title_links": ".gall_tit a:not(.reply_numbox)",
    "author": ".gall_writer",
    "date": ".gall_date",
    "empty": ".gall_list .no_data, .gall_list .no_result",
    "pagination": ".bottom_paging_box a, a.search_next, .search_next a",
}
MAX_LIST_CANDIDATES = 12
MAX_PAGINATION_SAMPLES = 12
NAVIGATION_KINDS = {
    "number",
    "next",
    "next_search",
    "previous",
    "first",
    "last",
    "other",
    "unavailable",
}
LINK_SCHEMES = {"https", "http", "javascript", "relative", "other", "missing"}
SAFE_EXCLUSIONS = {"ad", "pinned", "survey"}
SPECIAL_DATE_PROFILE_SOURCE = "reviewed_special_row_dates_alpha15"


def recognized_special_row(value, *, require_role_flags=True):
    """Decide whether row evidence identifies an excluded ad, notice, or survey."""
    reason = value["reason"]
    if reason not in SAFE_EXCLUSIONS:
        return False
    if reason in {"ad", "pinned"}:
        flag = "is_ad" if reason == "ad" else "is_pinned"
        return not require_role_flags or value.get("role_flags", {}).get(flag) is True
    fields = value.get("field_counts", {})
    return (
        value.get("number_kind") == "survey_label"
        and value.get("link_schemes") == {"javascript": 1}
        and fields.get("number") == 1
        and fields.get("title_links") == 1
        and (
            not require_role_flags
            or value.get("role_flags") == {"is_ad": False, "is_pinned": False}
        )
    )


def _control(char):
    return unicodedata.category(char) in {"Cc", "Cs"}


def _public_text(value, limit):
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or len(value) > limit
        or any(_control(char) and char not in "\n\r\t" for char in value)
    ):
        raise list_snapshot_error(
            "snapshot_parse", "bounded_text_invalid", "Invalid bounded public text"
        )
    return value or None


def _scope(target):
    keys = ("gallery_type", "gallery_id", "search_type", "keyword")
    return {key: target[key] for key in keys} | {"navigation": dict(target["navigation"])}


def _count(raw, key, *, maximum=1_000_000):
    value = raw.get(key)
    if type(value) is not int or not 0 <= value <= maximum:
        raise list_snapshot_error(
            "snapshot_parse", "count_invalid", "Invalid list observation count"
        )
    return value


def _safe_diagnostics(raw):
    """Copy only bounded DOM shapes, excluding text and attribute/query values."""
    if not isinstance(raw, dict):
        return {"counts": {}, "samples": []}
    counts = {}
    incoming_counts = raw.get("counts", {})
    if not isinstance(incoming_counts, dict):
        incoming_counts = {}
    for key, value in list(incoming_counts.items())[:16]:
        if key in SELECTORS.values() and type(value) is int and 0 <= value <= 1_000_000:
            counts[key] = value
    result = {"counts": counts, "samples": []}
    candidates = raw.get("list_candidates", [])
    if isinstance(candidates, list):
        inventory = []
        for entry in candidates[:MAX_LIST_CANDIDATES]:
            if not isinstance(entry, dict):
                continue
            candidate = {}
            tag = entry.get("tag")
            if isinstance(tag, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,30}", tag):
                candidate["tag"] = tag
            classes = entry.get("classes", [])
            if isinstance(classes, list):
                candidate["classes"] = [
                    value
                    for value in classes[:10]
                    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,60}", value)
                ]
            for key in (
                "table_row_count",
                "ordinary_row_count",
                "number_field_count",
                "writer_field_count",
                "date_field_count",
                "title_link_count",
                "empty_marker_count",
                "visible_empty_marker_count",
            ):
                value = entry.get(key)
                if type(value) is int and 0 <= value <= 1_000_000:
                    candidate[key] = value
            for key in ("has_id", "qualifies", "selected"):
                if type(entry.get(key)) is bool:
                    candidate[key] = entry[key]
            if entry.get("root_ownership") == "direct_tbody_rows":
                candidate["root_ownership"] = "direct_tbody_rows"
            schemes = entry.get("title_link_schemes")
            if isinstance(schemes, dict):
                candidate["title_link_schemes"] = {
                    key: value
                    for key, value in schemes.items()
                    if key in LINK_SCHEMES and type(value) is int and 0 <= value <= 1_000_000
                }
            inventory.append(candidate)
        result["list_candidates"] = inventory
    total = raw.get("list_candidate_total")
    if type(total) is int and 0 <= total <= 1_000_000:
        result["list_candidate_total"] = total
    truncated = raw.get("list_candidates_truncated")
    if type(truncated) is bool:
        result["list_candidates_truncated"] = truncated
    samples = []
    incoming = raw.get("samples", [])
    if not isinstance(incoming, list):
        return result
    for value in incoming[:18]:
        if not isinstance(value, dict) or value.get("selector") not in SELECTORS.values():
            continue
        sample = {"selector": value["selector"]}
        tag = value.get("tag")
        if isinstance(tag, str) and re.fullmatch(r"[A-Za-z0-9-]{1,30}", tag):
            sample["tag"] = tag
        classes = value.get("classes", [])
        if isinstance(classes, list):
            sample["classes"] = [
                item
                for item in classes[:10]
                if isinstance(item, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,60}", item)
            ]
        names = value.get("attribute_names", [])
        if isinstance(names, list):
            sample["attribute_names"] = [
                name
                for name in names[:12]
                if isinstance(name, str) and re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]{0,59}", name)
            ]
        shape = value.get("link_shape")
        if isinstance(shape, dict):
            safe_shape = {}
            for key in ("scheme", "host"):
                item = shape.get(key)
                if isinstance(item, str) and re.fullmatch(r"[A-Za-z0-9.:-]{1,100}", item):
                    safe_shape[key] = item
            segments = shape.get("path_segments")
            if type(segments) is int and 0 <= segments <= 100:
                safe_shape["path_segments"] = segments
            keys = shape.get("query_keys", [])
            if isinstance(keys, list):
                safe_shape["query_keys"] = [
                    key
                    for key in keys[:12]
                    if isinstance(key, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,60}", key)
                ]
            sample["link_shape"] = safe_shape
        samples.append(sample)
    result["samples"] = samples
    return result


def _absolute_link(value, base):
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 4096
        or any(ord(char) <= 32 or _control(char) for char in value)
        or re.search(r"%(?![0-9a-fA-F]{2})", value)
    ):
        raise DCSnapshotError("Invalid observed link")
    try:
        return urljoin(base, value)
    except ValueError as error:
        raise DCSnapshotError("Invalid observed link") from error


def _link_scheme(value):
    if value is None or value == "":
        return "missing"
    if not isinstance(value, str):
        return "other"
    match = re.match(r"^([a-z][a-z0-9+.-]*):", value, flags=re.IGNORECASE)
    if not match:
        return "relative"
    scheme = match[1].lower()
    return scheme if scheme in {"https", "http", "javascript"} else "other"


def _row_evidence(raw, row_order, reason):
    """Retain categories and counts, never excluded-row text or URL values."""
    number = _public_text(raw.get("number_raw"), 100)
    if number == "설문":
        number_kind = "survey_label"
    elif number == "공지":
        number_kind = "notice_label"
    elif number is not None and re.fullmatch(r"AD|광고", number, flags=re.IGNORECASE):
        number_kind = "ad_label"
    elif number is not None and re.fullmatch(r"[0-9]+", number):
        number_kind = "numeric"
    else:
        number_kind = "missing" if number is None else "other"
    fields = raw.get("field_counts")
    counts = {}
    if isinstance(fields, dict):
        counts = {
            key: fields[key]
            for key in ("number", "author", "date")
            if type(fields.get(key)) is int and 0 <= fields[key] <= 1_000_000
        }
    links = raw.get("links")
    if not isinstance(links, list) or len(links) > MAX_LINKS_PER_ROW:
        raise list_snapshot_error(
            "snapshot_parse", "row_link_limit", "Observed row links exceed inspection limit"
        )
    total = _count(raw, "link_total")
    if total != len(links):
        raise list_snapshot_error(
            "snapshot_parse", "row_link_limit", "Observed row links exceed inspection limit"
        )
    counts["title_links"] = total
    # Extra owned anchors, including reply links, are relevant to whether an
    # excluded row could still identify an actual post.
    if "all_links" in raw:
        links = raw["all_links"]
        if (
            not isinstance(links, list)
            or len(links) > MAX_LINKS_PER_ROW
            or _count(raw, "all_link_total") != len(links)
        ):
            raise list_snapshot_error(
                "snapshot_parse", "row_link_limit", "Observed row links exceed inspection limit"
            )
    schemes = {}
    for link in links:
        if not isinstance(link, dict):
            raise list_snapshot_error(
                "snapshot_parse", "row_evidence_invalid", "Invalid observed row link"
            )
        scheme = _link_scheme(link.get("href"))
        schemes[scheme] = schemes.get(scheme, 0) + 1
    return {
        "row_order": row_order,
        "reason": reason,
        "number_kind": number_kind,
        "link_schemes": schemes,
        "field_counts": counts,
        "role_flags": {key: raw[key] for key in ("is_ad", "is_pinned")},
    }


def _ordinary_row(raw, target, row_order, *, expected_date_cells=1):
    if not isinstance(raw, dict):
        raise list_snapshot_error("snapshot_parse", "row_evidence_invalid", "Invalid observed row")
    for key in ("is_ad", "is_pinned"):
        if type(raw.get(key)) is not bool:
            raise list_snapshot_error(
                "snapshot_parse", "row_evidence_invalid", "Invalid row classification evidence"
            )
    if raw["is_ad"]:
        return None, "ad"
    if raw["is_pinned"]:
        return None, "pinned"
    fields = raw.get("field_counts")
    if (
        not isinstance(fields, dict)
        or type(fields.get("number")) is not int
        or fields["number"] != 1
    ):
        return None, "ambiguous_row_fields"
    number = _public_text(raw.get("number_raw"), 100)
    if number is None:
        return None, "missing_post_number"
    if not re.fullmatch(r"[0-9]+", number):
        # This recognizes the rendered survey label and an action-only title
        # cell; it never executes the action or infers meaning from its code.
        links = raw.get("links")
        all_links = raw.get("all_links")
        if (
            number == "설문"
            and isinstance(links, list)
            and len(links) == 1
            and type(raw.get("link_total")) is int
            and raw["link_total"] == 1
            and isinstance(links[0], dict)
            and _link_scheme(links[0].get("href")) == "javascript"
            and isinstance(all_links, list)
            and len(all_links) == 1
            and type(raw.get("all_link_total")) is int
            and raw["all_link_total"] == 1
            and isinstance(all_links[0], dict)
            and all_links[0].get("href") == links[0].get("href")
        ):
            return None, "survey"
        return None, "non_numeric"
    if len(number) > 20 or int(number) < 1:
        return None, "invalid_post_number"
    if any(
        type(fields.get(key)) is not int or fields[key] != expected
        for key, expected in (("author", 1), ("date", expected_date_cells))
    ):
        return None, "ambiguous_row_fields"
    links = raw.get("links")
    if not isinstance(links, list) or len(links) > MAX_LINKS_PER_ROW:
        raise list_snapshot_error(
            "snapshot_parse", "row_link_limit", "Observed row links exceed inspection limit"
        )
    if _count(raw, "link_total") != len(links):
        raise list_snapshot_error(
            "snapshot_parse", "row_link_limit", "Observed row links exceed inspection limit"
        )
    candidates = []
    invalid = False
    wrong_gallery = False
    for link in links:
        if not isinstance(link, dict):
            raise list_snapshot_error(
                "snapshot_parse", "row_evidence_invalid", "Invalid observed row link"
            )
        try:
            post = validate_post_url(_absolute_link(link.get("href"), target["canonical_url"]))
        except DCSnapshotError:
            invalid = True
            continue
        if (post["gallery_type"], post["gallery_id"]) != (
            target["gallery_type"],
            target["gallery_id"],
        ):
            wrong_gallery = True
            continue
        candidates.append((post, _public_text(link.get("text_raw"), 1000)))
    if wrong_gallery:
        return None, "mixed_gallery_identity" if candidates or invalid else "wrong_gallery"
    identities = {post["canonical_url"] for post, _title in candidates}
    if invalid or len(identities) != 1:
        return None, "ambiguous_post_identity" if candidates else "invalid_post_link"
    if len({title for _post, title in candidates}) != 1:
        return None, "ambiguous_title"
    post, title = candidates[0]
    if post["post_id"] != str(int(number)):
        return None, "post_number_mismatch"
    if title is None:
        return None, "missing_title"
    return {
        "row_order": row_order,
        "post_id": post["post_id"],
        "canonical_url": post["canonical_url"],
        **({"picture_marker": True} if raw.get("picture_marker") is True else {}),
        "title": title,
        "author_raw": _public_text(raw.get("author_raw"), 500),
        "published_at_raw": _public_text(raw.get("published_at_raw"), 100),
    }, None


_ROW_FIELDS = ("number", "author", "date")
_MAIN_COLUMNS = (
    "table_row_count",
    "ordinary_row_count",
    "number_field_count",
    "writer_field_count",
    "date_field_count",
    "title_link_count",
)
_SECONDARY_COLUMNS = ("number_field_count", "date_field_count", "title_link_count")
PROFILE_ISSUES = frozenset(
    {
        "scope_unreviewed",
        "list_not_observed",
        "no_ordinary_rows",
        "ordinary_title_missing",
        "ordinary_author_missing",
        "ordinary_date_missing",
        "row_number_count",
        "row_author_count",
        "row_date_count",
        "row_title_link_count",
        "container_inventory",
        "container_selection",
        "main_table_shape",
        "secondary_table_shape",
        "secondary_rows",
        "secondary_table_empty",
        "multiple_profile_checks",
        "unavailable",
        *("main_" + key for key in _MAIN_COLUMNS),
        *("secondary_" + key for key in _SECONDARY_COLUMNS),
    }
)


def _raw_row_issue(rows_raw, special_counts):
    for ordinal, row in enumerate(rows_raw, 1):
        fields = row.get("field_counts")
        for key in _ROW_FIELDS:
            value = fields.get(key) if isinstance(fields, dict) else None
            expected = special_counts.get(key, {}).get(ordinal, 1)
            if type(value) is not int or value != expected:
                return "row_" + key + "_count"
        if type(row.get("link_total")) is not int or row["link_total"] != 1:
            return "row_title_link_count"
    return None


def reviewed_structure_issue(
    target,
    diagnostics,
    rows,
    row_issue,
    row_total,
    container_count,
    status,
    *,
    writer_field_total=None,
    date_field_total=None,
):
    """Return the first reviewed profile check that failed, or None on an exact match."""
    if (
        target.get("gallery_type") != "normal"
        or target.get("gallery_id") != "comic_new6"
        or target.get("search_type") != SEARCH_TYPE
        or target.get("keyword") != "ai"
        or target.get("navigation")
    ):
        return "scope_unreviewed"
    if status != "observed":
        return "list_not_observed"
    if not rows:
        return "no_ordinary_rows"
    if row_issue is not None:
        return row_issue
    candidates = diagnostics.get("list_candidates", [])
    if (
        diagnostics.get("list_candidate_total") != 1
        or diagnostics.get("list_candidates_truncated") is not False
        or not isinstance(candidates, list)
        or len(candidates) != container_count
        or container_count != 2
        or not all(isinstance(table, dict) for table in candidates)
    ):
        return "container_inventory"
    selected = [candidate for candidate in candidates if candidate.get("selected") is True]
    if len(selected) != 1:
        return "container_selection"
    main = selected[0]
    if (
        main.get("tag") != "TABLE"
        or main.get("classes") != ["gall_list"]
        or main.get("has_id") is not False
        or main.get("qualifies") is not True
        or main.get("root_ownership") != "direct_tbody_rows"
        or main.get("empty_marker_count") != 0
        or main.get("visible_empty_marker_count") != 0
    ):
        return "main_table_shape"
    metadata_totals = {
        "writer_field_count": writer_field_total,
        "date_field_count": date_field_total,
    }
    for key in _MAIN_COLUMNS:
        expected = metadata_totals.get(key)
        if main.get(key) != (row_total if expected is None else expected):
            return "main_" + key
    secondary = next(candidate for candidate in candidates if candidate is not main)
    if (
        secondary.get("tag") != "TABLE"
        or secondary.get("classes") != ["gall_list"]
        or secondary.get("root_ownership") != "direct_tbody_rows"
        or secondary.get("has_id") is not True
        or secondary.get("qualifies") is not False
        or secondary.get("selected") is not False
        or secondary.get("ordinary_row_count") != 0
        or secondary.get("writer_field_count") != 0
        or secondary.get("empty_marker_count") != 0
        or secondary.get("visible_empty_marker_count") != 0
    ):
        return "secondary_table_shape"
    count = secondary.get("table_row_count")
    if type(count) is not int or not 0 <= count <= MAX_ROWS:
        return "secondary_rows"
    for key in _SECONDARY_COLUMNS:
        if secondary.get(key) != count:
            return "secondary_" + key
    for field, issue in (
        ("title", "ordinary_title_missing"),
        ("author_raw", "ordinary_author_missing"),
        ("published_at_raw", "ordinary_date_missing"),
    ):
        if any(not row.get(field) for row in rows):
            return "multiple_profile_checks" if count == 0 else issue
    return "secondary_table_empty" if count == 0 else None


def date_settle_identities(rows, excluded):
    """Match the same ordinary identities and excluded roles in their original row positions."""
    identities = [(row["row_order"], row["post_id"]) for row in rows]
    identities.extend((row["row_order"], row["reason"]) for row in excluded)
    return sorted(identities)


def _missing_date_row(rows_raw, target, rows, excluded):
    unsafe = [row for row in excluded if not recognized_special_row(row)]
    if len(unsafe) != 1 or unsafe[0]["reason"] != "ambiguous_row_fields":
        return None
    pos = unsafe[0]["row_order"]
    # This row is read for identity only. It remains excluded from the initial snapshot.
    try:
        row, _ = _ordinary_row(rows_raw[pos - 1], target, pos, expected_date_cells=0)
    except DCSnapshotError:
        # A previously excluded field may itself be malformed. Keep the original failure.
        return None
    if (
        not row
        or not row["author_raw"]
        or row["published_at_raw"]
        or any(other["post_id"] == row["post_id"] for other in rows)
    ):
        return None
    return row


def parse_list_snapshot(
    raw: dict,
    *,
    expected_url: str,
    observed_at: datetime,
    layout_status: str = "unverified",
    _capture_date_rows=None,
) -> dict:
    """Map bounded public DOM metadata; structural review never enables a queue."""
    target = validate_list_url(expected_url)
    aware(observed_at)
    if layout_status not in {"unverified", "fixture_validated"} or not isinstance(raw, dict):
        raise list_snapshot_error(
            "snapshot_parse", "snapshot_shape_invalid", "Invalid list observation options"
        )
    diagnostics = _safe_diagnostics(raw.get("diagnostics"))
    try:
        current = validate_list_url(raw.get("document_url"))
    except DCSnapshotError as error:
        raise list_snapshot_error(
            "snapshot_parse",
            "snapshot_url_invalid",
            "Invalid observed list URL",
            diagnostics=diagnostics,
        ) from error
    if current["canonical_url"] != target["canonical_url"]:
        raise list_snapshot_error(
            "snapshot_parse",
            "snapshot_url_mismatch",
            "Search identity changed during observation",
            diagnostics=diagnostics,
        )
    list_count = _count(raw, "list_count")
    container_count = (
        _count(raw, "list_container_count") if "list_container_count" in raw else list_count
    )
    if list_count > container_count:
        raise list_snapshot_error(
            "snapshot_parse",
            "selected_count_invalid",
            "Invalid selected list count",
            diagnostics=diagnostics,
        )
    row_total = _count(raw, "row_total")
    pagination_total = _count(raw, "pagination_total")
    empty_count = _count(raw, "empty_marker_count")
    rows_raw, pagination_raw = raw.get("rows"), raw.get("pagination")
    if (
        not isinstance(rows_raw, list)
        or not isinstance(pagination_raw, list)
        or row_total != len(rows_raw)
        or row_total > MAX_ROWS
        or pagination_total != len(pagination_raw)
        or pagination_total > MAX_PAGINATION
    ):
        reason = (
            "row_limit"
            if row_total > MAX_ROWS
            else "pagination_limit"
            if pagination_total > MAX_PAGINATION
            else "inventory_mismatch"
        )
        raise list_snapshot_error(
            "snapshot_parse",
            reason,
            "List observation exceeds inspection limit",
            diagnostics=diagnostics,
        )
    if list_count != 1 and (row_total or empty_count):
        # Counts can still explain an unknown/ambiguous page, but never expose its rows.
        rows_raw = []
    rows, excluded, seen = [], [], set()
    if list_count == 1:
        for index, entry in enumerate(rows_raw, 1):
            row, reason = _ordinary_row(entry, target, index)
            if row is not None and row["post_id"] in seen:
                row, reason = None, "duplicate_post_id"
            if row is None:
                excluded.append(_row_evidence(entry, index, reason))
            else:
                seen.add(row["post_id"])
                rows.append(row)
    pagination, pagination_excluded, seen_urls = [], {}, set()
    next_search_links = []
    repeated_urls = set()
    rejection_counts, pagination_samples, sample_kinds = {}, [], {}
    for link_order, entry in enumerate(pagination_raw, 1):
        reason = None
        if not isinstance(entry, dict):
            raise list_snapshot_error(
                "snapshot_parse", "pagination_invalid", "Invalid pagination observation"
            )
        try:
            link_url = _absolute_link(entry.get("href"), target["canonical_url"])
            candidate = validate_list_url(link_url)
            if _scope(candidate) != _scope(target):
                reason = "different_scope"
            elif candidate["canonical_url"] == target["canonical_url"]:
                reason = "current_document"
            elif candidate["canonical_url"] in seen_urls:
                reason = "duplicate"
                repeated_urls.add(candidate["canonical_url"])
            elif list_count != 1:
                reason = "unrecognized_list"
            else:
                pagination.append(
                    {
                        "canonical_url": candidate["canonical_url"],
                        "page": candidate["page"],
                        "search_pos": candidate["search_pos"],
                    }
                )
                seen_urls.add(candidate["canonical_url"])
        except DCSnapshotError:
            reason = "invalid_url"
        evidence = classify_rejected_list_link(
            entry.get("href"), target["canonical_url"], expected_scope=_scope(target)
        )
        for code in evidence["reason_codes"]:
            rejection_counts[code] = rejection_counts.get(code, 0) + 1
        label_kind = entry.get("label_kind")
        if not isinstance(label_kind, str) or label_kind not in NAVIGATION_KINDS:
            label_kind = "unavailable"
        if label_kind == "next_search":
            next_search_links.append(pagination[-1] if reason is None else None)
        sample_kind = (
            evidence["validation_status"],
            tuple(evidence["reason_codes"]),
            label_kind,
            tuple(evidence["query_value_categories"].items()),
        )
        if (
            len(pagination_samples) < MAX_PAGINATION_SAMPLES
            and sample_kinds.get(sample_kind, 0) < 2
        ):
            sample_kinds[sample_kind] = sample_kinds.get(sample_kind, 0) + 1
            pagination_samples.append(
                {"link_order": link_order, "label_kind": label_kind, **evidence}
            )
        if reason:
            pagination_excluded[reason] = pagination_excluded.get(reason, 0) + 1
    if len(next_search_links) == 1:
        forward = next_search_links[0]
        if forward and forward["canonical_url"] not in repeated_urls:
            forward["label_kind"] = "next_search"
    if list_count == 0 and container_count:
        status = "unrecognized_empty"
    elif list_count == 0:
        status = "missing_list"
    elif list_count != 1:
        status = "ambiguous_list"
    elif row_total and empty_count:
        status = "conflicting_empty_marker"
    elif row_total:
        status = "observed"
    elif empty_count == 1:
        status = "empty"
    else:
        status = "unrecognized_empty"
    # Only proven special rows may have a different writer or date cell count.
    # Each table inventory must independently match the sum of its owned row fields.
    special_counts = {"author": {}, "date": {}}
    for exclusion in excluded:
        if recognized_special_row(exclusion):
            for field, per_row in special_counts.items():
                count = exclusion["field_counts"].get(field)
                if count is not None and count != 1:
                    per_row[exclusion["row_order"]] = count
    totals = {
        field: row_total + sum(count - 1 for count in per_row.values())
        for field, per_row in special_counts.items()
    }

    def profile_issue_for(per_row, date_total):
        return reviewed_structure_issue(
            target,
            diagnostics,
            rows,
            _raw_row_issue(rows_raw, per_row),
            row_total,
            container_count,
            status,
            writer_field_total=totals["author"],
            date_field_total=date_total,
        )

    profile_issue = profile_issue_for(special_counts, totals["date"])
    if (
        _capture_date_rows is not None
        and profile_issue == "row_date_count"
        and layout_status == "unverified"
    ):
        missing = _missing_date_row(rows_raw, target, rows, excluded)
        if missing is not None:
            pos = missing["row_order"]
            expected = special_counts | {"date": special_counts["date"] | {pos: 0}}
            if profile_issue_for(expected, totals["date"] - 1) is None:
                _capture_date_rows(
                    date_settle_identities(
                        [*rows, missing], [row for row in excluded if row["row_order"] != pos]
                    )
                )
    site_verified = layout_status == "unverified" and profile_issue is None
    source = None
    if site_verified:
        layout_status = "site_verified"
        if special_counts["date"]:
            source = SPECIAL_DATE_PROFILE_SOURCE
        elif special_counts["author"]:
            source = "user_list_diagnosis_alpha3"
        else:
            source = "user_list_probe_v12"
    rows_complete = (
        list_count == 1
        and status in {"observed", "empty"}
        and all(recognized_special_row(exclusion) for exclusion in excluded)
    )
    fixture_terminal = (
        layout_status == "fixture_validated"
        and raw.get("fixture_end_of_results") is True
        and status in {"observed", "empty"}
        and not pagination
        and not (set(pagination_excluded) - {"current_document", "duplicate"})
    )
    diagnostics["pagination_rejections"] = rejection_counts
    diagnostics["pagination_samples"] = pagination_samples
    return {
        "schema_version": 1,
        "scope": _scope(target),
        "url": target["canonical_url"],
        "page": target["page"],
        "search_pos": target["search_pos"],
        "observed_at": observed_at.isoformat(),
        "status": status,
        "layout_status": layout_status,
        "queue_eligible": False,
        "rows": rows,
        "excluded_rows": excluded,
        "rows_complete": rows_complete,
        "pagination_candidates": pagination,
        "end_of_results": fixture_terminal,
        "pagination_complete": fixture_terminal,
        "pagination_status": "fixture_terminal"
        if fixture_terminal
        else ("candidates_observed" if pagination else "missing_or_unrecognized"),
        "counts": {
            "list_containers": list_count,
            "matched_list_containers": container_count,
            "observed_rows": row_total,
            "ordinary_rows": len(rows),
            "excluded_rows": len(excluded),
            "empty_markers": empty_count,
            "pagination_links": pagination_total,
            "pagination_candidates": len(pagination),
            "pagination_excluded": pagination_excluded,
        },
        "selector_evidence": {
            "status": layout_status,
            "live_layout_verified": site_verified,
            "source": source,
            "verification_scope": "reviewed_search_structure" if site_verified else None,
            "profile_issue": profile_issue,
            "rows_complete": rows_complete,
            "selectors": dict(SELECTORS),
            "scope": {"gallery_type": target["gallery_type"], "gallery_id": target["gallery_id"]},
        },
        "diagnostics": diagnostics,
    }


LIST_DOM_JS = r"""(options) => {
 const selectors=options.selectors;
 const deadline=performance.now()+options.timeoutMs;
 const expired=Symbol();
 const budget=()=>{if(performance.now()>deadline)throw expired;};
 try {
 const visible=node=>{
  if(!node||!node.isConnected||![...node.getClientRects()].some(r=>r.width>0&&r.height>0))
   return false;
  let n=node;
  for(let depth=0;n&&depth<64;n=n.parentElement,depth++){
   const style=getComputedStyle(n);
   if(style.display==='none'||style.visibility!=='visible'||Number(style.opacity)===0)return false;
  }
  return n===null;
 };
 const text=(node,limit)=>{
  if(!visible(node))return null;
  const walker=document.createTreeWalker(node,NodeFilter.SHOW_TEXT);
  const parts=[];
  for(let child=walker.nextNode();child;child=walker.nextNode()){
   budget();
   const range=document.createRange();range.selectNodeContents(child);
   if(visible(child.parentElement)&&[...range.getClientRects()].some(r=>r.width>0&&r.height>0))
    parts.push(child.textContent);
  }
  const value=parts.join('').trim();
  // Keep both UTF-16 units of a supplementary character together at the cap.
  const end=value.codePointAt(limit-1)>0xffff?limit-1:limit;
  return value.slice(0,end)||null;
 };
 const shape=value=>{try{const u=new URL(value,document.baseURI);return {
  scheme:u.protocol.replace(':',''),host:u.hostname,
  path_segments:u.pathname.split('/').filter(Boolean).length,
  query_keys:[...u.searchParams.keys()].slice(0,12)};}catch(_error){return null;}};
 const diagnostics={counts:{},samples:[]};
 for(const selector of Object.values(selectors)){
  budget();
  const nodes=[...document.querySelectorAll(selector)];
  diagnostics.counts[selector]=nodes.length;
  for(const node of nodes.slice(0,2)){
   const sample={selector,tag:node.tagName,classes:[...node.classList].slice(0,10),
    attribute_names:[...node.attributes].map(x=>x.name).slice(0,12)};
   if(node.matches('a'))sample.link_shape=shape(node.getAttribute('href')||'');
   diagnostics.samples.push(sample);
  }
 }
 const containers=[...document.querySelectorAll(selectors.list)];
 // A structural candidate owns its tbody rows. Visibility and DOM order cannot
 // break ties between two matching list templates.
 const ownedRows=table=>table.matches('table.gall_list')?
  [...table.tBodies].filter(body=>body.parentElement===table).flatMap(body=>
   [...body.children].filter(row=>row.matches('tr'))):[];
 const owned= (table,selector)=>[...table.querySelectorAll(selector)]
  .filter(node=>node.closest('table')===table);
 const scheme=href=>{
  if(!href)return 'missing';
  const match=/^([a-z][a-z0-9+.-]*):/i.exec(href);
  if(!match)return 'relative';
  const name=match[1].toLowerCase();
  return ['https','http','javascript'].includes(name)?name:'other';
 };
 const candidates=containers.map(table=>{
  budget();
  const tableRows=ownedRows(table);
  const rows=tableRows.filter(row=>row.matches('tr.ub-content'));
  const empty=table.matches('table.gall_list')?owned(table,'.no_data, .no_result'):[];
  return {table,tableRows,rows,empty,qualifies:rows.length>0||empty.length>0};
 });
 const qualified=candidates.filter(candidate=>candidate.qualifies);
 const selected=qualified.length===1?qualified[0]:null;
 const root=selected?selected.table:null;
 const allRows=selected?selected.rows:[];
 const emptyNodes=selected?selected.empty.filter(visible):[];
 diagnostics.list_candidate_total=qualified.length;
 diagnostics.list_candidates_truncated=containers.length>options.maxListCandidates;
 diagnostics.list_candidates=candidates.slice(0,options.maxListCandidates).map(candidate=>{
  budget();
  const table=candidate.table,links=owned(table,selectors.title_links),schemes={};
  for(const link of links){const kind=scheme(link.getAttribute('href'));
   schemes[kind]=(schemes[kind]||0)+1;}
  return {tag:table.tagName,classes:[...table.classList].slice(0,10),
   root_ownership:'direct_tbody_rows',
   has_id:table.hasAttribute('id'),
   table_row_count:candidate.tableRows.length,ordinary_row_count:candidate.rows.length,
   number_field_count:owned(table,selectors.number).length,
   writer_field_count:owned(table,selectors.author).length,
   date_field_count:owned(table,selectors.date).length,title_link_count:links.length,
   title_link_schemes:schemes,empty_marker_count:candidate.empty.length,
   visible_empty_marker_count:candidate.empty.filter(visible).length,
   qualifies:candidate.qualifies,selected:table===root};
 });
 const pageLinks=[...document.querySelectorAll(selectors.pagination)];
 const navigationKind=link=>{
  const label=(text(link,40)||'').toLowerCase();
  if(!label)return 'unavailable';
  if(/^[0-9]+$/.test(label))return 'number';
  if(/^(다음\s*검색|next search)$/.test(label)&&visible(link))return 'next_search';
  if(/^(다음|다음페이지|다음 페이지|next|next page|›|»|>)$/.test(label))return 'next';
  if(/^(이전|이전페이지|이전 페이지|prev|previous|previous page|‹|«|<)$/.test(label))
   return 'previous';
  if(/^(처음|첫 페이지|first|first page)$/.test(label))return 'first';
  if(/^(끝|마지막|마지막 페이지|last|last page)$/.test(label))return 'last';
  return 'other';
 };
 const rowOwned=(row,selector)=>[...row.querySelectorAll(selector)]
  .filter(node=>node.closest('tr')===row&&node.closest('table')===root);
 const unique=(row,selector)=>{const nodes=rowOwned(row,selector);
  return {count:nodes.length,node:nodes.length===1?nodes[0]:null};};
 return {document_url:document.URL,list_count:qualified.length,
  list_container_count:containers.length,row_total:allRows.length,
  empty_marker_count:emptyNodes.length,pagination_total:pageLinks.length,diagnostics,
  rows:allRows.slice(0,options.maxRows).map(row=>{
   budget();
   const number=unique(row,selectors.number),author=unique(row,selectors.author);
   const date=unique(row,selectors.date),numberText=text(number.node,100);
   const links=rowOwned(row,selectors.title_links);
   const allLinks=rowOwned(row,'a');
   const picture=links.length===1 && visible(links[0].querySelector(':scope > .icon_pic'));
   return {number_raw:numberText, picture_marker:picture,
    is_ad:row.matches('.ad,.ad-row,.ad_row,.ub-ad,.gall_ad,[data-ad]')||
     /^(AD|광고)$/i.test(numberText||''),
    is_pinned:row.matches('.notice,.ub-notice,.notice_row')||numberText==='공지',
    field_counts:{number:number.count,author:author.count,date:date.count},
    author_raw:text(author.node,500),published_at_raw:text(date.node,100),
    all_link_total:allLinks.length,all_links:allLinks.slice(0,options.maxLinks).map(link=>({
     href:link.getAttribute('href')})),
    link_total:links.length,links:links.slice(0,options.maxLinks).map(link=>({
     href:link.getAttribute('href'),text_raw:text(link,1000)}))};
  }),
  pagination:pageLinks.slice(0,options.maxPagination).map(link=>({
   href:link.getAttribute('href'),label_kind:navigationKind(link)}))};
 } catch(error) {
   if(error===expired)return {list_dom_budget_exceeded:true};
   throw error;
 }
}"""


def inspect_list(
    page,
    *,
    expected_url: str,
    observed_at: datetime,
    timeout_ms: int = 15_000,
    _capture_date_rows=None,
) -> dict:
    """Observe the already-open DOM once; never navigate, click, or read response bytes."""
    target = validate_list_url(expected_url)
    aware(observed_at)
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 120_000:
        raise DCSnapshotError("Invalid list inspection timeout")
    deadline = time.monotonic() + timeout_ms / 1000

    def identity(phase):
        try:
            current = validate_list_url(page.url)
        except DCSnapshotError as error:
            raise list_snapshot_error(
                "document_identity", phase + "_url_invalid", "Invalid observed list URL"
            ) from error
        if current["canonical_url"] != target["canonical_url"]:
            raise list_snapshot_error(
                "document_identity",
                phase + "_url_mismatch",
                "Search identity changed during observation",
            )

    identity("before_dom")
    try:
        # This single DOM evaluation neither waits for nor accesses resources.
        raw = page.evaluate(
            LIST_DOM_JS,
            {
                "selectors": SELECTORS,
                "maxRows": MAX_ROWS,
                "maxLinks": MAX_LINKS_PER_ROW,
                "maxPagination": MAX_PAGINATION,
                "maxListCandidates": MAX_LIST_CANDIDATES,
                "timeoutMs": timeout_ms,
            },
        )
    except Exception as error:
        raise list_snapshot_error(
            "dom_read", "dom_evaluation_failed", "Read-only list DOM observation failed"
        ) from error
    identity("after_dom")
    if time.monotonic() > deadline or (
        isinstance(raw, dict)
        and set(raw) == {"list_dom_budget_exceeded"}
        and raw["list_dom_budget_exceeded"] is True
    ):
        raise list_snapshot_error(
            "dom_read", "dom_budget_exceeded", "List DOM observation exceeded inspection budget"
        )
    try:
        return parse_list_snapshot(
            raw,
            expected_url=expected_url,
            observed_at=observed_at,
            _capture_date_rows=_capture_date_rows,
        )
    except DCSnapshotError:
        raise
    except Exception as error:
        raise list_snapshot_error(
            "snapshot_parse", "parse_failed", "Read-only list DOM observation failed"
        ) from error
