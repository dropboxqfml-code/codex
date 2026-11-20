import io
import json
import sys
from collections import deque
from types import SimpleNamespace

import pytest

from image_monitor import PUBLIC_VERSION, auto_monitor_cli
from image_monitor.__main__ import main


def test_bounded_cli_separates_progress_from_result_without_reading_keyboard(
    tmp_path, monkeypatch, capsys
):
    roots = [tmp_path / name for name in ("watch", "older", "images")]
    result = {"status": "auto_monitor_completed", "files_verified": 2}

    def run_monitor(*paths, max_cycles, should_stop, on_progress):
        assert paths == tuple(roots)
        assert max_cycles == 2
        assert should_stop is None
        on_progress(
            {
                "phase": "waiting",
                "cycles_completed": 1,
                "posts_saved": 1,
                "files_verified": 2,
                "next_eligible_at": "2026-06-01T12:00:00+00:00",
            }
        )
        return result

    monkeypatch.setattr(auto_monitor_cli, "_console_stop", lambda: pytest.fail("Keyboard polled"))
    monkeypatch.setitem(
        sys.modules,
        "image_monitor.monitor_auto_session",
        SimpleNamespace(run_auto_monitor=run_monitor, auto_monitor_exit_code=lambda report: 0),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "image-monitor",
            "auto-monitor",
            "--watch-root",
            str(roots[0]),
            "--legacy-root",
            str(roots[1]),
            "--work-root",
            str(roots[2]),
            "--max-cycles",
            "2",
        ],
    )
    monkeypatch.delenv("IMAGE_MONITOR_CONSOLE_PROGRESS", raising=False)
    assert main() == 0
    output = capsys.readouterr()
    assert json.loads(output.out) == result
    assert "완료 1주기" in output.err and "재개 예정" in output.err


def test_console_stop_polls_without_waiting_and_latches_enter(monkeypatch):
    keys = deque()
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setitem(
        sys.modules, "msvcrt", SimpleNamespace(kbhit=lambda: bool(keys), getwch=keys.popleft)
    )
    pressed = auto_monitor_cli._console_stop()
    assert not pressed()
    keys.extend(["x", "\r"])
    assert pressed()
    assert pressed()
    monkeypatch.setattr(sys, "stdin", io.StringIO())
    assert auto_monitor_cli._console_stop() is None


def test_launcher_routes_progress_to_its_console(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("IMAGE_MONITOR_CONSOLE_PROGRESS", "1")
    console = io.StringIO()

    def open_console(name, mode, *, encoding, buffering):
        assert (name, mode, encoding, buffering) == ("CONOUT$", "w", "utf-8", 1)
        return console

    monkeypatch.setattr("builtins.open", open_console)
    with auto_monitor_cli._progress_output() as output:
        assert output is console
    assert console.closed


def test_startup_error_is_reported_on_stdout_without_exception_text(tmp_path, monkeypatch, capsys):
    def failed(*args, **kwargs):
        raise RuntimeError("private local details")

    monkeypatch.setitem(
        sys.modules,
        "image_monitor.monitor_auto_session",
        SimpleNamespace(run_auto_monitor=failed, auto_monitor_exit_code=lambda report: 0),
    )
    assert auto_monitor_cli.run_auto_monitor_cli(tmp_path, tmp_path, tmp_path, 2) == 2
    output = capsys.readouterr()
    assert json.loads(output.out) == {
        "program_version": PUBLIC_VERSION,
        "status": "auto_monitor_review",
        "error_type": "RuntimeError",
    }
    assert "private local details" not in output.out + output.err
