"""Owned headless list observations, without database or native-save operations."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from image_monitor.dcinside import DCSnapshotError
from image_monitor.list_inspection import _adjacent_latest_link
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
from image_monitor.watch_gap_recovery import gap_next_url, seed_next_url
from image_monitor.watch_history import historical_next_url
from image_monitor.watch_planner import WatchPlanError, plan_scan
from image_monitor.watch_store import MAX_MONITOR_SCAN_PAGES, MONITOR_SCOPE, WatchScope

_SETTLE_ISSUES = frozenset(
    {
        "secondary_table_empty",
        "ordinary_author_missing",
        "ordinary_date_missing",
        "ordinary_title_missing",
    }
)


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
                timeout=45_000,
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

    def _navigate(self, url):
        page = self._page
        failed_document = None

        def observe_response(response):
            nonlocal failed_document
            if (
                400 <= response.status < 600
                and response.url == url
                and response.request.is_navigation_request()
                and response.frame == page.main_frame
            ):
                failed_document = response

        page.on("response", observe_response)
        try:
            return page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        except Exception:
            # Chromium can return a document's headers and then reject its empty
            # error page. Preserve its actual status and Retry-After without retrying.
            if failed_document is not None:
                return failed_document
            raise
        finally:
            page.remove_listener("response", observe_response)

    def _inspect_document(self, url, scan_time, *, can_settle):
        page = self._page
        document_changed = False

        def navigated(frame):
            nonlocal document_changed
            if frame == page.main_frame:
                document_changed = True

        def sample(timeout_ms):
            return dict(
                inspect_list(
                    page,
                    expected_url=url,
                    observed_at=self._observation_time(scan_time),
                    timeout_ms=timeout_ms,
                )
            )

        # A reload can replace the document even if its canonical URL stays the same.
        page.on("framenavigated", navigated)
        try:
            snapshot = sample(15_000)
            issue = snapshot.get("selector_evidence", {}).get("profile_issue")
            if (
                can_settle
                and snapshot.get("layout_status") == "unverified"
                and snapshot.get("rows_complete") is True
                and issue in _SETTLE_ISSUES
                and not self._stop_requested()
            ):
                page.wait_for_timeout(1000)
                if not document_changed and not self._stop_requested():
                    snapshot = sample(750)
                    snapshot["selector_evidence"] = dict(
                        snapshot["selector_evidence"], settle_initial_issue=issue
                    )
            if document_changed:
                raise DCSnapshotError("Search document changed during observation")
            return snapshot
        finally:
            page.remove_listener("framenavigated", navigated)

    def scan(
        self, scope: WatchScope, observed_at: datetime, max_pages: int = 2, *, follow_up_state=None
    ) -> dict:
        """Read the latest page and verified pagination links within the passed budget.

        Each navigation runs once. A recognized incomplete render may receive
        one more DOM observation. Earlier pages survive a later page failure.
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
        seed_crossing = (
            isinstance(follow_up_state, dict) and follow_up_state.get("allow_seed_crossing") is True
        )
        extended = follow_up_state is not None
        if extended and (scope != MONITOR_SCOPE or self.browser != "chrome"):
            raise ValueError("A list gap follow-up requires the reviewed Chrome monitor")
        if type(max_pages) is not int or not (
            (2 if seed_crossing else 3) <= max_pages <= MAX_MONITOR_SCAN_PAGES
            if extended
            else 1 <= max_pages <= 2
        ):
            raise ValueError("max_pages is outside the requested scan budget")
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
                response = self._navigate(url)
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
                snapshot = self._inspect_document(
                    url,
                    scan_time,
                    can_settle=200 <= status < 300 and result["retry_after"] is None,
                )
                snapshot["scan_observed_at"] = scan_time.isoformat(timespec="microseconds")
                result["pages"].append(snapshot)
                if self._stop_requested():
                    return result | {"status": "cancelled", "reason": "requested_stop"}
                if index + 1 == max_pages:
                    break
                if extended:
                    if not 200 <= status < 300 or result["retry_after"] is not None:
                        break
                    source = follow_up_state.get("historical_source")
                    bookmark = follow_up_state.get("gap_bookmark")
                    if bookmark is not None and (
                        index == 1 or (index == 2 and result.get("gap_frontier_requested") is True)
                    ):
                        next_url = gap_next_url(
                            scope, follow_up_state, result["pages"], scan_time, bookmark
                        )
                        if next_url is not None:
                            target = validate_list_url(next_url)
                            url = target["canonical_url"]
                            if index == 1:
                                result["gap_frontier_requested"] = True
                                result["recovery_page_numbers"] = [
                                    p["page"] for p in result["pages"]
                                ]
                            result["recovery_page_numbers"].append(target["page"])
                            continue
                        if index == 2:
                            break  # A moved frontier never authorizes a guessed successor.
                    if source is not None and (
                        index == 1
                        or (index == 2 and snapshot.get("page") == source["boundary_page"])
                    ):
                        historical = historical_next_url(
                            scope,
                            follow_up_state,
                            result["pages"],
                            scan_time,
                            source,
                            allow_head_overlap=follow_up_state.get("allow_head_overlap") is True,
                        )
                        if historical is not None:
                            if index == 1:
                                result["historical_boundary_page"] = source["boundary_page"]
                            url = historical
                            target = validate_list_url(url)
                            continue
                        if snapshot["page"] != index + 1:
                            # A re-observed boundary changed. Keep the fresh head
                            # without moving beyond an unproven interval.
                            break
                    if seed_crossing:
                        next_url = seed_next_url(scope, follow_up_state, result["pages"], scan_time)
                        if next_url is not None:
                            following = validate_list_url(next_url)
                            if following["search_pos"] != target["search_pos"]:
                                result["gap_seed_route"] = True
                            if result.get("gap_seed_route") is True:
                                result["recovery_page_numbers"] = [
                                    *(p["page"] for p in result["pages"]),
                                    following["page"],
                                ]
                                target, url = following, following["canonical_url"]
                                continue
                        if result.get("gap_seed_route") is True:
                            break
                adjacent = _adjacent_latest_link(target, snapshot)
                if "url" not in adjacent:
                    break
                if extended and max_pages > 2:
                    # Consult only this run's fresh observations before spending
                    # another request. A completed overlap or uncertain row stops here.
                    prefix = plan_scan(
                        scope, follow_up_state, result["pages"], scan_time, allow_verified_live=True
                    )
                    if (
                        prefix["gap_reason"] not in {"anchor_not_reached", "overlap_incomplete"}
                        or prefix["scan_result"]["follow_up"]["canonical_url"] != adjacent["url"]
                    ):
                        break
                url = adjacent["url"]
                target = validate_list_url(url)
                continue
            except WatchPlanError:
                # Let the runtime persist the actual unverified observation and its gap.
                break
            except Exception as error:
                return self._failure(result, error, "inspection_error")
            break
        return result
