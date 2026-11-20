"""Exercise one candidate navigation with inert browser and DOM observations."""

import json
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from image_monitor import candidate_browser as backend
from image_monitor import watch_browser as lifecycle
from image_monitor.dcinside import DCSnapshotError
from image_monitor.native_ui import NativeUIError

NOW = datetime(2026, 11, 16, 4, 0, tzinfo=UTC)
URL = "https://gall.dcinside.com/board/view/?id=comic_new6&no=104"
CANDIDATE = {
    "gallery_type": "normal",
    "gallery_id": "comic_new6",
    "post_id": "104",
    "post_url": URL,
}


def snapshot():
    return {
        "gallery_type": "normal",
        "gallery_id": "comic_new6",
        "post_id": "104",
        "post_url": URL,
        "layout_status": "unverified",
        "queue_eligible": False,
        "published_at": "2026-11-16T13:00:00+09:00",
        "published_at_raw": "2026.11.16 13:00:00",
        "images": [],
        "observed_at": NOW.isoformat(),
    }


@pytest.fixture
def browser_session(monkeypatch):
    monkeypatch.setattr(lifecycle, "require_windows", lambda: None)
    executable = MagicMock(return_value=Path("chrome.exe"))
    monkeypatch.setattr(lifecycle, "browser_executable", executable)
    manager = MagicMock()
    driver = manager.__enter__.return_value
    browser = driver.chromium.launch.return_value
    browser.version = "test-version"
    page = browser.new_context.return_value.new_page.return_value
    response = page.goto.return_value
    response.status = 200
    response.header_value.return_value = None
    inspect = MagicMock(return_value=snapshot())
    monkeypatch.setattr(lifecycle, "_playwright", MagicMock(return_value=manager))
    monkeypatch.setattr(backend, "inspect_post", inspect)
    return manager, driver, browser, page, response, inspect, executable


def test_candidate_uses_owned_headless_lifecycle_and_one_dom_observation(browser_session):
    manager, driver, browser, page, response, inspect, executable = browser_session
    with backend.HeadlessCandidateBrowser(now=lambda: NOW) as owned:
        result = owned.inspect(CANDIDATE, NOW)
        browser.close.assert_not_called()
    assert result == {
        "status": "observed",
        "url": URL,
        "http_status": 200,
        "retry_after": None,
        "navigation_attempts": 1,
        "error_type": None,
        "error_code": None,
        "snapshot": snapshot(),
    }
    executable.assert_called_once_with("chrome")
    driver.chromium.launch.assert_called_once_with(
        executable_path="chrome.exe",
        headless=True,
        timeout=45_000,
        args=["--disable-background-networking"],
    )
    browser.new_context.assert_called_once_with(accept_downloads=False)
    page.goto.assert_called_once_with(URL, wait_until="domcontentloaded", timeout=30_000)
    response.header_value.assert_called_once_with("retry-after")
    inspect.assert_called_once_with(
        page, expected_url=URL, observed_at=NOW, include_dccon=False, timeout_ms=20_000
    )
    assert [call[0] for call in page.mock_calls] == ["goto", "goto().header_value"]
    driver.chromium.launch_persistent_context.assert_not_called()
    driver.chromium.connect_over_cdp.assert_not_called()
    browser.close.assert_called_once()
    manager.__exit__.assert_called_once_with(None, None, None)
    assert owned.browser_closed is True


@pytest.mark.parametrize(
    "candidate",
    [
        None,
        {},
        CANDIDATE | {"gallery_type": "minor"},
        CANDIDATE | {"gallery_id": "other"},
        CANDIDATE | {"post_id": "105"},
        CANDIDATE | {"post_id": 104},
        CANDIDATE | {"post_url": URL + "&page=1"},
        CANDIDATE | {"post_url": URL.replace("104", "00104")},
        CANDIDATE | {"post_url": URL.replace("https://", "http://")},
        CANDIDATE | {"post_url": URL.replace("comic_new6", "other")},
        CANDIDATE | {"post_url": URL.replace("/board/view/", "/mgallery/board/view/")},
        CANDIDATE | {"post_url": URL.replace("gall.dcinside.com", "example.test")},
    ],
)
def test_invalid_or_foreign_candidate_is_rejected_before_navigation(browser_session, candidate):
    with backend.HeadlessCandidateBrowser(now=lambda: NOW) as owned:
        with pytest.raises(ValueError):
            owned.inspect(candidate, NOW)
    browser_session[3].goto.assert_not_called()
    browser_session[5].assert_not_called()


@pytest.mark.parametrize("stamp", [None, "2026-11-16", datetime(2026, 11, 16)])
def test_invalid_observation_clock_is_rejected_before_navigation(browser_session, stamp):
    with backend.HeadlessCandidateBrowser(now=lambda: NOW) as owned:
        with pytest.raises(ValueError):
            owned.inspect(CANDIDATE, stamp)
    browser_session[3].goto.assert_not_called()
    browser_session[5].assert_not_called()


def test_inspect_requires_open_context():
    with pytest.raises(ValueError, match="open browser"):
        backend.HeadlessCandidateBrowser().inspect(CANDIDATE, NOW)


@pytest.mark.parametrize("status", [401, 403, 404, 410, 429, 500, 503])
def test_http_failure_retains_status_and_bounded_retry_without_inspection(browser_session, status):
    response = browser_session[4]
    response.status = status
    response.header_value.return_value = "1" * 300
    with backend.HeadlessCandidateBrowser(now=lambda: NOW) as owned:
        result = owned.inspect(CANDIDATE, NOW)
    assert result["status"] == "http_error"
    assert result["http_status"] == status
    assert result["retry_after"] == "1" * 256
    assert result["navigation_attempts"] == 1
    assert result["error_type"] == "HTTPStatusError"
    assert "snapshot" not in result
    browser_session[3].goto.assert_called_once()
    browser_session[5].assert_not_called()


def test_absent_response_stops_without_inspection(browser_session):
    browser_session[3].goto.return_value = None
    with backend.HeadlessCandidateBrowser(now=lambda: NOW) as owned:
        result = owned.inspect(CANDIDATE, NOW)
    assert result["status"] == "http_error"
    assert result["http_status"] is None
    browser_session[5].assert_not_called()


def test_network_failure_reports_only_class_and_known_code_without_retry(browser_session):
    browser_session[3].goto.side_effect = RuntimeError(
        "net::ERR_CONNECTION_RESET at https://private.example/?token=private"
    )
    with backend.HeadlessCandidateBrowser(now=lambda: NOW) as owned:
        result = owned.inspect(CANDIDATE, NOW)
    assert result["status"] == "network_error"
    assert result["error_type"] == "RuntimeError"
    assert result["error_code"] == "ERR_CONNECTION_RESET"
    assert "private" not in json.dumps(result)
    browser_session[3].goto.assert_called_once()
    browser_session[5].assert_not_called()


def test_dom_failure_keeps_safe_bounded_diagnostics_and_http_observation(browser_session):
    browser_session[5].side_effect = DCSnapshotError(
        "private external message",
        diagnostics={
            "body_count": 2,
            "cookie": "private-cookie",
            "nested": {"authorization": "private-authorization", "header_count": 1},
        },
    )
    with backend.HeadlessCandidateBrowser(now=lambda: NOW) as owned:
        result = owned.inspect(CANDIDATE, NOW)
    assert result["status"] == "inspection_error"
    assert result["http_status"] == 200
    assert result["error_type"] == "DCSnapshotError"
    assert result["diagnostics"] == {"body_count": 2, "nested": {"header_count": 1}}
    assert "private" not in json.dumps(result)
    assert "snapshot" not in result


def test_oversized_diagnostics_are_omitted(browser_session, monkeypatch):
    monkeypatch.setattr(backend, "MAX_OBSERVATION_BYTES", 300)
    browser_session[5].side_effect = DCSnapshotError("private", diagnostics={"text": "x" * 400})
    with backend.HeadlessCandidateBrowser(now=lambda: NOW) as owned:
        result = owned.inspect(CANDIDATE, NOW)
    assert result["status"] == "inspection_error"
    assert result["diagnostics_omitted"] == "metadata_limit"
    assert "diagnostics" not in result


@pytest.mark.parametrize("diagnostics", [{"bad": object()}, {"bad": float("nan")}])
def test_invalid_diagnostics_are_omitted_without_external_text(browser_session, diagnostics):
    browser_session[5].side_effect = DCSnapshotError("private", diagnostics=diagnostics)
    with backend.HeadlessCandidateBrowser(now=lambda: NOW) as owned:
        result = owned.inspect(CANDIDATE, NOW)
    assert result["status"] == "inspection_error"
    assert result["diagnostics_omitted"] == "invalid_metadata"
    assert "private" not in json.dumps(result)


def test_snapshot_secret_and_inline_byte_fields_are_removed_without_promoting_trust(
    browser_session,
):
    private = snapshot() | {
        "cookie": "private-cookie",
        "headers": {"authorization": "private-authorization"},
        "images": [{"display_url": "data:image/png;base64,PRIVATE", "body_order": 1}],
    }
    browser_session[5].return_value = private
    with backend.HeadlessCandidateBrowser(now=lambda: NOW) as owned:
        result = owned.inspect(CANDIDATE, NOW)
    observed = result["snapshot"]
    assert observed["layout_status"] == "unverified"
    assert observed["queue_eligible"] is False
    assert "cookie" not in observed and "headers" not in observed
    assert observed["images"][0]["display_url"] is None
    assert observed["images"][0]["source_scheme"] == "data"
    assert "PRIVATE" not in json.dumps(observed)
    assert private["images"][0]["display_url"].startswith("data:")


@pytest.mark.parametrize("value", [[], {"text": "x" * 1000}, {"bad": object()}])
def test_invalid_or_oversized_snapshot_is_not_returned(browser_session, monkeypatch, value):
    monkeypatch.setattr(backend, "MAX_OBSERVATION_BYTES", 500)
    browser_session[5].return_value = value
    with backend.HeadlessCandidateBrowser(now=lambda: NOW) as owned:
        result = owned.inspect(CANDIDATE, NOW)
    assert result["status"] == "inspection_error"
    assert "snapshot" not in result


@pytest.mark.parametrize("kind", ["snapshot", "diagnostics"])
@pytest.mark.parametrize("extra_byte", [0, 1])
def test_metadata_boundary_reserves_space_for_durable_result_wrapper(
    browser_session, kind, extra_byte
):
    assert backend.MAX_SNAPSHOT_BYTES - backend.MAX_OBSERVATION_BYTES == 16 * 1024
    metadata = snapshot() if kind == "snapshot" else {}
    metadata["padding"] = ""
    envelope = {
        "status": "observed" if kind == "snapshot" else "inspection_error",
        "url": URL,
        "http_status": 200,
        "retry_after": None,
        "navigation_attempts": 1,
        "error_type": None if kind == "snapshot" else "DCSnapshotError",
        "error_code": None,
        kind: metadata,
    }
    metadata["padding"] = "x" * (
        backend.MAX_OBSERVATION_BYTES - backend._metadata_size(envelope) + extra_byte
    )
    if kind == "snapshot":
        browser_session[5].return_value = metadata
    else:
        browser_session[5].side_effect = DCSnapshotError("private", diagnostics=metadata)
    with backend.HeadlessCandidateBrowser(now=lambda: NOW) as owned:
        result = owned.inspect(CANDIDATE, NOW)
    if extra_byte:
        assert kind not in result
        assert result["status"] == "inspection_error"
        if kind == "diagnostics":
            assert result["diagnostics_omitted"] == "metadata_limit"
    else:
        assert backend._metadata_size(result) == backend.MAX_OBSERVATION_BYTES
        wrapped = {
            "private_observation": result,
            "classification": {"time_status": "unknown", "save_approved": False},
            "control": {
                "finished_at": NOW.isoformat(),
                "next_eligible_at": (NOW + timedelta(seconds=60)).isoformat(),
                "interval_seconds": 60,
                "blocked": False,
                "http_status": 200,
            },
        }
        assert backend._metadata_size(wrapped) < backend.MAX_SNAPSHOT_BYTES


@pytest.mark.parametrize("offset", [-1, 121])
def test_actual_observation_outside_bounded_window_is_not_inspected(browser_session, offset):
    with backend.HeadlessCandidateBrowser(now=lambda: NOW + timedelta(seconds=offset)) as owned:
        result = owned.inspect(CANDIDATE, NOW)
    assert result["status"] == "inspection_error"
    assert result["error_type"] == "DCSnapshotError"
    browser_session[3].goto.assert_called_once()
    browser_session[5].assert_not_called()


@pytest.mark.parametrize("stage", ["navigation", "inspection"])
@pytest.mark.parametrize("error", [KeyboardInterrupt, SystemExit])
def test_cancellation_propagates_and_owned_browser_closes(browser_session, stage, error):
    target = browser_session[3].goto if stage == "navigation" else browser_session[5]
    target.side_effect = error("private")
    owned = backend.HeadlessCandidateBrowser(now=lambda: NOW)
    with pytest.raises(error):
        with owned:
            owned.inspect(CANDIDATE, NOW)
    assert owned.browser_closed is True
    browser_session[2].close.assert_called_once()


def test_platform_guard_precedes_inherited_browser_launch(browser_session, monkeypatch):
    def unsupported():
        raise NativeUIError("Windows required")

    monkeypatch.setattr(lifecycle, "require_windows", unsupported)
    with pytest.raises(NativeUIError, match="Windows"):
        with backend.HeadlessCandidateBrowser():
            pytest.fail("The platform guard must prevent launch")
    browser_session[6].assert_not_called()


def test_two_candidates_share_one_owned_session_and_keep_their_identity(browser_session):
    second = CANDIDATE | {"post_id": "105", "post_url": URL.replace("104", "105")}
    with backend.HeadlessCandidateBrowser(now=lambda: NOW) as owned:
        first_result = owned.inspect(CANDIDATE, NOW)
        second_result = owned.inspect(second, NOW)
    assert first_result["url"] == URL
    assert second_result["url"] == second["post_url"]
    assert [call.args[0] for call in browser_session[3].goto.call_args_list] == [
        URL,
        second["post_url"],
    ]
    browser_session[1].chromium.launch.assert_called_once()
    browser_session[2].close.assert_called_once()


def _safe_lifecycle_diagnostics(error, owned):
    error_types = {
        "Error",
        "TimeoutError",
        "TargetClosedError",
        "NativeUIError",
        "RuntimeError",
        "FileNotFoundError",
        "PermissionError",
        "OSError",
        "ImportError",
        "ModuleNotFoundError",
        "NotImplementedError",
        "ValueError",
        "TypeError",
        "AttributeError",
        "KeyError",
        "ConnectionError",
        "BrokenPipeError",
    }
    error_codes = {
        "ERR_TUNNEL_CONNECTION_FAILED",
        "ERR_NAME_NOT_RESOLVED",
        "ERR_CONNECTION_RESET",
        "ERR_CONNECTION_REFUSED",
        "Timeout",
    }

    def safe_type(value):
        if value is None:
            return None
        return value if isinstance(value, str) and value in error_types else "other"

    code = getattr(error, "error_code", None)
    closed = owned.browser_closed
    return {
        "error_type": safe_type(getattr(error, "error_type", None)),
        "error_code": code if isinstance(code, str) and code in error_codes else None,
        "browser_closed": closed if type(closed) is bool else None,
        "cleanup_error_type": safe_type(owned.cleanup_error_type),
    }


def test_real_fixture_lifecycle_diagnostics_preserve_known_failure_and_cleanup_state():
    error = lifecycle.WatchBrowserError("private lifecycle message", TimeoutError("private URL"))
    owned = SimpleNamespace(browser_closed=False, cleanup_error_type="TargetClosedError")
    assert _safe_lifecycle_diagnostics(error, owned) == {
        "error_type": "TimeoutError",
        "error_code": "Timeout",
        "browser_closed": False,
        "cleanup_error_type": "TargetClosedError",
    }


def test_real_fixture_lifecycle_diagnostics_omit_external_messages_and_unknown_values():
    error = SimpleNamespace(
        error_type="/private/browser/path",
        error_code="https://private.example/?token=secret",
    )
    owned = SimpleNamespace(browser_closed="private state", cleanup_error_type={"private": 1})
    diagnostics = _safe_lifecycle_diagnostics(error, owned)
    assert diagnostics == {
        "error_type": "other",
        "error_code": None,
        "browser_closed": None,
        "cleanup_error_type": "other",
    }
    assert "private" not in json.dumps(diagnostics)


def test_real_owned_browser_inspects_only_routed_candidate_dom(tmp_path, monkeypatch):
    pytest.importorskip("playwright.sync_api")
    if sys.platform != "win32":
        executable = shutil.which("chromium") or shutil.which("google-chrome")
        if not executable:
            pytest.skip("Installed Chromium unavailable")
        monkeypatch.setattr(lifecycle, "require_windows", lambda: None)
        monkeypatch.setattr(lifecycle, "browser_executable", lambda _: Path(executable))
    navigation = []
    html = """<!doctype html><meta charset="utf-8">
    <div class="gallview_head">
      <span class="title_subject">Invented candidate title</span>
      <span class="gall_writer" data-nick="Invented author"></span>
      <span class="gall_date" title="2026.11.16 13:00:00">13:00</span>
    </div><div class="write_div">Invented body without images</div>
    <div class="appending_file"><a href="https://attachment.example/unused">Unused</a></div>
    """

    def route_document(route):
        if route.request.url == URL and route.request.is_navigation_request():
            navigation.append(route.request.url)
            route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
        else:
            pytest.fail("Candidate inspection must not navigate attachment links")

    owned = backend.HeadlessCandidateBrowser(now=lambda: NOW)
    try:
        with owned:
            browser = owned._owned_browser
            owned._page.context.route("**/*", route_document)
            result = owned.inspect(CANDIDATE, NOW)
    except lifecycle.WatchBrowserError as error:
        pytest.fail(
            "Owned candidate browser lifecycle failed: "
            + json.dumps(_safe_lifecycle_diagnostics(error, owned), sort_keys=True),
            pytrace=False,
        )
    assert result["status"] == "observed"
    assert result["navigation_attempts"] == 1
    assert result["snapshot"]["published_at"] == "2026-11-16T13:00:00+09:00"
    assert result["snapshot"]["profile_evidence"]["header_count"] == 1
    assert result["snapshot"]["layout_status"] == "unverified"
    assert result["snapshot"]["queue_eligible"] is False
    assert result["snapshot"]["image_counts"]["included_unique"] == 0
    assert navigation == [URL]
    assert owned.browser_closed is True and browser.is_connected() is False
    assert list(tmp_path.iterdir()) == []
