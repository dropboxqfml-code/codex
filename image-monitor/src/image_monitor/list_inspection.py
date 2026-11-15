"""Inspect one DC search list in an owned, headless browser without saving or queuing."""

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from image_monitor.dcinside import DCSnapshotError
from image_monitor.native_probe import browser_executable
from image_monitor.native_ui import require_windows
from image_monitor.search_list import build_list_url, inspect_list, validate_list_url
from image_monitor.site_inspection import (
    _URL,
    MAX_SNAPSHOT_BYTES,
    _error_code,
    _public_url,
    _report_copy,
    _write_report,
)
from image_monitor.site_inspection import share_report as _site_share_report

DEFAULT_LIST_URL = build_list_url("normal", "comic_new6", "ai")
_RELATIVE_LIST_URL = re.compile(
    r"(?<![\w/:])/(?:mgallery/|mini/)?board/lists/?\?[^\s<>\"']+", re.IGNORECASE
)


def _playwright():
    from playwright.sync_api import sync_playwright

    return sync_playwright()


def _cursor_hash(value: str | None) -> str | None:
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else None


def _public_list_url(value: str) -> str | None:
    """Keep validated list scope while replacing a navigation cursor with its hash."""
    try:
        target = validate_list_url(urljoin("https://gall.dcinside.com", value))
        parsed = urlsplit(target["canonical_url"])
        pairs = [
            (key, item)
            for key, item in parse_qsl(parsed.query, max_num_fields=100)
            if key in {"id", "s_type", "s_keyword", "page"}
        ]
        cursor_hash = _cursor_hash(target["search_pos"])
        if cursor_hash is not None:
            pairs.append(("search_pos_sha256", cursor_hash))
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(pairs), ""))
    except (DCSnapshotError, ValueError, TypeError):
        return None


def share_report(report: dict) -> dict:
    """Remove secrets and local paths while keeping list scope useful for review."""
    replacements = {}
    marker = "LIST_INSPECTION_PUBLIC_URL_" + uuid.uuid4().hex + "_"

    def protect_url(match):
        value = match.group()
        safe_url = _public_list_url(value)
        if safe_url is None:
            safe_url = _public_url(
                urljoin("https://gall.dcinside.com", value)
                if value.startswith("/") and not value.startswith("//")
                else value
            )
        token = marker + str(len(replacements))
        replacements[token] = safe_url
        return token

    def prepare(value):
        if isinstance(value, dict):
            copied = {}
            for key, child in value.items():
                if key.lower() == "search_pos":
                    copied["search_pos_sha256"] = _cursor_hash(
                        child if isinstance(child, str) else None
                    )
                else:
                    copied[key] = prepare(child)
            return copied
        if isinstance(value, (list, tuple)):
            return [prepare(child) for child in value]
        if isinstance(value, str):
            return _RELATIVE_LIST_URL.sub(protect_url, _URL.sub(protect_url, value))
        return value

    def restore(value):
        if isinstance(value, dict):
            return {key: restore(child) for key, child in value.items()}
        if isinstance(value, list):
            return [restore(child) for child in value]
        if isinstance(value, str):
            return re.sub(
                re.escape(marker) + r"[0-9]+",
                lambda match: replacements.get(match.group(), match.group()),
                value,
            )
        return value

    return restore(_site_share_report(prepare(report)))


def _failure(report: dict, error: Exception) -> None:
    report.update(
        status="inspection_failed",
        error_type=type(error).__name__,
        error_code=_error_code(error),
        reason="Read-only search-list inspection did not complete",
    )
    if isinstance(error, DCSnapshotError):
        diagnostics = _report_copy(error.diagnostics, public=False)
        if len(json.dumps(diagnostics).encode("utf-8")) <= MAX_SNAPSHOT_BYTES:
            report["diagnostics"] = diagnostics
        else:
            report["diagnostics_omitted"] = "metadata_limit"


def run_list_inspection(
    work_root: Path, browser: str = "chrome", url: str = DEFAULT_LIST_URL
) -> dict:
    """Navigate once, inspect the current list DOM, and close this owned browser."""
    require_windows()
    target = validate_list_url(url)
    if browser not in {"edge", "chrome"}:
        raise ValueError("Choose edge or chrome")
    run_directory = Path(work_root).resolve() / uuid.uuid4().hex
    run_directory.mkdir(parents=True)
    report = {
        "schema_version": 1,
        "status": "inspection_failed",
        "inspection_only": True,
        "images_saved": False,
        "queue_modified": False,
        "browser": browser,
        "browser_mode": "headless",
        "url": target["canonical_url"],
        "http_status": None,
        "retry_after": None,
        "browser_closed": None,
        "navigation_attempts": 0,
        "error_type": None,
        "error_code": None,
        "last_stage": "preparing",
        "report_path": str(run_directory / "report.json"),
    }
    try:
        executable = browser_executable(browser)
        with _playwright() as driver:
            owned_browser = None
            try:
                report["last_stage"] = "browser_launch"
                owned_browser = driver.chromium.launch(
                    executable_path=str(executable),
                    headless=True,
                    timeout=15_000,
                    args=["--disable-background-networking"],
                )
                report["browser_version"] = owned_browser.version
                context = owned_browser.new_context(accept_downloads=False)
                page = context.new_page()
                report["last_stage"] = "page_navigation"
                report["navigation_attempts"] = 1
                response = page.goto(
                    target["canonical_url"], wait_until="domcontentloaded", timeout=30_000
                )
                status = response.status if response is not None else None
                report["http_status"] = status
                if response is not None:
                    retry_after = response.header_value("retry-after")
                    report["retry_after"] = retry_after[:256] if retry_after is not None else None
                if status is None or status >= 400:
                    report.update(
                        error_type="HTTPStatusError",
                        reason="Document response prevented inspection",
                    )
                else:
                    report["last_stage"] = "dom_inspection"
                    snapshot = inspect_list(
                        page,
                        expected_url=target["canonical_url"],
                        observed_at=datetime.now(UTC),
                        timeout_ms=15_000,
                    )
                    snapshot = _report_copy(snapshot, public=False)
                    if len(json.dumps(snapshot).encode("utf-8")) > MAX_SNAPSHOT_BYTES:
                        raise ValueError("Inspection metadata exceeds report limit")
                    report.update(status="inspected_unverified", snapshot=snapshot)
            except Exception as error:
                _failure(report, error)
            finally:
                if owned_browser is not None:
                    try:
                        owned_browser.close()
                        report["browser_closed"] = True
                    except Exception as error:
                        report["browser_closed"] = False
                        report["cleanup_error_type"] = type(error).__name__
                        if report["error_type"] is None:
                            _failure(report, error)
                        report["status"] = "inspection_failed"
    except Exception as error:
        if report["error_type"] is None:
            _failure(report, error)
        else:
            report["cleanup_error_type"] = type(error).__name__
        report["status"] = "inspection_failed"
    if report["status"] == "inspected_unverified":
        report["last_stage"] = "complete"
    _write_report(Path(report["report_path"]), report)
    return report
