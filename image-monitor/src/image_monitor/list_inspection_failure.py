"""Coded list-document failures, without diagnostic strings or page contents."""

from image_monitor.dcinside import DCSnapshotError
from image_monitor.list_links import validate_list_url
from image_monitor.monitor_gap_report import public_recovery_pages
from image_monitor.watch_store import MAX_MONITOR_SCAN_PAGES, MONITOR_SCOPE

_REASONS = {
    "observation_clock": {"outside_scan_window"},
    "document_identity": {
        "before_dom_url_invalid",
        "before_dom_url_mismatch",
        "after_dom_url_invalid",
        "after_dom_url_mismatch",
    },
    "dom_read": {"dom_evaluation_failed", "dom_budget_exceeded"},
    "snapshot_parse": {
        "bounded_text_invalid",
        "count_invalid",
        "selected_count_invalid",
        "row_link_limit",
        "row_evidence_invalid",
        "snapshot_shape_invalid",
        "snapshot_url_invalid",
        "snapshot_url_mismatch",
        "row_limit",
        "pagination_limit",
        "inventory_mismatch",
        "pagination_invalid",
        "parse_failed",
    },
    "document_settle": {"document_replaced", "same_url_document_replaced"},
}


def list_snapshot_error(stage, reason, message, *, diagnostics=None):
    """Keep the existing exception type and assign a code at the rejecting check."""
    error = DCSnapshotError(message, diagnostics=diagnostics)
    error.inspection_stage = stage
    error.inspection_reason = reason
    return error


def public_inspection_failure(value):
    if not isinstance(value, dict):
        return None
    stage, reason, sample = (value.get(key) for key in ("stage", "reason", "sample"))
    visit, page = value.get("visit"), value.get("page")
    if (
        not isinstance(stage, str)
        or stage not in _REASONS
        or not isinstance(reason, str)
        or reason not in _REASONS[stage]
        or not isinstance(sample, str)
        or sample not in {"initial", "settled"}
        or type(visit) is not int
        or not 1 <= visit <= MAX_MONITOR_SCAN_PAGES
        or type(page) is not int
        or not 1 <= page <= 999_999_999
        or (visit == 1 and page != 1)
        or (visit == 2 and page not in (1, 2))
    ):
        return None
    return {"stage": stage, "reason": reason, "sample": sample, "visit": visit, "page": page}


def inspection_page_numbers(outcome):
    """Identify successfully returned documents ending in one unmatched inspection."""
    if not isinstance(outcome, dict):
        return None
    if (
        outcome.get("status") != "inspection_error"
        or outcome.get("error_type") != "DCSnapshotError"
        or outcome.get("retry_after") is not None
    ):
        return None
    visits, pages = outcome.get("navigation"), outcome.get("pages")
    if (
        not isinstance(visits, list)
        or not isinstance(pages, list)
        or not 1 <= len(visits) <= MAX_MONITOR_SCAN_PAGES
        or len(pages) + 1 != len(visits)
    ):
        return None
    numbers = []
    for index, visit in enumerate(visits):
        if not isinstance(visit, dict):
            return None
        http = visit.get("http_status")
        if type(http) is not int or not 200 <= http < 300 or visit.get("retry_after") is not None:
            return None
        url = visit.get("url")
        try:
            target = validate_list_url(url)
        except DCSnapshotError:
            return None
        if (
            target["canonical_url"] != url
            or target["navigation"]
            or any(
                target[key] != getattr(MONITOR_SCOPE, key)
                for key in ("gallery_type", "gallery_id", "keyword", "search_type")
            )
        ):
            return None
        numbers.append(target["page"])
        if index < len(pages):
            page = pages[index]
            if (
                not isinstance(page, dict)
                or page.get("url") != url
                or type(page.get("page")) is not int
                or page["page"] != target["page"]
                or page.get("search_pos") != target["search_pos"]
            ):
                return None
    if (
        type(outcome.get("http_status")) is not int
        or outcome["http_status"] != visits[-1]["http_status"]
    ):
        return None
    return public_recovery_pages(numbers)


def bound_inspection_failure(outcome):
    """Bind an optional worker code to the exact final document navigation."""
    if not isinstance(outcome, dict):
        return None
    failure = public_inspection_failure(outcome.get("inspection_failure"))
    if failure is None:
        return None
    numbers = inspection_page_numbers(outcome)
    if numbers is None or failure["visit"] != len(numbers) or failure["page"] != numbers[-1]:
        return None
    return failure
