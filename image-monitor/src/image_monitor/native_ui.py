"""Fail-closed controls for the owned Windows browser, imported only on Windows.

UIA identifiers are intentionally strict. A browser/locale exposing a different tree
must be inspected on Windows rather than falling back to coordinates or menu order.
"""

import re
import sys
import time
from collections.abc import Callable


class NativeUIError(RuntimeError):
    """Stop the probe for manual inspection; never automatically retry UI input."""


def require_windows() -> None:
    if sys.platform != "win32":
        raise NativeUIError("Native saving requires a logged-in interactive Windows desktop")


def normalize_label(label: str) -> str:
    label = label.replace("&", "").replace("...", "…").strip()
    label = re.sub(r"\s*\([A-Za-z]\)(?=…?$)", "", label)
    return label.removesuffix("…").strip()


def choose_unique(elements: list, predicate: Callable, description: str):
    matches = [element for element in elements if predicate(element)]
    if len(matches) != 1:
        raise NativeUIError(f"Expected one {description}; found {len(matches)}")
    return matches[0]


class WindowsUI:
    def __init__(self, browser_pid: int, expected_window_title: str):
        require_windows()
        import ctypes
        from ctypes import wintypes

        import psutil
        from pywinauto import Desktop

        if not expected_window_title.strip():
            raise NativeUIError("A unique expected browser window title is required")
        self.expected_window_title = expected_window_title
        self.target_hwnd = None
        self.ctypes = ctypes
        self.psutil = psutil
        self.desktop = Desktop(backend="uia")
        self.root_process = psutil.Process(browser_pid)
        self.root_created = self.root_process.create_time()
        self.browser_suggested_filename = None
        self.stage = "desktop_guard"
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.user32.OpenInputDesktop.restype = wintypes.HANDLE
        self.user32.CloseDesktop.argtypes = [wintypes.HANDLE]
        self.user32.GetUserObjectInformationW.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.user32.IsWindow.argtypes = [wintypes.HWND]
        self.user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
        self.user32.GetWindow.restype = wintypes.HWND
        self.user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        self.user32.GetAncestor.restype = wintypes.HWND
        self.user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        self.user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.wintypes = wintypes
        self.target_hwnd = choose_unique(
            self._target_candidates(),
            lambda _hwnd: True,
            "browser window with the unique probe title",
        )

    def process_ids(self) -> set[int]:
        try:
            if (
                not self.root_process.is_running()
                or self.root_process.create_time() != self.root_created
            ):
                raise NativeUIError("Browser process identity changed")
            return {self.root_process.pid} | {
                process.pid for process in self.root_process.children(recursive=True)
            }
        except self.psutil.Error as error:
            raise NativeUIError("Cannot verify owned browser processes") from error

    def _window_pid(self, hwnd: int) -> int:
        pid = self.wintypes.DWORD()
        if not self.user32.GetWindowThreadProcessId(hwnd, self.ctypes.byref(pid)):
            return 0
        return pid.value

    def _window_text(self, hwnd: int) -> str:
        length = self.user32.GetWindowTextLengthW(hwnd)
        text = self.ctypes.create_unicode_buffer(length + 1)
        self.user32.GetWindowTextW(hwnd, text, len(text))
        return text.value

    def _class_name(self, hwnd: int) -> str:
        name = self.ctypes.create_unicode_buffer(256)
        self.user32.GetClassNameW(hwnd, name, len(name))
        return name.value

    def _target_candidates(self) -> list[int]:
        pids = self.process_ids()
        return [
            window.handle
            for window in self.desktop.windows()
            if self.user32.IsWindow(window.handle)
            and self._window_pid(window.handle) in pids
            and self._class_name(window.handle) == "Chrome_WidgetWin_1"
            and (
                self._window_text(window.handle) == self.expected_window_title
                or self._window_text(window.handle).startswith(self.expected_window_title + " - ")
            )
        ]

    def _assert_target_exists(self) -> None:
        candidates = self._target_candidates()
        if candidates != [self.target_hwnd]:
            raise NativeUIError("The bound probe window is missing, changed, or ambiguous")

    def _root_window(self, hwnd: int) -> int:
        return self.user32.GetAncestor(hwnd, 2) or hwnd  # GA_ROOT: parent chain, not owner chain

    def belongs_to_target(self, hwnd: int) -> bool:
        """Require a live parent/owner HWND chain ending at the bound probe window."""
        pids = self.process_ids()
        visited = set()
        current = self._root_window(hwnd)
        while current and current not in visited and len(visited) < 32:
            visited.add(current)
            if not self.user32.IsWindow(current) or self._window_pid(current) not in pids:
                return False
            if current == self.target_hwnd:
                return True
            owner = self.user32.GetWindow(current, 4)  # GW_OWNER
            current = self._root_window(owner) if owner else 0
        return False

    def focus_snapshot(self) -> dict:
        """Read safe focus diagnostics without validating or changing foreground focus.

        Window titles, process names, command lines and paths are deliberately not
        collected. This best-effort snapshot must not replace the original failure
        if the browser or a window disappears while it is being inspected.
        ``target_exists`` confirms a live HWND in the owned process tree only;
        the normal input guards still enforce the unique title binding.
        """
        target = getattr(self, "target_hwnd", None)
        if not isinstance(target, int) or target <= 0:
            target = None
        snapshot = {
            "target_hwnd": target,
            "foreground_hwnd": None,
            "foreground_pid": None,
            "foreground_class": None,
            "target_exists": None,
            "belongs_to_target": None,
            "target_foreground": None,
        }
        try:
            foreground = self.user32.GetForegroundWindow()
            if isinstance(foreground, int) and foreground > 0:
                snapshot["foreground_hwnd"] = foreground
                if self.user32.IsWindow(foreground):
                    snapshot["foreground_pid"] = self._window_pid(foreground) or None
                    snapshot["foreground_class"] = self._class_name(foreground) or None
            else:
                foreground = None
            pids = self.process_ids()
            exists = bool(
                target and self.user32.IsWindow(target) and self._window_pid(target) in pids
            )
            snapshot["target_exists"] = exists
            if not exists:
                snapshot["belongs_to_target"] = False
                snapshot["target_foreground"] = False
            elif foreground is not None:
                snapshot["belongs_to_target"] = self.belongs_to_target(foreground)
                snapshot["target_foreground"] = self._root_window(foreground) == target
            else:
                snapshot["belongs_to_target"] = False
                snapshot["target_foreground"] = False
        except Exception as error:
            snapshot["diagnostic_error_type"] = type(error).__name__
        return snapshot

    def assert_ready(self) -> None:
        handle = self.user32.OpenInputDesktop(0, False, 0x0001)  # DESKTOP_READOBJECTS
        if not handle:
            raise NativeUIError("Input desktop unavailable: pause until user checks session")
        try:
            name = self.ctypes.create_unicode_buffer(256)
            needed = self.wintypes.DWORD()
            if (
                not self.user32.GetUserObjectInformationW(
                    handle, 2, name, self.ctypes.sizeof(name), self.ctypes.byref(needed)
                )
                or name.value.casefold() != "default"
            ):
                raise NativeUIError("Interactive Default desktop is not active")
        finally:
            self.user32.CloseDesktop(handle)
        self._assert_target_exists()
        hwnd = self.user32.GetForegroundWindow()
        if not hwnd or not self.belongs_to_target(hwnd):
            raise NativeUIError("Foreground focus is outside the bound probe window; input stopped")

    def assert_target_ready(self) -> None:
        """Before Playwright input, the main page window itself must have focus."""
        self.assert_ready()
        if self._root_window(self.user32.GetForegroundWindow()) != self.target_hwnd:
            raise NativeUIError("The probe page itself is not in the foreground")

    def assert_control_ready(self, control, window) -> None:
        self.assert_ready()
        if (
            not self.belongs_to_target(window.handle)
            or control.process_id() not in self.process_ids()
        ):
            raise NativeUIError("UI control is outside the bound probe window owner chain")
        if not control.is_visible() or not control.is_enabled():
            raise NativeUIError("Identified native control is no longer visible and enabled")
        # top_level_parent() caches its result in pywinauto. Walk current parents
        # until a native HWND is found so a reparented/stale virtual element fails closed.
        current = control
        control_root = 0
        for _ in range(32):
            if current is None or current.process_id() not in self.process_ids():
                break
            hwnd = current.handle
            if isinstance(hwnd, int) and hwnd:
                control_root = self._root_window(hwnd)
                break
            current = current.parent()
        window_root = self._root_window(window.handle)
        if not self.belongs_to_target(control_root) or control_root != window_root:
            raise NativeUIError("UI control no longer belongs to the identified native window")
        foreground = self._root_window(self.user32.GetForegroundWindow())
        allowed_foreground = (
            {window_root}
            if self._class_name(window.handle) == "#32770"
            else {self.target_hwnd, window_root}
        )
        if foreground not in allowed_foreground:
            raise NativeUIError("Focus moved away from the identified native window")

    def owned_windows(self) -> list:
        self.assert_ready()
        return [
            window for window in self.desktop.windows() if self.belongs_to_target(window.handle)
        ]

    def wait_for(self, lookup: Callable, timeout: float = 15):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.assert_ready()
            result = lookup()
            if result is not None:
                return result
            time.sleep(0.1)
        raise NativeUIError("Native UI step timed out; inspect browser before retrying")

    def click_save_image_menu(self) -> None:
        self.stage = "context_menu"
        labels = {"Save image as", "이미지를 다른 이름으로 저장"}

        def lookup():
            items = [
                (item, window)
                for window in self.owned_windows()
                for item in window.descendants(control_type="MenuItem")
                if normalize_label(item.window_text()) in labels and item.is_visible()
            ]
            if not items:
                return None
            return choose_unique(
                items, lambda pair: pair[0].is_enabled(), "Save image as menu item"
            )

        item, window = self.wait_for(lookup)
        self.assert_control_ready(item, window)
        # UIA Invoke targets the identified element, not an arbitrary screen coordinate.
        item.invoke()

    def save_dialog(self, target: str) -> str | None:
        self.stage = "save_dialog"

        def lookup():
            dialogs = [
                window
                for window in self.owned_windows()
                if window.class_name() == "#32770"
                and normalize_label(window.window_text()) in {"Save As", "다른 이름으로 저장"}
            ]
            if not dialogs:
                return None
            return choose_unique(dialogs, lambda dialog: dialog.is_visible(), "Save As dialog")

        dialog = self.wait_for(lookup)
        filename = choose_unique(
            dialog.descendants(control_type="Edit"),
            lambda edit: edit.element_info.automation_id == "1001" and edit.is_visible(),
            "filename Edit with automation ID 1001",
        )
        self.assert_control_ready(filename, dialog)
        suggested = filename.get_value() or None
        self.browser_suggested_filename = suggested
        save = choose_unique(
            dialog.descendants(control_type="Button"),
            lambda button: (
                button.element_info.automation_id == "1"
                and normalize_label(button.window_text()) in {"Save", "저장"}
                and button.is_enabled()
            ),
            "Save button with automation ID 1",
        )
        self.assert_control_ready(filename, dialog)
        filename.set_edit_text(target)
        self.assert_control_ready(filename, dialog)
        if filename.get_value() != target:
            raise NativeUIError("Save dialog did not retain the exact staging path")
        self.assert_control_ready(save, dialog)
        save.invoke()
        dialog_handle = dialog.handle
        self.wait_for(
            lambda: (
                True
                if all(window.handle != dialog_handle for window in self.owned_windows())
                else None
            )
        )
        return suggested


class NativeSaveLock:
    """One native-save owner across all monitor processes in this Windows session."""

    def __enter__(self):
        require_windows()
        import ctypes
        from ctypes import wintypes

        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        self.kernel32.CreateMutexW.restype = wintypes.HANDLE
        self.kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel32.WaitForSingleObject.restype = wintypes.DWORD
        self.kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.kernel32.CreateMutexW(None, False, "Local\\ImageMonitor.NativeSave")
        if not self.handle:
            raise NativeUIError("Cannot create native-save mutex")
        outcome = self.kernel32.WaitForSingleObject(self.handle, 0)
        if outcome != 0:
            if outcome == 0x80:  # abandoned: acquired, but prior save state is uncertain
                self.kernel32.ReleaseMutex(self.handle)
            self.kernel32.CloseHandle(self.handle)
            raise NativeUIError("Native-save owner is busy or abandoned; inspect previous work")
        return self

    def __exit__(self, *_):
        self.kernel32.ReleaseMutex(self.handle)
        self.kernel32.CloseHandle(self.handle)
