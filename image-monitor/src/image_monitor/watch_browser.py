"""Owned headless list observations, without database or native-save operations."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from image_monitor.dcinside import DCSnapshotError
from image_monitor.list_inspection import _adjacent_page
from image_monitor.native_probe import browser_executable
from image_monitor.native_ui import require_windows
from image_monitor.paths import aware
from image_monitor.search_list import (
    SEARCH_TYPE,
    _safe_diagnostics,
    build_list_url,
    inspect_list,
    validate_list_url,
)
from image_monitor.site_inspection import _error_code
from image_monitor.watch_store import WatchScope


def _playwright():
    from playwright.sync_api import sync_playwright

    return sync_playwright()


def _utc_now() -> datetime:
    return datetime.now(UTC)


class WatchBrowserError(RuntimeError):
    """A lifecycle failure whose message contains no external exception text."""

    def __init__(self, message: str, error: BaseException):
        super().__init__(message)
        self.error_type = type(error).__name__
        self.error_code = _error_code(error)


class HeadlessWatchBrowser:
    """Keep one newly launched system browser for bounded read-only scan cycles.

    The caller owns the watch lease, scan schedule, and all persistence. The
    optional clock supplies actual page observation times in controlled tests.
    """

    def __init__(
        self,
        browser: str = "chrome",
        *,
        now: Callable[[], datetime] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ):
        self.browser = browser
        self.browser_closed: bool | None = None
        self.browser_version: str | None = None
        self.cleanup_error_type: str | None = None
        self._now = _utc_now if now is None else now
        self._should_stop = should_stop
        self._manager = None
        self._driver_entered = False
        self._owned_browser = None
        self._page = None
        self._entered = False

    @property
    def version(self) -> str | None:
        return self.browser_version

    def __enter__(self):
        # No browser discovery, launch, or filesystem mutation precedes this guard.
        require_windows()
        if self.browser not in {"chrome", "edge"}:
            raise ValueError("Choose edge or chrome")
        if not callable(self._now):
            raise ValueError("now must be a clock callable")
        if self._should_stop is not None and not callable(self._should_stop):
            raise ValueError("should_stop must be a callable")
        if self._entered:
            raise ValueError("A watch browser context can only be entered once")
        self._entered = True
        try:
            executable = browser_executable(self.browser)
            self._manager = _playwright()
            driver = self._manager.__enter__()
            self._driver_entered = True
            self._owned_browser = driver.chromium.launch(
                executable_path=str(executable),
                headless=True,
                timeout=15_000,
                args=["--disable-background-networking"],
            )
            self.browser_version = self._owned_browser.version
            context = self._owned_browser.new_context(accept_downloads=False)
            self._page = context.new_page()
        except BaseException as error:
            self._close(type(error), error, error.__traceback__)
            if isinstance(error, Exception):
                raise WatchBrowserError(
                    "Owned headless watch browser could not be opened", error
                ) from None
            raise
        return self

    def _close(self, exc_type=None, exc_value=None, traceback=None):
        failure = None
        try:
            if self._owned_browser is not None:
                try:
                    self._owned_browser.close()
                    self.browser_closed = True
                except BaseException as error:
                    self.browser_closed = False
                    failure = error
        finally:
            self._owned_browser = None
            self._page = None
            if self._driver_entered:
                try:
                    self._manager.__exit__(exc_type, exc_value, traceback)
                except BaseException as error:
                    if failure is None:
                        failure = error
                finally:
                    self._driver_entered = False
                    self._manager = None
        if failure is not None:
            self.cleanup_error_type = type(failure).__name__
        return failure

    def __exit__(self, exc_type, exc_value, traceback):
        failure = self._close(exc_type, exc_value, traceback)
        if failure is not None and exc_type is None:
            if not isinstance(failure, Exception):
                raise failure
            raise WatchBrowserError(
                "Owned headless watch browser could not be closed", failure
            ) from None
        return False

    def _observation_time(self, scan_time: datetime) -> datetime:
        observed = aware(self._now()).astimezone(UTC)
        if not scan_time <= observed <= scan_time + timedelta(seconds=120):
            raise DCSnapshotError("Page observation is outside the bounded scan window")
        return observed

    @staticmethod
    def _failure(result: dict, error: Exception, status: str) -> dict:
        result.update(status=status, error_type=type(error).__name__, error_code=_error_code(error))
        if isinstance(error, DCSnapshotError):
            result["diagnostics"] = _safe_diagnostics(error.diagnostics)
        return result

    def _stop_requested(self):
        if self._should_stop is None:
            return False
        requested = self._should_stop()
        if type(requested) is not bool:
            raise ValueError("should_stop must return a boolean")
        return requested

    def scan(self, scope: WatchScope, observed_at: datetime, max_pages: int = 2) -> dict:
        """Read fresh latest page one and at most one actual adjacent page link.

        Document failures stop immediately. Earlier snapshots survive a later
        navigation or inspection failure; retries and cursor changes are absent.
        """
        if self._page is None:
            raise ValueError("A watch scan requires an open browser context")
        if not isinstance(scope, WatchScope):
            raise ValueError("scope must be a WatchScope")
        scope.key()
        if scope.search_type != SEARCH_TYPE:
            raise ValueError("Watch scope requires the exact title/body search type")
        if not isinstance(observed_at, datetime):
            raise ValueError("observed_at must be a timezone-aware datetime")
        scan_time = aware(observed_at).astimezone(UTC)
        if type(max_pages) is not int or not 1 <= max_pages <= 2:
            raise ValueError("max_pages must be 1 or 2")
        # Construct this independently on every cycle; never reuse a prior URL.
        target = validate_list_url(
            build_list_url(scope.gallery_type, scope.gallery_id, scope.keyword, 1, None)
        )
        url = target["canonical_url"]
        result = {
            "pages": [],
            "navigation": [],
            "status": "observed",
            "http_status": None,
            "retry_after": None,
            "lastRetryAfter": None,
        }
        for index in range(max_pages):
            if self._stop_requested():
                return result | {"status": "cancelled", "reason": "requested_stop"}
            navigation = {"url": url, "http_status": None, "retry_after": None}
            result["navigation"].append(navigation)
            result.update(http_status=None, retry_after=None, lastRetryAfter=None)
            try:
                response = self._page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                status = response.status if response is not None else None
                navigation["http_status"] = status
                result["http_status"] = status
                if response is not None:
                    retry_after = response.header_value("retry-after")
                    if isinstance(retry_after, str):
                        navigation["retry_after"] = retry_after[:256]
                        result.update(
                            retry_after=navigation["retry_after"],
                            lastRetryAfter=navigation["retry_after"],
                        )
            except Exception as error:
                return self._failure(result, error, "network_error")
            if self._stop_requested():
                return result | {"status": "cancelled", "reason": "requested_stop"}
            if status is None or status >= 400:
                result.update(status="http_error", error_type="HTTPStatusError")
                return result
            try:
                snapshot = dict(
                    inspect_list(
                        self._page,
                        expected_url=url,
                        observed_at=self._observation_time(scan_time),
                        timeout_ms=15_000,
                    )
                )
                snapshot["scan_observed_at"] = scan_time.isoformat(timespec="microseconds")
                result["pages"].append(snapshot)
                if self._stop_requested():
                    return result | {"status": "cancelled", "reason": "requested_stop"}
                if index == 0 and max_pages == 2:
                    adjacent = _adjacent_page(target, snapshot)
                    if "url" in adjacent:
                        url = adjacent["url"]
                        continue
            except Exception as error:
                return self._failure(result, error, "inspection_error")
            break
        return result
