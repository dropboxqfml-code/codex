"""Use the modern recycle-on-delete Windows backend, never its legacy fallback."""

import sys
from pathlib import Path

from send2trash import send2trash

from .privacy import local_path


def _windows_backend():
    # Send2Trash's public dispatcher can silently fall back to SHFileOperation
    # when pywin32 is absent. Require IFileOperation / FOFX_RECYCLEONDELETE instead.
    from send2trash.win.modern import send2trash as modern_send2trash

    return modern_send2trash


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
