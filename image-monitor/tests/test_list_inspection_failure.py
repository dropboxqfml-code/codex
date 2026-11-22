"""Only the failed document and the exact rejecting check can supply a failure code."""

import json
from unittest.mock import Mock

import pytest
from test_search_list import NOW, URL, raw_snapshot
from test_watch_browser import PAGE_ONE, PAGE_TWO, snapshot

from image_monitor.dcinside import DCSnapshotError
from image_monitor.list_inspection_failure import (
    bound_inspection_failure,
    inspection_page_numbers,
    public_inspection_failure,
)
from image_monitor.search_list import MAX_PAGINATION, MAX_ROWS, inspect_list


@pytest.mark.parametrize(
    "case, stage, reason",
    [
        ("url_before", "document_identity", "before_dom_url_mismatch"),
        ("foreign_before", "document_identity", "before_dom_url_invalid"),
        ("url_after", "document_identity", "after_dom_url_mismatch"),
        ("foreign_after", "document_identity", "after_dom_url_invalid"),
        ("budget", "dom_read", "dom_budget_exceeded"),
        ("thrown_budget_text", "dom_read", "dom_evaluation_failed"),
        ("invalid_shape", "snapshot_parse", "snapshot_shape_invalid"),
        ("list_identity", "snapshot_parse", "snapshot_url_mismatch"),
        ("row_cap", "snapshot_parse", "row_limit"),
        ("pagination_cap", "snapshot_parse", "pagination_limit"),
        ("count_mismatch", "snapshot_parse", "inventory_mismatch"),
    ],
)
def test_failure_taxonomy_comes_from_rejecting_check(case, stage, reason):
    page = Mock()
    page.url = URL

    def evaluate(*_):
        if case in {"url_after", "foreign_after"}:
            page.url = URL.replace("page=1", "page=2") if case == "url_after" else "about:blank"
        if case == "budget":
            return {"list_dom_budget_exceeded": True}
        if case == "thrown_budget_text":
            raise RuntimeError("List DOM budget exhausted: PRIVATE URL")
        if case == "invalid_shape":
            return None
        if case == "list_identity":
            return raw_snapshot(document_url=URL.replace("page=1", "page=2"))
        if case == "row_cap":
            return raw_snapshot(row_total=MAX_ROWS + 1)
        if case == "pagination_cap":
            return raw_snapshot(pagination_total=MAX_PAGINATION + 1)
        if case == "count_mismatch":
            return raw_snapshot(pagination_total=1, pagination=[])
        return raw_snapshot()

    page.evaluate.side_effect = evaluate
    if case in {"url_before", "foreign_before"}:
        page.url = URL.replace("page=1", "page=2") if case == "url_before" else "about:blank"
    with pytest.raises(DCSnapshotError) as failed:
        inspect_list(page, expected_url=URL, observed_at=NOW)
    assert (failed.value.inspection_stage, failed.value.inspection_reason) == (stage, reason)
    page.goto.assert_not_called()


def outcome():
    return {
        "status": "inspection_error",
        "error_type": "DCSnapshotError",
        "http_status": 200,
        "retry_after": None,
        "pages": [snapshot()],
        "navigation": [
            {"url": u, "http_status": 200, "retry_after": None} for u in (PAGE_ONE, PAGE_TWO)
        ],
        "inspection_failure": {
            "stage": "dom_read",
            "reason": "dom_budget_exceeded",
            "sample": "initial",
            "page": 2,
            "visit": 2,
        },
    }


@pytest.mark.parametrize(
    "changed",
    [
        "legacy",
        "truthy_bool",
        "wrong_attempt",
        "wrong_page",
        "other_scope",
        "header",
        "unmatched_http",
        "extra_snapshot",
        "changed_prefix",
        "failed_prefix",
        "unsupported_error",
        "raw_category",
        "private_note",
    ],
)
def test_private_marker_requires_the_exact_final_unmatched_navigation(changed):
    raw = outcome()
    failure = dict(raw["inspection_failure"])
    if changed == "legacy":
        del raw["inspection_failure"]
        assert inspection_page_numbers(raw) == [1, 2]
    elif changed == "truthy_bool":
        raw["inspection_failure"]["visit"] = True
    elif changed == "wrong_attempt":
        raw["inspection_failure"].update(visit=1, page=1)
    elif changed == "wrong_page":
        raw["inspection_failure"]["page"] = 1
    elif changed == "other_scope":
        raw["navigation"][-1]["url"] = PAGE_TWO.replace("comic_new6", "private")
    elif changed == "header":
        raw["navigation"][-1]["retry_after"] = "90"
    elif changed == "unmatched_http":
        raw["http_status"] = 201
    elif changed == "extra_snapshot":
        raw["pages"].append(snapshot(url=PAGE_TWO))
    elif changed == "changed_prefix":
        raw["pages"][0]["url"] = PAGE_TWO
    elif changed == "failed_prefix":
        raw["navigation"][0]["http_status"] = 503
    elif changed == "unsupported_error":
        raw["error_type"] = "Error"
    elif changed == "raw_category":
        raw["inspection_failure"]["reason"] = "https://private.invalid/"
    else:
        raw["inspection_failure"]["private_note"] = "secret"
        assert bound_inspection_failure(raw) == failure
        assert "secret" not in json.dumps(public_inspection_failure(raw["inspection_failure"]))
        return
    assert bound_inspection_failure(raw) is None
