"""Exercise the new native-monitor launch modes with real CMD and inert commands."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from test_windows_uv_lookup import fake_uv, guarded_launcher, run_lookup

PROJECT = Path(__file__).resolve().parents[1]
LAUNCHER = PROJECT / "RUN_WINDOWS_TEST.cmd"
WINDOWS = pytest.mark.skipif(sys.platform != "win32", reason="Requires real Windows CMD")
MODES = ("--monitor-save-test", "--monitor-finish")
OLD_MODES = (
    "--monitor",
    "--candidate-finish",
    "--candidate-save-test",
    "--candidate-test",
    "--watch-test",
    "--site-inspect",
    "--list-inspect",
    "--save-post",
    "--recover-closed",
    "--resume-preinput",
)


def run_cmd(launcher, arguments, *, environment=None):
    environment = environment or os.environ.copy()
    processor = Path(environment["SYSTEMROOT"]) / "System32" / "cmd.exe"
    command = f'"{processor}" /d /s /c ""{launcher}" {" ".join(arguments)}"'
    return subprocess.run(
        command,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=30,
        check=False,
    )


def copy_launcher(folder, text):
    folder.mkdir()
    path = folder / LAUNCHER.name
    path.write_bytes(text.replace("\n", "\r\n").encode("ascii"))
    return path


def inert_launcher_text():
    text = LAUNCHER.read_text("ascii")
    text = text.replace(
        "\n:new_log\n", '\n:new_log\nset "LOG_FILE=NUL"\ngoto after_dependencies\n', 1
    )
    marker = 'if "%MONITOR_SAVE_TEST%"=="1" goto start_monitor_save_test'
    assert text.count(marker) == 1
    return text.replace(marker, ":after_dependencies\n" + marker, 1)


def test_new_monitor_launchers_are_ascii_crlf_files():
    for filename in ("RUN_MONITOR_SAVE.cmd", "RUN_MONITOR_FINISH.cmd", LAUNCHER.name):
        data = (PROJECT / filename).read_bytes()
        data.decode("ascii")
        assert b"\r\n" in data and b"\n" not in data.replace(b"\r\n", b"")


@WINDOWS
@pytest.mark.parametrize(
    ("mode", "conflict"),
    [(mode, conflict) for mode in MODES for conflict in OLD_MODES + MODES if mode != conflict],
)
@pytest.mark.parametrize("new_first", [False, True])
def test_monitor_native_modes_reject_all_other_operations_before_setup(
    tmp_path, mode, conflict, new_first
):
    launcher = guarded_launcher(tmp_path / "guarded monitor native")
    arguments = (mode, conflict, "--chrome") if new_first else (conflict, "--chrome", mode)
    result = run_cmd(launcher, arguments)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "cannot be combined" in result.stderr
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))


@WINDOWS
def test_monitor_native_save_requires_chrome_before_setup(tmp_path):
    launcher = guarded_launcher(tmp_path / "guarded monitor browser")
    result = run_cmd(launcher, ("--monitor-save-test",))
    assert result.returncode == 2
    assert "requires the supplied Chrome launcher" in result.stderr
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))


@WINDOWS
@pytest.mark.parametrize(
    "arguments",
    [
        ("--monitor-save-test", "--find-uv"),
        ("--find-uv", "--monitor-finish", "--monitor-save-test"),
        ("--monitor-save-test", "--recover-closed", "--find-uv"),
        ("--resume-preinput", "--monitor-finish", "--find-uv"),
    ],
)
def test_new_modes_preserve_readonly_uv_lookup_without_setup(tmp_path, arguments):
    launcher = guarded_launcher(tmp_path / "monitor lookup 한글 & space")
    executable = fake_uv(tmp_path / "uv 한글 & space")
    system32 = Path(os.environ["SystemRoot"]) / "System32"
    found = run_lookup(
        path=f"{executable.parent};{system32}", launcher=launcher, arguments=arguments
    )
    assert os.path.normcase(found) == os.path.normcase(str(executable))


@WINDOWS
@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("RUN_MONITOR_SAVE.cmd", "--monitor-save-test --chrome"),
        ("RUN_MONITOR_FINISH.cmd", "--monitor-finish --chrome"),
    ],
)
def test_new_wrappers_forward_fixed_options_and_return_exit_code(tmp_path, filename, expected):
    folder = tmp_path / "monitor wrapper 한글 & space"
    folder.mkdir()
    wrapper = folder / filename
    wrapper.write_bytes((PROJECT / filename).read_bytes())
    (folder / LAUNCHER.name).write_bytes(b"@echo off\r\necho %*\r\nexit /b 19\r\n")
    result = run_cmd(wrapper, ())
    assert result.returncode == 19, result.stderr
    assert result.stdout.strip() == expected
    assert not list(folder.glob("WINDOWS_TEST_RESULT-*.txt"))


@WINDOWS
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("chrome_first", [False, True])
def test_new_modes_route_only_to_their_own_command_branch(tmp_path, mode, chrome_first):
    text = inert_launcher_text()
    targets = (
        ("start_monitor_save_test", "monitor-save-test", 88),
        ("start_monitor_finish", "monitor-finish", 89),
        ("start_monitor", "monitor", 90),
        ("start_candidate_finish", "candidate-finish", 91),
        ("start_candidate_save_test", "candidate-save-test", 92),
        ("start_candidate_test", "candidate-test", 93),
        ("start_watch_test", "watch-test", 94),
        ("start_list_inspection", "list-inspect", 95),
        ("start_site_inspection", "site-inspect", 96),
        ("start_post_save", "save-post", 97),
        ("start_probe", "native-probe", 98),
    )
    for label, command, code in targets:
        text = text.replace(
            f"\n:{label}\n", f"\n:{label}\necho MODE={command}\nexit /b {code}\n", 1
        )
    text = (
        "\n".join(
            "exit /b 87" if line.startswith(('"%UV_EXE%"', "winget.exe ", 'start "" ')) else line
            for line in text.splitlines()
        )
        + "\n"
    )
    launcher = copy_launcher(tmp_path / "monitor route 한글 & space", text)
    arguments = ("--chrome", mode) if chrome_first else (mode, "--chrome")
    result = run_cmd(launcher, arguments)
    assert result.returncode == (88 if mode == "--monitor-save-test" else 89), result.stderr
    assert result.stdout.strip() == f"MODE={mode[2:]}"
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))


@WINDOWS
@pytest.mark.parametrize("mode", MODES)
def test_monitor_native_commands_quote_two_roots_and_keep_earlier_save_root_unused(tmp_path, mode):
    text = inert_launcher_text()
    lines = []
    matches = 0
    command_name = mode[2:]
    for line in text.splitlines():
        if line.startswith('"%UV_EXE%"') and f" image-monitor {command_name} " in line:
            command = line.split(" image-monitor ", 1)[1].split(' >>"%LOG_FILE%"', 1)[0]
            assert "recover" not in command and "resume" not in command
            assert "ImageMonitorCandidateSave" not in command
            if mode == "--monitor-finish":
                assert "--browser" not in command
            lines += [f"echo COMMAND={command}", "exit /b 89"]
            matches += 1
        elif line.startswith(('"%UV_EXE%"', "winget.exe ", 'start "" ')):
            lines.append("exit /b 87")
        else:
            lines.append(line)
    assert matches == 1
    launcher = copy_launcher(tmp_path / "monitor roots 한글 & space", "\n".join(lines) + "\n")
    environment = os.environ.copy()
    environment["LOCALAPPDATA"] = str(tmp_path / "local 한글 & space")
    result = run_cmd(launcher, (mode, "--chrome"), environment=environment)
    assert result.returncode == 89, result.stderr
    expected = (
        f'COMMAND={command_name} --watch-root "{environment["LOCALAPPDATA"]}\\ImageMonitorWatch" '
        f'--work-root "{environment["LOCALAPPDATA"]}\\ImageMonitorMonitorSave"'
    )
    if mode == "--monitor-save-test":
        expected += ' --browser "chrome"'
    assert result.stdout.strip().splitlines()[-1] == expected
    assert not Path(environment["LOCALAPPDATA"]).exists()
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))


@WINDOWS
@pytest.mark.parametrize("mode", MODES)
def test_monitor_native_setup_failure_reports_its_own_operation_without_launching_ui(
    tmp_path, mode
):
    text = LAUNCHER.read_text("ascii")
    text = text.replace(
        "\n:new_log\n", '\n:new_log\nset "LOG_FILE=%~dp0captured.txt"\ngoto failed\n', 1
    )
    text = (
        "\n".join(
            "rem external command guarded by test" if line.startswith('start "" ') else line
            for line in text.splitlines()
        )
        + "\n"
    )
    launcher = copy_launcher(tmp_path / "monitor failure 한글 & space", text)
    result = run_cmd(launcher, (mode, "--chrome"))
    assert result.returncode == 1, result.stderr
    report = (launcher.parent / "captured.txt").read_text("utf-8")
    expected = (
        "MONITOR_CANDIDATE_NATIVE_SAVE"
        if mode == "--monitor-save-test"
        else "MONITOR_CANDIDATE_VERIFICATION"
    )
    assert f"RESULT: STOPPED - {expected}" in report
    assert "RESULT: FAILED - automation" not in report
    if mode == "--monitor-save-test":
        assert "No automatic retry or recovery" in report
        assert "No native image saving" not in report
