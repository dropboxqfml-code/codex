"""Fail-closed controls for the owned Windows browser, imported only on Windows.

UIA identifiers are intentionally strict. A browser/locale exposing a different tree
must be inspected on Windows rather than falling back to coordinates or menu order.
"""

import re
import sys
import time
from collections.abc import Callable
from pathlib import PureWindowsPath

_IMAGE_EXTENSION_FAMILIES = (
    ({".png"}, ".png"),
    ({".jpg", ".jpeg"}, ".jpg"),
    ({".webp"}, ".webp"),
    ({".gif"}, ".gif"),
    ({".bmp"}, ".bmp"),
    ({".tif", ".tiff"}, ".tiff"),
)


class NativeUIError(RuntimeError):
    """Stop the probe for manual inspection; never automatically retry UI input."""


class NativeFocusError(NativeUIError):
    """The bound browser exists, but the required foreground window lost focus."""


def require_windows() -> None:
    if sys.platform != "win32":
        raise NativeUIError("Native saving requires a logged-in interactive Windows desktop")


def normalize_label(label: str) -> str:
    label = label.replace("&", "").replace("...", "…").strip()
    label = re.sub(r"\s*\([A-Za-z]\)(?=…?$)", "", label)
    return label.removesuffix("…").strip()


def image_filter_extension(label: str) -> str | None:
    """Recognize only an explicit single-format native file-type filter."""
    if not isinstance(label, str):
        return None
    match = re.fullmatch(
        r"[^()\x00]{1,200}\(\s*(\*\.[a-zA-Z0-9]+(?:\s*;\s*\*\.[a-zA-Z0-9]+)*)\s*\)",
        label.strip(),
    )
    if match is None:
        return None
    extensions = {part.strip()[1:].lower() for part in match[1].split(";")}
    return next(
        (suffix for family, suffix in _IMAGE_EXTENSION_FAMILIES if extensions <= family), None
    )


def registry_image_extension(
    label: str, read_description: Callable[[str], str | None]
) -> str | None:
    """Prove an exact bare native type label using fixed image associations only.

    Chromium's Windows picker uses this same read-only .extension -> ProgID ->
    default-description relation, including localized Windows associations:
    https://source.chromium.org/chromium/chromium/src/+/main:ui/shell_dialogs/select_file_dialog_win.cc
    """
    if (
        not isinstance(label, str)
        or not label
        or len(label) > 200
        or any(char in label for char in "\0*?")
        or label in {"All Files", "All files", "모든 파일"}
    ):
        return None
    matches = set()
    try:
        for family, _suffix in _IMAGE_EXTENSION_FAMILIES:
            for extension in sorted(family):
                if read_description(extension) == label:
                    matches.add(extension)
    except (OSError, ImportError):
        return None
    if not matches:
        return None
    return next((suffix for family, suffix in _IMAGE_EXTENSION_FAMILIES if matches <= family), None)


def _registry_file_type_description(extension: str) -> str | None:
    import winreg

    def default_value(path):
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, path, 0, winreg.KEY_READ) as key:
            value, kind = winreg.QueryValueEx(key, "")
            return value if kind == winreg.REG_SZ and isinstance(value, str) and value else None

    try:
        prog_id = default_value(extension)
        return default_value(prog_id) if prog_id and "\0" not in prog_id else None
    except FileNotFoundError:
        return None


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
        self.browser_suggested_extension = None
        self.browser_suggested_file_type = None
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
        self.user32.IsWindowEnabled.argtypes = [wintypes.HWND]
        self.user32.IsWindowVisible.argtypes = [wintypes.HWND]
        self.user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
        self.user32.GetWindow.restype = wintypes.HWND
        self.user32.GetParent.argtypes = [wintypes.HWND]
        self.user32.GetParent.restype = wintypes.HWND
        self.user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        self.user32.GetAncestor.restype = wintypes.HWND
        self.user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        self.user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user32.SendMessageTimeoutW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            ctypes.c_size_t,
            ctypes.c_ssize_t,
            wintypes.UINT,
            wintypes.UINT,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        self.user32.SendMessageTimeoutW.restype = ctypes.c_ssize_t
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

    def menu_snapshot(
        self,
        *,
        max_items: int = 80,
        max_nodes: int = 500,
        max_depth: int = 6,
        max_seconds: float = 2,
    ) -> dict:
        """Read bounded menu diagnostics from this probe's process tree only.

        Direct desktop children can be virtual Menu roots with no HWND. Include
        such roots for diagnosis, without treating them as safe input targets.
        Names are read only for Menu/MenuItem nodes in owned processes. Limits
        apply between provider calls; a single COM call cannot be interrupted.
        """
        snapshot = {
            "items": [],
            "roots_seen": 0,
            "owned_roots": 0,
            "foreign_roots_excluded": 0,
            "nodes_scanned": 0,
            "foreign_nodes_excluded": 0,
            "bound_menu_nodes": 0,
            "unbound_menu_nodes": 0,
            "unknown_binding_menu_nodes": 0,
            "truncated": False,
            "errors": [],
        }

        def error_type(error):
            name = type(error).__name__
            if name not in snapshot["errors"] and len(snapshot["errors"]) < 8:
                snapshot["errors"].append(name)

        def read(operation, default=None):
            try:
                return operation()
            except Exception as error:
                error_type(error)
                return default

        def handle(value):
            return value if type(value) is int and value > 0 else 0

        try:
            if min(max_items, max_nodes, max_seconds) <= 0 or max_depth < 0:
                raise ValueError("Diagnostic limits must be positive")
            pids = self.process_ids()
            deadline = time.monotonic() + max_seconds
            visited = set()
            queue = []
            for root in self.desktop.windows():
                if time.monotonic() >= deadline or snapshot["roots_seen"] >= max_nodes:
                    snapshot["truncated"] = True
                    break
                snapshot["roots_seen"] += 1
                if read(root.process_id) not in pids:
                    snapshot["foreign_roots_excluded"] += 1
                    continue
                snapshot["owned_roots"] += 1
                root_hwnd = handle(read(lambda root=root: root.handle))
                root_class = None
                if (
                    root_hwnd
                    and read(lambda root_hwnd=root_hwnd: self._window_pid(root_hwnd)) in pids
                ):
                    root_class = read(lambda root_hwnd=root_hwnd: self._class_name(root_hwnd))
                queue.append((root, 0, root_hwnd, root_class))

            while queue:
                if (
                    snapshot["nodes_scanned"] >= max_nodes
                    or len(snapshot["items"]) >= max_items
                    or time.monotonic() >= deadline
                ):
                    snapshot["truncated"] = True
                    break
                node, depth, root_hwnd, root_class = queue.pop(0)
                snapshot["nodes_scanned"] += 1
                pid = read(node.process_id)
                if pid not in pids:
                    snapshot["foreign_nodes_excluded"] += 1
                    continue
                runtime_id = read(lambda node=node: node.element_info.runtime_id)
                if isinstance(runtime_id, (list, tuple)) and all(
                    type(part) is int for part in runtime_id
                ):
                    identity = (pid, tuple(runtime_id))
                else:
                    identity = (pid, id(node))
                if identity in visited:
                    continue
                visited.add(identity)
                role = read(lambda node=node: node.element_info.control_type)
                if role in {"Menu", "MenuItem"}:
                    label = read(node.window_text)
                    hwnd = handle(read(lambda node=node: node.handle))
                    binding = read(
                        lambda hwnd=hwnd, root_hwnd=root_hwnd: self.belongs_to_target(
                            hwnd or root_hwnd
                        )
                    )
                    binding = binding if type(binding) is bool else None
                    visible, enabled = read(node.is_visible), read(node.is_enabled)
                    snapshot["items"].append(
                        {
                            "label": label[:120] if isinstance(label, str) else None,
                            "type": role,
                            "process_id": pid,
                            "native_hwnd": hwnd,
                            "root_hwnd": root_hwnd,
                            "root_class": root_class,
                            "is_root": depth == 0,
                            "belongs_to_target": binding,
                            "visible": visible if type(visible) is bool else None,
                            "enabled": enabled if type(enabled) is bool else None,
                        }
                    )
                    key = (
                        "bound_menu_nodes"
                        if binding is True
                        else "unbound_menu_nodes"
                        if binding is False
                        else "unknown_binding_menu_nodes"
                    )
                    snapshot[key] += 1
                children = read(node.children, [])
                if depth < max_depth:
                    room = max_nodes - snapshot["nodes_scanned"] - len(queue)
                    if len(children) > room:
                        snapshot["truncated"] = True
                    queue.extend(
                        (child, depth + 1, root_hwnd, root_class)
                        for child in children[: max(0, room)]
                    )
                elif children:
                    snapshot["truncated"] = True
        except Exception as error:
            error_type(error)
            snapshot["diagnostic_error_type"] = type(error).__name__
        return snapshot

    def _assert_bound_desktop(self) -> None:
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

    def assert_ready(self) -> None:
        self._assert_bound_desktop()
        hwnd = self.user32.GetForegroundWindow()
        if not hwnd or not self.belongs_to_target(hwnd):
            raise NativeFocusError(
                "Foreground focus is outside the bound probe window; input stopped"
            )

    def assert_target_ready(self) -> None:
        """Before Playwright input, the main page window itself must have focus."""
        self.assert_ready()
        if self._root_window(self.user32.GetForegroundWindow()) != self.target_hwnd:
            raise NativeFocusError("The probe page itself is not in the foreground")

    def wait_for_initial_foreground(self, *, timeout: float = 20.0) -> None:
        """Allow the user or Windows to foreground the bound Chrome after launch."""
        if type(timeout) not in (int, float) or not 0 < timeout <= 20:
            raise ValueError("Initial foreground wait must be within 20 seconds")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._assert_bound_desktop()
            if not self.user32.IsWindowEnabled(self.target_hwnd):
                raise NativeUIError("The bound browser window is disabled")
            foreground = self.user32.GetForegroundWindow()
            if foreground:
                pid = self._window_pid(foreground)
                if not self.user32.IsWindow(foreground) or not pid:
                    raise NativeUIError("The Windows foreground window is invalid")
                if pid in self.process_ids():
                    if self._root_window(foreground) != self.target_hwnd:
                        raise NativeUIError("A different window of the owned browser is active")
                    return
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(0.2, remaining))
        raise NativeFocusError("Foreground focus is outside the bound probe window; input stopped")

    def assert_control_ready(self, control, window) -> None:
        self.assert_ready()
        native_hwnd = window.handle
        if (
            type(native_hwnd) is not int
            or native_hwnd <= 0
            or not self.belongs_to_target(native_hwnd)
            or control.process_id() not in self.process_ids()
        ):
            raise NativeUIError("UI control is outside the bound probe window owner chain")
        if not window.is_visible() or not control.is_visible() or not control.is_enabled():
            raise NativeUIError("Identified native control is no longer visible and enabled")

        # Chromium may expose an intermediate Pane with its own HWND before the
        # real browser Window ancestor. A first-positive-HWND test mistakes that
        # Pane for the root. Rebind the trusted native window via ElementFromHandle
        # and require the fresh UIA parent chain to reach that exact element.
        # UIAElementInfo equality calls IUIAutomation.CompareElements; wrapper
        # handles and top_level_parent() caches are not identity proof.
        try:
            fresh_root = self.desktop.window(handle=native_hwnd).wrapper_object()
            if fresh_root.process_id() not in self.process_ids():
                raise NativeUIError("Native window provider is outside the owned process tree")
            expected = fresh_root.element_info
            current = control
            visited = []
            matched = False
            for _ in range(32):
                if current is None:
                    break
                pid = current.process_id()
                if pid and pid not in self.process_ids():
                    break
                info = current.element_info
                if any(info == previous for previous in visited):
                    break
                visited.append(info)
                role = info.control_type
                if role == "Document":
                    raise NativeUIError("Document content is not an identified native UI control")
                if info == expected:
                    matched = True
                    break
                if role == "Window":
                    break
                current = current.parent()
        except NativeUIError:
            raise
        except Exception as error:
            raise NativeUIError("Cannot verify the current native UI parent chain") from error
        if not matched:
            raise NativeUIError("UI control no longer belongs to the identified native window")

        # Recheck native ownership and focus after provider traversal, immediately
        # before the caller acts. A same-PID element alone is never sufficient.
        self.assert_ready()
        if (
            not self.user32.IsWindow(native_hwnd)
            or self._window_pid(native_hwnd) not in self.process_ids()
            or not self.belongs_to_target(native_hwnd)
        ):
            raise NativeUIError("Identified native window changed during UI verification")
        if not control.is_visible() or not control.is_enabled():
            raise NativeUIError("Identified native control is no longer visible and enabled")
        window_root = self._root_window(native_hwnd)
        foreground = self._root_window(self.user32.GetForegroundWindow())
        allowed_foreground = (
            {window_root}
            if self._class_name(native_hwnd) == "#32770"
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
        labels = {"Save image as", "이미지를 다른 이름으로 저장", "다른 이름으로 사진 저장"}

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

    def _replace_filename_text(self, filename, filename_host, dialog, target: str) -> None:
        """Replace only the identified native filename Edit, preserving edit notifications."""
        hwnd = filename.handle

        def assert_filename():
            self.assert_control_ready(filename_host, dialog)
            self.assert_control_ready(filename, dialog)
            native_pid = self._window_pid(hwnd) if type(hwnd) is int and hwnd > 0 else 0
            if (
                type(hwnd) is not int
                or hwnd <= 0
                or filename.handle != hwnd
                or filename.element_info.handle != hwnd
                or not self.user32.IsWindow(hwnd)
                or not self.user32.IsWindowVisible(hwnd)
                or self._class_name(hwnd) != "Edit"
                or native_pid != filename.process_id()
                or native_pid not in self.process_ids()
                or self._root_window(hwnd) != dialog.handle
                or filename.parent().element_info != filename_host.element_info
                or filename_host.element_info.automation_id != "FileNameControlHost"
                or filename_host.element_info.control_type != "ComboBox"
                or type(filename_host.handle) is not int
                or filename_host.handle <= 0
                or self.user32.GetParent(hwnd) != filename_host.handle
                or self._window_pid(filename_host.handle) != native_pid
                or filename_host.process_id() != native_pid
                or not self.belongs_to_target(hwnd)
                or not self.belongs_to_target(dialog.handle)
            ):
                raise NativeUIError("Filename Edit does not match its owned native dialog")

        # WM_SETTEXT/ValuePattern.SetValue can change the combo's displayed text
        # without delivering the edit-change notifications the shell consumes.
        # EM_REPLACESEL is the native edit operation used by pywinauto's Win32
        # EditWrapper, and these messages are scoped to this verified child HWND.
        text = self.ctypes.create_unicode_buffer(target, len(target.encode("utf-16-le")) // 2 + 1)
        messages = (
            (0x00B1, 0, -1),  # EM_SETSEL: select all text in this edit only.
            (0x00C2, 1, self.ctypes.cast(text, self.ctypes.c_void_p).value),  # EM_REPLACESEL
        )
        for message, wparam, lparam in messages:
            assert_filename()
            result = self.ctypes.c_size_t()
            if not self.user32.SendMessageTimeoutW(
                hwnd, message, wparam, lparam, 0x22, 2_000, self.ctypes.byref(result)
            ):  # SMTO_ABORTIFHUNG | SMTO_ERRORONEXIT; never retry uncertain input.
                raise NativeUIError("Filename Edit message did not complete safely")
        assert_filename()
        if filename.get_value() != target:
            raise NativeUIError("Save dialog did not retain the exact staging path")

    def save_dialog(self, target: str | Callable[[str | None], str]) -> str | None:
        self.stage = "save_dialog"
        self.browser_suggested_extension = None
        self.browser_suggested_file_type = None

        def lookup():
            # Edge's out-of-process file picker can be a child in the browser's
            # UIA tree rather than a direct desktop child. Bind the actual owned
            # foreground HWND; desktop UIA enumeration can omit this dialog.
            self.assert_ready()
            native_hwnd = self.user32.GetForegroundWindow()
            if not native_hwnd or not self.user32.IsWindow(native_hwnd):
                return None
            native_pid = self._window_pid(native_hwnd)
            if native_pid not in self.process_ids() or not self.belongs_to_target(native_hwnd):
                raise NativeUIError("Foreground save window is outside the owned window chain")
            if (
                not self.user32.IsWindowVisible(native_hwnd)
                or self._class_name(native_hwnd) != "#32770"
                or normalize_label(self._window_text(native_hwnd))
                not in {"Save As", "다른 이름으로 저장"}
            ):
                return None
            dialog = self.desktop.window(handle=native_hwnd).wrapper_object()
            if dialog.handle != native_hwnd or dialog.process_id() != native_pid:
                raise NativeUIError("Save dialog provider does not match its native window")
            return dialog if dialog.is_visible() else None

        dialog = self.wait_for(lookup)
        filename_host = choose_unique(
            dialog.descendants(control_type="ComboBox"),
            lambda combo: (
                combo.element_info.automation_id == "FileNameControlHost" and combo.is_visible()
            ),
            "filename ComboBox with automation ID FileNameControlHost",
        )
        self.assert_control_ready(filename_host, dialog)
        filename = choose_unique(
            filename_host.children(control_type="Edit"),
            lambda edit: edit.element_info.automation_id == "1001" and edit.is_visible(),
            "filename Edit with automation ID 1001",
        )
        self.assert_control_ready(filename, dialog)
        suggested = filename.get_value() or None
        self.browser_suggested_filename = suggested
        type_control = None
        if (
            callable(target)
            and isinstance(suggested, str)
            and suggested
            and not PureWindowsPath(suggested).suffix
        ):
            type_control = choose_unique(
                dialog.descendants(control_type="ComboBox"),
                lambda combo: (
                    combo.element_info.automation_id == "FileTypeControlHost" and combo.is_visible()
                ),
                "native file type ComboBox with automation ID FileTypeControlHost",
            )
            self.assert_control_ready(type_control, dialog)
            try:
                file_type = type_control.selected_text()
            except Exception as error:
                raise NativeUIError("Cannot read the selected native image file type") from error
            self.assert_control_ready(type_control, dialog)
            self.browser_suggested_file_type = file_type if isinstance(file_type, str) else None
            extension = image_filter_extension(file_type)
            if extension is None:
                extension = registry_image_extension(file_type, _registry_file_type_description)
            if extension is None:
                raise NativeUIError("Native image file type is unsupported or ambiguous")
            self.browser_suggested_extension = extension
        if callable(target):
            target = target(suggested)
        if not isinstance(target, str) or not target or "\0" in target:
            raise NativeUIError("Save target must be a nonempty path string")
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
        if type_control is not None:
            self.assert_control_ready(type_control, dialog)
            if type_control.selected_text() != self.browser_suggested_file_type:
                raise NativeUIError("Selected native image file type changed before input")
        if not filename.has_keyboard_focus():
            self.assert_control_ready(filename, dialog)
            # Use only this identified element inside the already foreground
            # dialog. The wrapper's set_focus can restore a window; do not use
            # window activation, global keys or mouse coordinates here.
            filename.element_info.element.SetFocus()
            self.assert_control_ready(filename, dialog)
            if not filename.has_keyboard_focus():
                raise NativeUIError("Save dialog control did not acquire keyboard focus")
        self._replace_filename_text(filename, filename_host, dialog, target)
        self.assert_control_ready(save, dialog)
        save.invoke()
        dialog_handle = dialog.handle
        self.wait_for(
            lambda: (
                True
                if not self.user32.IsWindow(dialog_handle)
                or not self.user32.IsWindowVisible(dialog_handle)
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
