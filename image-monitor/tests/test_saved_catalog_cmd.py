"""Exercise the fixed offline preview root through real Windows argument parsing."""

import os
from pathlib import Path

import pytest
from test_monitor_save_cmd import WINDOWS, copy_launcher, run_cmd
from test_windows_uv_lookup import guarded_launcher, inert_monitor_launcher_text

PROJECT = Path(__file__).resolve().parents[1]


def capture_monitor_launcher(folder):
    lines = []
    matches = 0
    for line in inert_monitor_launcher_text().splitlines():
        if line.startswith('"%UV_EXE%"') and " image-monitor monitor " in line:
            arguments = line.split(" image-monitor ", 1)[1].split(' >>"%LOG_FILE%"', 1)[0]
            lines.extend([f'call "%~dp0capture.cmd" {arguments}', "exit /b %ERRORLEVEL%"])
            matches += 1
        elif line.startswith(('"%UV_EXE%"', "winget.exe ", 'start "" ')):
            lines.append("exit /b 87")
        else:
            lines.append(line)
    assert matches == 1
    launcher = copy_launcher(folder, "\n".join(lines) + "\n")
    capture = ["@echo off", *[f'echo ARG{index}="%~{index}"' for index in range(1, 9)]]
    capture.append("exit /b 100")
    (folder / "capture.cmd").write_bytes(("\r\n".join(capture) + "\r\n").encode("ascii"))
    return launcher


def expected_arguments(local_root):
    return [
        'ARG1="monitor"',
        'ARG2="--work-root"',
        f'ARG3="{local_root}\\ImageMonitorWatch"',
        'ARG4="--save-root"',
        f'ARG5="{local_root}\\ImageMonitorMonitorSave"',
        'ARG6="--batch-root"',
        f'ARG7="{local_root}\\ImageMonitorBatch"',
        'ARG8=""',
    ]


@WINDOWS
@pytest.mark.parametrize("chrome_first", [False, True])
def test_monitor_passes_three_fixed_roots_as_single_arguments_without_starting_native_input(
    tmp_path, chrome_first
):
    launcher = capture_monitor_launcher(tmp_path / "monitor saved roots 한글 & space")
    environment = os.environ.copy()
    environment["LOCALAPPDATA"] = str(tmp_path / "local saved 한글 & space")
    arguments = ("--chrome", "--monitor") if chrome_first else ("--monitor", "--chrome")
    result = run_cmd(launcher, arguments, environment=environment)
    assert result.returncode == 100, result.stderr
    actual = [line for line in result.stdout.splitlines() if line.startswith("ARG")]
    assert actual == expected_arguments(environment["LOCALAPPDATA"])
    assert not Path(environment["LOCALAPPDATA"]).exists()
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))


@WINDOWS
def test_normal_monitor_wrapper_uses_the_preview_root_and_preserves_exit_code(tmp_path):
    launcher = capture_monitor_launcher(tmp_path / "saved viewer wrapper 한글 & space")
    wrapper = launcher.parent / "RUN_MONITOR.cmd"
    wrapper.write_bytes((PROJECT / wrapper.name).read_bytes())
    environment = os.environ.copy()
    environment["LOCALAPPDATA"] = str(tmp_path / "saved wrapper local 한글 & space")
    result = run_cmd(wrapper, (), environment=environment)
    assert result.returncode == 100, result.stderr
    actual = [line for line in result.stdout.splitlines() if line.startswith("ARG")]
    assert actual == expected_arguments(environment["LOCALAPPDATA"])
    assert not Path(environment["LOCALAPPDATA"]).exists()


@WINDOWS
@pytest.mark.parametrize(
    "extra",
    [("--save-root", "C:/foreign"), ("--batch-root", "C:/foreign"), ("--preview-id", "foreign")],
)
def test_windows_launcher_does_not_allow_users_to_replace_the_fixed_preview_root(tmp_path, extra):
    launcher = guarded_launcher(tmp_path / "guarded saved viewer")
    result = run_cmd(launcher, ("--monitor", "--chrome", *extra))
    assert result.returncode == 2
    assert "Unsupported test launcher argument" in result.stderr
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))
