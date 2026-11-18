"""Gracefully close only the exact browser of an already finalized native run.

The caller holds NativeSaveLock and has verified every completed artifact and
the absence of an active save attempt. This module never launches a browser,
drives native input, terminates a process, or changes pending-save state.
"""

import math
import os
import re
import socket
import stat
import subprocess
import time
from pathlib import Path

from image_monitor.artifact_files import ArtifactError, _plain_path
from image_monitor.native_probe import close_probe_browser, connect_owned_browser
from image_monitor.native_state import browser_still_running, session_id
from image_monitor.native_ui import NativeUIError, require_windows

_BROWSER_PATH = re.compile(
    r"/devtools/browser/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_MAX_PORT_FILE_BYTES = 4096
_PROFILE_EXIT_TIMEOUT_SECONDS = 5
_PROFILE_EXIT_POLL_SECONDS = 0.1


def _psutil():
    import psutil

    return psutil


def _playwright():
    from playwright.sync_api import sync_playwright

    return sync_playwright()


def _require(condition, message):
    if not condition:
        raise NativeUIError(message)


def _profile(value):
    _require(
        isinstance(value, str) and value and not any(ord(char) < 32 for char in value),
        "The completed browser profile is invalid",
    )
    path = Path(value)
    _require(
        path.is_absolute() and not str(path).startswith("\\\\"),
        "The completed browser requires an absolute local profile",
    )
    try:
        path = _plain_path(path)
        _require(stat.S_ISDIR(path.lstat().st_mode), "The completed browser profile is missing")
    except (ArtifactError, OSError) as error:
        raise NativeUIError("The completed browser profile cannot be verified") from error
    return path


def _normalized(value):
    return os.path.normcase(os.path.abspath(value))


def _owned_process(pending, profile, psutil):
    pid, created = pending["browser_pid"], pending["browser_create_time"]
    try:
        process = psutil.Process(pid)
        if process.create_time() != created:
            return None
        _require(process.pid == pid, "The completed browser process identity changed")
        name = process.name()
        _require(
            isinstance(name, str) and name.casefold() == "chrome.exe",
            "The completed browser process is not Chrome",
        )
        _require(
            session_id(pid) == session_id(),
            "The completed browser is outside this Windows session",
        )
        arguments = process.cmdline()
        _require(
            isinstance(arguments, list)
            and all(isinstance(argument, str) for argument in arguments),
            "The completed browser command line cannot be verified",
        )
        profiles = []
        for index, argument in enumerate(arguments):
            if argument.startswith("--user-data-dir="):
                profiles.append(argument.split("=", 1)[1])
            elif argument == "--user-data-dir":
                _require(
                    index + 1 < len(arguments), "The completed browser profile flag is invalid"
                )
                profiles.append(arguments[index + 1])
            elif argument.startswith("--user-data-dir"):
                raise NativeUIError("The completed browser profile flag is ambiguous")
        _require(
            len(profiles) == 1 and profiles[0],
            "The completed browser profile flag is ambiguous",
        )
        process_profile = _profile(profiles[0])
        _require(
            _normalized(process_profile) == _normalized(profile),
            "The completed browser does not own the registered profile",
        )
        return process
    except psutil.NoSuchProcess:
        return None
    except psutil.Error as error:
        raise NativeUIError("The completed browser process cannot be inspected") from error


def _same_file(before, after):
    return (
        os.path.samestat(before, after)
        and before.st_size == after.st_size
        and before.st_mtime_ns == after.st_mtime_ns
    )


def _endpoint(profile):
    path = profile / "DevToolsActivePort"
    try:
        _plain_path(path)
        named = path.lstat()
        _require(
            stat.S_ISREG(named.st_mode)
            and not getattr(named, "st_file_attributes", 0) & 0x400
            and 1 <= named.st_size <= _MAX_PORT_FILE_BYTES,
            "The completed browser debugging endpoint file is invalid",
        )
        descriptor = os.open(
            path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        )
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            _require(_same_file(named, opened), "The completed browser endpoint changed")
            data = stream.read(_MAX_PORT_FILE_BYTES + 1)
            after = os.fstat(stream.fileno())
        _plain_path(path)
        _require(
            len(data) <= _MAX_PORT_FILE_BYTES
            and _same_file(opened, after)
            and _same_file(after, path.lstat()),
            "The completed browser endpoint changed",
        )
        lines = data.decode("ascii").splitlines()
        _require(
            len(lines) == 2
            and re.fullmatch(r"[1-9][0-9]{0,4}", lines[0]) is not None
            and 1 <= int(lines[0]) <= 65535
            and _BROWSER_PATH.fullmatch(lines[1]) is not None,
            "The completed browser debugging endpoint is invalid",
        )
        return int(lines[0]), lines[1]
    except (ArtifactError, OSError, UnicodeError) as error:
        raise NativeUIError(
            "The completed browser debugging endpoint cannot be verified"
        ) from error


def _listens_on(process, port, psutil):
    try:
        connections = process.net_connections(kind="tcp")
    except (psutil.Error, OSError, NotImplementedError) as error:
        raise NativeUIError(
            "The completed browser debugging listener cannot be verified"
        ) from error
    _require(
        isinstance(connections, (list, tuple)),
        "The completed browser debugging listener cannot be verified",
    )
    try:
        matching = [
            connection
            for connection in connections
            if connection.family == socket.AF_INET
            and connection.type == socket.SOCK_STREAM
            and connection.status == psutil.CONN_LISTEN
            and getattr(connection.laddr, "ip", None) == "127.0.0.1"
            and getattr(connection.laddr, "port", None) == port
        ]
    except (AttributeError, TypeError) as error:
        raise NativeUIError(
            "The completed browser debugging listener cannot be verified"
        ) from error
    _require(
        len(matching) == 1,
        "The registered process does not uniquely own the local debugging listener",
    )


class _WaitForOwnedProcess:
    def __init__(self, process, psutil):
        self.process, self.psutil = process, psutil

    def wait(self, *, timeout):
        try:
            return self.process.wait(timeout=timeout)
        except self.psutil.NoSuchProcess:
            return 0
        except self.psutil.TimeoutExpired as error:
            raise subprocess.TimeoutExpired("owned-completed-browser", timeout) from error
        except self.psutil.Error as error:
            raise NativeUIError("The completed browser exit cannot be verified") from error


def _wait_for_profile_absence(pending):
    # Waiting for the registered root process does not establish that its exact
    # profile has left every same-session Chrome process. Windows process-list
    # visibility can also briefly lag a signaled process handle. Keep the full
    # independent liveness check and allow its ordinary shutdown to settle.
    deadline = time.monotonic() + _PROFILE_EXIT_TIMEOUT_SECONDS
    while True:
        running = browser_still_running(pending)
        _require(type(running) is bool, "The completed browser profile state is unknown")
        if not running:
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(_PROFILE_EXIT_POLL_SECONDS, remaining))


def close_completed_browser(pending: dict) -> bool:
    """Close only an unchanged registered Chrome owning its exact local CDP port.

    A missing or reused PID returns False without connecting to anything. Other
    missing ownership evidence raises NativeUIError. True additionally requires
    independent confirmation that the registered process and profile are unused.
    """
    require_windows()
    _require(isinstance(pending, dict), "Completed browser state is invalid")
    pid, created = pending.get("browser_pid"), pending.get("browser_create_time")
    _require(
        type(pid) is int
        and 0 < pid < 2**32
        and type(created) in {int, float}
        and 0 < created < 2**53
        and math.isfinite(created),
        "The completed browser process registration is invalid",
    )
    profile = _profile(pending.get("browser_profile"))
    psutil = _psutil()
    process = _owned_process(pending, profile, psutil)
    if process is None:
        return False
    endpoint = _endpoint(profile)
    _listens_on(process, endpoint[0], psutil)
    driver = _playwright().start()
    disconnect_attempted = False
    failure = None
    try:
        browser = connect_owned_browser(driver, endpoint[0])
        # Attaching can race an exited/reused local port. Recheck the complete
        # process, profile, file and listening-socket proof before any close.
        process = _owned_process(pending, profile, psutil)
        if process is None:
            return False
        _require(_endpoint(profile) == endpoint, "The completed browser endpoint changed")
        _listens_on(process, endpoint[0], psutil)
        close_probe_browser(browser, _WaitForOwnedProcess(process, psutil))
        # Release this reconnecting client before independently waiting for all
        # use of the exact registered profile to disappear. This is only a
        # transport disconnect, never evidence of browser/profile absence.
        disconnect_attempted = True
        try:
            driver.stop()
        except Exception as error:
            raise NativeUIError("The completed browser inspection did not disconnect") from error
        return _wait_for_profile_absence(pending)
    except NativeUIError as error:
        failure = error
        raise
    except Exception as error:
        failure = error
        raise NativeUIError("The completed browser could not be closed safely") from error
    except BaseException as error:
        failure = error
        raise
    finally:
        if not disconnect_attempted:
            try:
                driver.stop()
            except Exception as error:
                if failure is None:
                    raise NativeUIError(
                        "The completed browser inspection did not disconnect"
                    ) from error
