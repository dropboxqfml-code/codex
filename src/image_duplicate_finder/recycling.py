"""Use the modern recycle-on-delete Windows backend, never its legacy fallback."""

import importlib
import platform
import sys
from pathlib import Path
from threading import Lock

from .privacy import local_path

_version_lock = Lock()


def send2trash(path: str) -> None:
    # Delay package initialization until the runtime guard is installed.
    from send2trash import send2trash as backend

    backend(path)


def windows_kernel_version() -> str:
    # platform.version() also asks for a hostname while constructing platform.uname().
    # Only the local kernel version is needed to choose Windows recycle flags.
    return ".".join(map(str, sys.getwindowsversion().platform_version))


def _windows_backend():
    # Send2Trash's public dispatcher can silently fall back to SHFileOperation
    # when pywin32 is absent. Require IFileOperation / FOFX_RECYCLEONDELETE instead.
    with _version_lock:
        original = platform.version
        try:
            # Both send2trash.win and .modern import platform.version during initialization.
            # Give those imports an equivalent local-only version provider, then restore stdlib.
            platform.version = windows_kernel_version
            modern = importlib.import_module("send2trash.win.modern")
            modern.version = windows_kernel_version
        finally:
            platform.version = original
    return modern.send2trash


def recycle_file(path: str) -> None:
    local_path(Path(path))
    if sys.platform != "win32":
        send2trash(path)
        return
    try:
        backend = _windows_backend()
    except ImportError as error:
        raise OSError(
            "Windows 휴지통에 필요한 pywin32가 없습니다. 의존성을 다시 설치하세요."
        ) from error
    try:
        backend(path)
    except Exception as error:
        # COM initialization may fail before Send2Trash's own OSError conversion.
        # Preserve per-file results even for those failures. Never use another backend.
        raise OSError(f"Windows 휴지통 이동 실패: {error}") from error
