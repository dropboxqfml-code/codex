"""Read completion from an owned Chrome downloads page without driving downloads.

Chrome's downloads.mojom defines State.kComplete as numeric 2. This contract,
including exact filePath and url.url, was also observed in headed Chrome 156
native Save As checks in both supported UI locales. Edge has not passed this
background-page contract and is deliberately unsupported here.
"""

import ntpath
import time
from pathlib import Path

from image_monitor.native_ui import NativeUIError

_DOWNLOADS_URL = "chrome://downloads/"
_MAX_ITEMS = 1_000
_READ_MODEL = """limit => {
    const manager = document.querySelector('downloads-manager');
    const list = manager?.shadowRoot?.querySelector('#downloadsList');
    const items = Array.isArray(list?.items) ? list.items :
        (Array.isArray(manager?.items_) ? manager.items_ : null);
    return {
        manager_present: Boolean(manager),
        items_available: Boolean(items),
        truncated: Boolean(items && items.length > limit),
        rows: (items || []).slice(0, limit).map(item => ({
            state: item.state,
            file_path: item.filePath,
            source_url: typeof item.url === 'string' ? item.url : item.url?.url,
            danger_type: item.dangerType,
            is_dangerous: item.isDangerous,
            is_insecure: item.isInsecure,
            file_externally_removed: item.fileExternallyRemoved,
            is_reviewable: item.isReviewable,
        })),
    };
}"""


class BrowserCompletionError(NativeUIError):
    """The browser has not provided an unambiguous, safe completion record."""


def _windows_path(value):
    if not isinstance(value, str) or not value or len(value) > 32_767 or "\x00" in value:
        return None
    drive, tail = ntpath.splitdrive(value)
    if not drive or not tail.startswith(("\\", "/")) or not ntpath.isabs(value):
        return None
    return ntpath.normcase(ntpath.normpath(value))


class BrowserCompletion:
    """Keep one read-only background downloads tab in an already owned browser.

    Pass the bound native ``ui`` when entering the context so tab creation can
    verify foreground ownership before the first save. The source page, its
    title, native window title and foreground window must remain unchanged.
    This class never requests a download, changes its behavior or reads bytes.
    """

    def __init__(self, browser, context, source_page, browser_kind, *, ui=None):
        self.browser = browser
        self.context = context
        self.source_page = source_page
        self.browser_kind = browser_kind
        self.ui = ui
        self._session = None
        self._target_id = None
        self._page = None
        self._entered = False
        self.cleanup_error = None

    def __enter__(self):
        if self.browser_kind != "chrome":
            raise BrowserCompletionError("Browser completion is verified for Chrome only")
        if self._entered or self._session is not None:
            raise BrowserCompletionError("Browser completion context cannot be reused")
        if self.ui is None:
            raise BrowserCompletionError(
                "A bound foreground UI is required before opening downloads"
            )
        if (
            self.source_page.context is not self.context
            or self.context.browser is not self.browser
            or not any(context is self.context for context in self.browser.contexts)
        ):
            raise BrowserCompletionError("The source page is outside the supplied owned context")
        self._entered = True
        try:
            self.ui.assert_target_ready()
            self._source_title = self.source_page.title()
            self._source_url = self.source_page.url
            self._window_title = self.ui._window_text(self.ui.target_hwnd)
            self._foreground = self.ui.user32.GetForegroundWindow()
            if not self._source_title or not self._window_title:
                raise BrowserCompletionError("The bound source title must be nonempty")
            self._assert_source_ready()
            self._session = self.browser.new_browser_cdp_session()
            response = self._session.send(
                "Target.createTarget",
                {"url": _DOWNLOADS_URL, "background": True},
                timeout=2_000,
            )
            target_id = response.get("targetId")
            if not isinstance(target_id, str) or not target_id:
                raise BrowserCompletionError("The created downloads target has no identity")
            self._target_id = target_id
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                self._assert_source_ready()
                self._find_created_page()
                if self._page is not None:
                    model = self._read_model()
                    if model["items_available"]:
                        self._assert_source_ready()
                        return self
                self.source_page.wait_for_timeout(100)
            raise BrowserCompletionError("The Chrome downloads model did not become available")
        except Exception:
            self.close(suppress_errors=True)
            raise

    def _assert_source_ready(self):
        self.ui.assert_target_ready()
        if (
            self.source_page.is_closed()
            or self.source_page.url != self._source_url
            or self.source_page.title() != self._source_title
            or self.ui._window_text(self.ui.target_hwnd) != self._window_title
            or self.ui.user32.GetForegroundWindow() != self._foreground
            or self.source_page.evaluate("document.hasFocus()") is not True
        ):
            raise BrowserCompletionError("The bound source page lost its identity or foreground")

    def _find_created_page(self):
        if self._page is not None:
            if self._page.is_closed() or self._page.url != _DOWNLOADS_URL:
                raise BrowserCompletionError("The owned downloads page changed or closed")
            return
        candidates = [page for page in self.context.pages if page.url == _DOWNLOADS_URL]
        if len(candidates) > 1:
            raise BrowserCompletionError("The owned downloads page is ambiguous")
        if not candidates:
            return
        candidate = candidates[0]
        page_session = self.context.new_cdp_session(candidate)
        try:
            info = page_session.send("Target.getTargetInfo", timeout=2_000).get("targetInfo", {})
            if info.get("targetId") != self._target_id or info.get("url") != _DOWNLOADS_URL:
                raise BrowserCompletionError("The downloads page is not the created target")
        finally:
            page_session.detach()
        self._page = candidate

    def _read_model(self):
        self._find_created_page()
        model = self._page.evaluate(_READ_MODEL, _MAX_ITEMS)
        if (
            not isinstance(model, dict)
            or type(model.get("manager_present")) is not bool
            or type(model.get("items_available")) is not bool
            or type(model.get("truncated")) is not bool
            or not isinstance(model.get("rows"), list)
        ):
            raise BrowserCompletionError("The Chrome downloads model has an unknown shape")
        if model["truncated"] or len(model["rows"]) > _MAX_ITEMS:
            raise BrowserCompletionError("The Chrome downloads model exceeds its inspection bound")
        if model["items_available"] and not model["manager_present"]:
            raise BrowserCompletionError("The Chrome downloads manager is missing")
        return model

    def wait_for_completion(self, destination: Path, source_url: str, ui, timeout=60) -> dict:
        if not self._entered or self._target_id is None or self._page is None:
            raise BrowserCompletionError("Browser completion context is not open")
        if ui is not self.ui:
            raise BrowserCompletionError("Browser completion UI ownership changed")
        expected_path = _windows_path(str(destination))
        if expected_path is None or not isinstance(source_url, str) or not source_url:
            raise BrowserCompletionError(
                "Completion requires an absolute destination and source URL"
            )
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not 0 < timeout <= 300
        ):
            raise BrowserCompletionError("Completion timeout must be between zero and 300 seconds")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._assert_source_ready()
            model = self._read_model()
            if model["items_available"]:
                rows = model["rows"]
                if any(not isinstance(row, dict) for row in rows):
                    raise BrowserCompletionError("The Chrome download entry has an unknown shape")
                matching = [
                    row for row in rows if _windows_path(row.get("file_path")) == expected_path
                ]
                if len(matching) > 1:
                    raise BrowserCompletionError("Multiple Chrome downloads have the destination")
                if matching:
                    row = matching[0]
                    if row.get("source_url") != source_url:
                        raise BrowserCompletionError(
                            "Chrome download source does not match the image"
                        )
                    flags = (
                        "is_dangerous",
                        "is_insecure",
                        "file_externally_removed",
                        "is_reviewable",
                    )
                    if any(row.get(flag) is not False for flag in flags):
                        raise BrowserCompletionError(
                            "Chrome download safety or existence is uncertain"
                        )
                    if type(row.get("danger_type")) is not int or row["danger_type"] != 0:
                        raise BrowserCompletionError("Chrome download danger status is uncertain")
                    state = row.get("state")
                    if type(state) is not int or state not in {0, 2}:
                        raise BrowserCompletionError(
                            "Chrome download state is not a safe completion"
                        )
                    if state == 2:
                        self._assert_source_ready()
                        return {
                            "state": "COMPLETE",
                            "destination_confirmed": True,
                            "source_confirmed": True,
                            "destination": str(destination),
                            "source_url": source_url,
                        }
            self._assert_source_ready()
            self.source_page.wait_for_timeout(100)
        raise BrowserCompletionError(
            "Chrome did not confirm download completion before the deadline"
        )

    def close(self, *, suppress_errors=False):
        error = None
        try:
            if self._target_id is not None:
                response = self._session.send(
                    "Target.closeTarget", {"targetId": self._target_id}, timeout=2_000
                )
                if response.get("success") is not True:
                    raise BrowserCompletionError("The created downloads target did not close")
                self._target_id = None
        except Exception as caught:
            error = caught
            self.cleanup_error = type(caught).__name__
        finally:
            if self._session is not None:
                try:
                    self._session.detach()
                except Exception as caught:
                    error = error or caught
                    self.cleanup_error = type(caught).__name__
                self._session = None
            self._page = None
        if error is not None and not suppress_errors:
            raise BrowserCompletionError(
                "The owned downloads reader did not close safely"
            ) from error

    def __exit__(self, exc_type, exc_value, traceback):
        self.close(suppress_errors=exc_type is not None)
        if exc_type is None:
            self._assert_source_ready()
        return False
