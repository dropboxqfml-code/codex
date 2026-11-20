import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from image_monitor import watch_browser as backend
from image_monitor.dcinside import DCSnapshotError
from image_monitor.native_ui import NativeUIError
from image_monitor.search_list import SEARCH_TYPE, build_list_url, validate_list_url
from image_monitor.watch_store import WatchScope

NOW = datetime(2026, 11, 15, 12, tzinfo=UTC)
SCOPE = WatchScope("test", "normal", "comic_new6", "ai", SEARCH_TYPE)
PAGE_ONE = build_list_url("normal", "comic_new6", "ai")
PAGE_TWO = build_list_url("normal", "comic_new6", "ai", page=2)


def snapshot(*, url=PAGE_ONE, links=()):
    target = validate_list_url(url)
    return {
        "status": "observed",
        "layout_status": "unverified",
        "queue_eligible": False,
        "url": url,
        "page": target["page"],
        "search_pos": target["search_pos"],
        "observed_at": NOW.isoformat(),
        "counts": {"list_containers": 1},
        "rows": [{"canonical_url": "https://gall.dcinside.com/board/view/?id=comic_new6&no=1"}],
        "pagination_candidates": [
            {
                "canonical_url": link,
                "page": validate_list_url(link)["page"],
                "search_pos": validate_list_url(link)["search_pos"],
            }
            for link in links
        ],
    }


@pytest.fixture
def browser_session(monkeypatch):
    monkeypatch.setattr(backend, "require_windows", lambda: None)
    executable = MagicMock(side_effect=lambda browser: Path(browser + ".exe"))
    monkeypatch.setattr(backend, "browser_executable", executable)
    manager = MagicMock()
    driver = manager.__enter__.return_value
    browser = driver.chromium.launch.return_value
    browser.version = "test-version"
    page = browser.new_context.return_value.new_page.return_value
    response = page.goto.return_value
    response.status = 200
    response.header_value.return_value = None
    inspect = MagicMock(return_value=snapshot())
    playwright = MagicMock(return_value=manager)
    monkeypatch.setattr(backend, "_playwright", playwright)
    monkeypatch.setattr(backend, "inspect_list", inspect)
    return manager, driver, browser, page, response, inspect, playwright, executable


def test_platform_guard_precedes_browser_discovery_and_launch(monkeypatch, browser_session):
    monkeypatch.setattr(backend, "require_windows", windows_guard)
    with pytest.raises(NativeUIError, match="Windows"):
        with backend.HeadlessWatchBrowser():
            pytest.fail("The platform guard must reject entry")
    browser_session[6].assert_not_called()
    browser_session[7].assert_not_called()


def windows_guard():
    raise NativeUIError("Windows required")


def test_real_non_windows_guard_rejects_before_launch(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    playwright = MagicMock()
    monkeypatch.setattr(backend, "_playwright", playwright)
    with pytest.raises(NativeUIError, match="Windows"):
        with backend.HeadlessWatchBrowser():
            pytest.fail("Windows guard must reject Linux")
    playwright.assert_not_called()


@pytest.mark.parametrize("choice", ["chrome", "edge"])
def test_owns_one_fresh_headless_system_browser_and_closes_only_it(browser_session, choice):
    manager, driver, browser, page, response, inspect, _, executable = browser_session
    owned = backend.HeadlessWatchBrowser(choice, now=lambda: NOW)
    assert owned.browser_closed is None
    with owned as entered:
        assert entered is owned
        report = entered.scan(SCOPE, NOW)
        assert entered.browser_version == entered.version == "test-version"
        browser.close.assert_not_called()
    executable.assert_called_once_with(choice)
    driver.chromium.launch.assert_called_once_with(
        executable_path=choice + ".exe",
        headless=True,
        timeout=45_000,
        args=["--disable-background-networking"],
    )
    driver.chromium.launch_persistent_context.assert_not_called()
    driver.chromium.connect_over_cdp.assert_not_called()
    browser.new_context.assert_called_once_with(accept_downloads=False)
    page.goto.assert_called_once_with(PAGE_ONE, wait_until="domcontentloaded", timeout=30_000)
    response.header_value.assert_called_once_with("retry-after")
    inspect.assert_called_once_with(page, expected_url=PAGE_ONE, observed_at=NOW, timeout_ms=15_000)
    assert report["status"] == "observed"
    assert report["pages"][0]["layout_status"] == "unverified"
    assert "scan_observed_at" not in inspect.return_value
    assert report["pages"][0]["scan_observed_at"] == NOW.isoformat(timespec="microseconds")
    assert report["navigation"] == [{"url": PAGE_ONE, "http_status": 200, "retry_after": None}]
    assert [item[0] for item in page.mock_calls] == [
        "goto",
        "goto().header_value",
        "on",
        "remove_listener",
    ]
    browser.close.assert_called_once()
    manager.__exit__.assert_called_once_with(None, None, None)
    assert owned.browser_closed is True


def test_two_scans_share_session_and_always_reset_latest_page_one(browser_session):
    _, driver, browser, page, _, inspect, *_ = browser_session
    inspect.side_effect = [snapshot(links=[PAGE_TWO]), snapshot(url=PAGE_TWO)] * 2
    times = iter(NOW + timedelta(seconds=value) for value in [1, 32, 61, 92])
    with backend.HeadlessWatchBrowser(now=lambda: next(times)) as owned:
        first = owned.scan(SCOPE, NOW)
        second = owned.scan(SCOPE, NOW + timedelta(seconds=60))
        browser.close.assert_not_called()
    assert [item.args[0] for item in page.goto.call_args_list] == [
        PAGE_ONE,
        PAGE_TWO,
        PAGE_ONE,
        PAGE_TWO,
    ]
    assert [item.kwargs["observed_at"] for item in inspect.call_args_list] == [
        NOW + timedelta(seconds=value) for value in [1, 32, 61, 92]
    ]
    assert len(first["pages"]) == len(second["pages"]) == 2
    assert {item["scan_observed_at"] for item in second["pages"]} == {
        (NOW + timedelta(seconds=60)).isoformat(timespec="microseconds")
    }
    driver.chromium.launch.assert_called_once()
    browser.new_context.assert_called_once()
    browser.close.assert_called_once()


def test_second_page_links_never_recurse_to_third_page(browser_session):
    page, inspect = browser_session[3], browser_session[5]
    third = build_list_url("normal", "comic_new6", "ai", page=3)
    inspect.side_effect = [snapshot(links=[PAGE_TWO]), snapshot(url=PAGE_TWO, links=[third])]
    with backend.HeadlessWatchBrowser(now=lambda: NOW) as owned:
        report = owned.scan(SCOPE, NOW)
    assert len(report["pages"]) == page.goto.call_count == 2


@pytest.mark.parametrize(
    "links",
    [
        [],
        [build_list_url("normal", "comic_new6", "ai", page=3)],
        [build_list_url("normal", "comic_new6", "other", page=2)],
        [build_list_url("normal", "another", "ai", page=2)],
        [build_list_url("minor", "comic_new6", "ai", page=2)],
        [build_list_url("normal", "comic_new6", "ai", page=2, search_pos="-123")],
        [PAGE_TWO + "&search_head="],
        [PAGE_TWO + "&exception_mode=recommend"],
        [PAGE_TWO, PAGE_TWO],
    ],
)
def test_only_one_actual_same_scope_latest_adjacent_link_is_followed(browser_session, links):
    page, inspect = browser_session[3], browser_session[5]
    inspect.return_value = snapshot(links=links)
    with backend.HeadlessWatchBrowser(now=lambda: NOW) as owned:
        report = owned.scan(SCOPE, NOW)
    assert len(report["pages"]) == 1
    page.goto.assert_called_once()


@pytest.mark.parametrize("field,value", [("status", "ambiguous_list"), ("rows", [])])
def test_adjacent_navigation_requires_observed_nonempty_root(browser_session, field, value):
    page, inspect = browser_session[3], browser_session[5]
    inspect.return_value = snapshot(links=[PAGE_TWO]) | {field: value}
    with backend.HeadlessWatchBrowser(now=lambda: NOW) as owned:
        owned.scan(SCOPE, NOW)
    page.goto.assert_called_once()


@pytest.mark.parametrize("count", [0, 2])
def test_adjacent_navigation_requires_one_qualified_root(browser_session, count):
    page, inspect = browser_session[3], browser_session[5]
    inspect.return_value = snapshot(links=[PAGE_TWO]) | {"counts": {"list_containers": count}}
    with backend.HeadlessWatchBrowser(now=lambda: NOW) as owned:
        owned.scan(SCOPE, NOW)
    page.goto.assert_called_once()


def test_one_page_limit_ignores_actual_adjacent_link(browser_session):
    page, inspect = browser_session[3], browser_session[5]
    inspect.return_value = snapshot(links=[PAGE_TWO])
    with backend.HeadlessWatchBrowser(now=lambda: NOW) as owned:
        report = owned.scan(SCOPE, NOW, max_pages=1)
    assert len(report["pages"]) == 1
    page.goto.assert_called_once()


@pytest.mark.parametrize("status", [None, 400, 401, 403, 404, 429, 503])
def test_http_failure_stops_without_inspection_or_retry(browser_session, status):
    browser, page, response, inspect = browser_session[2:6]
    if status is None:
        page.goto.return_value = None
    else:
        response.status = status
        response.header_value.return_value = "120"
    with backend.HeadlessWatchBrowser(now=lambda: NOW) as owned:
        report = owned.scan(SCOPE, NOW)
    assert report["status"] == "http_error"
    assert report["http_status"] == status
    assert (
        report["retry_after"] == report["lastRetryAfter"] == ("120" if status is not None else None)
    )
    assert report["pages"] == []
    page.goto.assert_called_once()
    inspect.assert_not_called()
    response.body.assert_not_called()
    response.text.assert_not_called()
    browser.close.assert_called_once()


def test_retry_after_is_bounded(browser_session):
    browser_session[4].status = 429
    browser_session[4].header_value.return_value = "x" * 500
    with backend.HeadlessWatchBrowser(now=lambda: NOW) as owned:
        report = owned.scan(SCOPE, NOW)
    assert report["retry_after"] == report["lastRetryAfter"] == "x" * 256
    assert report["navigation"][0]["retry_after"] == "x" * 256


def incomplete_page(issue="secondary_table_empty", *, complete=True):
    return snapshot() | {"rows_complete": complete, "selector_evidence": {"profile_issue": issue}}


@pytest.mark.parametrize(
    ("issue", "complete", "status", "retry_after"),
    [
        ("scope_unreviewed", True, 200, None),
        ("container_inventory", True, 200, None),
        ("multiple_profile_checks", True, 200, None),
        ("ordinary_date_missing", False, 200, None),
        ("secondary_table_empty", True, 304, None),
        ("secondary_table_empty", True, 200, "60"),
    ],
)
def test_dom_settle_requires_a_recognized_incomplete_profile_and_safe_response(
    browser_session, issue, complete, status, retry_after
):
    page, response, inspect = browser_session[3:6]
    response.status = status
    response.header_value.return_value = retry_after
    inspect.return_value = incomplete_page(issue, complete=complete)
    with backend.HeadlessWatchBrowser(now=lambda: NOW) as owned:
        result = owned.scan(SCOPE, NOW)
    assert result["pages"][0]["layout_status"] == "unverified"
    page.wait_for_timeout.assert_not_called()
    assert page.goto.call_count == inspect.call_count == 1


def test_dom_settle_does_not_reinspect_after_stop(browser_session):
    page, _, inspect = browser_session[3:6]
    inspect.return_value = incomplete_page()
    with backend.HeadlessWatchBrowser(
        now=lambda: NOW, should_stop=lambda: page.wait_for_timeout.called
    ) as owned:
        result = owned.scan(SCOPE, NOW)
    assert result["status"] == "cancelled"
    assert result["pages"][0]["layout_status"] == "unverified"
    assert page.goto.call_count == inspect.call_count == 1


def test_dom_settle_rejects_replaced_main_document_even_at_same_url(browser_session):
    page, _, inspect = browser_session[3:6]
    inspect.return_value = incomplete_page()
    page.wait_for_timeout.side_effect = lambda _ms: page.on.call_args.args[1](page.main_frame)
    with backend.HeadlessWatchBrowser(now=lambda: NOW) as owned:
        result = owned.scan(SCOPE, NOW)
    assert result["status"] == "inspection_error"
    assert result["pages"] == []
    assert page.goto.call_count == inspect.call_count == 1


@pytest.mark.parametrize("failure", ["http", "network", "inspection"])
def test_second_page_failure_preserves_first_snapshot(browser_session, failure):
    page, response, inspect = browser_session[3:6]
    first = snapshot(links=[PAGE_TWO])
    inspect.side_effect = [first, DCSnapshotError("private DOM detail")]
    if failure == "http":
        failed = MagicMock(status=503)
        failed.header_value.return_value = "120"
        page.goto.side_effect = [response, failed]
    elif failure == "network":
        page.goto.side_effect = [response, RuntimeError("net::ERR_CONNECTION_RESET private token")]
    with backend.HeadlessWatchBrowser(now=lambda: NOW) as owned:
        report = owned.scan(SCOPE, NOW)
    assert report["status"] == failure + "_error"
    assert len(report["pages"]) == 1
    assert report["pages"][0]["url"] == first["url"]
    assert len(report["navigation"]) == page.goto.call_count == 2
    assert "private" not in json.dumps(report)


@pytest.mark.parametrize(
    "message,code",
    [
        (
            "net::ERR_TUNNEL_CONNECTION_FAILED https://private.invalid/?token=secret",
            "ERR_TUNNEL_CONNECTION_FAILED",
        ),
        ("Timeout 30000ms exceeded at C:/Users/private", "Timeout"),
        ("net::ERR_UNKNOWN https://private.invalid/?token=secret", None),
    ],
)
def test_network_errors_expose_only_whitelisted_code(browser_session, message, code):
    browser_session[3].goto.side_effect = RuntimeError(message)
    with backend.HeadlessWatchBrowser(now=lambda: NOW) as owned:
        report = owned.scan(SCOPE, NOW)
    assert report["status"] == "network_error"
    assert report["error_type"] == "RuntimeError"
    assert report["error_code"] == code
    assert "private" not in json.dumps(report)
    assert "secret" not in json.dumps(report)
    browser_session[5].assert_not_called()


def test_inspection_error_retains_only_bounded_shape_diagnostics(browser_session):
    browser_session[5].side_effect = DCSnapshotError(
        "private cookie token",
        diagnostics={
            "counts": {".gall_list": 0, "private cookie": "secret"},
            "samples": [],
            "headers": {"authorization": "secret"},
            "message": "private DOM text",
        },
    )
    with backend.HeadlessWatchBrowser(now=lambda: NOW) as owned:
        report = owned.scan(SCOPE, NOW)
    assert report["status"] == "inspection_error"
    assert report["diagnostics"]["counts"] == {".gall_list": 0}
    assert report["diagnostics"]["samples"] == []
    assert "private" not in json.dumps(report)
    assert "secret" not in json.dumps(report)


@pytest.mark.parametrize("offset", [-1, 121])
def test_page_observation_must_remain_within_scan_window(browser_session, offset):
    with backend.HeadlessWatchBrowser(now=lambda: NOW + timedelta(seconds=offset)) as owned:
        report = owned.scan(SCOPE, NOW)
    assert report["status"] == "inspection_error"
    assert report["error_type"] == "DCSnapshotError"
    browser_session[5].assert_not_called()


@pytest.mark.parametrize("error_type", [KeyboardInterrupt, SystemExit])
def test_cancel_closes_owned_browser_and_driver(browser_session, error_type):
    browser_session[3].goto.side_effect = error_type("cancel")
    owned = backend.HeadlessWatchBrowser(now=lambda: NOW)
    with pytest.raises(error_type):
        with owned:
            owned.scan(SCOPE, NOW)
    browser_session[2].close.assert_called_once()
    browser_session[0].__exit__.assert_called_once()
    assert owned.browser_closed is True


def test_launch_error_is_sanitized_and_closes_driver(browser_session):
    browser_session[1].chromium.launch.side_effect = RuntimeError("private executable path")
    owned = backend.HeadlessWatchBrowser()
    with pytest.raises(backend.WatchBrowserError) as caught:
        with owned:
            pytest.fail("Launch should fail")
    assert "private" not in str(caught.value)
    assert caught.value.error_type == "RuntimeError"
    assert owned.browser_closed is None
    browser_session[0].__exit__.assert_called_once()
    browser_session[2].close.assert_not_called()


def test_setup_error_closes_owned_browser(browser_session):
    browser_session[2].new_context.side_effect = RuntimeError("private context failure")
    owned = backend.HeadlessWatchBrowser()
    with pytest.raises(backend.WatchBrowserError):
        with owned:
            pytest.fail("Context setup should fail")
    assert owned.browser_closed is True
    browser_session[2].close.assert_called_once()
    browser_session[0].__exit__.assert_called_once()


def test_cleanup_error_is_sanitized_and_driver_still_closes(browser_session):
    browser_session[2].close.side_effect = RuntimeError("private process detail")
    owned = backend.HeadlessWatchBrowser(now=lambda: NOW)
    with pytest.raises(backend.WatchBrowserError) as caught:
        with owned:
            owned.scan(SCOPE, NOW)
    assert owned.browser_closed is False
    assert owned.cleanup_error_type == "RuntimeError"
    assert "private" not in str(caught.value)
    browser_session[0].__exit__.assert_called_once()


def test_cleanup_failure_does_not_replace_cancellation(browser_session):
    browser_session[2].close.side_effect = RuntimeError("private process detail")
    owned = backend.HeadlessWatchBrowser()
    with pytest.raises(KeyboardInterrupt):
        with owned:
            raise KeyboardInterrupt()
    assert owned.browser_closed is False
    assert owned.cleanup_error_type == "RuntimeError"
    browser_session[0].__exit__.assert_called_once()


@pytest.mark.parametrize("limit", [0, 3, True, "2"])
def test_page_limit_validation_precedes_navigation(browser_session, limit):
    with backend.HeadlessWatchBrowser(now=lambda: NOW) as owned:
        with pytest.raises(ValueError, match="max_pages"):
            owned.scan(SCOPE, NOW, max_pages=limit)
    browser_session[3].goto.assert_not_called()


def test_scope_search_type_cannot_silently_change(browser_session):
    scope = WatchScope("test", "normal", "comic_new6", "ai", "other")
    with backend.HeadlessWatchBrowser(now=lambda: NOW) as owned:
        with pytest.raises(ValueError, match="search type"):
            owned.scan(scope, NOW)
    browser_session[3].goto.assert_not_called()


def test_naive_scan_time_is_rejected_before_navigation(browser_session):
    with backend.HeadlessWatchBrowser(now=lambda: NOW) as owned:
        with pytest.raises(ValueError, match="aware"):
            owned.scan(SCOPE, NOW.replace(tzinfo=None))
    browser_session[3].goto.assert_not_called()


def test_scan_requires_active_context(browser_session):
    owned = backend.HeadlessWatchBrowser(now=lambda: NOW)
    with pytest.raises(ValueError, match="open browser"):
        owned.scan(SCOPE, NOW)
    with owned:
        owned.scan(SCOPE, NOW)
    with pytest.raises(ValueError, match="open browser"):
        owned.scan(SCOPE, NOW)
    assert browser_session[3].goto.call_args_list == [
        call(PAGE_ONE, wait_until="domcontentloaded", timeout=30_000)
    ]


@pytest.mark.parametrize("condition", [False, 1, "stop"])
def test_stop_condition_must_be_callable_before_browser_launch(browser_session, condition):
    with pytest.raises(ValueError, match="callable"):
        with backend.HeadlessWatchBrowser(should_stop=condition):
            pass
    browser_session[6].assert_not_called()
    browser_session[7].assert_not_called()


def test_preexisting_stop_does_not_navigate_or_inspect(browser_session):
    with backend.HeadlessWatchBrowser(now=lambda: NOW, should_stop=lambda: True) as owned:
        report = owned.scan(SCOPE, NOW)
    assert report["status"] == "cancelled"
    assert report["reason"] == "requested_stop"
    assert report["pages"] == report["navigation"] == []
    browser_session[3].goto.assert_not_called()
    browser_session[5].assert_not_called()
    assert owned.browser_closed is True


def test_stop_during_navigation_avoids_further_dom_inspection(browser_session):
    stopped = False

    def response(*_args, **_kwargs):
        nonlocal stopped
        stopped = True
        return browser_session[4]

    browser_session[3].goto.side_effect = response
    with backend.HeadlessWatchBrowser(now=lambda: NOW, should_stop=lambda: stopped) as owned:
        report = owned.scan(SCOPE, NOW)
    assert report["status"] == "cancelled"
    assert report["http_status"] == 200
    assert len(report["navigation"]) == 1
    assert report["pages"] == []
    browser_session[5].assert_not_called()


def test_stop_after_first_snapshot_preserves_it_without_following_page_two(browser_session):
    stopped = False

    def inspect(*_args, **_kwargs):
        nonlocal stopped
        stopped = True
        return snapshot(links=[PAGE_TWO])

    browser_session[5].side_effect = inspect
    with backend.HeadlessWatchBrowser(now=lambda: NOW, should_stop=lambda: stopped) as owned:
        report = owned.scan(SCOPE, NOW)
    assert report["status"] == "cancelled"
    assert len(report["pages"]) == len(report["navigation"]) == 1
    assert report["pages"][0]["url"] == PAGE_ONE
    browser_session[3].goto.assert_called_once_with(
        PAGE_ONE, wait_until="domcontentloaded", timeout=30_000
    )
    assert owned.browser_closed is True


@pytest.mark.parametrize("value", [None, 1, "true"])
def test_nonboolean_stop_callback_result_is_rejected_before_navigation(browser_session, value):
    with backend.HeadlessWatchBrowser(should_stop=lambda: value) as owned:
        with pytest.raises(ValueError, match="boolean"):
            owned.scan(SCOPE, NOW)
    browser_session[3].goto.assert_not_called()
