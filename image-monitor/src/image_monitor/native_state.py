"""Durable per-user/session save guard, independent of a probe's chosen work root."""

import json
import os
import uuid
from pathlib import Path

from image_monitor.native_ui import NativeUIError, require_windows


def session_id(process_id: int | None = None) -> int:
    require_windows()
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    result = wintypes.DWORD()
    if not kernel32.ProcessIdToSessionId(process_id or os.getpid(), ctypes.byref(result)):
        raise NativeUIError("Cannot verify Windows session identity")
    return result.value


def shared_state_path() -> Path:
    require_windows()
    import ctypes
    from ctypes import wintypes

    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell32.SHGetFolderPathW.argtypes = [
        wintypes.HWND,
        ctypes.c_int,
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
    ]
    directory = ctypes.create_unicode_buffer(260)
    if shell32.SHGetFolderPathW(None, 0x001C, None, 0, directory) != 0:
        raise NativeUIError("Cannot locate the user's local application state directory")
    return Path(directory.value) / "ImageMonitor" / f"native-save-session-{session_id()}.json"


class PendingSave:
    """Caller must hold NativeSaveLock during every read/modify/recovery operation.

    State is written before browser launch. Only verified success or explicit recovery
    may remove it; changing --work-root cannot bypass an unresolved operation.
    """

    def __init__(self, path: Path):
        self.path = path

    def read(self) -> dict | None:
        try:
            with self.path.open(encoding="utf-8") as stream:
                value = json.load(stream)
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as error:
            raise NativeUIError(
                "Shared native-save state is unreadable; manual inspection required"
            ) from error
        if not isinstance(value, dict) or not all(
            isinstance(value.get(field), str) and value[field]
            for field in ("run_id", "run_directory", "browser_profile")
        ):
            raise NativeUIError("Shared native-save state is invalid; manual inspection required")
        return value

    def assert_clear(self) -> None:
        if self.read() is not None:
            raise NativeUIError(
                "A save is unresolved in this Windows session. Inspect its report/browser, "
                "then use native-recover --confirm-browser-closed"
            )

    def begin(self, run_directory: Path) -> dict:
        self.assert_clear()
        value = {
            "schema_version": 1,
            "run_id": uuid.uuid4().hex,
            "run_directory": str(run_directory),
            "browser_profile": str(run_directory / "browser-profile"),
            "browser_pid": None,
            "browser_create_time": None,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.path.open("x", encoding="utf-8") as stream:
                json.dump(value, stream)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError as error:
            raise NativeUIError("A native save is already pending") from error
        return value

    def update_browser(self, value: dict, pid: int, created: float) -> None:
        self._assert_current(value)
        updated = value | {"browser_pid": pid, "browser_create_time": created}
        temporary = self.path.with_name(f"{self.path.name}.{uuid.uuid4().hex}.tmp")
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(updated, stream)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(self.path)
        value.update(updated)

    def _assert_current(self, value: dict) -> None:
        current = self.read()
        if current is None or current["run_id"] != value["run_id"]:
            raise NativeUIError("Shared native-save state changed unexpectedly")

    def finish(self, value: dict) -> None:
        self._assert_current(value)
        self.path.unlink()


def browser_still_running(value: dict) -> bool:
    """Check both the registered process and profile use, including a pre-registration crash."""
    require_windows()
    import psutil

    pid, created = value.get("browser_pid"), value.get("browser_create_time")
    if pid is not None:
        try:
            if psutil.Process(pid).create_time() == created:
                return True
        except psutil.NoSuchProcess:
            pass
        except psutil.Error as error:
            raise NativeUIError("Cannot confirm that the previous browser exited") from error
    profile = os.path.normcase(os.path.abspath(value["browser_profile"]))
    current_session = session_id()
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = process.info["name"]
            if not name:
                if session_id(process.pid) == current_session:
                    raise NativeUIError("Unknown process in this session; recovery blocked")
                continue
            if name.casefold() not in {"msedge.exe", "chrome.exe"}:
                continue
            if session_id(process.pid) != current_session:
                continue
            args = process.info["cmdline"]
            if args is None:
                raise NativeUIError("Cannot inspect a browser in this session; recovery blocked")
            for index, argument in enumerate(args):
                candidate = None
                if argument.startswith("--user-data-dir="):
                    candidate = argument.split("=", 1)[1]
                elif argument == "--user-data-dir" and index + 1 < len(args):
                    candidate = args[index + 1]
                if candidate and os.path.normcase(os.path.abspath(candidate)) == profile:
                    return True
        except psutil.NoSuchProcess:
            continue
        except psutil.Error as error:
            raise NativeUIError("Cannot inspect browser processes; recovery blocked") from error
    return False


def recover_pending(state: PendingSave, is_running=browser_still_running) -> dict:
    value = state.read()
    if value is None:
        return {"status": "no_pending_save"}
    if is_running(value):
        raise NativeUIError("Previous browser/profile is still active; close it before recovery")
    state.finish(value)
    return {"status": "resolved", "run_directory": value["run_directory"], "files_preserved": True}


def run_recovery() -> dict:
    from image_monitor.native_ui import NativeSaveLock

    require_windows()
    with NativeSaveLock():
        return recover_pending(PendingSave(shared_state_path()))
