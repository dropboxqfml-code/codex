"""Explain an incomplete list scan using bounded structural evidence only."""

from image_monitor.monitor_gap_report import public_recovery_pages
from image_monitor.search_list import (
    MAX_LIST_CANDIDATES,
    MAX_ROWS,
    PROFILE_ISSUES,
    SAFE_EXCLUSIONS,
    SPECIAL_DATE_PROFILE_SOURCE,
    SPECIAL_TITLE_PROFILE_SOURCE,
    reviewed_structure_issue,
)
from image_monitor.watch_history import MAX_HISTORICAL_PAGE
from image_monitor.watch_planner import WatchPlanError, _exclusion_evidence, _safe_exclusion
from image_monitor.watch_store import MAX_MONITOR_SCAN_PAGES

DIAGNOSIS_REASONS = frozenset(
    {
        "list_profile_unverified_or_incomplete",
        "list_transport_or_inspection_failure",
        "excluded_rows_unverified",
        "order_unverified",
        "pagination_ambiguous",
        "pagination_unverified",
        "pagination_missing",
        "historical_cursor_unverified",
    }
)
PLANNER_ISSUES = frozenset(
    {
        "snapshot_layout",
        "snapshot_identity",
        "observation_time",
        "list_status",
        "row_identity",
        "row_order",
        "exclusion_evidence",
        "pagination_identity",
        "no_page_evidence",
        "invalid_planner_evidence",
    }
)
_PAGE_STATES = {
    "missing_list",
    "ambiguous_list",
    "unrecognized_empty",
    "conflicting_empty_marker",
    "observed",
    "empty",
}
_TRANSPORT_ERRORS = {
    "ERR_TUNNEL_CONNECTION_FAILED",
    "ERR_NAME_NOT_RESOLVED",
    "ERR_CONNECTION_RESET",
    "ERR_CONNECTION_REFUSED",
    "Timeout",
}
_TRANSPORT = {"observed", "http_error", "inspection_error", "network_error", "cancelled"}
_LAYOUT = {"site_verified", "unverified", "fixture_validated"}
_EXCLUSION_REASONS = {
    "ad",
    "pinned",
    "wrong_gallery",
    "survey",
    "ambiguous_row_fields",
    "missing_post_number",
    "non_numeric",
    "invalid_post_number",
    "mixed_gallery_identity",
    "ambiguous_post_identity",
    "invalid_post_link",
    "ambiguous_title",
    "post_number_mismatch",
    "missing_title",
    "duplicate_post_id",
    "unclassified",
}
_SETTLE_ISSUES = {
    "ordinary_title_missing",
    "ordinary_author_missing",
    "ordinary_date_missing",
    "row_date_count",
    "row_title_link_count",
    "secondary_table_empty",
}
_EXCLUDED_ROW_GROUPS = ("ad", "pinned", "survey", "ambiguous_row_fields", "other_excluded")


def _category(value, allowed):
    return value if isinstance(value, str) and value in allowed else None


def _count(value, maximum, minimum=0):
    return value if type(value) is int and minimum <= value <= maximum else None


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _known_safe_exclusion(row, reason):
    try:
        return _safe_exclusion({"reason": reason} | _exclusion_evidence(row), "site_verified")
    except WatchPlanError:
        return False


def _excluded_cell_mismatches(excluded, field):
    """Count stored exceptions by row role without exposing any row or author identity."""
    result = {}
    if not isinstance(excluded, list) or len(excluded) > MAX_ROWS:
        return result
    for entry in excluded:
        row = _mapping(entry)
        cells = _count(_mapping(row.get("field_counts")).get(field), 1_000_000)
        if cells is None or cells == 1:
            continue
        group = _category(row.get("reason"), _EXCLUDED_ROW_GROUPS) or "other_excluded"
        if (
            field in ("date", "title_links")
            and group in SAFE_EXCLUSIONS
            and not _known_safe_exclusion(row, group)
        ):
            group = "other_excluded"
        counts = result.setdefault(group, {})
        kind = "missing" if cells == 0 else "multiple"
        counts[kind] = counts.get(kind, 0) + 1
    return result


def _public_cell_mismatches(value, excluded_count):
    """Re-project a histogram at a public boundary, bounded by observed excluded rows."""
    result = {}
    if _count(excluded_count, MAX_ROWS) is None:
        return result
    source_groups = _mapping(value)
    for group in _EXCLUDED_ROW_GROUPS:
        source = _mapping(source_groups.get(group))
        counts = {
            kind: source[kind]
            for kind in ("missing", "multiple")
            if _count(source.get(kind), MAX_ROWS, 1) is not None
        }
        if counts:
            result[group] = counts
    if sum(sum(counts.values()) for counts in result.values()) > excluded_count:
        return {}
    return result


def _public_date_cells(page, result):
    source = page["date_cells"]
    ordinary, excluded = result["ordinary_rows"], result["excluded_rows"]
    detail = {}
    if ordinary is not None and _count(source.get("ordinary_rows_with_one"), ordinary) == ordinary:
        detail["ordinary_rows_with_one"] = ordinary
    known = _count(source.get("excluded_rows_counted"), excluded) if excluded is not None else None
    if known is not None:
        detail["excluded_rows_counted"] = known
    rows_total = None
    if "ordinary_rows_with_one" in detail and known is not None and known == excluded:
        rows_total = _count(source.get("row_cell_total"), ordinary + known * 1_000_000, ordinary)
    if rows_total is not None:
        detail["row_cell_total"] = rows_total
    table = _count(source.get("table_cell_total"), 1_000_000)
    if table is not None:
        detail["table_cell_total"] = table
    detail["table_check"] = "unavailable"
    if rows_total is not None and table is not None:
        detail["table_check"] = "matches_rows" if table == rows_total else "differs_from_rows"
    date_fields = {"date_cells": detail}
    mismatches = _public_cell_mismatches(page.get("date_cell_mismatches"), known)
    if mismatches:
        date_fields["date_cell_mismatches"] = mismatches
    return date_fields


def _public_page(page, number):
    # Re-project from an allowlist even if called with a stored or externally supplied summary.
    reasons = _mapping(page.get("exclusion_reasons"))
    result = {
        "page": number,
        "status": _category(page.get("status"), _PAGE_STATES),
        "layout_status": _category(page.get("layout_status"), _LAYOUT),
        "profile_issue": _category(page.get("profile_issue"), PROFILE_ISSUES),
        "settle_initial_issue": _category(page.get("settle_initial_issue"), _SETTLE_ISSUES),
        "ordinary_rows": _count(page.get("ordinary_rows"), MAX_ROWS),
        "excluded_rows": _count(page.get("excluded_rows"), MAX_ROWS),
        "list_containers": _count(page.get("list_containers"), 1_000_000),
        "matched_list_containers": _count(page.get("matched_list_containers"), 1_000_000),
        "unsafe_exclusions": _count(page.get("unsafe_exclusions"), MAX_ROWS),
        "exclusion_reasons": {
            key: reasons[key]
            for key in sorted(_EXCLUSION_REASONS)
            if _count(reasons.get(key), MAX_ROWS, 1) is not None
        },
    }
    if result["profile_issue"] == "row_author_count" or result["layout_status"] == "site_verified":
        mismatches = _public_cell_mismatches(
            page.get("author_cell_mismatches"), result["excluded_rows"]
        )
        if mismatches:
            result["author_cell_mismatches"] = mismatches
    if (
        result["profile_issue"] in ("row_date_count", "main_date_field_count")
        or result["layout_status"] == "site_verified"
    ) and isinstance(page.get("date_cells"), dict):
        result.update(_public_date_cells(page, result))
    if result["profile_issue"] == "row_title_link_count":
        raw = _mapping(page.get("title_link_mismatches"))
        counts = _public_cell_mismatches(raw, result["excluded_rows"])
        ordinary = _mapping(raw.get("ordinary")).get("multiple")
        if result["ordinary_rows"] is not None and _count(ordinary, result["ordinary_rows"], 1):
            counts["ordinary"] = {"multiple": ordinary}
        if counts:
            result["title_link_mismatches"] = counts
    return result


def public_list_diagnosis(value):
    """Project a diagnostic on each report/HTTP boundary, including reloaded data."""
    if not isinstance(value, dict):
        return None
    reason = _category(value.get("reason"), DIAGNOSIS_REASONS)
    pages = value.get("pages")
    if reason is None or not isinstance(pages, list):
        return None
    extended = _count(value.get("follow_up_page_limit"), MAX_MONITOR_SCAN_PAGES, 3)
    page_limit = extended or 2
    boundary = _historical_boundary(value.get("historical_boundary_page"), extended)
    recovery = public_recovery_pages(value.get("recovery_page_numbers"), page_limit)
    if recovery is not None and (len(recovery) != len(pages) or boundary is not None):
        recovery = None
    return {
        "reason": reason,
        "transport": _category(value.get("transport"), _TRANSPORT),
        "transport_error_code": _category(value.get("transport_error_code"), _TRANSPORT_ERRORS),
        "http_status": _count(value.get("http_status"), 599, 100),
        "planner_issue": _category(value.get("planner_issue"), PLANNER_ISSUES),
        **({"follow_up_page_limit": extended} if extended else {}),
        **({"historical_boundary_page": boundary} if boundary else {}),
        **({"recovery_page_numbers": recovery} if recovery else {}),
        "pages": [
            _public_page(_mapping(page), _page_number(page, index, boundary, recovery))
            for index, page in enumerate(pages[:page_limit], 1)
        ],
    }


def _stored_row_issue(excluded):
    # Excluded rows retain their column counts in pre-diagnostic snapshots.
    if isinstance(excluded, list) and len(excluded) <= MAX_ROWS:
        for row in excluded:
            fields = _mapping(_mapping(row).get("field_counts"))
            for key, issue in (
                ("number", "row_number_count"),
                ("author", "row_author_count"),
                ("date", "row_date_count"),
                ("title_links", "row_title_link_count"),
            ):
                count = _count(fields.get(key), 1_000_000)
                if count is not None and count != 1:
                    return issue
    return None


def _selected_date_total(page, containers, row_total):
    diagnostics = _mapping(page.get("diagnostics"))
    tables = diagnostics.get("list_candidates")
    if (
        _count(diagnostics.get("list_candidate_total"), 1) == 1
        and diagnostics.get("list_candidates_truncated") is False
        and isinstance(tables, list)
        and len(tables) == _count(containers, MAX_LIST_CANDIDATES, 1)
        and all(isinstance(table, dict) and type(table.get("selected")) is bool for table in tables)
    ):
        selected = [table for table in tables if table["selected"]]
        if len(selected) == 1:
            table = selected[0]
            if (
                table.get("tag") == "TABLE"
                and table.get("qualifies") is True
                and table.get("root_ownership") == "direct_tbody_rows"
                and _count(table.get("ordinary_row_count"), MAX_ROWS) == row_total
            ):
                return _count(table.get("date_field_count"), 1_000_000)
    return None


def date_cell_diagnosis(page, issue):
    """Summarize the selected table and its observed row counts, without their content."""
    evidence = _mapping(page.get("selector_evidence"))
    verified_exceptions = (
        page.get("layout_status") == "site_verified"
        and evidence.get("source") == SPECIAL_DATE_PROFILE_SOURCE
    )
    if not verified_exceptions and issue not in ("row_date_count", "main_date_field_count"):
        return {}
    result = {"date_cells": {}}
    detail = result["date_cells"]
    counts = _mapping(page.get("counts"))
    rows, excluded = page.get("rows"), page.get("excluded_rows")
    n = _count(counts.get("observed_rows"), MAX_ROWS)
    if (
        page.get("status") != "observed"
        or _count(counts.get("list_containers"), 1) != 1
        or n is None
        or not isinstance(rows, list)
        or not isinstance(excluded, list)
        or len(rows) + len(excluded) != n
        or _count(counts.get("ordinary_rows"), n) != len(rows)
        or _count(counts.get("excluded_rows"), n) != len(excluded)
    ):
        return result
    positions = {_count(_mapping(row).get("row_order"), n, 1) for row in [*rows, *excluded]}
    if positions != set(range(1, n + 1)):
        return result
    # The parser admits a row to rows[] only after its date selector matched exactly once.
    detail["ordinary_rows_with_one"] = len(rows)
    excluded_dates = [
        _count(_mapping(_mapping(row).get("field_counts")).get("date"), 1_000_000)
        for row in excluded
    ]
    known = [count for count in excluded_dates if count is not None]
    detail["excluded_rows_counted"] = len(known)
    if len(known) == len(excluded):
        detail["row_cell_total"] = len(rows) + sum(known)
    result["date_cell_mismatches"] = _excluded_cell_mismatches(excluded, "date")
    detail["table_cell_total"] = _selected_date_total(
        page, counts.get("matched_list_containers"), n
    )
    return result


def title_link_diagnosis(page, issue):
    if issue != "row_title_link_count":
        return {}
    counts = _excluded_cell_mismatches(page.get("excluded_rows"), "title_links")
    ordinary = _mapping(page.get("selector_evidence")).get("ordinary_multiple_title_links")
    if _count(ordinary, MAX_ROWS, 1):
        counts["ordinary"] = {"multiple": ordinary}
    return {"title_link_mismatches": counts}


def _stored_page(page):
    counts = _mapping(page.get("counts"))
    evidence = _mapping(page.get("selector_evidence"))
    rows, excluded = page.get("rows"), page.get("excluded_rows")
    issue = _category(evidence.get("profile_issue"), PROFILE_ISSUES)
    # Older observations retained parsed rows and the table inventory, but not
    # every raw ordinary-row column count. Report only a gate these data prove.
    if page.get("layout_status") == "unverified" and issue is None:
        issue = "unavailable"
        scope = _mapping(page.get("scope"))
        if (
            {"gallery_type", "gallery_id", "search_type", "keyword"} <= scope.keys()
            and _category(page.get("status"), _PAGE_STATES) is not None
            and isinstance(rows, list)
            and len(rows) <= MAX_ROWS
            and all(isinstance(row, dict) for row in rows)
        ):
            issue = (
                reviewed_structure_issue(
                    scope,
                    _mapping(page.get("diagnostics")),
                    rows,
                    _stored_row_issue(excluded),
                    _count(counts.get("observed_rows"), MAX_ROWS),
                    _count(counts.get("matched_list_containers"), 1_000_000),
                    page.get("status"),
                )
                or "unavailable"
            )
    reasons = {}
    unsafe = None
    if isinstance(excluded, list) and len(excluded) <= MAX_ROWS:
        unsafe = 0
        for raw in excluded:
            row = _mapping(raw)
            reason = _category(row.get("reason"), _EXCLUSION_REASONS) or "unclassified"
            if not _known_safe_exclusion(row, reason):
                unsafe += 1
                reasons[reason] = reasons.get(reason, 0) + 1
    return {
        "status": page.get("status"),
        "layout_status": page.get("layout_status"),
        "profile_issue": issue,
        "settle_initial_issue": evidence.get("settle_initial_issue"),
        "ordinary_rows": len(rows) if isinstance(rows, list) else None,
        "excluded_rows": len(excluded) if isinstance(excluded, list) else None,
        "list_containers": counts.get("list_containers"),
        "matched_list_containers": counts.get("matched_list_containers"),
        "unsafe_exclusions": unsafe,
        "exclusion_reasons": reasons,
        "author_cell_mismatches": _excluded_cell_mismatches(excluded, "author")
        if issue == "row_author_count"
        or (
            page.get("layout_status") == "site_verified"
            and evidence.get("source")
            in (
                "user_list_diagnosis_alpha3",
                SPECIAL_DATE_PROFILE_SOURCE,
                SPECIAL_TITLE_PROFILE_SOURCE,
            )
        )
        else {},
    }


def _historical_boundary(value, limit):
    if limit == MAX_MONITOR_SCAN_PAGES:
        return _count(value, MAX_HISTORICAL_PAGE - 1, MAX_MONITOR_SCAN_PAGES)
    return None


def _page_number(page, ordinal, boundary, recovery=None):
    if recovery is not None:
        if not 1 <= ordinal <= len(recovery):
            return None
        expected = recovery[ordinal - 1]
        return _count(_mapping(page).get("page"), expected, expected)
    if boundary is None:
        return ordinal
    if not 1 <= ordinal <= MAX_MONITOR_SCAN_PAGES:
        return None
    # Only the two recent pages and the observed boundary pair have labels
    # on this route. A contradictory snapshot cannot supply a page number.
    expected = (1, 2, boundary, boundary + 1)[ordinal - 1]
    return _count(_mapping(page).get("page"), expected, expected)


def diagnose_list_page(
    page,
    ordinal,
    *,
    historical_boundary_page=None,
    recovery_page_numbers=None,
    include_date_cells=True,
):
    """Project a private page's observed validation, counts and proven exceptions."""
    recovery = public_recovery_pages(recovery_page_numbers)
    number = _page_number(page, ordinal, historical_boundary_page, recovery)
    page = _mapping(page)
    stored = _stored_page(page)
    if include_date_cells:
        stored.update(date_cell_diagnosis(page, stored["profile_issue"]))
        stored.update(title_link_diagnosis(page, stored["profile_issue"]))
    return _public_page(stored, number)


def diagnose_list_scan(latest_scan):
    """Read the last scan's evidence without revisiting the site or granting eligibility."""
    if not isinstance(latest_scan, dict) or latest_scan.get("complete") is not False:
        return None
    reason = _category(latest_scan.get("gap_reason"), DIAGNOSIS_REASONS)
    result = _mapping(latest_scan.get("result"))
    outcome = _mapping(result.get("private_observation"))
    if reason is None or not (outcome or result.get("planner_issue")):
        return None
    pages = outcome.get("pages")
    extended = _count(
        _mapping(result.get("control")).get("follow_up_page_limit"), MAX_MONITOR_SCAN_PAGES, 3
    )
    recovery = public_recovery_pages(outcome.get("recovery_page_numbers"), extended or 2)
    historical = _mapping(result.get("historical_follow_up"))
    # The URL selected by the browser still identifies a historical visit when
    # its layout fails validation before the planner can issue a coverage receipt.
    boundary = _historical_boundary(
        historical.get("boundary_page", outcome.get("historical_boundary_page")), extended
    )
    return public_list_diagnosis(
        {
            "reason": reason,
            "transport": outcome.get("status"),
            "transport_error_code": outcome.get("error_code"),
            "http_status": outcome.get("http_status"),
            "planner_issue": result.get("planner_issue"),
            "follow_up_page_limit": extended,
            "historical_boundary_page": boundary,
            "recovery_page_numbers": recovery,
            "pages": [
                diagnose_list_page(
                    page, i, historical_boundary_page=boundary, recovery_page_numbers=recovery
                )
                for i, page in enumerate(pages[: extended or 2], 1)
            ]
            if isinstance(pages, list)
            else [],
        }
    )
