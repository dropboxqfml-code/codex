"""Exercise the two batch launch modes through real CMD without starting a saver."""

import os
from pathlib import Path

import pytest
from test_monitor_save_cmd import WINDOWS, copy_launcher, run_cmd
from test_windows_uv_lookup import fake_uv, guarded_launcher, run_lookup

PROJECT = Path(__file__).resolve().parents[1]
LAUNCHER = PROJECT / "RUN_WINDOWS_TEST.cmd"
MODES = ("--monitor-save-batch", "--monitor-batch-finish")
OLD_MODES = (
    "--monitor",
    "--monitor-save-test",
    "--monitor-finish",
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


def inert_launcher_text():
    text = LAUNCHER.read_text("ascii")
    text = text.replace(
        "\n:new_log\n", '\n:new_log\nset "LOG_FILE=NUL"\ngoto batch_after_dependencies\n', 1
    )
    marker = 'if "%MONITOR_SAVE_BATCH%"=="1" goto start_monitor_save_batch'
    assert text.count(marker) == 1
    return text.replace(marker, ":batch_after_dependencies\n" + marker, 1)


def test_batch_launchers_and_central_dispatcher_keep_ascii_crlf():
    for name in ("RUN_MONITOR_BATCH.cmd", "RUN_MONITOR_BATCH_FINISH.cmd", LAUNCHER.name):
        data = (PROJECT / name).read_bytes()
        data.decode("ascii")
        assert b"\r\n" in data and b"\n" not in data.replace(b"\r\n", b"")


@WINDOWS
@pytest.mark.parametrize(
    ("mode", "conflict"),
    [(mode, conflict) for mode in MODES for conflict in OLD_MODES + MODES if mode != conflict],
)
@pytest.mark.parametrize("new_first", [False, True])
def test_batch_modes_reject_every_other_operation_before_logs_or_setup(
    tmp_path, mode, conflict, new_first
):
    launcher = guarded_launcher(tmp_path / "batch guard 한글 & space")
    options = (mode, "--chrome", conflict) if new_first else (conflict, mode, "--chrome")
    result = run_cmd(launcher, options)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "cannot be combined" in result.stderr
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))


@WINDOWS
def test_batch_saving_requires_fixed_chrome_before_setup(tmp_path):
    launcher = guarded_launcher(tmp_path / "batch chrome")
    result = run_cmd(launcher, ("--monitor-save-batch",))
    assert result.returncode == 2 and "requires the supplied Chrome launcher" in result.stderr
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))


@WINDOWS
@pytest.mark.parametrize(
    "options",
    [
        ("--monitor-save-batch", "--find-uv"),
        ("--find-uv", "--monitor-batch-finish", "--monitor-save-batch"),
        ("--monitor-save-batch", "--recover-closed", "--find-uv"),
        ("--resume-preinput", "--monitor-batch-finish", "--find-uv"),
    ],
)
def test_batch_modes_keep_readonly_uv_lookup_fast_path(tmp_path, options):
    launcher = guarded_launcher(tmp_path / "batch lookup 한글 & space")
    executable = fake_uv(tmp_path / "uv batch 한글 & space")
    system32 = Path(os.environ["SystemRoot"]) / "System32"
    found = run_lookup(path=f"{executable.parent};{system32}", launcher=launcher, arguments=options)
    assert os.path.normcase(found) == os.path.normcase(str(executable))
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))


@WINDOWS
@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("RUN_MONITOR_BATCH.cmd", "--monitor-save-batch --chrome"),
        ("RUN_MONITOR_BATCH_FINISH.cmd", "--monitor-batch-finish --chrome"),
    ],
)
def test_batch_wrappers_supply_fixed_mode_and_preserve_exit_code(tmp_path, filename, expected):
    folder = tmp_path / "batch wrapper 한글 & space"
    folder.mkdir()
    wrapper = folder / filename
    wrapper.write_bytes((PROJECT / filename).read_bytes())
    (folder / LAUNCHER.name).write_bytes(b"@echo off\r\necho %*\r\nexit /b 19\r\n")
    result = run_cmd(wrapper, ())
    assert result.returncode == 19 and result.stdout.strip() == expected
    assert not list(folder.glob("WINDOWS_TEST_RESULT-*.txt"))


@WINDOWS
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("chrome_first", [False, True])
def test_batch_dispatch_selects_only_its_own_command_branch(tmp_path, mode, chrome_first):
    text = inert_launcher_text()
    targets = (
        ("start_monitor_save_batch", "monitor-save-batch", 86),
        ("start_monitor_batch_finish", "monitor-batch-finish", 87),
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
            "exit /b 85" if line.startswith(('"%UV_EXE%"', "winget.exe ", 'start "" ')) else line
            for line in text.splitlines()
        )
        + "\n"
    )
    launcher = copy_launcher(tmp_path / "batch route 한글 & space", text)
    options = ("--chrome", mode) if chrome_first else (mode, "--chrome")
    result = run_cmd(launcher, options)
    assert result.returncode == (86 if mode == "--monitor-save-batch" else 87), result.stderr
    assert result.stdout.strip() == f"MODE={mode[2:]}"
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))


@WINDOWS
@pytest.mark.parametrize("mode", MODES)
def test_batch_commands_quote_all_three_roots_and_keep_legacy_output_separate(tmp_path, mode):
    text = inert_launcher_text()
    lines = []
    matches = 0
    for line in text.splitlines():
        if line.startswith('"%UV_EXE%"') and f" image-monitor {mode[2:]} " in line:
            command = line.split(" image-monitor ", 1)[1].split(' >>"%LOG_FILE%"', 1)[0]
            assert not any(option in command for option in ("--browser", "recover", "resume"))
            assert "ImageMonitorCandidateSave" not in command
            lines.extend([f"echo COMMAND={command}", "exit /b 86"])
            matches += 1
        elif line.startswith(('"%UV_EXE%"', "winget.exe ", 'start "" ')):
            lines.append("exit /b 85")
        else:
            lines.append(line)
    assert matches == 1
    launcher = copy_launcher(tmp_path / "batch roots 한글 & space", "\n".join(lines) + "\n")
    environment = os.environ.copy()
    environment["LOCALAPPDATA"] = str(tmp_path / "local batch 한글 & space")
    result = run_cmd(launcher, (mode, "--chrome"), environment=environment)
    assert result.returncode == 86, result.stderr
    local = environment["LOCALAPPDATA"]
    expected = (
        f'COMMAND={mode[2:]} --watch-root "{local}\\ImageMonitorWatch" '
        f'--legacy-root "{local}\\ImageMonitorMonitorSave" --work-root "{local}\\ImageMonitorBatch"'
    )
    assert result.stdout.strip().splitlines()[-1] == expected
    assert not Path(local).exists()
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))


@WINDOWS
@pytest.mark.parametrize("mode", MODES)
def test_batch_setup_failure_reports_its_mode_without_launching_any_ui(tmp_path, mode):
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
    launcher = copy_launcher(tmp_path / "batch failure 한글 & space", text)
    result = run_cmd(launcher, (mode, "--chrome"))
    assert result.returncode == 1, result.stderr
    report = (launcher.parent / "captured.txt").read_text("utf-8")
    expected = (
        "MONITOR_BATCH_NATIVE_SAVE"
        if mode == "--monitor-save-batch"
        else "MONITOR_BATCH_VERIFICATION"
    )
    assert f"RESULT: STOPPED - {expected}" in report
    assert "RESULT: FAILED - automation" not in report
    if mode == "--monitor-save-batch":
        assert "No automatic retry or recovery" in report
        assert "No native image saving" not in report


@WINDOWS
@pytest.mark.parametrize("mode", MODES)
def test_batch_header_describes_only_its_operation_before_dependency_setup(tmp_path, mode):
    text = LAUNCHER.read_text("ascii")
    text = text.replace(
        'set "LOG_FILE=%~dp0WINDOWS_TEST_RESULT-%RANDOM%-%RANDOM%.txt"',
        'set "LOG_FILE=%~dp0captured.txt"',
        1,
    )
    text = text.replace('if not exist "pyproject.toml" goto missing_project', "exit /b 73", 1)
    launcher = copy_launcher(tmp_path / "batch header 한글 & space", text)
    result = run_cmd(launcher, (mode, "--chrome"))
    assert result.returncode == 73, result.stderr
    report = (launcher.parent / "captured.txt").read_text("utf-8")
    assert "synthetic-image" not in report
    assert "STAGE:" not in report
    if mode == "--monitor-save-batch":
        assert "Bounded native saving of at most two new" in report
        assert "For each new post, click save-start once" in report
        assert "Offline reconciliation" not in report
    else:
        assert "Offline reconciliation of already completed monitor batch" in report
        assert "Bounded native saving" not in report
        assert "Selected browser:" not in report
