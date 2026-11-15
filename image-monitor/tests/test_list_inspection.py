import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from image_monitor import list_inspection as inspection
from image_monitor.dcinside import DCSnapshotError
from image_monitor.native_ui import NativeUIError
from image_monitor.search_list import build_list_url, validate_list_url


@pytest.fixture
def browser_session(monkeypatch):
    monkeypatch.setattr(inspection, "require_windows", lambda: None)
    monkeypatch.setattr(inspection, "browser_executable", lambda browser: Path(browser + ".exe"))
    manager = MagicMock()
    driver = manager.__enter__.return_value
    browser = driver.chromium.launch.return_value
    browser.version = "test-version"
    page = browser.new_context.return_value.new_page.return_value
    response = page.goto.return_value
    response.status = 200
    response.header_value.return_value = None
    inspect = MagicMock(
        return_value={
            "status": "observed",
            "layout_status": "unverified",
            "queue_eligible": False,
            "rows": [{"canonical_url": "https://gall.dcinside.com/board/view/?id=test&no=1"}],
            "pagination_candidates": [],
        }
    )
    monkeypatch.setattr(inspection, "_playwright", lambda: manager)
    monkeypatch.setattr(inspection, "inspect_list", inspect)
    return manager, driver, browser, page, response, inspect


def test_default_list_is_page_one_without_inherited_search_cursor():
    target = validate_list_url(inspection.DEFAULT_LIST_URL)
    assert target["gallery_type"] == "normal"
    assert target["gallery_id"] == "comic_new6"
    assert target["search_type"] == "search_subject_memo"
    assert target["keyword"] == "ai"
    assert target["page"] == 1
    assert target["search_pos"] is None


def test_platform_guard_precedes_filesystem_validation_or_browser(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    root = tmp_path / "not-created"
    browser = MagicMock()
    validate = MagicMock()
    monkeypatch.setattr(inspection, "_playwright", browser)
    monkeypatch.setattr(inspection, "validate_list_url", validate)
    with pytest.raises(NativeUIError, match="Windows"):
        inspection.run_list_inspection(root)
    assert not root.exists()
    validate.assert_not_called()
    browser.assert_not_called()


def test_invalid_url_is_rejected_before_filesystem_or_launch(tmp_path, browser_session):
    root = tmp_path / "not-created"
    with pytest.raises(DCSnapshotError):
        inspection.run_list_inspection(root, url="https://example.invalid/board/lists/")
    assert not root.exists()
    browser_session[1].chromium.launch.assert_not_called()


def test_invalid_browser_is_rejected_before_filesystem_or_launch(tmp_path, browser_session):
    root = tmp_path / "not-created"
    with pytest.raises(ValueError, match="edge or chrome"):
        inspection.run_list_inspection(root, browser="firefox")
    assert not root.exists()
    browser_session[1].chromium.launch.assert_not_called()


@pytest.mark.parametrize("browser_choice", ["chrome", "edge"])
def test_owned_headless_one_shot_inspection_is_unverified_and_closes(
    tmp_path, browser_session, browser_choice
):
    manager, driver, browser, page, response, inspect = browser_session
    # A DOM result cannot grant real-site verification to this read-only probe.
    inspect.return_value["layout_status"] = "site_verified"
    report = inspection.run_list_inspection(tmp_path, browser=browser_choice)
    driver.chromium.launch.assert_called_once_with(
        executable_path=browser_choice + ".exe",
        headless=True,
        timeout=15_000,
        args=["--disable-background-networking"],
    )
    driver.chromium.launch_persistent_context.assert_not_called()
    browser.new_context.assert_called_once_with(accept_downloads=False)
    page.goto.assert_called_once_with(
        inspection.DEFAULT_LIST_URL, wait_until="domcontentloaded", timeout=30_000
    )
    response.header_value.assert_called_once_with("retry-after")
    inspect.assert_called_once()
    assert inspect.call_args.args == (page,)
    assert inspect.call_args.kwargs["expected_url"] == inspection.DEFAULT_LIST_URL
    assert inspect.call_args.kwargs["timeout_ms"] == 15_000
    assert inspect.call_args.kwargs["observed_at"].utcoffset().total_seconds() == 0
    assert report["status"] == "inspected_unverified"
    assert report["last_stage"] == "complete"
    assert report["browser_mode"] == "headless"
    assert report["navigation_attempts"] == 1
    assert report["inspection_only"] is True
    assert report["images_saved"] is False
    assert report["queue_modified"] is False
    assert report["browser_closed"] is True
    assert report["snapshot"] == inspect.return_value
    assert json.loads(Path(report["report_path"]).read_text()) == report
    assert list(tmp_path.rglob("*")) == [
        Path(report["report_path"]).parent,
        Path(report["report_path"]),
    ]
    # Navigation and one response-header read are the only browser-page operations.
    assert [call[0] for call in page.mock_calls] == ["goto", "goto().header_value"]
    browser.close.assert_called_once()
    manager.__exit__.assert_called_once()


@pytest.mark.parametrize("status", [None, 400, 401, 403, 404, 429, 503])
def test_error_response_stops_after_one_attempt_without_body_probe(
    tmp_path, browser_session, status
):
    manager, _driver, browser, page, response, inspect = browser_session
    if status is None:
        page.goto.return_value = None
    else:
        response.status = status
        response.header_value.return_value = "120"
    report = inspection.run_list_inspection(tmp_path)
    assert report["status"] == "inspection_failed"
    assert report["http_status"] == status
    assert report["last_stage"] == "page_navigation"
    assert report["retry_after"] == ("120" if status is not None else None)
    assert report["error_type"] == "HTTPStatusError"
    assert report["navigation_attempts"] == 1
    inspect.assert_not_called()
    page.goto.assert_called_once()
    browser.close.assert_called_once()
    manager.__exit__.assert_called_once()


def test_retry_after_is_bounded(tmp_path, browser_session):
    browser_session[4].status = 429
    browser_session[4].header_value.return_value = "a" * 500
    report = inspection.run_list_inspection(tmp_path)
    assert report["retry_after"] == "a" * 256
    browser_session[3].goto.assert_called_once()


def test_structure_failure_keeps_diagnostics_without_exception_text(tmp_path, browser_session):
    diagnostics = {"counts": {"table.gall_list": 0}, "samples": []}
    browser_session[5].side_effect = DCSnapshotError("private page text", diagnostics=diagnostics)
    report = inspection.run_list_inspection(tmp_path)
    assert report["status"] == "inspection_failed"
    assert report["last_stage"] == "dom_inspection"
    assert report["diagnostics"] == diagnostics
    assert report["error_type"] == "DCSnapshotError"
    assert "private page text" not in json.dumps(report)
    browser_session[2].close.assert_called_once()


def test_browser_cleanup_failure_turns_success_into_failure(tmp_path, browser_session):
    browser_session[2].close.side_effect = RuntimeError("private process detail")
    report = inspection.run_list_inspection(tmp_path)
    assert report["status"] == "inspection_failed"
    assert report["browser_closed"] is False
    assert report["cleanup_error_type"] == "RuntimeError"
    assert "private process detail" not in json.dumps(report)
    browser_session[0].__exit__.assert_called_once()


def test_launch_failure_closes_driver_and_writes_report(tmp_path, browser_session):
    browser_session[1].chromium.launch.side_effect = RuntimeError("private installation path")
    report = inspection.run_list_inspection(tmp_path)
    assert report["status"] == "inspection_failed"
    assert report["browser_closed"] is None
    assert report["navigation_attempts"] == 0
    assert report["last_stage"] == "browser_launch"
    assert "private installation path" not in json.dumps(report)
    assert Path(report["report_path"]).is_file()
    browser_session[5].assert_not_called()
    browser_session[0].__exit__.assert_called_once()


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            "net::ERR_TUNNEL_CONNECTION_FAILED at https://example.invalid/?token=secret",
            "ERR_TUNNEL_CONNECTION_FAILED",
        ),
        ("Timeout 30000ms exceeded at https://example.invalid/?token=secret", "Timeout"),
        ("net::ERR_UNRECOGNIZED at https://example.invalid/?token=secret", None),
    ],
)
def test_navigation_failure_exposes_only_whitelisted_error_code(
    tmp_path, browser_session, message, expected
):
    browser_session[3].goto.side_effect = RuntimeError(message)
    report = inspection.run_list_inspection(tmp_path)
    assert report["status"] == "inspection_failed"
    assert report["last_stage"] == "page_navigation"
    assert report["error_code"] == expected
    assert report["navigation_attempts"] == 1
    assert "secret" not in json.dumps(report)
    browser_session[2].close.assert_called_once()
    browser_session[5].assert_not_called()


def test_share_report_retains_scope_and_hashes_cursor_without_local_paths_or_secrets():
    cursor = "-1200000"
    digest = hashlib.sha256(cursor.encode()).hexdigest()
    url = build_list_url("normal", "comic_new6", "ai", page=2, search_pos=cursor)
    report = {
        "report_path": "C:/Users/private/report.json",
        "url": inspection.DEFAULT_LIST_URL,
        "snapshot": {
            "url": url,
            "search_pos": cursor,
            "pagination_candidates": [{"canonical_url": url, "search_pos": cursor}],
            "rows": [{"canonical_url": "https://gall.dcinside.com/board/view/?id=test&no=1"}],
            "evidence": [url, "https://user:password@cdn.example/img?token=secret#fragment"],
            "headers": {"authorization": "secret"},
            "run_directory": "C:/Users/private/run",
        },
    }
    shared = inspection.share_report(report)
    assert "report_path" not in shared
    assert shared["url"] == inspection.DEFAULT_LIST_URL
    public_url = shared["snapshot"]["url"]
    assert "id=comic_new6" in public_url
    assert "s_type=search_subject_memo" in public_url
    assert "s_keyword=ai" in public_url
    assert "page=2" in public_url
    assert "search_pos_sha256=" + digest in public_url
    assert shared["snapshot"]["search_pos_sha256"] == digest
    assert "search_pos" not in shared["snapshot"]
    assert shared["snapshot"]["pagination_candidates"][0]["canonical_url"] == public_url
    assert shared["snapshot"]["rows"][0]["canonical_url"].endswith("?id=test&no=1")
    assert shared["snapshot"]["evidence"] == [public_url, "https://cdn.example/img"]
    serialized = json.dumps(shared)
    assert cursor not in serialized
    assert "secret" not in serialized
    assert "password" not in serialized
    assert "C:/Users" not in serialized
    assert "headers" not in shared["snapshot"]
    assert report["snapshot"]["search_pos"] == cursor


def test_share_report_sanitizes_relative_list_urls_and_rejects_unvalidated_scope():
    cursor = "-700"
    url = build_list_url("normal", "comic_new6", "ai", page=2, search_pos=cursor)
    relative = url.removeprefix("https://gall.dcinside.com")
    shared = inspection.share_report(
        {
            "evidence": [
                relative,
                "https://gall.dcinside.com/board/lists/?id=invalid!&token=secret",
                "/board/lists/?id=invalid!&search_pos=private&token=secret",
                "https://evil.invalid/board/lists/?id=comic_new6&s_keyword=ai&token=secret",
            ]
        }
    )
    assert cursor not in json.dumps(shared)
    assert "secret" not in json.dumps(shared)
    assert "private" not in json.dumps(shared)
    assert "search_pos_sha256=" in shared["evidence"][0]
    assert shared["evidence"][1] == "https://gall.dcinside.com/board/lists/"
    assert shared["evidence"][2] == "https://gall.dcinside.com/board/lists/"
    assert shared["evidence"][3] == "https://evil.invalid/board/lists/"


def test_share_report_preserves_each_url_in_a_long_pagination_inventory():
    urls = [build_list_url("normal", "comic_new6", "ai", page=index) for index in range(1, 15)]
    shared = inspection.share_report({"pagination_candidates": [{"url": url} for url in urls]})
    assert [candidate["url"] for candidate in shared["pagination_candidates"]] == urls


@pytest.mark.parametrize("scheme", ["data", "blob", "file"])
def test_private_snapshot_omits_inline_or_local_url_bytes(tmp_path, browser_session, scheme):
    browser_session[5].return_value = {"rows": [{"canonical_url": scheme + ":private-payload"}]}
    report = inspection.run_list_inspection(tmp_path)
    row = report["snapshot"]["rows"][0]
    assert row["canonical_url"] is None
    assert row["source_scheme"] == scheme
    assert "private-payload" not in Path(report["report_path"]).read_text()


def test_unbounded_snapshot_is_not_written(tmp_path, browser_session, monkeypatch):
    monkeypatch.setattr(inspection, "MAX_SNAPSHOT_BYTES", 50)
    browser_session[5].return_value = {"rows": [{"fixture": "a" * 100}]}
    report = inspection.run_list_inspection(tmp_path)
    assert report["status"] == "inspection_failed"
    assert "snapshot" not in report


def test_unbounded_failure_diagnostics_are_omitted(tmp_path, browser_session, monkeypatch):
    monkeypatch.setattr(inspection, "MAX_SNAPSHOT_BYTES", 50)
    browser_session[5].side_effect = DCSnapshotError("private", diagnostics={"fixture": "a" * 100})
    report = inspection.run_list_inspection(tmp_path)
    assert report["status"] == "inspection_failed"
    assert "diagnostics" not in report
    assert report["diagnostics_omitted"] == "metadata_limit"


def _candidate(url):
    target = validate_list_url(url)
    return {
        "canonical_url": target["canonical_url"],
        "page": target["page"],
        "search_pos": target["search_pos"],
    }


def _observed_snapshot(url=inspection.DEFAULT_LIST_URL, candidates=()):
    target = validate_list_url(url)
    return {
        "status": "observed",
        "layout_status": "unverified",
        "queue_eligible": False,
        "url": target["canonical_url"],
        "page": target["page"],
        "search_pos": target["search_pos"],
        "scope": {key: target[key] for key in inspection._SCOPE_KEYS},
        "counts": {"list_containers": 1},
        "rows": [{"canonical_url": "https://gall.dcinside.com/board/view/?id=test&no=1"}],
        "pagination_candidates": list(candidates),
    }


def test_latest_list_follows_one_actual_adjacent_link_and_never_a_third_page(
    tmp_path, browser_session
):
    manager, driver, browser, page, response, inspect = browser_session
    next_url = build_list_url("normal", "comic_new6", "ai", page=2)
    third_url = build_list_url("normal", "comic_new6", "ai", page=3)
    first = _observed_snapshot(candidates=[_candidate(next_url)])
    second = _observed_snapshot(next_url, [_candidate(third_url)])
    inspect.side_effect = [first, second]
    report = inspection.run_list_inspection(tmp_path)
    assert page.goto.call_args_list == [
        call(inspection.DEFAULT_LIST_URL, wait_until="domcontentloaded", timeout=30_000),
        call(next_url, wait_until="domcontentloaded", timeout=30_000),
    ]
    assert report["status"] == "inspected_unverified"
    assert report["navigation_attempts"] == 2
    assert report["snapshot"] == first
    assert report["follow_up"] == {
        "status": "observed",
        "url": next_url,
        "http_status": 200,
        "retry_after": None,
        "snapshot": second,
    }
    assert inspect.call_count == 2
    assert inspect.call_args_list[1].kwargs["expected_url"] == next_url
    assert inspect.call_args_list[1].kwargs["timeout_ms"] == 15_000
    assert response.header_value.call_args_list == [call("retry-after"), call("retry-after")]
    assert [operation[0] for operation in page.mock_calls] == [
        "goto",
        "goto().header_value",
        "goto",
        "goto().header_value",
    ]
    driver.chromium.launch.assert_called_once()
    browser.new_context.assert_called_once_with(accept_downloads=False)
    browser.close.assert_called_once()
    manager.__exit__.assert_called_once()
    assert json.loads(Path(report["report_path"]).read_text()) == report


def test_follow_up_preserves_matching_navigation_filters(tmp_path, browser_session):
    suffix = "&search_head=1&exception_mode=recommend"
    url = inspection.DEFAULT_LIST_URL + suffix
    next_url = build_list_url("normal", "comic_new6", "ai", page=2) + suffix
    first = _observed_snapshot(url, [_candidate(next_url)])
    browser_session[5].side_effect = [first, _observed_snapshot(next_url)]
    report = inspection.run_list_inspection(tmp_path, url=url)
    assert report["navigation_attempts"] == 2
    assert report["follow_up"]["url"] == validate_list_url(next_url)["canonical_url"]
    assert report["follow_up"]["snapshot"]["scope"]["navigation"] == {
        "search_head": "1",
        "exception_mode": "recommend",
    }


def test_observed_empty_cursor_is_revalidated_as_latest_before_follow_up(tmp_path, browser_session):
    next_url = build_list_url("normal", "comic_new6", "ai", page=2)
    candidate = {"canonical_url": next_url + "&search_pos=", "page": 2, "search_pos": None}
    browser_session[5].side_effect = [
        _observed_snapshot(candidates=[candidate]),
        _observed_snapshot(next_url),
    ]
    report = inspection.run_list_inspection(tmp_path)
    assert report["navigation_attempts"] == 2
    assert report["follow_up"]["url"] == next_url
    assert browser_session[3].goto.call_args == call(
        next_url, wait_until="domcontentloaded", timeout=30_000
    )


@pytest.mark.parametrize(("first_page", "cursor"), [(1, "-1200000"), (2, None), (2, "-1200000")])
def test_non_latest_initial_window_never_follows_even_a_matching_next_link(
    tmp_path, browser_session, first_page, cursor
):
    url = build_list_url("normal", "comic_new6", "ai", page=first_page, search_pos=cursor)
    next_url = build_list_url("normal", "comic_new6", "ai", page=first_page + 1, search_pos=cursor)
    browser_session[5].return_value = _observed_snapshot(url, [_candidate(next_url)])
    report = inspection.run_list_inspection(tmp_path, url=url)
    assert report["navigation_attempts"] == 1
    assert report["follow_up"] == {
        "status": "skipped",
        "reason": "initial_page_is_not_latest_page_one",
    }
    browser_session[3].goto.assert_called_once()


@pytest.mark.parametrize(
    "candidate_url",
    [
        build_list_url("normal", "comic_new6", "ai", page=2, search_pos="-999"),
        build_list_url("minor", "comic_new6", "ai", page=2),
        build_list_url("normal", "other", "ai", page=2),
        build_list_url("normal", "comic_new6", "other", page=2),
        build_list_url("normal", "comic_new6", "ai", page=2) + "&search_head=1",
        build_list_url("normal", "comic_new6", "ai", page=3),
        "https://evil.invalid/board/lists/?id=comic_new6&s_type=search_subject_memo&s_keyword=ai&page=2",
        inspection.DEFAULT_LIST_URL.replace("search_subject_memo", "search_name") + "&page=2",
    ],
)
def test_changed_cursor_scope_navigation_or_non_adjacent_link_is_not_followed(
    tmp_path, browser_session, candidate_url
):
    candidate = {"canonical_url": candidate_url, "page": 2, "search_pos": None}
    browser_session[5].return_value = _observed_snapshot(candidates=[candidate])
    report = inspection.run_list_inspection(tmp_path)
    assert report["navigation_attempts"] == 1
    assert report["follow_up"]["status"] == "no_adjacent_page"
    browser_session[3].goto.assert_called_once()


def test_duplicate_adjacent_candidates_are_ambiguous_and_not_followed(tmp_path, browser_session):
    candidate = _candidate(build_list_url("normal", "comic_new6", "ai", page=2))
    browser_session[5].return_value = _observed_snapshot(candidates=[candidate, candidate])
    report = inspection.run_list_inspection(tmp_path)
    assert report["navigation_attempts"] == 1
    assert report["follow_up"] == {"status": "skipped", "reason": "ambiguous_adjacent_links"}
    browser_session[3].goto.assert_called_once()


@pytest.mark.parametrize(
    ("status", "containers", "rows"),
    [
        ("missing_list", 0, []),
        ("ambiguous_list", 2, []),
        ("empty", 1, []),
        ("conflicting_empty_marker", 1, [{}]),
        ("observed", 2, [{}]),
        ("observed", 1, []),
    ],
)
def test_unusable_first_main_list_never_follows_pagination(
    tmp_path, browser_session, status, containers, rows
):
    next_url = build_list_url("normal", "comic_new6", "ai", page=2)
    first = _observed_snapshot(candidates=[_candidate(next_url)])
    first.update(status=status, counts={"list_containers": containers}, rows=rows)
    browser_session[5].return_value = first
    report = inspection.run_list_inspection(tmp_path)
    assert report["status"] == "inspected_unverified"
    assert report["snapshot"] == first
    assert report["follow_up"] == {"status": "skipped", "reason": "main_list_not_observed"}
    browser_session[3].goto.assert_called_once()


@pytest.mark.parametrize("status", [None, 403, 429, 503])
def test_second_response_error_preserves_first_and_stops_without_retry(
    tmp_path, browser_session, status
):
    _manager, _driver, browser, page, response, inspect = browser_session
    next_url = build_list_url("normal", "comic_new6", "ai", page=2)
    first = _observed_snapshot(candidates=[_candidate(next_url)])
    inspect.return_value = first
    second_response = MagicMock() if status is not None else None
    if second_response is not None:
        second_response.status = status
        second_response.header_value.return_value = "120"
    page.goto.side_effect = [response, second_response]
    report = inspection.run_list_inspection(tmp_path)
    assert report["status"] == "inspection_failed"
    assert report["last_stage"] == "follow_up_navigation"
    assert report["error_type"] == "HTTPStatusError"
    assert report["http_status"] == 200
    assert report["snapshot"] == first
    assert report["navigation_attempts"] == 2
    assert report["follow_up"]["status"] == "failed"
    assert report["follow_up"]["http_status"] == status
    assert report["follow_up"]["retry_after"] == ("120" if status is not None else None)
    assert "snapshot" not in report["follow_up"]
    assert page.goto.call_count == 2
    inspect.assert_called_once()
    browser.close.assert_called_once()


def test_second_navigation_exception_keeps_first_with_only_safe_error_code(
    tmp_path, browser_session
):
    next_url = build_list_url("normal", "comic_new6", "ai", page=2)
    first = _observed_snapshot(candidates=[_candidate(next_url)])
    browser_session[5].return_value = first
    browser_session[3].goto.side_effect = [
        browser_session[4],
        RuntimeError("net::ERR_CONNECTION_RESET at https://example.invalid/?token=secret"),
    ]
    report = inspection.run_list_inspection(tmp_path)
    assert report["status"] == "inspection_failed"
    assert report["last_stage"] == "follow_up_navigation"
    assert report["snapshot"] == first
    assert report["error_code"] == "ERR_CONNECTION_RESET"
    assert report["follow_up"]["error_code"] == "ERR_CONNECTION_RESET"
    assert report["follow_up"]["status"] == "failed"
    assert "secret" not in json.dumps(report)
    assert browser_session[3].goto.call_count == 2
    browser_session[2].close.assert_called_once()


def test_second_dom_exception_keeps_first_and_safe_diagnostics(tmp_path, browser_session):
    next_url = build_list_url("normal", "comic_new6", "ai", page=2)
    first = _observed_snapshot(candidates=[_candidate(next_url)])
    diagnostics = {"counts": {".gall_list": 0}, "samples": []}
    browser_session[5].side_effect = [
        first,
        DCSnapshotError("private second document", diagnostics=diagnostics),
    ]
    report = inspection.run_list_inspection(tmp_path)
    assert report["status"] == "inspection_failed"
    assert report["last_stage"] == "follow_up_dom_inspection"
    assert report["snapshot"] == first
    assert report["follow_up"]["status"] == "failed"
    assert report["diagnostics"] == diagnostics
    assert "private second document" not in json.dumps(report)
    assert browser_session[3].goto.call_count == 2
    browser_session[2].close.assert_called_once()


def test_combined_report_limit_discards_only_second_snapshot(
    tmp_path, browser_session, monkeypatch
):
    monkeypatch.setattr(inspection, "MAX_REPORT_BYTES", 6000)
    next_url = build_list_url("normal", "comic_new6", "ai", page=2)
    first = _observed_snapshot(candidates=[_candidate(next_url)])
    second = _observed_snapshot(next_url)
    second["fixture_metadata"] = "a" * 5000
    browser_session[5].side_effect = [first, second]
    report = inspection.run_list_inspection(tmp_path)
    assert report["status"] == "inspection_failed"
    assert report["snapshot"] == first
    assert report["follow_up"]["status"] == "failed"
    assert "snapshot" not in report["follow_up"]
    assert Path(report["report_path"]).stat().st_size <= 6000


def test_share_report_redacts_cursor_in_nested_follow_up_without_losing_scope():
    cursor = "-1200000"
    url = build_list_url("normal", "comic_new6", "ai", page=2, search_pos=cursor)
    shared = inspection.share_report(
        {"follow_up": {"url": url, "snapshot": _observed_snapshot(url, [_candidate(url)])}}
    )
    assert cursor not in json.dumps(shared)
    digest = hashlib.sha256(cursor.encode()).hexdigest()
    assert "search_pos_sha256=" + digest in shared["follow_up"]["url"]
    assert shared["follow_up"]["snapshot"]["search_pos_sha256"] == digest
    assert "page=2" in shared["follow_up"]["snapshot"]["url"]
