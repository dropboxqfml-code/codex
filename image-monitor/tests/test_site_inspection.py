import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from image_monitor import site_inspection as inspection
from image_monitor.dcinside import DCSnapshotError
from image_monitor.native_ui import NativeUIError


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
    snapshot = {
        "images": [{"display_url": "https://cdn.example/image?token=private", "body_order": 1}],
        "attachment_inventory": [],
        "queue_eligible": False,
    }
    inspect = MagicMock(return_value=snapshot)
    monkeypatch.setattr(inspection, "_playwright", lambda: manager)
    monkeypatch.setattr(inspection, "inspect_post", inspect)
    return manager, driver, browser, page, response, inspect


def test_non_windows_guard_precedes_any_filesystem_or_browser_effect(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    root = tmp_path / "not-created"
    browser = MagicMock()
    monkeypatch.setattr(inspection, "_playwright", browser)
    with pytest.raises(NativeUIError, match="Windows"):
        inspection.run_site_inspection(root)
    assert not root.exists()
    browser.assert_not_called()


def test_invalid_post_url_is_rejected_before_launch_or_report_directory(tmp_path, browser_session):
    root = tmp_path / "not-created"
    with pytest.raises(DCSnapshotError):
        inspection.run_site_inspection(root, url="https://example.invalid/post")
    assert not root.exists()
    browser_session[1].chromium.launch.assert_not_called()


def test_owned_headless_inspection_reports_private_snapshot_and_closes_browser(
    tmp_path, browser_session
):
    manager, driver, browser, page, response, inspect = browser_session
    report = inspection.run_site_inspection(tmp_path, url=inspection.DEFAULT_POST_URL + "&page=2")
    driver.chromium.launch.assert_called_once_with(
        executable_path="chrome.exe",
        headless=True,
        timeout=15_000,
        args=["--disable-background-networking"],
    )
    browser.new_context.assert_called_once_with(accept_downloads=False)
    page.goto.assert_called_once_with(
        inspection.DEFAULT_POST_URL, wait_until="domcontentloaded", timeout=30_000
    )
    response.header_value.assert_called_once_with("retry-after")
    assert inspect.call_args.kwargs["timeout_ms"] == 20_000
    assert inspect.call_args.kwargs["observed_at"].utcoffset().total_seconds() == 0
    assert report["status"] == "inspected_unverified"
    assert report["last_stage"] == "complete"
    assert report["error_code"] is None
    assert report["images_saved"] is False
    assert report["queue_modified"] is False
    assert report["browser_closed"] is True
    assert "token=private" in report["snapshot"]["images"][0]["display_url"]
    assert json.loads(Path(report["report_path"]).read_text()) == report
    assert list(tmp_path.rglob("*")) == [
        Path(report["report_path"]).parent,
        Path(report["report_path"]),
    ]
    browser.close.assert_called_once()
    manager.__exit__.assert_called_once()


@pytest.mark.parametrize("status", [401, 403, 404, 429, 503])
def test_error_status_is_observed_once_without_body_inspection_or_retry(
    tmp_path, browser_session, status
):
    manager, _driver, browser, page, response, inspect = browser_session
    response.status = status
    response.header_value.return_value = "120"
    report = inspection.run_site_inspection(tmp_path)
    assert report["status"] == "inspection_failed"
    assert report["http_status"] == status
    assert report["last_stage"] == "page_navigation"
    assert report["retry_after"] == "120"
    assert report["error_type"] == "HTTPStatusError"
    inspect.assert_not_called()
    page.goto.assert_called_once()
    browser.close.assert_called_once()
    manager.__exit__.assert_called_once()


def test_structural_failure_preserves_only_diagnostics_and_generic_error(tmp_path, browser_session):
    manager, _driver, browser, _page, _response, inspect = browser_session
    diagnostics = {"counts": {".write_div": 0}, "samples": []}
    inspect.side_effect = DCSnapshotError("secret HTML must not be logged", diagnostics=diagnostics)
    report = inspection.run_site_inspection(tmp_path)
    assert report["status"] == "inspection_failed"
    assert report["error_type"] == "DCSnapshotError"
    assert report["last_stage"] == "dom_inspection"
    assert report["diagnostics"] == diagnostics
    assert "secret HTML" not in json.dumps(report)
    browser.close.assert_called_once()
    manager.__exit__.assert_called_once()


def test_browser_cleanup_failure_changes_success_to_failure(tmp_path, browser_session):
    manager, _driver, browser, _page, _response, _inspect = browser_session
    browser.close.side_effect = RuntimeError("secret process detail")
    report = inspection.run_site_inspection(tmp_path)
    assert report["status"] == "inspection_failed"
    assert report["browser_closed"] is False
    assert report["cleanup_error_type"] == "RuntimeError"
    assert report["last_stage"] == "dom_inspection"
    assert "secret process detail" not in json.dumps(report)
    manager.__exit__.assert_called_once()


def test_launch_failure_still_closes_driver_and_writes_private_report(tmp_path, browser_session):
    manager, driver, _browser, _page, _response, inspect = browser_session
    driver.chromium.launch.side_effect = RuntimeError("private installation path")
    report = inspection.run_site_inspection(tmp_path)
    assert report["status"] == "inspection_failed"
    assert report["browser_closed"] is None
    assert report["last_stage"] == "browser_launch"
    inspect.assert_not_called()
    manager.__exit__.assert_called_once()
    assert Path(report["report_path"]).is_file()
    assert "private installation path" not in json.dumps(report)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            "net::ERR_TUNNEL_CONNECTION_FAILED at https://example.invalid/?token=secret",
            "ERR_TUNNEL_CONNECTION_FAILED",
        ),
        (
            "net::ERR_NAME_NOT_RESOLVED at https://example.invalid/?token=secret",
            "ERR_NAME_NOT_RESOLVED",
        ),
        (
            "net::ERR_CONNECTION_RESET at https://example.invalid/?token=secret",
            "ERR_CONNECTION_RESET",
        ),
        (
            "net::ERR_CONNECTION_REFUSED at https://example.invalid/?token=secret",
            "ERR_CONNECTION_REFUSED",
        ),
        ("Timeout 30000ms exceeded: https://example.invalid/?token=secret", "Timeout"),
        ("net::ERR_UNRECOGNIZED at https://example.invalid/?token=secret", None),
    ],
)
def test_navigation_failure_has_only_whitelisted_code_and_preserves_stage(
    tmp_path, browser_session, message, expected
):
    browser_session[3].goto.side_effect = RuntimeError(message)
    report = inspection.run_site_inspection(tmp_path)
    assert report["status"] == "inspection_failed"
    assert report["last_stage"] == "page_navigation"
    assert report["error_code"] == expected
    assert "token=secret" not in json.dumps(report)
    browser_session[2].close.assert_called_once()


def test_share_report_removes_url_queries_credentials_fragments_and_local_paths():
    report = {
        "report_path": "C:/Users/private/report.json",
        "url": inspection.DEFAULT_POST_URL + "&s_keyword=secret#fragment",
        "snapshot": {
            "images": [
                {"display_url": "https://user:pass@cdn.example/img?id=token&no=secret#part"}
            ],
            "evidence": [
                "https://cdn.example/ref?password=secret",
                "//cdn.example/relative?token=secret#hidden",
            ],
            "original_attachment_filename": "그림.png",
            "headers": {"authorization": "secret"},
        },
    }
    shared = inspection.share_report(report)
    assert "report_path" not in shared
    assert shared["url"] == inspection.DEFAULT_POST_URL
    assert shared["snapshot"]["images"][0]["display_url"] == "https://cdn.example/img"
    assert shared["snapshot"]["evidence"] == ["https://cdn.example/ref", "//cdn.example/relative"]
    assert shared["snapshot"]["original_attachment_filename"] == "그림.png"
    assert "headers" not in shared["snapshot"]
    assert "token" not in json.dumps(shared)
    assert "secret" not in json.dumps(shared)
    assert "token" in report["snapshot"]["images"][0]["display_url"]


@pytest.mark.parametrize("scheme", ["data", "blob", "file"])
def test_private_report_omits_inline_or_local_url_bytes(tmp_path, browser_session, scheme):
    browser_session[-1].return_value = {
        "pending_images": [{"display_url": scheme + ":private-payload", "reason": "unsupported"}]
    }
    report = inspection.run_site_inspection(tmp_path)
    item = report["snapshot"]["pending_images"][0]
    assert item["display_url"] is None
    assert item["source_scheme"] == scheme
    assert item["reason"] == "unsupported"
    assert "private-payload" not in Path(report["report_path"]).read_text()


def test_large_snapshot_is_not_written_as_unbounded_metadata(
    tmp_path, browser_session, monkeypatch
):
    monkeypatch.setattr(inspection, "MAX_SNAPSHOT_BYTES", 50)
    browser_session[-1].return_value = {"images": [{"filename": "a" * 100}]}
    report = inspection.run_site_inspection(tmp_path)
    assert report["status"] == "inspection_failed"
    assert "snapshot" not in report


def test_atomic_report_replacement_never_exposes_partial_json(tmp_path, monkeypatch):
    path = tmp_path / "report.json"
    path.write_text('{"status":"old"}')
    replace = Path.replace
    observed = []

    def before_replace(temporary, target):
        observed.append(json.loads(path.read_text()))
        assert json.loads(temporary.read_text()) == {"status": "new"}
        return replace(temporary, target)

    monkeypatch.setattr(Path, "replace", before_replace)
    inspection._write_report(path, {"status": "new"})
    assert observed == [{"status": "old"}]
    assert json.loads(path.read_text()) == {"status": "new"}
    if os.name != "nt":
        assert path.stat().st_mode & 0o077 == 0


def test_failed_report_serialization_keeps_previous_report(tmp_path):
    path = tmp_path / "report.json"
    path.write_text('{"status":"old"}')
    with pytest.raises(TypeError):
        inspection._write_report(path, {"not_json": object()})
    assert json.loads(path.read_text()) == {"status": "old"}
    assert not path.with_suffix(".tmp").exists()
