import json
import shutil
import sys
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from image_monitor.dcinside import DCSnapshotError
from image_monitor.search_list import (
    MAX_PAGINATION,
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
    return result | changes


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
        URL + "&search_pos=",
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
        (row(links=[{"href": POST, "text_raw": None}]), "missing_title"),
    ],
)
def test_nonordinary_or_uncertain_rows_have_bounded_reason_only(entry, reason):
    snapshot = parse(raw_snapshot([entry]))
    assert snapshot["rows"] == []
    assert snapshot["excluded_rows"] == [{"row_order": 1, "reason": reason}]
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
    assert ambiguous_page["excluded_rows"] == [{"row_order": 2, "reason": "ambiguous_row_fields"}]
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
    assert duplicate["excluded_rows"] == [{"row_order": 2, "reason": "duplicate_post_id"}]


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
    assert snapshot["excluded_rows"] == [{"row_order": 1, "reason": "mixed_gallery_identity"}]


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


def test_rejected_pagination_links_prevent_fixture_completeness():
    raw = raw_snapshot(
        fixture_end_of_results=True,
        pagination_total=1,
        pagination=[{"href": "javascript:nextPage()"}],
    )
    snapshot = parse(raw, layout_status="fixture_validated")
    assert not snapshot["end_of_results"]
    assert not snapshot["pagination_complete"]


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
        ("<table class='gall_list'></table><table class='gall_list'></table>", "ambiguous_list"),
    ],
)
def test_browser_fixture_distinguishes_explicit_empty_from_missing_dom(local_page, html, status):
    load, _requests = local_page
    page = load(html)
    snapshot = inspect_list(page, expected_url=URL, observed_at=NOW)
    assert snapshot["status"] == status
    assert snapshot["rows"] == []
    assert not snapshot["end_of_results"]
