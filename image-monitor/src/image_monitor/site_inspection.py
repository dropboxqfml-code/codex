"""Read one DC post in an owned, headless browser without native saving or queuing."""

import json
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from image_monitor.dcinside import DCSnapshotError, inspect_post, validate_post_url
from image_monitor.native_probe import browser_executable
from image_monitor.native_ui import require_windows

DEFAULT_POST_URL = "https://gall.dcinside.com/board/view/?id=comic_new6&no=7036949"
MAX_SNAPSHOT_BYTES = 4 * 1024 * 1024
_SECRET_KEYS = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "cookies",
    "set-cookie",
    "password",
    "headers",
    "request_headers",
    "response_headers",
}
_PRIVATE_KEYS = {"report_path", "run_directory", "work_root"}
_URL = re.compile(r"(?:https?:)?//[^\s<>\"']+", re.IGNORECASE)


def _playwright():
    from playwright.sync_api import sync_playwright

    return sync_playwright()


def _public_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        if not host:
            return "[invalid URL omitted]"
        authority = f"[{host}]" if ":" in host else host
        if parsed.port is not None:
            authority += f":{parsed.port}"
        query = ""
        if host.lower() == "gall.dcinside.com" and parsed.path.rstrip("/") in {
            "/board/view",
            "/mgallery/board/view",
            "/mini/board/view",
        }:
            pairs = parse_qsl(parsed.query, max_num_fields=100)
            retained = [
                (key, item)
                for key, item in pairs
                if (key == "id" and re.fullmatch(r"[A-Za-z0-9_]{1,64}", item))
                or (key == "no" and re.fullmatch(r"[0-9]{1,20}", item))
            ]
            query = urlencode(retained)
        return urlunsplit((parsed.scheme, authority, parsed.path, query, ""))
    except ValueError:
        return "[invalid URL omitted]"


def _report_copy(value, *, public: bool):
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            if key.lower() in _SECRET_KEYS or (public and key.lower() in _PRIVATE_KEYS):
                continue
            scheme = (
                child.split(":", 1)[0].lower() if isinstance(child, str) and ":" in child else None
            )
            if (key.endswith("_url") or key == "url") and scheme in {"data", "blob", "file"}:
                result[key] = None
                result.setdefault("source_scheme", scheme)
                result.setdefault("reason", "non_http_url_omitted")
            else:
                result[key] = _report_copy(child, public=public)
        return result
    if isinstance(value, (list, tuple)):
        return [_report_copy(child, public=public) for child in value]
    if public and isinstance(value, str):
        if value.lower().startswith(("data:", "blob:", "file:")):
            return "[non-HTTP URL omitted]"
        return _URL.sub(lambda match: _public_url(match.group()), value)
    return value


def share_report(report: dict) -> dict:
    """Return a copy suitable for the result TXT, excluding URL tokens and local paths."""
    return _report_copy(report, public=True)


def _write_report(path: Path, report: dict) -> None:
    temporary = path.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _error_code(error) -> str | None:
    try:
        message = str(error)
    except Exception:
        return None
    for code in (
        "ERR_TUNNEL_CONNECTION_FAILED",
        "ERR_NAME_NOT_RESOLVED",
        "ERR_CONNECTION_RESET",
        "ERR_CONNECTION_REFUSED",
    ):
        if re.search(r"net::" + code + r"\b", message):
            return code
    if type(error).__name__ == "TimeoutError" or re.search(
        r"\bTimeout\s+\d+\s*ms\s+exceeded\b", message, re.IGNORECASE
    ):
        return "Timeout"
    return None


def _failure(report, error):
    report.update(
        status="inspection_failed",
        error_type=type(error).__name__,
        error_code=_error_code(error),
        reason="Read-only site inspection did not complete",
    )
    if isinstance(error, DCSnapshotError):
        report["diagnostics"] = _report_copy(error.diagnostics, public=False)


def run_site_inspection(
    work_root: Path, browser: str = "chrome", url: str = DEFAULT_POST_URL
) -> dict:
    require_windows()
    target = validate_post_url(url)
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
        "url": target["canonical_url"],
        "http_status": None,
        "retry_after": None,
        "browser_closed": None,
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
                    snapshot = inspect_post(
                        page,
                        expected_url=target["canonical_url"],
                        observed_at=datetime.now(UTC),
                        include_dccon=False,
                        timeout_ms=20_000,
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
