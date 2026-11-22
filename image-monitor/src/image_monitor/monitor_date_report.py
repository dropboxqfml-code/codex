"""Report verified special-row date counts for this list check."""

from image_monitor.monitor_gap_report import public_recovery_pages
from image_monitor.search_list import SPECIAL_DATE_PROFILE_SOURCE
from image_monitor.watch_diagnosis import _public_page, diagnose_list_page


def verified_date_cell_checks(pages):
    """Read anonymous counts only from pages accepted with the special-row date rule."""
    numbers = [page["page"] for page in pages]
    checks = []
    for visit, page in enumerate(pages, 1):
        if (
            page.get("layout_status") == "site_verified"
            and page.get("selector_evidence", {}).get("source") == SPECIAL_DATE_PROFILE_SOURCE
        ):
            check = diagnose_list_page(page, visit, recovery_page_numbers=numbers)
            checks.append(check | {"visit": visit})
    return public_date_cell_checks(checks, numbers)


def public_date_cell_checks(checks, numbers):
    """Associate each displayed count with one verified visit, even across search windows."""
    visits = public_recovery_pages(numbers)
    if visits is None or not isinstance(checks, list) or len(checks) > len(visits):
        return []
    public = []
    previous = 0
    for check in checks:
        if not isinstance(check, dict):
            return []
        visit = check.get("visit")
        if type(visit) is not int or not previous < visit <= len(visits):
            return []
        previous = visit
        number = visits[visit - 1]
        if type(check.get("page")) is not int or check["page"] != number:
            return []
        page = _public_page(check, number)
        mismatches = page.get("date_cell_mismatches")
        cells = page.get("date_cells", {})
        if (
            page["layout_status"] != "site_verified"
            or not mismatches
            or set(mismatches) - {"ad", "pinned", "survey"}
            or cells.get("table_check") != "matches_rows"
        ):
            return []
        public.append(
            {
                "visit": visit,
                "page": number,
                "layout_status": page["layout_status"],
                "ordinary_rows": page["ordinary_rows"],
                "excluded_rows": page["excluded_rows"],
                "date_cells": cells,
                "date_cell_mismatches": mismatches,
            }
        )
    return public
