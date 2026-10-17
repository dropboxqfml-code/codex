"""Local-file checks and a Python-level runtime guard (not a native OS sandbox)."""

import ctypes
import ntpath
import os
import stat
import sys
from pathlib import Path


class LocalOnlyError(ValueError):
    pass


def windows_local_drive(path: str, drive_type=None) -> str:
    # Reject UNC, device namespaces, and mapped network drives before any filesystem lookup.
    if path.startswith(("\\\\", "//", "\\??\\")):
        raise LocalOnlyError("네트워크·장치 경로는 사용할 수 없습니다")
    drive, _ = ntpath.splitdrive(path)
    if len(drive) != 2 or drive[1] != ":":
        raise LocalOnlyError("로컬 드라이브의 절대 경로를 선택하세요")
    if drive_type is None:
        query = ctypes.windll.kernel32.GetDriveTypeW
        query.argtypes = [ctypes.c_wchar_p]
        query.restype = ctypes.c_uint
        drive_type = query
    root = drive + "\\"
    if drive_type(root) not in {2, 3, 5, 6}:  # removable, fixed, CD, RAM; not remote/unknown
        raise LocalOnlyError("네트워크·알 수 없는 드라이브는 사용할 수 없습니다")
    return root


def check_linux_mount(path: Path) -> None:
    # Do not traverse an NFS/SMB/FUSE mount while checking its contents.
    if sys.platform != "linux":
        return
    selected = (0, "")
    with open("/proc/self/mountinfo", encoding="utf-8") as mounts:
        for line in mounts:
            before, after = line.split(" - ", 1)
            mount = before.split()[4]
            for encoded, decoded in [("\\040", " "), ("\\011", "\t"), ("\\134", "\\")]:
                mount = mount.replace(encoded, decoded)
            root = Path(mount)
            if (path == root or root in path.parents) and len(mount) > selected[0]:
                selected = (len(mount), after.split()[0])
    if selected[1] not in {
        "overlay",
        "ext2",
        "ext3",
        "ext4",
        "xfs",
        "btrfs",
        "tmpfs",
        "ramfs",
        "vfat",
        "exfat",
        "ntfs",
        "ntfs3",
        "squashfs",
        "zfs",
        "fuseblk",
    }:
        raise LocalOnlyError("로컬로 확인되지 않은 파일시스템은 사용할 수 없습니다")


def local_path(path: Path) -> Path:
    raw = os.fspath(path)
    if raw.startswith(("\\\\", "//")) or "://" in raw:
        raise LocalOnlyError("네트워크 경로와 URL은 사용할 수 없습니다")
    absolute = Path(os.path.abspath(raw))  # lexical only; resolve() can access a remote link
    check_linux_mount(absolute)
    if sys.platform == "win32":
        windows_local_drive(str(absolute))
        for variable in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
            value = os.environ.get(variable)
            if value:
                cloud = Path(os.path.abspath(value))
                if absolute == cloud or cloud in absolute.parents:
                    raise LocalOnlyError("OneDrive 동기화 폴더는 사용할 수 없습니다")
    # Inspect from the root down so a link is rejected before following its children.
    for part in reversed([absolute, *absolute.parents]):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue  # allow a new local DB/key destination
        if stat.S_ISLNK(info.st_mode):
            raise LocalOnlyError("심볼릭 링크 경로는 사용할 수 없습니다")
        attributes = getattr(info, "st_file_attributes", 0)
        if attributes & (0x400 | 0x1000 | 0x40000 | 0x400000):
            raise LocalOnlyError("재분석 지점·오프라인·클라우드 파일은 사용할 수 없습니다")
    return absolute


_installed = False
_blocked = {"network": 0, "process": 0}


def runtime_blocks() -> dict[str, int]:
    return dict(_blocked)


def runtime_guard_enabled() -> bool:
    return _installed


def install_runtime_guard() -> None:
    global _installed
    if _installed:
        return
    platform = os.environ.get("QT_QPA_PLATFORM", "").lower()
    allowed = {
        "win32": {"windows", "offscreen", "minimal"},
        "linux": {"xcb", "wayland", "wayland-egl", "offscreen", "minimal"},
        "darwin": {"cocoa", "offscreen", "minimal"},
    }.get(sys.platform, {"offscreen", "minimal"})
    if platform and any(p.split(":", 1)[0] not in allowed for p in platform.split(";")):
        raise LocalOnlyError("원격 화면 Qt backend는 사용할 수 없습니다")
    if sys.platform == "linux":
        display = os.environ.get("DISPLAY", "")
        if display and not display.startswith((":", "unix:", "unix/:")):
            raise LocalOnlyError("원격 X11 화면은 사용할 수 없습니다")
    for name in (
        "QT_QPA_GENERIC_PLUGINS",
        "QT_PLUGIN_PATH",
        "QT_QPA_PLATFORM_PLUGIN_PATH",
        "QT_QPA_FONTDIR",
        "QT_LOGGING_CONF",
        "QML_IMPORT_PATH",
        "QML2_IMPORT_PATH",
    ):
        os.environ.pop(name, None)

    def guard(event, args):
        network = event.startswith(("socket.connect", "socket.bind", "socket.sendto"))
        network |= event in {
            "socket.getaddrinfo",
            "socket.gethostbyname",
            "socket.gethostbyaddr",
            "socket.getnameinfo",
            "socket.gethostname",
        }
        if event == "socket.__new__" and len(args) >= 2:
            network |= int(args[1]) in {2, 10, 23}  # IPv4, IPv6 (POSIX and Windows)
        if network:
            _blocked["network"] += 1
            raise PermissionError("이 앱에서는 Python 네트워크 통신이 차단됩니다")
        if event in {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn"} or (
            event.startswith("os.startfile") or event == "webbrowser.open"
        ):
            _blocked["process"] += 1
            raise PermissionError("이 앱에서는 외부 프로그램 실행이 차단됩니다")

    sys.addaudithook(guard)
    _installed = True


def configure_qt_library_paths() -> None:
    from PySide6.QtCore import QCoreApplication, QLibraryInfo

    if sys.platform == "win32" and getattr(sys, "frozen", False):
        plugins = Path(sys._MEIPASS) / "PySide6" / "plugins"
    else:
        plugins = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath))
    QCoreApplication.setLibraryPaths([str(local_path(plugins))])
