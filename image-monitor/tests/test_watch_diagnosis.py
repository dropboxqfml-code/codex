"""Diagnostics read the original failed observation and never promote its trust."""

import json
from copy import deepcopy

import pytest
from test_search_list import NOW, parse, profile_row, reviewed_raw, row
from test_watch_runtime import BrowserFactory, FakeClock, observed, snapshot, stored

from image_monitor import watch_runtime
from image_monitor.watch_diagnosis import diagnose_list_scan, public_list_diagnosis


def scan(*pages, reason="list_profile_unverified_or_incomplete"):
    return {
        "complete": False,
        "gap_reason": reason,
        "result": {
            "private_observation": {
                "status": "observed",
                "http_status": 200,
                "pages": list(pages),
            }
        },
    }


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (lambda raw: raw["rows"][0].update(author_raw=None), "ordinary_author_missing"),
        (lambda raw: raw["rows"][0].update(published_at_raw=None), "ordinary_date_missing"),
        (
            lambda raw: raw["diagnostics"]["list_candidates"][0].update(writer_field_count=9),
            "main_writer_field_count",
        ),
        (
            lambda raw: raw["diagnostics"]["list_candidates"][1].update(date_field_count=9),
            "secondary_date_field_count",
        ),
        (
            lambda raw: raw["diagnostics"]["list_candidates"][1].update(has_id=False),
            "secondary_table_shape",
        ),
    ],
)
def test_new_and_previous_snapshot_give_specific_safe_shape_issue(change, expected):
    raw = reviewed_raw()
    change(raw)
    page = parse(raw)
    assert page["layout_status"] == "unverified" and not page["queue_eligible"]
    assert page["selector_evidence"]["profile_issue"] == expected
    original = deepcopy(page)
    for legacy in (False, True):
        if legacy:
            del page["selector_evidence"]["profile_issue"]
        result = diagnose_list_scan(scan(page))
        assert result["pages"][0]["profile_issue"] == expected
        assert result["pages"][0]["matched_list_containers"] == 2
        assert result == public_list_diagnosis(result)
        assert original["rows"] == page["rows"]


def test_old_snapshot_retains_provable_column_counts_for_excluded_rows():
    raw = reviewed_raw([profile_row(102), profile_row(101)])
    raw["rows"][0]["field_counts"]["author"] = 0
    page = parse(raw)
    assert page["selector_evidence"].pop("profile_issue") == "row_author_count"
    result = diagnose_list_scan(scan(page))
    assert result["pages"][0]["profile_issue"] == "row_author_count"
    assert result["pages"][0]["exclusion_reasons"] == {"ambiguous_row_fields": 1}


def test_changed_table_has_priority_over_passively_waitable_metadata():
    raw = reviewed_raw()
    raw["rows"][0]["published_at_raw"] = None
    raw["diagnostics"]["list_candidates"][0]["classes"] = ["gall_list", "PRIVATE_CLASS"]
    page = parse(raw)
    assert page["selector_evidence"]["profile_issue"] == "main_table_shape"
    result = diagnose_list_scan(scan(page))
    assert "PRIVATE_CLASS" not in json.dumps(result)


def test_per_page_unsafe_exclusions_are_counted_using_planner_rules():
    regular = profile_row(101)
    missing = row(
        number="", links=[{"href": "https://private.invalid/secret", "text_raw": "PRIVATE"}]
    )
    pin = row("공지", is_pinned=True)
    page = parse(reviewed_raw([regular, missing, pin]))
    result = diagnose_list_scan(scan(page, reason="excluded_rows_unverified"))
    visible = result["pages"][0]
    assert visible["ordinary_rows"] == 1 and visible["excluded_rows"] == 2
    assert visible["unsafe_exclusions"] == 1
    assert visible["exclusion_reasons"] == {"missing_post_number": 1}
    assert "PRIVATE" not in json.dumps(result) and "private.invalid" not in json.dumps(result)


@pytest.mark.parametrize(
    ("page_change", "issue"),
    [
        ({"layout_status": "unverified"}, "snapshot_layout"),
        ({"scan_observed_at": NOW.isoformat()}, "observation_time"),
        ({"scope": {"keyword": "unexpected"}}, "snapshot_identity"),
    ],
)
def test_runtime_keeps_only_typed_planner_issue_in_diagnostic(
    tmp_path, monkeypatch, page_change, issue
):
    monkeypatch.setattr(watch_runtime, "require_windows", lambda: None)
    factory = BrowserFactory(observed(lambda time: snapshot([101], time) | page_change))
    report = watch_runtime.run_watch_trial(tmp_path, backend_factory=factory, clock=FakeClock())
    assert report["status"] == "watch_test_partial"
    saved = stored(tmp_path)["state"]["latest_scan"]
    result = diagnose_list_scan(saved)
    assert result["planner_issue"] == issue
    assert result["transport"] == "observed" and result["http_status"] == 200
    assert result["pages"][0]["ordinary_rows"] == 1
    assert "Invented private" not in json.dumps(result)


def test_projection_bounds_numeric_values_enums_rows_and_keys():
    secret = "private://token"
    candidates = [
        {
            "page": 888,
            "status": secret,
            "profile_issue": secret,
            "settle_initial_issue": secret,
            "ordinary_rows": True,
            "excluded_rows": -1,
            "list_containers": 10**25,
            "unsafe_exclusions": [],
            "exclusion_reasons": {secret: 1, "survey": -1, "pinned": 9},
            "secret": secret,
        }
    ] * 3
    value = {
        "reason": "order_unverified",
        "transport": [secret],
        "http_status": 888,
        "pages": candidates,
        "planner_issue": secret,
    }
    result = public_list_diagnosis(value)
    assert [page["page"] for page in result["pages"]] == [1, 2]
    assert all(page["profile_issue"] is None for page in result["pages"])
    assert result["pages"][0]["exclusion_reasons"] == {"pinned": 9}
    assert "private" not in json.dumps(result)
    assert result["http_status"] is None and result["pages"][0]["ordinary_rows"] is None
    assert public_list_diagnosis(result) == result


def test_empty_absent_and_resolved_diagnostics():
    assert diagnose_list_scan(None) is None
    assert diagnose_list_scan(scan() | {"complete": True}) is None
    assert diagnose_list_scan(scan(reason="private://token")) is None
    assert diagnose_list_scan({"complete": False, "gap_reason": "order_unverified"}) is None
    failed = scan(reason="list_transport_or_inspection_failure")
    failed["result"]["private_observation"] = {"status": "http_error", "http_status": 429}
    assert diagnose_list_scan(failed) == {
        "reason": "list_transport_or_inspection_failure",
        "transport": "http_error",
        "transport_error_code": None,
        "http_status": 429,
        "planner_issue": None,
        "pages": [],
    }
