"""Inspect a DC search list and one observed next-page link without saving or queuing."""

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from image_monitor.dcinside import DCSnapshotError
from image_monitor.list_links import LIST_LINK_VALUE_CATEGORIES
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
MAX_REPORT_BYTES = MAX_SNAPSHOT_BYTES
_REPORT_RESERVE_BYTES = 1024
_SCOPE_KEYS = ("gallery_type", "gallery_id", "search_type", "keyword", "navigation")
_DIAGNOSTIC_QUERY_KEYS = {
    "id",
    "s_type",
    "s_keyword",
    "page",
    "search_pos",
    "search_head",
    "exception_mode",
}
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

    def prepare(value, path=()):
        if isinstance(value, dict):
            if (
                len(path) >= 4
                and path[-4:-2] == ("diagnostics", "pagination_samples")
                and type(path[-2]) is int
                and path[-1] == "query_value_categories"
            ):
                return {
                    key: child
                    for key, child in value.items()
                    if key in _DIAGNOSTIC_QUERY_KEYS
                    and isinstance(child, str)
                    and child in LIST_LINK_VALUE_CATEGORIES
                }
            copied = {}
            for key, child in value.items():
                if key.lower() == "search_pos":
                    copied["search_pos_sha256"] = _cursor_hash(
                        child if isinstance(child, str) else None
                    )
                else:
                    copied[key] = prepare(child, (*path, key))
            return copied
        if isinstance(value, (list, tuple)):
            return [prepare(child, (*path, index)) for index, child in enumerate(value)]
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
        if "diagnostics" not in report or not _report_fits(report, reserve=_REPORT_RESERVE_BYTES):
            report.pop("diagnostics", None)
            report["diagnostics_omitted"] = "metadata_limit"


def _report_fits(report: dict, *, reserve: int = 0) -> bool:
    return (
        len(json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"))
        <= MAX_REPORT_BYTES - reserve
    )


def _store_snapshot(report: dict, destination: dict, snapshot: dict) -> None:
    snapshot = _report_copy(snapshot, public=False)
    if len(json.dumps(snapshot).encode("utf-8")) > MAX_SNAPSHOT_BYTES:
        raise ValueError("Inspection metadata exceeds report limit")
    destination["snapshot"] = snapshot
    if not _report_fits(report, reserve=_REPORT_RESERVE_BYTES):
        del destination["snapshot"]
        raise ValueError("Combined inspection metadata exceeds report limit")


def _adjacent_page(target: dict, snapshot: dict) -> dict:
    """Choose only one actual, revalidated adjacent link in the latest search window."""
    if target["page"] != 1 or target["search_pos"] is not None:
        return {"status": "skipped", "reason": "initial_page_is_not_latest_page_one"}
    return _adjacent_latest_link(target, snapshot)


def _adjacent_latest_link(target: dict, snapshot: dict) -> dict:
    """Find one observed consecutive link without changing the search window."""
    if (
        target["search_pos"] is not None
        or snapshot.get("status") != "observed"
        or snapshot.get("counts", {}).get("list_containers") != 1
        or not snapshot.get("rows")
    ):
        return {"status": "skipped", "reason": "main_list_not_observed"}
    candidates = []
    for observed in snapshot.get("pagination_candidates", []):
        if not isinstance(observed, dict):
            continue
        try:
            candidate = validate_list_url(observed.get("canonical_url"))
        except DCSnapshotError:
            continue
        if (
            any(candidate[key] != target[key] for key in _SCOPE_KEYS)
            or candidate["page"] != target["page"] + 1
            or candidate["search_pos"] != target["search_pos"]
            or observed.get("page") != candidate["page"]
            or observed.get("search_pos") != candidate["search_pos"]
        ):
            continue
        candidates.append(candidate["canonical_url"])
    if not candidates:
        return {"status": "no_adjacent_page", "reason": "no_same_scope_adjacent_link"}
    if len(candidates) != 1:
        return {"status": "skipped", "reason": "ambiguous_adjacent_links"}
    return {
        "status": "failed",
        "url": candidates[0],
        "http_status": None,
        "retry_after": None,
    }


def _response_status(response, destination: dict) -> bool:
    status = response.status if response is not None else None
    destination["http_status"] = status
    if response is not None:
        retry_after = response.header_value("retry-after")
        destination["retry_after"] = retry_after[:256] if retry_after is not None else None
    return status is not None and status < 400


def _inspect_follow_up(page, target: dict, report: dict) -> None:
    follow_up = _adjacent_page(target, report["snapshot"])
    report["follow_up"] = follow_up
    if "url" not in follow_up:
        return
    if not _report_fits(report, reserve=_REPORT_RESERVE_BYTES):
        report["follow_up"] = {"status": "skipped", "reason": "metadata_limit"}
        return
    try:
        report["last_stage"] = "follow_up_navigation"
        report["navigation_attempts"] = 2
        response = page.goto(follow_up["url"], wait_until="domcontentloaded", timeout=30_000)
        if not _response_status(response, follow_up):
            follow_up.update(
                error_type="HTTPStatusError", reason="Document response prevented inspection"
            )
            report.update(
                status="inspection_failed",
                error_type="HTTPStatusError",
                reason="Follow-up document response prevented inspection",
            )
            return
        report["last_stage"] = "follow_up_dom_inspection"
        snapshot = inspect_list(
            page,
            expected_url=follow_up["url"],
            observed_at=datetime.now(UTC),
            timeout_ms=15_000,
        )
        _store_snapshot(report, follow_up, snapshot)
        follow_up["status"] = "observed"
    except Exception as error:
        follow_up.update(
            status="failed",
            error_type=type(error).__name__,
            error_code=_error_code(error),
            reason="Read-only follow-up inspection did not complete",
        )
        _failure(report, error)


def run_list_inspection(
    work_root: Path, browser: str = "chrome", url: str = DEFAULT_LIST_URL
) -> dict:
    """Inspect at most two pages using observed links, then close this owned browser."""
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
        "follow_up": {"status": "skipped", "reason": "first_page_unavailable"},
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
                if not _response_status(response, report):
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
                    _store_snapshot(report, report, snapshot)
                    report["status"] = "inspected_unverified"
                    _inspect_follow_up(page, target, report)
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
    if not _report_fits(report):
        report.pop("diagnostics", None)
        report["follow_up"].pop("snapshot", None)
        report["follow_up"].update(status="failed", reason="metadata_limit")
        report.update(
            status="inspection_failed",
            error_type="ValueError",
            error_code=None,
            reason="Combined inspection metadata exceeds report limit",
        )
        if not _report_fits(report):
            report.pop("snapshot", None)
        if not _report_fits(report):
            raise ValueError("Inspection report metadata exceeds limit")
    _write_report(Path(report["report_path"]), report)
    return report
