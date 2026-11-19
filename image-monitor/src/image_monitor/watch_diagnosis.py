"""Explain an incomplete list scan using bounded structural evidence only."""

from image_monitor.search_list import MAX_ROWS, PROFILE_ISSUES, reviewed_structure_issue
from image_monitor.watch_planner import WatchPlanError, _exclusion_evidence, _safe_exclusion

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
    "secondary_table_empty",
}


def _category(value, allowed):
    return value if isinstance(value, str) and value in allowed else None


def _count(value, maximum, minimum=0):
    return value if type(value) is int and minimum <= value <= maximum else None


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _public_page(page, ordinal):
    # Re-project from an allowlist even if called with a stored or externally supplied summary.
    reasons = _mapping(page.get("exclusion_reasons"))
    return {
        "page": ordinal,
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


def public_list_diagnosis(value):
    """Project a diagnostic on each report/HTTP boundary, including reloaded data."""
    if not isinstance(value, dict):
        return None
    reason = _category(value.get("reason"), DIAGNOSIS_REASONS)
    pages = value.get("pages")
    if reason is None or not isinstance(pages, list):
        return None
    return {
        "reason": reason,
        "transport": _category(value.get("transport"), _TRANSPORT),
        "transport_error_code": _category(value.get("transport_error_code"), _TRANSPORT_ERRORS),
        "http_status": _count(value.get("http_status"), 599, 100),
        "planner_issue": _category(value.get("planner_issue"), PLANNER_ISSUES),
        "pages": [_public_page(_mapping(page), index) for index, page in enumerate(pages[:2], 1)],
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
            try:
                known_safe = _safe_exclusion(
                    {"reason": reason} | _exclusion_evidence(row), "site_verified"
                )
            except WatchPlanError:
                known_safe = False
            if not known_safe:
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
    }


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
    return public_list_diagnosis(
        {
            "reason": reason,
            "transport": outcome.get("status"),
            "transport_error_code": outcome.get("error_code"),
            "http_status": outcome.get("http_status"),
            "planner_issue": result.get("planner_issue"),
            "pages": [_stored_page(_mapping(page)) for page in pages[:2]]
            if isinstance(pages, list)
            else [],
        }
    )
