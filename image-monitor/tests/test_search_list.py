import json
import shutil
import sys
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from image_monitor.dcinside import DCSnapshotError
from image_monitor.search_list import (
    MAX_LIST_CANDIDATES,
    MAX_PAGINATION,
    MAX_PAGINATION_SAMPLES,
    MAX_ROWS,
    build_list_url,
    inspect_list,
    parse_list_snapshot,
    validate_list_url,
)

URL = build_list_url("normal", "comic_new6", "ai")
POST = "https://gall.dcinside.com/board/view/?id=comic_new6&no=7036949"
NOW = datetime(2026, 11, 15, tzinfo=UTC)


def row(number="7036949", **changes):
    result = {
        "number_raw": number,
        "is_ad": False,
        "is_pinned": False,
        "field_counts": {"number": 1, "author": 1, "date": 1},
        "link_total": 1,
        "links": [{"href": POST, "text_raw": "합성 ai 글"}],
        "author_raw": "공개 필명 (123.45)",
        "published_at_raw": "10:23",
    }
    result.update(changes)
    result.setdefault("all_links", [{"href": link.get("href")} for link in result["links"]])
    result.setdefault("all_link_total", result["link_total"])
    return result


def raw_snapshot(rows=None, **changes):
    rows = [row()] if rows is None else rows
    return {
        "document_url": URL,
        "list_count": 1,
        "row_total": len(rows),
        "rows": rows,
        "empty_marker_count": 0,
        "pagination_total": 0,
        "pagination": [],
        "diagnostics": {},
    } | changes


def parse(raw, **options):
    return parse_list_snapshot(raw, expected_url=URL, observed_at=NOW, **options)


def exclusion_pairs(snapshot):
    return [
        {key: entry[key] for key in ("row_order", "reason")} for entry in snapshot["excluded_rows"]
    ]


def profile_row(number):
    return row(
        str(number),
        links=[{"href": f"/board/view/?id=comic_new6&no={number}", "text_raw": "fixture ai"}],
    )


def reviewed_raw(rows=None):
    rows = [profile_row(101)] if rows is None else rows
    main = {
        "tag": "TABLE",
        "classes": ["gall_list"],
        "root_ownership": "direct_tbody_rows",
        "has_id": False,
        "qualifies": True,
        "selected": True,
        "table_row_count": len(rows),
        "ordinary_row_count": len(rows),
        "number_field_count": len(rows),
        "writer_field_count": len(rows),
        "date_field_count": len(rows),
        "title_link_count": sum(entry["link_total"] for entry in rows),
        "empty_marker_count": 0,
        "visible_empty_marker_count": 0,
    }
    secondary = main | {
        "has_id": True,
        "qualifies": False,
        "selected": False,
        "table_row_count": 3,
        "ordinary_row_count": 0,
        "number_field_count": 3,
        "writer_field_count": 0,
        "date_field_count": 3,
        "title_link_count": 3,
    }
    return raw_snapshot(
        rows,
        list_container_count=2,
        diagnostics={
            "list_candidates": [main, secondary],
            "list_candidate_total": 1,
            "list_candidates_truncated": False,
        },
    )


@pytest.mark.parametrize("ordinary_count", [1, 7, 31])
def test_reviewed_structure_supports_bounded_dynamic_row_counts_without_queue_approval(
    ordinary_count,
):
    snapshot = parse(
        reviewed_raw([profile_row(number) for number in range(100, 100 + ordinary_count)])
    )
    assert snapshot["layout_status"] == "site_verified"
    assert snapshot["selector_evidence"]["verification_scope"] == "reviewed_search_structure"
    assert snapshot["selector_evidence"]["source"] == "user_list_probe_v12"
    assert snapshot["selector_evidence"]["live_layout_verified"]
    assert snapshot["rows_complete"]
    assert not snapshot["queue_eligible"]
    assert not snapshot["end_of_results"]
    assert not snapshot["pagination_complete"]


@pytest.mark.parametrize(
    "url",
    [
        build_list_url("normal", "another", "ai"),
        build_list_url("minor", "comic_new6", "ai"),
        build_list_url("mini", "comic_new6", "ai"),
        build_list_url("normal", "comic_new6", "AI"),
        URL + "&search_head=7",
    ],
)
def test_reviewed_structure_does_not_promote_other_galleries_searches_or_filters(url):
    snapshot = parse_list_snapshot(
        reviewed_raw() | {"document_url": url}, expected_url=url, observed_at=NOW
    )
    assert snapshot["layout_status"] == "unverified"
    assert not snapshot["selector_evidence"]["live_layout_verified"]


@pytest.mark.parametrize(
    "changes",
    [
        {"has_id": True},
        {"root_ownership": "descendant_rows"},
        {"number_field_count": 2},
        {"writer_field_count": 0},
        {"date_field_count": 0},
        {"title_link_count": 2},
        {"table_row_count": 2},
    ],
)
def test_reviewed_structure_requires_exact_main_root_and_owned_fields(changes):
    raw = reviewed_raw()
    raw["diagnostics"]["list_candidates"][0].update(changes)
    assert parse(raw)["layout_status"] == "unverified"


@pytest.mark.parametrize("writer_count", [0, 2])
@pytest.mark.parametrize("reason", ["ad", "pinned", "survey"])
def test_only_proven_special_rows_can_have_nonstandard_writer_counts(reason, writer_count):
    if reason == "survey":
        special = row("설문", links=[{"href": "javascript:privateAction()"}])
    else:
        special = row("AD" if reason == "ad" else "공지", **{"is_" + reason: True})
    special["field_counts"]["author"] = writer_count
    special["author_raw"] = "PRIVATE_WRITER"
    raw = reviewed_raw([profile_row(102), special, profile_row(101)])
    main = raw["diagnostics"]["list_candidates"][0]
    main["writer_field_count"] = 2 + writer_count
    snapshot = parse(raw)
    assert snapshot["layout_status"] == "site_verified"
    assert snapshot["rows_complete"] and not snapshot["queue_eligible"]
    assert snapshot["selector_evidence"]["source"] == "user_list_diagnosis_alpha3"
    assert [item["post_id"] for item in snapshot["rows"]] == ["102", "101"]
    assert snapshot["excluded_rows"][0]["reason"] == reason
    assert snapshot["excluded_rows"][0]["field_counts"]["author"] == writer_count
    assert "PRIVATE_WRITER" not in json.dumps(snapshot)
    # A matching count outside the owned rows still represents an unknown table shape.
    main["writer_field_count"] += 1
    snapshot = parse(raw)
    assert snapshot["layout_status"] == "unverified"
    assert snapshot["selector_evidence"]["profile_issue"] == "main_writer_field_count"


@pytest.mark.parametrize(
    "unrecognized",
    [
        profile_row(101),
        row("설문", links=[{"href": POST}]),
        row("AD label in a title"),
        row("private notice"),
    ],
)
@pytest.mark.parametrize("writer_count", [0, 2])
def test_malformed_ordinary_or_unproven_row_stays_unverified(unrecognized, writer_count):
    entry = unrecognized | {"field_counts": {"number": 1, "date": 1, "author": writer_count}}
    # Offsetting defects sum to the reviewed total but cannot cancel one another.
    special = row("공지", is_pinned=True)
    special["field_counts"]["author"] = 2 - writer_count
    raw = reviewed_raw([profile_row(102), special, entry])
    snapshot = parse(raw)
    assert snapshot["layout_status"] == "unverified"
    assert snapshot["selector_evidence"]["profile_issue"] == "row_author_count"
    assert not snapshot["rows_complete"]
    assert not snapshot["queue_eligible"]


@pytest.mark.parametrize("field", ["number", "date", "title_links"])
def test_other_shape_checks_still_apply_to_proven_special_rows(field):
    special = row("공지", is_pinned=True)
    special["field_counts"]["author"] = 0
    if field == "title_links":
        special.update(links=[], link_total=0, all_links=[], all_link_total=0)
    else:
        special["field_counts"][field] = 0
    raw = reviewed_raw([profile_row(101), special])
    raw["diagnostics"]["list_candidates"][0]["writer_field_count"] = 1
    snapshot = parse(raw)
    assert snapshot["layout_status"] == "unverified"
    assert snapshot["selector_evidence"]["profile_issue"] in {
        "row_number_count",
        "row_date_count",
        "row_title_link_count",
    }


@pytest.mark.parametrize("missing", ["title", "author", "date"])
def test_reviewed_structure_requires_visible_ordinary_metadata(missing):
    entry = profile_row(101)
    if missing == "title":
        entry["links"][0]["text_raw"] = None
    else:
        entry[{"author": "author_raw", "date": "published_at_raw"}[missing]] = None
    assert parse(reviewed_raw([entry]))["layout_status"] == "unverified"


def test_unknown_non_numeric_exclusion_preserves_structure_and_blocks_row_completeness():
    unknown = row(
        "unreviewed label", links=[{"href": "javascript:fixtureAction()", "text_raw": "secret"}]
    )
    snapshot = parse(reviewed_raw([unknown, profile_row(101)]))
    assert snapshot["layout_status"] == "site_verified"
    assert not snapshot["rows_complete"]
    assert snapshot["excluded_rows"] == [
        {
            "row_order": 1,
            "reason": "non_numeric",
            "number_kind": "other",
            "link_schemes": {"javascript": 1},
            "field_counts": {"number": 1, "author": 1, "date": 1, "title_links": 1},
            "role_flags": {"is_ad": False, "is_pinned": False},
        }
    ]
    assert "unreviewed label" not in json.dumps(snapshot)
    assert "fixtureAction" not in json.dumps(snapshot)
    assert "secret" not in json.dumps(snapshot)


def test_exact_rendered_survey_label_and_one_action_only_link_are_safe_exclusion_evidence():
    survey = row(
        "설문", links=[{"href": "javascript:fixtureSurvey()", "text_raw": "private title"}]
    )
    snapshot = parse(reviewed_raw([survey, profile_row(101)]))
    assert snapshot["excluded_rows"][0] == {
        "row_order": 1,
        "reason": "survey",
        "number_kind": "survey_label",
        "link_schemes": {"javascript": 1},
        "field_counts": {"number": 1, "author": 1, "date": 1, "title_links": 1},
        "role_flags": {"is_ad": False, "is_pinned": False},
    }
    assert snapshot["rows_complete"]
    assert snapshot["layout_status"] == "site_verified"
    assert "fixtureSurvey" not in json.dumps(snapshot)
    assert "private title" not in json.dumps(snapshot)


@pytest.mark.parametrize(
    "number,links",
    [
        ("설문 ", [{"href": "javascript:fixtureSurvey()"}]),
        ("other", [{"href": "javascript:fixtureSurvey()"}]),
        ("설문", [{"href": "/board/view/?id=comic_new6&no=101"}]),
        (
            "설문",
            [{"href": "javascript:fixtureSurvey()"}, {"href": "/board/view/?id=comic_new6&no=101"}],
        ),
        ("설문", [{"href": "javascript:first()"}, {"href": "javascript:second()"}]),
    ],
)
def test_unresolved_labels_and_mixed_post_links_never_become_safe_surveys(number, links):
    snapshot = parse(raw_snapshot([row(number, links=links, link_total=len(links))]))
    assert snapshot["excluded_rows"][0]["reason"] == "non_numeric"
    assert not snapshot["rows_complete"]


def test_survey_requires_all_owned_anchors_to_exclude_an_actual_post_identity():
    action = {"href": "javascript:fixtureSurvey()"}
    entry = row(
        "설문",
        links=[action],
        all_link_total=2,
        all_links=[action, {"href": "/board/view/?id=comic_new6&no=101"}],
    )
    snapshot = parse(raw_snapshot([entry]))
    assert snapshot["excluded_rows"][0]["reason"] == "non_numeric"
    assert snapshot["excluded_rows"][0]["link_schemes"] == {"javascript": 1, "relative": 1}
    assert not snapshot["rows_complete"]
    entry.pop("all_links")
    entry.pop("all_link_total")
    assert parse(raw_snapshot([entry]))["excluded_rows"][0]["reason"] == "non_numeric"


@pytest.mark.parametrize(
    "kind,path",
    [
        ("normal", "/board/lists/"),
        ("minor", "/mgallery/board/lists/"),
        ("mini", "/mini/board/lists/"),
    ],
)
def test_constructed_gallery_urls_are_synthetic_identities_only(kind, path):
    url = build_list_url(kind, "gallery_x", "ai 그림")
    identity = validate_list_url(url)
    assert identity == {
        "gallery_type": kind,
        "gallery_id": "gallery_x",
        "search_type": "search_subject_memo",
        "keyword": "ai 그림",
        "page": 1,
        "search_pos": None,
        "navigation": {},
        "canonical_url": url,
    }
    assert url.startswith("https://gall.dcinside.com" + path)


def test_identity_normalizes_page_and_cursor_but_preserves_exact_filters_and_keyword():
    identity = validate_list_url(URL + "&search_pos=-000123&search_head=7&exception_mode=recommend")
    assert identity["search_pos"] == "-123"
    assert identity["navigation"] == {"search_head": "7", "exception_mode": "recommend"}
    without_page = URL.removesuffix("&page=1")
    assert validate_list_url(without_page)["canonical_url"] == URL
    assert validate_list_url(URL.replace("ai", "AI"))["keyword"] == "AI"
    assert build_list_url("normal", "comic_new6", "ai") == URL
    assert "search_pos" not in URL


@pytest.mark.parametrize(
    "invalid",
    [
        URL.replace("https:", "http:"),
        URL.replace("gall.dcinside.com", "gall.dcinside.com.evil.invalid"),
        URL.replace("gall.dcinside.com", "user@gall.dcinside.com"),
        URL.replace("gall.dcinside.com", "gall.dcinside.com:443"),
        URL.replace("/lists/", "/view/"),
        URL.replace("/lists/", "/lists//"),
        URL + "#fragment",
        URL + "&id=other",
        URL + "&page=2",
        URL + "&search_pos=1&search_pos=2",
        URL + "&redirect=https://evil.invalid",
        URL + "&no=7",
        URL.replace("s_type=search_subject_memo", "s_type=search_subject"),
        URL.replace("s_type=search_subject_memo&", ""),
        URL.replace("id=comic_new6", "id=..%2Fother"),
        URL.replace("s_keyword=ai", "s_keyword="),
        URL.replace("s_keyword=ai", "s_keyword=%20ai"),
        URL.replace("s_keyword=ai", "s_keyword=ai%00"),
        URL.replace("s_keyword=ai", "s_keyword=a%C2%85b"),
        URL.replace("s_keyword=ai", "s_keyword=%FF"),
        URL.replace("s_keyword=ai", "s_keyword=%GG"),
        URL.replace("s_keyword=ai", "s_keyword=ai%"),
        URL.replace("page=1", "page=0"),
        URL.replace("page=1", "page=-1"),
        URL.replace("page=1", "page=1000000000"),
        URL + "&search_pos=+123",
        URL + "&search_pos=1%0A",
        URL + "&search_head=abc",
        URL + "&exception_mode=a%2Fb",
        URL + "&broken",
    ],
)
def test_ambiguous_or_wrong_search_urls_fail_closed(invalid):
    with pytest.raises(DCSnapshotError):
        validate_list_url(invalid)


@pytest.mark.parametrize(
    "changes",
    [
        {"gallery_type": "other"},
        {"gallery_type": []},
        {"gallery_id": "../x"},
        {"keyword": ""},
        {"keyword": "a\nb"},
        {"keyword": "a\ud800b"},
        {"page": True},
        {"page": 0},
        {"search_pos": 123},
        {"search_pos": ""},
    ],
)
def test_bad_construction_options_fail_closed(changes):
    args = {"gallery_type": "normal", "gallery_id": "comic_new6", "keyword": "ai"} | changes
    with pytest.raises(DCSnapshotError):
        build_list_url(**args)


def test_explicit_blank_display_link_cursor_is_the_latest_search_window():
    assert validate_list_url(URL + "&search_pos=")["canonical_url"] == URL
    raw = raw_snapshot(
        pagination_total=1,
        pagination=[{"href": URL.replace("page=1", "page=2") + "&search_pos="}],
    )
    snapshot = parse(raw)
    assert snapshot["pagination_candidates"][0]["search_pos"] is None
    sample = snapshot["diagnostics"]["pagination_samples"][0]
    assert sample["query_value_categories"]["search_pos"] == "empty"
    assert sample["validation_status"] == "accepted"


@pytest.mark.parametrize("layout", ["unverified", "fixture_validated"])
def test_public_shown_metadata_has_exact_ids_raw_dates_and_never_queue_permission(layout):
    snapshot = parse(raw_snapshot(), layout_status=layout)
    assert snapshot["status"] == "observed"
    assert snapshot["rows"] == [
        {
            "row_order": 1,
            "post_id": "7036949",
            "canonical_url": POST,
            "title": "합성 ai 글",
            "author_raw": "공개 필명 (123.45)",
            "published_at_raw": "10:23",
        }
    ]
    assert not snapshot["queue_eligible"]
    assert not snapshot["selector_evidence"]["live_layout_verified"]
    assert not snapshot["end_of_results"]
    assert not snapshot["pagination_complete"]
    assert "published_at" not in snapshot["rows"][0]
    assert "ip_display" not in snapshot["rows"][0]
    json.dumps(snapshot)


@pytest.mark.parametrize(
    "entry,reason",
    [
        (row(is_pinned=True), "pinned"),
        (row(is_ad=True), "ad"),
        (row("공지"), "non_numeric"),
        (row("0"), "invalid_post_number"),
        (row("1" * 21), "invalid_post_number"),
        (row(None), "missing_post_number"),
        (row(""), "missing_post_number"),
        (row(None, field_counts={"number": 0, "author": 1, "date": 1}), "ambiguous_row_fields"),
        (row(None, field_counts={"number": 2, "author": 1, "date": 1}), "ambiguous_row_fields"),
        (row("7"), "post_number_mismatch"),
        (row(field_counts={"number": 2, "author": 1, "date": 1}), "ambiguous_row_fields"),
        (
            row(links=[{"href": POST.replace("comic_new6", "another"), "text_raw": "x"}]),
            "wrong_gallery",
        ),
        (
            row(links=[{"href": POST.replace("/board/", "/mini/board/"), "text_raw": "x"}]),
            "wrong_gallery",
        ),
        (row(links=[{"href": "javascript:alert(1)", "text_raw": "x"}]), "invalid_post_link"),
        (
            row(links=[{"href": POST.replace("https:", "http:"), "text_raw": "x"}]),
            "invalid_post_link",
        ),
        (
            row(
                links=[
                    {"href": "https://gall.dcinside.com/?id=comic_new6&no=7036949", "text_raw": "x"}
                ]
            ),
            "invalid_post_link",
        ),
        (row(links=[{"href": POST, "text_raw": None}]), "missing_title"),
    ],
)
def test_nonordinary_or_uncertain_rows_have_bounded_evidence(entry, reason):
    snapshot = parse(raw_snapshot([entry]))
    assert snapshot["rows"] == []
    assert exclusion_pairs(snapshot) == [{"row_order": 1, "reason": reason}]
    assert snapshot["status"] == "observed"


@pytest.mark.parametrize("number_count", [0, 2])
def test_missing_or_duplicate_number_cells_cannot_advance_fixture_planner(number_count):
    from image_monitor.watch_planner import plan_scan
    from image_monitor.watch_store import WatchScope

    scope = WatchScope("fixture", "normal", "comic_new6", "ai", "search_subject_memo")

    def ordinary(number):
        return row(
            str(number),
            links=[{"href": POST.replace("7036949", str(number)), "text_raw": f"ai {number}"}],
        )

    baseline_page = parse(raw_snapshot([ordinary(100)]), layout_status="fixture_validated")
    empty = {"generation": 0, "baseline": None, "checkpoint": None, "latest_scan": None}
    baseline = plan_scan(scope, empty, [baseline_page], NOW, synthetic_fixture=True)
    state = empty | {
        "generation": 1,
        "baseline": baseline["baseline"],
        "checkpoint": baseline["checkpoint"],
    }
    unresolved = ordinary(103) | {
        "number_raw": None,
        "field_counts": {"number": number_count, "author": 1, "date": 1},
    }
    ambiguous_page = parse(
        raw_snapshot([ordinary(104), unresolved, ordinary(100)], fixture_end_of_results=True),
        layout_status="fixture_validated",
    )
    assert exclusion_pairs(ambiguous_page) == [{"row_order": 2, "reason": "ambiguous_row_fields"}]
    result = plan_scan(scope, state, [ambiguous_page], NOW, synthetic_fixture=True)
    assert not result["complete"]
    assert result["gap_reason"] == "excluded_rows_unverified"
    repaired_page = parse(
        raw_snapshot([ordinary(104), ordinary(103), ordinary(100)], fixture_end_of_results=True),
        layout_status="fixture_validated",
    )
    repaired = plan_scan(scope, state, [repaired_page], NOW, synthetic_fixture=True)
    assert repaired["complete"]
    assert [item["post_id"] for item in repaired["candidates"]] == ["104", "103"]


def test_ambiguous_links_duplicate_ids_and_numeric_cell_mismatch_are_not_post_identity():
    ambiguous = row(
        link_total=2,
        links=[
            {"href": POST, "text_raw": "x"},
            {"href": POST.replace("7036949", "7036950"), "text_raw": "x"},
        ],
    )
    assert parse(raw_snapshot([ambiguous]))["excluded_rows"][0]["reason"] == (
        "ambiguous_post_identity"
    )
    duplicate = parse(raw_snapshot([row(), row()]))
    assert len(duplicate["rows"]) == 1
    assert exclusion_pairs(duplicate) == [{"row_order": 2, "reason": "duplicate_post_id"}]


@pytest.mark.parametrize("own_link", [POST, "javascript:unknownPost()"])
def test_mixed_foreign_and_own_or_unresolved_links_are_never_safely_ignored(own_link):
    mixed = row(
        link_total=2,
        links=[
            {"href": own_link, "text_raw": "합성 ai 글"},
            {"href": POST.replace("comic_new6", "another"), "text_raw": "외부 갤러리"},
        ],
    )
    snapshot = parse(raw_snapshot([mixed]))
    assert snapshot["rows"] == []
    assert exclusion_pairs(snapshot) == [{"row_order": 1, "reason": "mixed_gallery_identity"}]


@pytest.mark.parametrize(
    "list_count,empty_count,status",
    [
        (0, 0, "missing_list"),
        (2, 0, "ambiguous_list"),
        (1, 0, "unrecognized_empty"),
        (1, 1, "empty"),
        (1, 2, "unrecognized_empty"),
    ],
)
def test_missing_or_unknown_empty_list_never_means_confirmed_empty(list_count, empty_count, status):
    snapshot = parse(raw_snapshot([], list_count=list_count, empty_marker_count=empty_count))
    assert snapshot["status"] == status
    assert not snapshot["end_of_results"]


def test_empty_marker_with_rows_is_conflicting_and_fixture_terminal_must_be_explicit():
    snapshot = parse(raw_snapshot(empty_marker_count=1), layout_status="fixture_validated")
    assert snapshot["status"] == "conflicting_empty_marker"
    raw = raw_snapshot([], empty_marker_count=1, fixture_end_of_results=True)
    assert not parse(raw)["end_of_results"]
    terminal = parse(raw, layout_status="fixture_validated")
    assert terminal["end_of_results"] and terminal["pagination_complete"]
    assert terminal["pagination_status"] == "fixture_terminal"
    assert not terminal["queue_eligible"]


def test_pagination_candidates_require_same_exact_scope_and_validated_absolute_urls():
    links = [
        URL.replace("page=1", "page=2") + "&search_pos=-123",
        URL.replace("page=1", "page=2") + "&search_pos=-123",
        URL,
        URL.replace("comic_new6", "another"),
        URL.replace("s_keyword=ai", "s_keyword=AI"),
        URL + "&search_head=7",
        "https://evil.invalid/?token=must-not-appear",
        "javascript:alert(1)",
    ]
    raw = raw_snapshot(pagination_total=len(links), pagination=[{"href": url} for url in links])
    snapshot = parse(raw)
    assert snapshot["pagination_candidates"] == [
        {
            "canonical_url": links[0],
            "page": 2,
            "search_pos": "-123",
        }
    ]
    assert snapshot["counts"]["pagination_excluded"] == {
        "duplicate": 1,
        "current_document": 1,
        "different_scope": 3,
        "invalid_url": 2,
    }
    assert "must-not-appear" not in json.dumps(snapshot)
    assert snapshot["pagination_status"] == "candidates_observed"
    raw["fixture_end_of_results"] = True
    assert not parse(raw, layout_status="fixture_validated")["end_of_results"]


def test_malformed_observed_host_is_rejected_without_discarding_other_list_rows():
    invalid = "https://[broken-host/"
    raw = raw_snapshot(
        [profile_row(102), row("101", links=[{"href": invalid, "text_raw": "unused"}])],
        pagination_total=2,
        pagination=[{"href": invalid}, {"href": URL.replace("page=1", "page=2")}],
    )
    snapshot = parse(raw)
    assert [item["post_id"] for item in snapshot["rows"]] == ["102"]
    assert exclusion_pairs(snapshot) == [{"row_order": 2, "reason": "invalid_post_link"}]
    assert snapshot["rows_complete"] is False
    assert [link["page"] for link in snapshot["pagination_candidates"]] == [2]
    assert snapshot["counts"]["pagination_excluded"] == {"invalid_url": 1}


def test_rejected_pagination_links_prevent_fixture_completeness():
    raw = raw_snapshot(
        fixture_end_of_results=True,
        pagination_total=1,
        pagination=[{"href": "javascript:nextPage()"}],
    )
    snapshot = parse(raw, layout_status="fixture_validated")
    assert not snapshot["end_of_results"]
    assert not snapshot["pagination_complete"]


@pytest.mark.parametrize("extra", ["duplicate", "different", "foreign", None])
def test_search_range_forward_evidence_requires_one_unambiguous_link(extra):
    next_range = URL + "&search_pos=-20"
    links = [{"href": next_range, "label_kind": "next_search"}]
    if extra == "duplicate":
        links.append({"href": next_range, "label_kind": "page_number"})
    elif extra == "different":
        links.append({"href": URL + "&search_pos=-40", "label_kind": "next_search"})
    elif extra == "foreign":
        links.append({"href": "https://example.invalid/", "label_kind": "next_search"})
    raw = raw_snapshot(pagination_total=len(links), pagination=links)
    marked = [item for item in parse(raw)["pagination_candidates"] if "label_kind" in item]
    assert [item["canonical_url"] for item in marked] == ([next_range] if extra is None else [])


@pytest.mark.parametrize(
    "changes",
    [
        {"document_url": URL.replace("s_keyword=ai", "s_keyword=another")},
        {"list_count": True},
        {"row_total": -1},
        {"row_total": MAX_ROWS + 1},
        {"pagination_total": MAX_PAGINATION + 1},
        {"rows": "not-a-list"},
        {"pagination": "not-a-list"},
    ],
)
def test_wrong_identity_and_unbounded_or_malformed_observation_fail_closed(changes):
    with pytest.raises(DCSnapshotError):
        parse(raw_snapshot(**changes))


def test_diagnostics_keep_only_bounded_shapes_and_no_attributes_or_query_values():
    raw = raw_snapshot(
        diagnostics={
            "counts": {".gall_list": 1, "secret selector": 99},
            "samples": [
                {
                    "selector": ".gall_list",
                    "tag": "TABLE",
                    "classes": ["gall_list"],
                    "attribute_names": ["class", "data-ip"],
                    "outerHTML": "private HTML",
                    "data-ip": "private IP",
                    "link_shape": {
                        "scheme": "https",
                        "host": "gall.dcinside.com",
                        "path_segments": 2,
                        "query_keys": ["id", "search_pos"],
                        "query_values": ["private cursor"],
                    },
                }
            ],
        }
    )
    output = json.dumps(parse(raw))
    assert "private" not in output
    assert "secret selector" not in output
    assert parse(raw)["diagnostics"]["counts"] == {".gall_list": 1}
    assert parse(raw_snapshot(diagnostics={"counts": []}))["diagnostics"]["counts"] == {}


def test_candidate_inventory_is_bounded_and_drops_nonstructural_content():
    candidate = {
        "tag": "TABLE",
        "classes": ["gall_list"],
        "id": "fixture_recommend",
        "has_id": True,
        "table_row_count": 20,
        "ordinary_row_count": 0,
        "number_field_count": 20,
        "writer_field_count": 0,
        "date_field_count": 20,
        "title_link_count": 20,
        "title_link_schemes": {"https": 20, "private-token": 1, "http": -1},
        "empty_marker_count": 0,
        "qualifies": False,
        "selected": False,
        "outerHTML": "private content",
    }
    raw = raw_snapshot(
        diagnostics={
            "list_candidates": [candidate] * (MAX_LIST_CANDIDATES + 1),
            "list_candidate_total": 1,
            "list_candidates_truncated": True,
        }
    )
    diagnostics = parse(raw)["diagnostics"]
    assert len(diagnostics["list_candidates"]) == MAX_LIST_CANDIDATES
    assert diagnostics["list_candidates"][0]["has_id"]
    assert "id" not in diagnostics["list_candidates"][0]
    assert diagnostics["list_candidates"][0]["title_link_schemes"] == {"https": 20}
    assert diagnostics["list_candidates_truncated"]
    assert "private" not in json.dumps(diagnostics)


def test_pagination_rejection_diagnostics_explain_types_without_copying_query_values():
    links = [
        URL.replace("page=1", "page=") + "&search_pos=",
        URL + "&search_pos=%20%20",
        URL + "&search_pos=secret-cursor%00",
        URL + "&page=2&private-key=private-value",
        URL.replace("comic_new6", "foreign_gallery"),
    ]
    snapshot = parse(
        raw_snapshot(
            pagination_total=len(links),
            pagination=[{"href": href, "label_kind": "next"} for href in links],
        )
    )
    diagnostics = snapshot["diagnostics"]
    assert diagnostics["pagination_rejections"]["blank_page"] == 1
    assert diagnostics["pagination_rejections"]["invalid_cursor"] == 1
    assert diagnostics["pagination_rejections"]["control_query_value"] == 1
    assert diagnostics["pagination_rejections"]["duplicate_query_key"] == 1
    assert diagnostics["pagination_rejections"]["unknown_query_keys"] == 1
    assert diagnostics["pagination_rejections"]["gallery_id_mismatch"] == 1
    samples = diagnostics["pagination_samples"]
    assert samples[0]["query_value_categories"]["page"] == "empty"
    assert samples[0]["query_value_categories"]["search_pos"] == "empty"
    assert samples[1]["query_value_categories"]["search_pos"] == "surrounding_whitespace"
    assert samples[2]["control_character_count"] == 1
    assert samples[3]["duplicate_query_key_count"] == 1
    assert samples[3]["unknown_query_key_count"] == 1
    assert all(sample["label_kind"] == "next" for sample in samples)
    output = json.dumps(diagnostics)
    for secret in ("secret-cursor", "private-key", "private-value", "foreign_gallery"):
        assert secret not in output


def test_pagination_samples_stay_bounded_and_keep_navigation_label_categories_only():
    links = [
        {"href": URL.replace("page=1", f"page={page}"), "label_kind": "number"}
        for page in range(2, 30)
    ]
    links += [
        {"href": URL.replace("page=1", "page=30"), "label_kind": "next"},
        {"href": URL.replace("page=1", "page=31"), "label_kind": ["private label"]},
    ]
    diagnostics = parse(raw_snapshot(pagination_total=len(links), pagination=links))["diagnostics"]
    assert len(diagnostics["pagination_samples"]) <= MAX_PAGINATION_SAMPLES
    assert any(sample["label_kind"] == "next" for sample in diagnostics["pagination_samples"])
    assert "private" not in json.dumps(diagnostics)


def test_inspection_only_evaluates_dom_and_rechecks_identity():
    page = Mock()
    page.url = URL
    page.evaluate.return_value = raw_snapshot()
    assert inspect_list(page, expected_url=URL, observed_at=NOW)["status"] == "observed"
    page.evaluate.assert_called_once()
    page.goto.assert_not_called()
    page.click.assert_not_called()
    page.locator.assert_not_called()


def test_changed_identity_during_dom_observation_fails_closed():
    page = Mock()
    page.url = URL

    def change_identity(*args):
        page.url = URL + "&search_pos=-123"
        return raw_snapshot()

    page.evaluate.side_effect = change_identity
    with pytest.raises(DCSnapshotError, match="identity changed"):
        inspect_list(page, expected_url=URL, observed_at=NOW)


@pytest.mark.parametrize("timeout", [0, -1, True, 120001])
def test_invalid_timeout_never_touches_page(timeout):
    page = Mock()
    with pytest.raises(DCSnapshotError, match="timeout"):
        inspect_list(page, expected_url=URL, observed_at=NOW, timeout_ms=timeout)
    assert page.mock_calls == []


@pytest.fixture(scope="module")
def browser():
    playwright = pytest.importorskip("playwright.sync_api")
    if sys.platform == "win32":
        from image_monitor.native_probe import browser_executable

        executable = str(browser_executable("chrome"))
    else:
        executable = shutil.which("chromium") or shutil.which("google-chrome")
    if not executable:
        pytest.skip("Installed browser unavailable")
    with playwright.sync_playwright() as driver:
        instance = driver.chromium.launch(
            executable_path=executable, headless=True, args=["--disable-background-networking"]
        )
        yield instance
        instance.close()


@pytest.fixture
def local_page(browser):
    context = browser.new_context(accept_downloads=False)
    page = context.new_page()
    requests = []

    def load(html):
        def fixture_response(route):
            requests.append(route.request.url)
            if route.request.url == URL:
                route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
            else:
                route.abort()

        context.route("**/*", fixture_response)
        page.goto(URL, wait_until="domcontentloaded")
        return page

    yield load, requests
    context.close()


def test_browser_fixture_reads_visible_metadata_without_hidden_attributes_or_resources(local_page):
    load, requests = local_page
    page = load("""<!doctype html><html><body>
      <table class="gall_list"><tbody>
       <tr class="ub-content"><td class="gall_num">7036949</td>
        <td class="gall_tit"><a href="/board/view/?id=comic_new6&amp;no=7036949">ai 그림</a>
         <a class="reply_numbox" href="/board/view/?id=comic_new6&amp;no=7036949#comment">[7]</a>
        </td>
        <td class="gall_writer" data-nick="hidden nickname" data-ip="hidden full IP">
         <span>공개이름</span><span style="display:none">hidden display IP</span>
         <span style="opacity:0">hidden opacity IP</span><span class="ip">(123.45)</span>
         <span style="font-size:0">hidden zero-size IP</span>
        </td>
        <td class="gall_date" title="hidden full date">10:23</td>
       </tr>
       <tr class="ub-content"><td class="gall_num">공지</td></tr>
       <tr class="ub-content ad-row"><td class="gall_num">광고</td></tr>
      </tbody></table>
      <div class="bottom_paging_box"><a
       href="?id=comic_new6&amp;s_type=search_subject_memo&amp;s_keyword=ai&amp;page=2&amp;search_pos=-123"
       >2</a></div>
      </body></html>""")
    snapshot = inspect_list(page, expected_url=URL, observed_at=NOW)
    assert snapshot["status"] == "observed"
    assert snapshot["rows"][0]["post_id"] == "7036949"
    assert snapshot["rows"][0]["title"] == "ai 그림"
    assert "공개이름" in snapshot["rows"][0]["author_raw"]
    assert "(123.45)" in snapshot["rows"][0]["author_raw"]
    assert snapshot["rows"][0]["published_at_raw"] == "10:23"
    assert [item["reason"] for item in snapshot["excluded_rows"]] == ["pinned", "ad"]
    assert snapshot["pagination_candidates"][0]["page"] == 2
    assert snapshot["pagination_candidates"][0]["search_pos"] == "-123"
    assert "hidden" not in json.dumps(snapshot)
    assert requests == [URL]
    assert page.url == URL
    assert snapshot["layout_status"] == "unverified"
    assert not snapshot["queue_eligible"] and not snapshot["end_of_results"]


@pytest.mark.parametrize(
    "html,status",
    [
        ("<p>unexpected document</p>", "missing_list"),
        ("<table class='gall_list'><tbody></tbody></table>", "unrecognized_empty"),
        (
            "<table class='gall_list'><tbody><tr><td class='no_data'>검색결과 없음</td>"
            "</tr></tbody></table>",
            "empty",
        ),
        (
            "<table class='gall_list'></table><table class='gall_list'></table>",
            "unrecognized_empty",
        ),
    ],
)
def test_browser_fixture_distinguishes_explicit_empty_from_missing_dom(local_page, html, status):
    load, _requests = local_page
    page = load(html)
    snapshot = inspect_list(page, expected_url=URL, observed_at=NOW)
    assert snapshot["status"] == status
    assert snapshot["rows"] == []
    assert not snapshot["end_of_results"]


def fixture_table(*, ordinary=True, count=1, start=100, table_id="", style=""):
    rows = []
    for number in range(start, start + count):
        row_class = ' class="ub-content"' if ordinary else ""
        author = '<td class="gall_writer">fixture author</td>' if ordinary else ""
        rows.append(
            f'<tr{row_class}><td class="gall_num">{number}</td>'
            '<td class="gall_tit"><a '
            f'href="/board/view/?id=comic_new6&amp;no={number}">fixture title</a></td>'
            f'{author}<td class="gall_date">10:23</td></tr>'
        )
    attributes = f' id="{table_id}"' if table_id else ""
    if style:
        attributes += f' style="{style}"'
    return f'<table class="gall_list"{attributes}><tbody>' + "".join(rows) + "</tbody></table>"


@pytest.mark.parametrize("prefix_length", [998, 999])
def test_browser_keeps_complete_unicode_characters_at_the_title_limit(local_page, prefix_length):
    load, _requests = local_page
    prefix = "가" * prefix_length
    page = load(fixture_table().replace("fixture title", prefix + "😀끝"))
    snapshot = inspect_list(page, expected_url=URL, observed_at=NOW)
    assert snapshot["rows"][0]["title"] == (prefix + "😀" if prefix_length == 998 else prefix)


@pytest.mark.parametrize("main_first", [True, False])
def test_browser_fixture_selects_owned_main_template_among_two_visible_tables(
    local_page, main_first
):
    load, requests = local_page
    main = fixture_table(count=22)
    recommendation = fixture_table(
        ordinary=False, count=20, start=200, table_id="fixture_recommend"
    )
    tables = [main, recommendation] if main_first else [recommendation, main]
    page = load("<!doctype html><html><body>" + "".join(tables) + "</body></html>")
    snapshot = inspect_list(page, expected_url=URL, observed_at=NOW)
    assert snapshot["status"] == "observed"
    assert [row["post_id"] for row in snapshot["rows"]] == [str(n) for n in range(100, 122)]
    assert snapshot["counts"]["list_containers"] == 1
    assert snapshot["counts"]["matched_list_containers"] == 2
    assert snapshot["diagnostics"]["counts"][".gall_list"] == 2
    assert snapshot["diagnostics"]["counts"][".gall_num"] == 42
    inventory = snapshot["diagnostics"]["list_candidates"]
    selected = next(candidate for candidate in inventory if candidate["selected"])
    secondary = next(candidate for candidate in inventory if not candidate["qualifies"])
    assert selected["ordinary_row_count"] == selected["writer_field_count"] == 22
    assert selected["number_field_count"] == selected["date_field_count"] == 22
    assert selected["title_link_schemes"] == {"relative": 22}
    assert not selected["has_id"]
    assert secondary["ordinary_row_count"] == secondary["writer_field_count"] == 0
    assert secondary["table_row_count"] == secondary["number_field_count"] == 20
    assert secondary["date_field_count"] == secondary["title_link_count"] == 20
    assert secondary["has_id"]
    assert requests == [URL]
    assert not snapshot["queue_eligible"]
    assert snapshot["selector_evidence"]["live_layout_verified"]
    assert snapshot["layout_status"] == "site_verified"


@pytest.mark.parametrize("mixed_post", [False, True])
def test_browser_fixture_reads_survey_label_without_executing_its_action(local_page, mixed_post):
    load, requests = local_page
    main = fixture_table().replace(
        "<tbody>",
        """<tbody><tr class="ub-content"><td class="gall_num">설문</td>
        <td class="gall_tit"><a href="javascript:window.fixtureSurveyExecuted=true"
         onclick="window.fixtureOnclickExecuted=true">excluded fixture title</a></td>
        <td class="gall_writer">excluded fixture author</td><td class="gall_date">10:23</td>
        </tr><tr class="ub-content"><td class="gall_num">공지</td>
        <td class="gall_tit"><a href="http://example.invalid/notice">excluded notice</a></td>
        <td class="gall_writer">excluded notice author</td><td class="gall_date">10:23</td></tr>""",
    )
    if mixed_post:
        main = main.replace(
            ">excluded fixture title</a>",
            '>excluded fixture title</a><a class="reply_numbox" '
            'href="/board/view/?id=comic_new6&amp;no=101">[1]</a>',
        )
    page = load(main + fixture_table(ordinary=False, count=3, table_id="fixture_recommend"))
    snapshot = inspect_list(page, expected_url=URL, observed_at=NOW)
    assert snapshot["layout_status"] == "site_verified"
    assert snapshot["rows_complete"] is not mixed_post
    assert [entry["reason"] for entry in snapshot["excluded_rows"]] == [
        "non_numeric" if mixed_post else "survey",
        "pinned",
    ]
    assert snapshot["excluded_rows"][0]["number_kind"] == "survey_label"
    assert snapshot["excluded_rows"][0]["link_schemes"] == (
        {"javascript": 1, "relative": 1} if mixed_post else {"javascript": 1}
    )
    assert snapshot["excluded_rows"][1]["role_flags"]["is_pinned"] is True
    assert "excluded fixture" not in json.dumps(snapshot)
    assert "fixtureSurveyExecuted" not in json.dumps(snapshot)
    assert (
        page.evaluate("window.fixtureSurveyExecuted || window.fixtureOnclickExecuted || null")
        is None
    )
    assert requests == [URL]


def test_browser_fixture_nested_fields_do_not_belong_to_the_ordinary_row(local_page):
    load, _requests = local_page
    nested = fixture_table(start=200).replace('class="gall_list"', "")
    main = fixture_table().replace("</tr>", f"<td>{nested}</td></tr>")
    page = load(main + fixture_table(ordinary=False, count=3, table_id="fixture_recommend"))
    snapshot = inspect_list(page, expected_url=URL, observed_at=NOW)
    assert snapshot["layout_status"] == "site_verified"
    assert [entry["post_id"] for entry in snapshot["rows"]] == ["100"]
    assert snapshot["excluded_rows"] == []
    assert snapshot["diagnostics"]["list_candidates"][0]["writer_field_count"] == 1


@pytest.mark.parametrize("decoy_style", ["", "display:none", "visibility:hidden"])
def test_browser_fixture_two_owned_row_templates_remain_ambiguous(local_page, decoy_style):
    load, _requests = local_page
    page = load(
        fixture_table(count=2)
        + fixture_table(count=1, start=200, table_id="fixture_decoy", style=decoy_style)
    )
    snapshot = inspect_list(page, expected_url=URL, observed_at=NOW)
    assert snapshot["status"] == "ambiguous_list"
    assert snapshot["counts"]["list_containers"] == 2
    assert snapshot["rows"] == []
    assert all(candidate["qualifies"] for candidate in snapshot["diagnostics"]["list_candidates"])
    assert not any(
        candidate["selected"] for candidate in snapshot["diagnostics"]["list_candidates"]
    )


def test_browser_fixture_hidden_secondary_without_row_template_is_unambiguous(local_page):
    load, _requests = local_page
    page = load(
        fixture_table() + fixture_table(ordinary=False, count=2, start=200, style="display:none")
    )
    snapshot = inspect_list(page, expected_url=URL, observed_at=NOW)
    assert snapshot["status"] == "observed"
    assert snapshot["rows"][0]["post_id"] == "100"


@pytest.mark.parametrize("other_style", ["", "display:none"])
def test_browser_fixture_structural_empty_templates_cannot_be_tiebroken_by_visibility(
    local_page, other_style
):
    load, _requests = local_page
    empty = '<table class="gall_list"><tbody><tr><td class="no_data">fixture empty</td>'
    empty += "</tr></tbody></table>"
    other = empty.replace('class="gall_list"', f'class="gall_list" style="{other_style}"')
    snapshot = inspect_list(load(empty + other), expected_url=URL, observed_at=NOW)
    assert snapshot["status"] == "ambiguous_list"
    assert snapshot["counts"]["list_containers"] == 2
    assert snapshot["counts"]["empty_markers"] == 0


def test_browser_fixture_one_hidden_empty_marker_is_unrecognized_empty(local_page):
    load, _requests = local_page
    page = load(
        '<table class="gall_list" style="display:none"><tbody><tr>'
        '<td class="no_result">fixture empty</td></tr></tbody></table>'
    )
    snapshot = inspect_list(page, expected_url=URL, observed_at=NOW)
    assert snapshot["status"] == "unrecognized_empty"
    candidate = snapshot["diagnostics"]["list_candidates"][0]
    assert candidate["selected"]
    assert candidate["empty_marker_count"] == 1
    assert candidate["visible_empty_marker_count"] == 0


def test_browser_fixture_explicit_empty_main_is_selected_over_generic_recommendations(local_page):
    load, _requests = local_page
    page = load(
        '<table class="gall_list"><tbody><tr><td class="no_data">fixture empty</td>'
        "</tr></tbody></table>" + fixture_table(ordinary=False, count=20, start=200)
    )
    snapshot = inspect_list(page, expected_url=URL, observed_at=NOW)
    assert snapshot["status"] == "empty"
    assert snapshot["counts"]["list_containers"] == 1
    assert snapshot["counts"]["matched_list_containers"] == 2
    assert snapshot["rows"] == []
    assert not snapshot["end_of_results"]


def test_browser_fixture_nested_table_rows_are_owned_only_by_the_inner_table(local_page):
    load, _requests = local_page
    page = load(
        '<table class="gall_list"><tbody><tr><td>' + fixture_table() + "</td></tr></tbody></table>"
    )
    snapshot = inspect_list(page, expected_url=URL, observed_at=NOW)
    assert snapshot["status"] == "observed"
    inventory = snapshot["diagnostics"]["list_candidates"]
    assert inventory[0]["ordinary_row_count"] == 0
    assert inventory[0]["writer_field_count"] == 0
    assert not inventory[0]["qualifies"]
    assert inventory[1]["ordinary_row_count"] == 1
    assert snapshot["rows"][0]["post_id"] == "100"


def test_browser_fixture_pagination_diagnostics_classify_visible_next_label(local_page):
    load, _requests = local_page
    page = load(
        fixture_table() + '<div class="bottom_paging_box"><a '
        'href="?id=comic_new6&amp;s_type=search_subject_memo&amp;s_keyword=ai&amp;page=2'
        '&amp;search_pos=">다음</a></div>'
        '<a href="?id=comic_new6&amp;s_type=search_subject_memo&amp;s_keyword=ai&amp;page=99">'
        "unrelated</a>"
    )
    snapshot = inspect_list(page, expected_url=URL, observed_at=NOW)
    assert snapshot["counts"]["pagination_links"] == 1
    assert snapshot["pagination_candidates"][0]["page"] == 2
    sample = snapshot["diagnostics"]["pagination_samples"][0]
    assert sample["label_kind"] == "next"
    assert sample["query_value_categories"]["search_pos"] == "empty"


@pytest.mark.parametrize(
    ("label", "hidden", "expected"),
    [
        ("다음검색", False, True),
        ("다음 검색", False, True),
        ("다음 검색", True, False),
        ("이전검색", False, False),
    ],
)
def test_browser_fixture_classifies_only_visible_forward_search_label(
    local_page, label, hidden, expected
):
    load, _requests = local_page
    style = ' style="display:none"' if hidden else ""
    page = load(
        fixture_table() + f'<div class="bottom_paging_box"><a{style} '
        'href="?id=comic_new6&amp;s_type=search_subject_memo&amp;s_keyword=ai&amp;page=1'
        f'&amp;search_pos=-250">{label}</a></div>'
    )
    snapshot = inspect_list(page, expected_url=URL, observed_at=NOW)
    assert (
        any(link.get("label_kind") == "next_search" for link in snapshot["pagination_candidates"])
        is expected
    )
