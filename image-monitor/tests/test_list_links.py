import json

import pytest

from image_monitor.dcinside import DCSnapshotError
from image_monitor.list_links import (
    LIST_LINK_REASON_CODES,
    LIST_LINK_VALUE_CATEGORIES,
    LIST_PATHS,
    build_list_url,
    classify_rejected_list_link,
    validate_list_url,
)

URL = build_list_url("normal", "comic_new6", "ai")
SCOPE = {
    "gallery_type": "normal",
    "gallery_id": "comic_new6",
    "search_type": "search_subject_memo",
    "keyword": "ai",
    "navigation": {},
}


@pytest.mark.parametrize("kind", LIST_PATHS)
def test_empty_display_cursor_is_the_latest_window_without_changing_scope(kind):
    base = build_list_url(kind, "gallery_x", "ai 그림", page=2)
    identity = validate_list_url(base + "&search_pos=&search_head=7&exception_mode=recommend")
    assert identity["search_pos"] is None
    assert identity["page"] == 2
    assert identity["keyword"] == "ai 그림"
    assert identity["navigation"] == {"search_head": "7", "exception_mode": "recommend"}
    assert identity["canonical_url"] == base + "&search_head=7&exception_mode=recommend"
    assert validate_list_url(base + "&search_pos=") == validate_list_url(base)


def test_constructor_keeps_an_explicit_invalid_cursor_distinct_from_default_latest():
    assert "search_pos" not in build_list_url("normal", "comic_new6", "ai")
    with pytest.raises(DCSnapshotError):
        build_list_url("normal", "comic_new6", "ai", search_pos="")


@pytest.mark.parametrize(
    "extra",
    [
        "&search_pos=+1",
        "&search_pos=%20",
        "&search_pos=-",
        "&search_pos=1.0",
        "&search_pos=1%00",
        "&search_pos=1&search_pos=",
        "&search_pos=&search_pos=",
        "&search_pos=&page=2",
        "&search_pos=&unknown=value",
    ],
)
def test_blank_cursor_normalization_does_not_relax_other_validation(extra):
    with pytest.raises(DCSnapshotError):
        validate_list_url(URL + extra)


def test_relative_display_pagination_reports_empty_cursor_without_rejection():
    result = classify_rejected_list_link(
        "?id=comic_new6&page=2&search_pos=&s_type=search_subject_memo&s_keyword=ai",
        URL,
        SCOPE,
    )
    assert result == {
        "validation_status": "accepted",
        "reason_codes": [],
        "link_shape": {
            "scheme": "relative",
            "host": "gall.dcinside.com",
            "path_segments": 2,
            "query_keys": ["id", "page", "s_keyword", "s_type", "search_pos"],
        },
        "query_value_categories": {
            "id": "scope_match",
            "page": "positive_integer",
            "search_pos": "empty",
            "s_type": "exact_search_type",
            "s_keyword": "scope_match",
        },
        "query_parameter_count": 5,
        "duplicate_query_key_count": 0,
        "unknown_query_key_count": 0,
        "control_character_count": 0,
    }


@pytest.mark.parametrize(
    "href,reason,key,category",
    [
        (URL.replace("page=1", "page="), "blank_page", "page", "empty"),
        (URL.replace("page=1", "page=0"), "invalid_page", "page", "invalid"),
        (URL + "&search_pos=+123", "invalid_cursor", "search_pos", "surrounding_whitespace"),
        (URL + "&search_pos=-", "invalid_cursor", "search_pos", "invalid"),
        (URL + "&page=2", "duplicate_query_key", "page", "duplicate"),
        (URL + "&search_pos=%00", "control_query_value", "search_pos", "control"),
        (
            URL.replace("search_subject_memo", "search_subject"),
            "unexpected_search_type",
            "s_type",
            "other_search_type",
        ),
        (URL.replace("s_keyword=ai", "s_keyword="), "invalid_keyword", "s_keyword", "empty"),
        (URL + "&search_head=abc", "invalid_search_head", "search_head", "invalid"),
        (
            URL + "&exception_mode=a%2Fb",
            "invalid_exception_mode",
            "exception_mode",
            "invalid",
        ),
    ],
)
def test_registered_failure_reasons_and_query_categories_explain_validation(
    href, reason, key, category
):
    result = classify_rejected_list_link(href, URL, SCOPE)
    assert result["validation_status"] == "invalid_url"
    assert reason in result["reason_codes"]
    assert result["query_value_categories"][key] == category
    assert set(result["reason_codes"]) <= LIST_LINK_REASON_CODES
    assert set(result["query_value_categories"].values()) <= LIST_LINK_VALUE_CATEGORIES


@pytest.mark.parametrize(
    "href,reason",
    [
        (URL.replace("https:", "http:"), "unsupported_scheme"),
        (URL.replace("gall.dcinside.com", "gall.dcinside.com.evil.invalid"), "unexpected_origin"),
        (URL.replace("gall.dcinside.com", "user@gall.dcinside.com"), "unexpected_origin"),
        (URL.replace("gall.dcinside.com", "gall.dcinside.com:443"), "unexpected_origin"),
        (URL.replace("/lists/", "/lists//"), "unsupported_path"),
        (URL.replace("/lists/", "/view/"), "unsupported_path"),
        (URL + "#secret-fragment", "fragment_not_allowed"),
        (URL + "&search_pos=%GG", "malformed_percent_encoding"),
        (URL + "&search_pos=%FF", "malformed_query"),
        (URL + "&broken", "malformed_query"),
        ("javascript:unknownFunction()", "unsupported_scheme"),
        (None, "invalid_observed_link"),
        ([], "invalid_observed_link"),
        ("", "invalid_observed_link"),
        ("x" * 4097, "link_too_long"),
    ],
)
def test_diagnostic_validation_stays_strict_for_origin_path_and_url_syntax(href, reason):
    result = classify_rejected_list_link(href, URL, SCOPE)
    assert result["validation_status"] == "invalid_url"
    assert reason in result["reason_codes"]


@pytest.mark.parametrize(
    "href,reason",
    [
        (URL.replace("comic_new6", "another"), "gallery_id_mismatch"),
        (URL.replace("/board/", "/mini/board/"), "gallery_type_mismatch"),
        (URL.replace("s_keyword=ai", "s_keyword=AI"), "keyword_mismatch"),
        (URL + "&search_head=7", "navigation_mismatch"),
    ],
)
def test_valid_but_different_search_scope_is_classified_separately(href, reason):
    result = classify_rejected_list_link(href, URL, SCOPE)
    assert result["validation_status"] == "different_scope"
    assert result["reason_codes"] == [reason]


def test_diagnostics_count_duplicates_unknown_keys_and_controls_without_copying_values():
    href = URL + "&private_author=private-value&private_author=another-value&search_pos=789%00"
    result = classify_rejected_list_link(href, URL, SCOPE)
    assert result["unknown_query_key_count"] == 2
    assert result["duplicate_query_key_count"] == 1
    assert result["control_character_count"] == 1
    assert result["query_parameter_count"] == 7
    assert set(result["reason_codes"]) == {
        "unknown_query_keys",
        "duplicate_query_key",
        "control_query_value",
    }
    serialized = json.dumps(result)
    for private in ("private_author", "private-value", "another-value", "789", "comic_new6"):
        assert private not in serialized


def test_custom_schemes_origins_paths_and_unknown_keys_never_enter_diagnostics():
    secret_parts = ("privateprotocol", "private-host.invalid", "private-path", "private-key")
    href = "privateprotocol://private-host.invalid/private-path?private-key=secret-value"
    result = classify_rejected_list_link(href, URL, SCOPE)
    assert result["link_shape"] == {
        "scheme": "other",
        "host": "other",
        "path_segments": 1,
        "query_keys": [],
    }
    serialized = json.dumps(result)
    assert all(part not in serialized for part in (*secret_parts, "secret-value"))


def test_parameter_limit_diagnostics_are_bounded_and_do_not_make_link_valid():
    result = classify_rejected_list_link(URL + "&unknown=secret" * 80, URL, SCOPE)
    assert result["validation_status"] == "invalid_url"
    assert result["reason_codes"] == ["query_parameter_limit"]
    assert result["query_parameter_count"] == 84
    assert result["query_value_categories"] == {}
    assert "secret" not in json.dumps(result)
