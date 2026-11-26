"""Read an Enter event through the trial's actual Windows console input path."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


def _read_in_own_console():
    import ctypes
    import msvcrt
    from ctypes import wintypes
    from threading import Event

    from image_monitor.auto_monitor_cli import _console_stop, _progress_output
    from image_monitor.monitor_trial_progress import MonitorTrial

    class Key(ctypes.Structure):
        _fields_ = [
            ("down", wintypes.BOOL),
            ("repeat", wintypes.WORD),
            ("virtual", wintypes.WORD),
            ("scan", wintypes.WORD),
            ("char", wintypes.WCHAR),
            ("state", wintypes.DWORD),
        ]

    class Input(ctypes.Structure):
        _fields_ = [("kind", wintypes.WORD), ("key", Key)]

    write = ctypes.WinDLL("kernel32", use_last_error=True).WriteConsoleInputW
    write.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(Input),
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    )
    write.restype = wintypes.BOOL
    fd = os.open("CONIN$", os.O_RDWR | os.O_BINARY)
    with os.fdopen(fd, "rb", buffering=0) as input_stream:
        sys.stdin = input_stream
        keyboard = _console_stop()
        assert keyboard is not None
        trial = MonitorTrial(_progress_output, keyboard)
        with trial.observe():
            trial.record("waiting for Enter")
            events = (Input * 2)(
                Input(1, Key(True, 1, 13, 28, "\r", 0)), Input(1, Key(False, 1, 13, 28, "\r", 0))
            )
            written = wintypes.DWORD()
            if not write(
                msvcrt.get_osfhandle(input_stream.fileno()), events, 2, ctypes.byref(written)
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            assert written.value == 2
            pause = Event()
            for _ in range(100):
                if trial.should_stop():
                    break
                pause.wait(0.05)
            assert trial.stop_trigger == "enter" and trial.enter_elapsed == trial.stop_elapsed


@pytest.mark.skipif(os.name != "nt", reason="Windows console input buffer")
def test_enter_stops_trial_from_a_real_windows_console():
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = subprocess.SW_HIDE
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve())],
        creationflags=subprocess.CREATE_NEW_CONSOLE,
        startupinfo=info,
        env=os.environ | {"PYTHONUTF8": "1", "IMAGE_MONITOR_CONSOLE_PROGRESS": "1"},
        capture_output=True,
        encoding="utf-8",
        timeout=20,
    )
    assert proc.returncode == 0, proc.stderr
    assert "실행 창 Enter 입력 확인" in proc.stderr


if __name__ == "__main__":
    _read_in_own_console()
