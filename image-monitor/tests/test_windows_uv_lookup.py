"""Exercise real CMD lookup without executing uv, installing anything, or opening a UI.

The registry case is restricted to explicitly opted-in GitHub Actions Windows runners.
It restores the exact previous User PATH value/type before leaving the test.
"""

import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Requires real Windows CMD")
LAUNCHER = Path(__file__).resolve().parents[1] / "RUN_WINDOWS_TEST.cmd"


def run_lookup(*, path: str, launcher=LAUNCHER, arguments=("--find-uv",)) -> str:
    # Refuse to run an older launcher that could enter installation instead.
    assert "--find-uv" in launcher.read_text(encoding="ascii")
    environment = os.environ.copy()
    environment["PATH"] = path
    environment["PYTHONUTF8"] = "1"
    # os.environ is case-insensitive on Windows, but its copied dict is not.
    command_processor = Path(environment["SYSTEMROOT"]) / "System32" / "cmd.exe"
    # /s /c needs one surrounding quote pair in addition to the executable's pair.
    command = f'"{command_processor}" /d /s /c ""{launcher}" {" ".join(arguments)}"'
    existing_logs = set(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))
    result = subprocess.run(
        command,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=30,
        check=False,
    )
    assert set(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt")) == existing_logs
    assert result.returncode == 0, result.stderr
    lines = result.stdout.strip().splitlines()
    assert len(lines) == 1, result.stdout
    assert lines[0].startswith('"') and lines[0].endswith('"'), result.stdout
    return lines[0][1:-1]


def fake_uv(directory: Path) -> Path:
    directory.mkdir()
    executable = directory / "uv.exe"
    # Deliberately not a PE executable. Lookup must never invoke it, even for --version.
    executable.write_bytes(b"not executable: discovery fixture only\r\n")
    return executable


def test_process_path_lookup_preserves_korean_spaces_and_ampersand(tmp_path):
    executable = fake_uv(tmp_path / "uv 한글 & space")
    system32 = Path(os.environ["SystemRoot"]) / "System32"
    found = run_lookup(path=f"{executable.parent};{system32}")
    assert os.path.normcase(found) == os.path.normcase(str(executable))


def guarded_launcher(directory):
    """Keep a parser regression from ever reaching setup, log creation or native UI."""
    directory.mkdir()
    text = LAUNCHER.read_text(encoding="ascii")
    assert "\n:new_log\n" in text
    text = text.replace("\n:new_log\n", "\n:new_log\nexit /b 77\n", 1)
    copied = directory / LAUNCHER.name
    copied.write_bytes(text.replace("\n", "\r\n").encode("ascii"))
    return copied


@pytest.mark.parametrize(
    "arguments",
    [
        ("--chrome", "--find-uv"),
        ("--find-uv", "--chrome", "--recover-closed"),
        ("--recover-closed", "--chrome", "--find-uv"),
        ("--site-inspect", "--chrome", "--find-uv"),
        ("--find-uv", "--site-inspect", "--recover-closed"),
        ("--recover-closed", "--site-inspect", "--chrome", "--find-uv"),
        ("--save-post", "--chrome", "--find-uv"),
        ("--find-uv", "--save-post", "--recover-closed"),
        ("--site-inspect", "--save-post", "--find-uv"),
        ("--save-post", "--site-inspect", "--recover-closed", "--find-uv"),
        ("--resume-preinput", "--find-uv"),
        ("--find-uv", "--save-post", "--resume-preinput", "--chrome"),
        ("--resume-preinput", "--recover-closed", "--find-uv"),
        ("--site-inspect", "--resume-preinput", "--find-uv"),
        ("--list-inspect", "--chrome", "--find-uv"),
        ("--find-uv", "--list-inspect", "--site-inspect"),
        ("--save-post", "--list-inspect", "--find-uv"),
        ("--list-inspect", "--recover-closed", "--find-uv"),
        ("--resume-preinput", "--find-uv", "--list-inspect"),
        ("--watch-test", "--chrome", "--find-uv"),
        ("--find-uv", "--watch-test", "--site-inspect"),
        ("--list-inspect", "--watch-test", "--find-uv"),
        ("--save-post", "--watch-test", "--find-uv"),
        ("--watch-test", "--recover-closed", "--find-uv"),
        ("--resume-preinput", "--find-uv", "--watch-test"),
        ("--candidate-test", "--chrome", "--find-uv"),
        ("--find-uv", "--candidate-test", "--site-inspect"),
        ("--candidate-test", "--list-inspect", "--find-uv"),
        ("--save-post", "--candidate-test", "--recover-closed", "--find-uv"),
        ("--candidate-test", "--resume-preinput", "--watch-test", "--find-uv"),
        ("--candidate-save-test", "--chrome", "--find-uv"),
        ("--find-uv", "--candidate-save-test", "--candidate-test"),
        ("--candidate-save-test", "--save-post", "--recover-closed", "--find-uv"),
        ("--resume-preinput", "--candidate-save-test", "--watch-test", "--find-uv"),
        ("--candidate-finish", "--find-uv"),
        ("--find-uv", "--candidate-finish", "--candidate-save-test"),
        ("--candidate-finish", "--save-post", "--recover-closed", "--find-uv"),
        ("--resume-preinput", "--candidate-finish", "--watch-test", "--find-uv"),
        (
            "--watch-test",
            "--list-inspect",
            "--site-inspect",
            "--save-post",
            "--recover-closed",
            "--resume-preinput",
            "--find-uv",
        ),
    ],
)
def test_check_flags_preserve_read_only_lookup(tmp_path, arguments):
    launcher = guarded_launcher(tmp_path / "launcher 한글 & space")
    executable = fake_uv(tmp_path / "uv 한글 & space")
    system32 = Path(os.environ["SystemRoot"]) / "System32"
    found = run_lookup(
        path=f"{executable.parent};{system32}", launcher=launcher, arguments=arguments
    )
    assert os.path.normcase(found) == os.path.normcase(str(executable))


@pytest.mark.parametrize("arguments", [("--unsupported",), ("--find-uv", "--unsupported")])
def test_unknown_arguments_stop_before_setup_or_lookup(tmp_path, arguments):
    launcher = guarded_launcher(tmp_path / "guarded launcher")
    command_processor = Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"
    command = f'"{command_processor}" /d /s /c ""{launcher}" {" ".join(arguments)}"'
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 2
    assert "Unsupported test launcher argument" in result.stderr
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))


@pytest.mark.parametrize(
    ("filename", "expected_arguments"),
    [
        ("RUN_CHROME_TEST.cmd", "--chrome"),
        ("RETRY_CHROME_TEST.cmd", "--chrome --recover-closed"),
        ("RUN_SITE_INSPECTION.cmd", "--site-inspect --chrome"),
        ("RUN_LIST_INSPECTION.cmd", "--list-inspect --chrome"),
        ("RUN_WATCH_TEST.cmd", "--watch-test --chrome"),
        ("RUN_CANDIDATE_TEST.cmd", "--candidate-test --chrome"),
        ("RUN_CANDIDATE_SAVE_TEST.cmd", "--candidate-save-test --chrome"),
        ("RUN_CANDIDATE_FINISH.cmd", "--candidate-finish"),
        ("RUN_POST_SAVE_TEST.cmd", "--save-post --chrome"),
        ("RETRY_POST_SAVE_TEST.cmd", "--save-post --chrome --resume-preinput"),
    ],
)
def test_supplied_wrappers_forward_explicit_options_and_exit_status(
    tmp_path, filename, expected_arguments
):
    folder = tmp_path / "Chrome 한글 & space"
    folder.mkdir()
    wrapper = folder / filename
    wrapper.write_bytes((LAUNCHER.parent / filename).read_bytes())
    # This inert stub is the only program the copied wrapper may call.
    (folder / LAUNCHER.name).write_bytes(b"@echo off\r\necho %*\r\nexit /b 19\r\n")
    command_processor = Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"
    command = f'"{command_processor}" /d /s /c ""{wrapper}""'
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 19, result.stderr
    assert result.stdout.strip() == expected_arguments


@pytest.mark.parametrize(
    "arguments",
    [
        ("--site-inspect", "--recover-closed"),
        ("--recover-closed", "--site-inspect"),
        ("--chrome", "--site-inspect", "--recover-closed"),
    ],
)
def test_site_inspection_rejects_native_recovery_before_setup(tmp_path, arguments):
    launcher = guarded_launcher(tmp_path / "guarded inspection")
    command_processor = Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"
    command = f'"{command_processor}" /d /s /c ""{launcher}" {" ".join(arguments)}"'
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 2
    assert "cannot recover native-save state" in result.stderr
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))


@pytest.mark.parametrize(
    "arguments",
    [
        ("--site-inspect", "--save-post"),
        ("--save-post", "--site-inspect"),
        ("--save-post", "--chrome", "--recover-closed", "--site-inspect"),
    ],
)
def test_post_save_rejects_read_only_inspection_before_setup(tmp_path, arguments):
    launcher = guarded_launcher(tmp_path / "guarded post save")
    command_processor = Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"
    command = f'"{command_processor}" /d /s /c ""{launcher}" {" ".join(arguments)}"'
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 2
    assert "cannot be combined with post saving" in result.stderr
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))


@pytest.mark.parametrize(
    "arguments",
    [
        ("--resume-preinput",),
        ("--chrome", "--resume-preinput"),
        ("--save-post", "--resume-preinput", "--recover-closed"),
        ("--recover-closed", "--resume-preinput", "--save-post"),
        ("--site-inspect", "--resume-preinput"),
        ("--save-post", "--resume-preinput", "--site-inspect"),
    ],
)
def test_preinput_resume_rejects_incompatible_modes_before_setup(tmp_path, arguments):
    launcher = guarded_launcher(tmp_path / "guarded preinput resume")
    command_processor = Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"
    command = f'"{command_processor}" /d /s /c ""{launcher}" {" ".join(arguments)}"'
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 2
    assert "Pre-input resume requires post saving" in result.stderr
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))


@pytest.mark.parametrize(
    "arguments",
    [
        ("--list-inspect", "--site-inspect"),
        ("--site-inspect", "--chrome", "--list-inspect"),
        ("--list-inspect", "--save-post"),
        ("--save-post", "--list-inspect"),
        ("--list-inspect", "--recover-closed"),
        ("--recover-closed", "--list-inspect"),
        ("--list-inspect", "--resume-preinput"),
        ("--resume-preinput", "--list-inspect"),
        ("--list-inspect", "--save-post", "--resume-preinput", "--recover-closed"),
    ],
)
def test_list_inspection_rejects_incompatible_modes_before_setup(tmp_path, arguments):
    launcher = guarded_launcher(tmp_path / "guarded list inspection")
    command_processor = Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"
    command = f'"{command_processor}" /d /s /c ""{launcher}" {" ".join(arguments)}"'
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 2
    assert "Read-only list inspection cannot be combined" in result.stderr
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))


@pytest.mark.parametrize(
    "conflict",
    ["--site-inspect", "--list-inspect", "--save-post", "--recover-closed", "--resume-preinput"],
)
@pytest.mark.parametrize("watch_first", [False, True])
def test_watch_trial_rejects_incompatible_modes_before_setup(tmp_path, conflict, watch_first):
    launcher = guarded_launcher(tmp_path / "guarded watch trial")
    arguments = ["--watch-test", conflict] if watch_first else [conflict, "--watch-test"]
    command_processor = Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"
    command = f'"{command_processor}" /d /s /c ""{launcher}" {" ".join(arguments)}"'
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 2
    assert "Bounded list-watch trial cannot be combined" in result.stderr
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))


@pytest.mark.parametrize(
    "conflict",
    [
        "--watch-test",
        "--site-inspect",
        "--list-inspect",
        "--save-post",
        "--recover-closed",
        "--resume-preinput",
    ],
)
@pytest.mark.parametrize("candidate_first", [False, True])
def test_candidate_inspection_rejects_incompatible_modes_before_setup(
    tmp_path, conflict, candidate_first
):
    launcher = guarded_launcher(tmp_path / "guarded candidate inspection")
    arguments = (
        ["--candidate-test", conflict] if candidate_first else [conflict, "--candidate-test"]
    )
    command_processor = Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"
    command = f'"{command_processor}" /d /s /c ""{launcher}" {" ".join(arguments)}"'
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 2
    assert "Bounded candidate inspection cannot be combined" in result.stderr
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))


@pytest.mark.parametrize(
    "conflict",
    [
        "--candidate-test",
        "--watch-test",
        "--site-inspect",
        "--list-inspect",
        "--save-post",
        "--recover-closed",
        "--resume-preinput",
    ],
)
@pytest.mark.parametrize("save_first", [False, True])
def test_candidate_save_rejects_other_modes_before_setup(tmp_path, conflict, save_first):
    launcher = guarded_launcher(tmp_path / "guarded candidate save")
    arguments = (
        ["--candidate-save-test", conflict] if save_first else [conflict, "--candidate-save-test"]
    )
    arguments.append("--chrome")
    command_processor = Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"
    command = f'"{command_processor}" /d /s /c ""{launcher}" {" ".join(arguments)}"'
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 2
    assert "Candidate native saving cannot be combined" in result.stderr
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))


def test_candidate_save_requires_chrome_before_setup(tmp_path):
    launcher = guarded_launcher(tmp_path / "guarded candidate browser")
    command_processor = Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"
    command = f'"{command_processor}" /d /s /c ""{launcher}" --candidate-save-test"'
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 2
    assert "Candidate native saving requires the supplied Chrome launcher" in result.stderr
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))


@pytest.mark.parametrize(
    "conflict",
    [
        "--candidate-save-test",
        "--candidate-test",
        "--watch-test",
        "--site-inspect",
        "--list-inspect",
        "--save-post",
        "--recover-closed",
        "--resume-preinput",
    ],
)
@pytest.mark.parametrize("finish_first", [False, True])
def test_completed_candidate_verification_rejects_other_modes_before_setup(
    tmp_path, conflict, finish_first
):
    launcher = guarded_launcher(tmp_path / "guarded candidate finish")
    arguments = (
        ["--candidate-finish", conflict] if finish_first else [conflict, "--candidate-finish"]
    )
    command_processor = Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"
    command = f'"{command_processor}" /d /s /c ""{launcher}" {" ".join(arguments)}"'
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 2
    assert "Completed candidate verification cannot be combined" in result.stderr
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))


def inert_candidate_finish_launcher_text():
    """Retain offline mode routing while guarding setup and every external command."""
    text = LAUNCHER.read_text(encoding="ascii")
    text = text.replace(
        "\n:new_log\n", '\n:new_log\nset "LOG_FILE=NUL"\ngoto after_dependencies\n', 1
    )
    marker = 'if "%CANDIDATE_FINISH%"=="1" goto start_candidate_finish'
    assert text.count(marker) == 1
    return text.replace(marker, ":after_dependencies\n" + marker, 1)


@pytest.mark.parametrize("arguments", [("--candidate-finish",), ("--chrome", "--candidate-finish")])
def test_completed_candidate_verification_routes_before_every_native_or_browser_mode(
    tmp_path, arguments
):
    text = inert_candidate_finish_launcher_text()
    for label, mode, code in [
        ("start_probe", "native-probe", 92),
        ("start_site_inspection", "site-inspect", 91),
        ("start_post_save", "save-post", 93),
        ("start_list_inspection", "list-inspect", 95),
        ("start_watch_test", "watch-test", 96),
        ("start_candidate_test", "candidate-test", 97),
        ("start_candidate_save_test", "candidate-save-test", 98),
        ("start_candidate_finish", "candidate-finish", 99),
    ]:
        text = text.replace(f"\n:{label}\n", f"\n:{label}\necho MODE={mode}\nexit /b {code}\n", 1)
    lines = [
        "exit /b 77" if line.startswith(('"%UV_EXE%"', "winget.exe ", 'start "" ')) else line
        for line in text.splitlines()
    ]
    launcher = tmp_path / LAUNCHER.name
    launcher.write_bytes(("\r\n".join(lines) + "\r\n").encode("ascii"))
    command_processor = Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"
    command = f'"{command_processor}" /d /s /c ""{launcher}" {" ".join(arguments)}"'
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 99, result.stderr
    assert result.stdout.strip() == "MODE=candidate-finish"
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))


def test_completed_candidate_command_preserves_both_quoted_roots_without_browser_or_native_flags(
    tmp_path,
):
    text = inert_candidate_finish_launcher_text()
    finish_commands = 0
    lines = []
    for line in text.splitlines():
        if line.startswith('"%UV_EXE%"') and " image-monitor candidate-finish " in line:
            command = line.split(" image-monitor ", 1)[1].split(' >>"%LOG_FILE%"', 1)[0]
            assert "--browser" not in command
            assert "resume" not in command and "recover" not in command
            lines.extend([f"echo COMMAND={command}", "exit /b 99"])
            finish_commands += 1
        elif line.startswith(('"%UV_EXE%"', "winget.exe ", 'start "" ')):
            lines.append("exit /b 77")
        else:
            lines.append(line)
    assert finish_commands == 1
    launcher = tmp_path / LAUNCHER.name
    launcher.write_bytes(("\r\n".join(lines) + "\r\n").encode("ascii"))
    environment = os.environ.copy()
    environment["LOCALAPPDATA"] = str(tmp_path / "local 한글 & space")
    command_processor = Path(environment["SYSTEMROOT"]) / "System32" / "cmd.exe"
    command = f'"{command_processor}" /d /s /c ""{launcher}" --candidate-finish"'
    result = subprocess.run(
        command,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 99, result.stderr
    expected = (
        f'COMMAND=candidate-finish --watch-root "{environment["LOCALAPPDATA"]}'
        f'\\ImageMonitorWatch" --work-root "{environment["LOCALAPPDATA"]}'
        '\\ImageMonitorCandidateSave"'
    )
    assert result.stdout.strip().splitlines()[-1] == expected
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))
    assert not Path(environment["LOCALAPPDATA"]).exists()


def inert_candidate_save_launcher_text():
    """Bypass setup only; retain the real mode checks and guarded command routing."""
    text = LAUNCHER.read_text(encoding="ascii")
    text = text.replace(
        "\n:new_log\n", '\n:new_log\nset "LOG_FILE=NUL"\ngoto after_dependencies\n', 1
    )
    marker = 'if "%CANDIDATE_SAVE_TEST%"=="1" goto start_candidate_save_test'
    assert text.count(marker) == 1
    return text.replace(marker, ":after_dependencies\n" + marker, 1)


@pytest.mark.parametrize(
    "arguments", [("--candidate-save-test", "--chrome"), ("--chrome", "--candidate-save-test")]
)
def test_candidate_save_routes_before_all_other_modes_and_recovery(tmp_path, arguments):
    text = inert_candidate_save_launcher_text()
    for label, mode, code in [
        ("start_probe", "native-probe", 92),
        ("start_site_inspection", "site-inspect", 91),
        ("start_post_save", "save-post", 93),
        ("start_list_inspection", "list-inspect", 95),
        ("start_watch_test", "watch-test", 96),
        ("start_candidate_test", "candidate-test", 97),
        ("start_candidate_save_test", "candidate-save-test", 98),
    ]:
        text = text.replace(
            f"\n:{label}\n",
            f"\n:{label}\necho MODE={mode} BROWSER=%TEST_BROWSER%\nexit /b {code}\n",
            1,
        )
    lines = [
        "exit /b 77" if line.startswith(('"%UV_EXE%"', "winget.exe ", 'start "" ')) else line
        for line in text.splitlines()
    ]
    launcher = tmp_path / LAUNCHER.name
    launcher.write_bytes(("\r\n".join(lines) + "\r\n").encode("ascii"))
    command_processor = Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"
    command = f'"{command_processor}" /d /s /c ""{launcher}" {" ".join(arguments)}"'
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 98, result.stderr
    assert result.stdout.strip() == "MODE=candidate-save-test BROWSER=chrome"
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))


def test_candidate_save_command_uses_two_distinct_quoted_roots_without_automatic_recovery(tmp_path):
    text = inert_candidate_save_launcher_text()
    candidate_commands = 0
    lines = []
    for line in text.splitlines():
        if line.startswith('"%UV_EXE%"') and " image-monitor candidate-save-test " in line:
            command = line.split(" image-monitor ", 1)[1].split(' >>"%LOG_FILE%"', 1)[0]
            assert "resume" not in command and "recover" not in command
            lines.extend([f"echo COMMAND={command}", "exit /b 98"])
            candidate_commands += 1
        elif line.startswith(('"%UV_EXE%"', "winget.exe ", 'start "" ')):
            lines.append("exit /b 77")
        else:
            lines.append(line)
    assert candidate_commands == 1
    launcher = tmp_path / LAUNCHER.name
    launcher.write_bytes(("\r\n".join(lines) + "\r\n").encode("ascii"))
    environment = os.environ.copy()
    environment["LOCALAPPDATA"] = str(tmp_path / "local 한글 & space")
    command_processor = Path(environment["SYSTEMROOT"]) / "System32" / "cmd.exe"
    command = f'"{command_processor}" /d /s /c ""{launcher}" --candidate-save-test --chrome"'
    result = subprocess.run(
        command,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 98, result.stderr
    expected = (
        f'COMMAND=candidate-save-test --watch-root "{environment["LOCALAPPDATA"]}'
        f'\\ImageMonitorWatch" --work-root "{environment["LOCALAPPDATA"]}'
        '\\ImageMonitorCandidateSave" --browser "chrome"'
    )
    assert result.stdout.strip().splitlines()[-1] == expected
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))
    assert not Path(environment["LOCALAPPDATA"]).exists()


def inert_candidate_launcher_text():
    """Keep setup and native input inert while testing the real routing decision."""
    text = LAUNCHER.read_text(encoding="ascii")
    text = text.replace(
        "\n:new_log\n", '\n:new_log\nset "LOG_FILE=NUL"\ngoto after_dependencies\n', 1
    )
    marker = 'if "%CANDIDATE_TEST%"=="1" goto start_candidate_test'
    assert text.count(marker) == 1
    return text.replace(marker, ":after_dependencies\n" + marker, 1)


@pytest.mark.parametrize(
    ("arguments", "expected_browser"),
    [
        (("--candidate-test",), "edge"),
        (("--candidate-test", "--chrome"), "chrome"),
        (("--chrome", "--candidate-test"), "chrome"),
    ],
)
def test_candidate_inspection_routes_before_watch_recovery_and_all_native_modes(
    tmp_path, arguments, expected_browser
):
    text = inert_candidate_launcher_text()
    for label, mode, code in [
        ("start_probe", "native-probe", 92),
        ("start_site_inspection", "site-inspect", 91),
        ("start_post_save", "save-post", 93),
        ("start_list_inspection", "list-inspect", 95),
        ("start_watch_test", "watch-test", 96),
        ("start_candidate_test", "candidate-test", 97),
    ]:
        text = text.replace(
            f"\n:{label}\n",
            f"\n:{label}\necho MODE={mode} BROWSER=%TEST_BROWSER%\nexit /b {code}\n",
            1,
        )
    lines = [
        "exit /b 77" if line.startswith(('"%UV_EXE%"', "winget.exe ", 'start "" ')) else line
        for line in text.splitlines()
    ]
    launcher = tmp_path / LAUNCHER.name
    launcher.write_bytes(("\r\n".join(lines) + "\r\n").encode("ascii"))
    command_processor = Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"
    command = f'"{command_processor}" /d /s /c ""{launcher}" {" ".join(arguments)}"'
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 97, result.stderr
    assert result.stdout.strip() == f"MODE=candidate-test BROWSER={expected_browser}"
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))


@pytest.mark.parametrize("chrome", [False, True])
def test_candidate_inspection_command_reuses_quoted_watch_work_root_and_selected_browser(
    tmp_path, chrome
):
    text = inert_candidate_launcher_text()
    candidate_commands = 0
    lines = []
    for line in text.splitlines():
        if line.startswith('"%UV_EXE%"') and " image-monitor candidate-test " in line:
            command = line.split(" image-monitor ", 1)[1].split(' >>"%LOG_FILE%"', 1)[0]
            lines.extend([f"echo COMMAND={command}", "exit /b 97"])
            candidate_commands += 1
        elif line.startswith(('"%UV_EXE%"', "winget.exe ", 'start "" ')):
            lines.append("exit /b 77")
        else:
            lines.append(line)
    assert candidate_commands == 1
    launcher = tmp_path / LAUNCHER.name
    launcher.write_bytes(("\r\n".join(lines) + "\r\n").encode("ascii"))
    environment = os.environ.copy()
    environment["LOCALAPPDATA"] = str(tmp_path / "local 한글 & space")
    command_processor = Path(environment["SYSTEMROOT"]) / "System32" / "cmd.exe"
    arguments = ["--candidate-test"]
    if chrome:
        arguments.append("--chrome")
    command = f'"{command_processor}" /d /s /c ""{launcher}" {" ".join(arguments)}"'
    result = subprocess.run(
        command,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 97, result.stderr
    browser = "chrome" if chrome else "edge"
    expected = (
        f'COMMAND=candidate-test --work-root "{environment["LOCALAPPDATA"]}'
        f'\\ImageMonitorWatch" --browser "{browser}"'
    )
    assert result.stdout.strip().splitlines()[-1] == expected
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))
    assert not Path(environment["LOCALAPPDATA"]).exists()


def inert_watch_launcher_text():
    """Bypass setup in a copy, guarding every external command before running CMD."""
    text = LAUNCHER.read_text(encoding="ascii")
    text = text.replace(
        "\n:new_log\n", '\n:new_log\nset "LOG_FILE=NUL"\ngoto after_dependencies\n', 1
    )
    marker = 'if "%WATCH_TEST%"=="1" goto start_watch_test'
    assert text.count(marker) == 1
    return text.replace(marker, ":after_dependencies\n" + marker, 1)


@pytest.mark.parametrize(
    ("arguments", "expected_browser"),
    [
        (("--watch-test",), "edge"),
        (("--watch-test", "--chrome"), "chrome"),
        (("--chrome", "--watch-test"), "chrome"),
    ],
)
def test_watch_trial_routes_before_recovery_and_all_native_modes(
    tmp_path, arguments, expected_browser
):
    text = inert_watch_launcher_text()
    for label, mode, code in [
        ("start_probe", "native-probe", 92),
        ("start_site_inspection", "site-inspect", 91),
        ("start_post_save", "save-post", 93),
        ("start_list_inspection", "list-inspect", 95),
        ("start_watch_test", "watch-test", 96),
    ]:
        text = text.replace(
            f"\n:{label}\n",
            f"\n:{label}\necho MODE={mode} BROWSER=%TEST_BROWSER%\nexit /b {code}\n",
            1,
        )
    lines = [
        "exit /b 77" if line.startswith(('"%UV_EXE%"', "winget.exe ", 'start "" ')) else line
        for line in text.splitlines()
    ]
    launcher = tmp_path / LAUNCHER.name
    launcher.write_bytes(("\r\n".join(lines) + "\r\n").encode("ascii"))
    command_processor = Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"
    command = f'"{command_processor}" /d /s /c ""{launcher}" {" ".join(arguments)}"'
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 96, result.stderr
    assert result.stdout.strip() == f"MODE=watch-test BROWSER={expected_browser}"
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))


@pytest.mark.parametrize("chrome", [False, True])
def test_watch_trial_command_expands_quoted_work_root_and_selected_browser(tmp_path, chrome):
    text = inert_watch_launcher_text()
    watch_commands = 0
    lines = []
    for line in text.splitlines():
        if line.startswith('"%UV_EXE%"') and " image-monitor watch-test " in line:
            command = line.split(" image-monitor ", 1)[1].split(' >>"%LOG_FILE%"', 1)[0]
            lines.extend([f"echo COMMAND={command}", "exit /b 96"])
            watch_commands += 1
        elif line.startswith(('"%UV_EXE%"', "winget.exe ", 'start "" ')):
            lines.append("exit /b 77")
        else:
            lines.append(line)
    assert watch_commands == 1
    launcher = tmp_path / LAUNCHER.name
    launcher.write_bytes(("\r\n".join(lines) + "\r\n").encode("ascii"))
    environment = os.environ.copy()
    environment["LOCALAPPDATA"] = str(tmp_path / "local 한글 & space")
    command_processor = Path(environment["SYSTEMROOT"]) / "System32" / "cmd.exe"
    arguments = ["--watch-test"]
    if chrome:
        arguments.append("--chrome")
    command = f'"{command_processor}" /d /s /c ""{launcher}" {" ".join(arguments)}"'
    result = subprocess.run(
        command,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 96, result.stderr
    browser = "chrome" if chrome else "edge"
    expected = (
        f'COMMAND=watch-test --work-root "{environment["LOCALAPPDATA"]}'
        f'\\ImageMonitorWatch" --browser "{browser}"'
    )
    assert result.stdout.strip().splitlines()[-1] == expected
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))
    assert not Path(environment["LOCALAPPDATA"]).exists()


@pytest.mark.parametrize(
    ("arguments", "expected_browser"),
    [
        (("--list-inspect",), "edge"),
        (("--list-inspect", "--chrome"), "chrome"),
        (("--chrome", "--list-inspect"), "chrome"),
    ],
)
def test_list_inspection_routes_before_recovery_and_all_native_modes(
    tmp_path, arguments, expected_browser
):
    text = LAUNCHER.read_text(encoding="ascii")
    text = text.replace(
        "\n:new_log\n", '\n:new_log\nset "LOG_FILE=NUL"\ngoto after_dependencies\n', 1
    )
    marker = 'if "%READ_ONLY_LIST_INSPECTION%"=="1" goto start_list_inspection'
    assert marker in text
    text = text.replace(marker, ":after_dependencies\n" + marker, 1)
    for label, mode, code in [
        ("start_probe", "native-probe", 92),
        ("start_site_inspection", "site-inspect", 91),
        ("start_post_save", "save-post", 93),
        ("start_list_inspection", "list-inspect", 95),
    ]:
        text = text.replace(
            f"\n:{label}\n",
            f"\n:{label}\necho MODE={mode} BROWSER=%TEST_BROWSER%\nexit /b {code}\n",
            1,
        )
    lines = [
        "exit /b 77" if line.startswith(('"%UV_EXE%"', "winget.exe ", 'start "" ')) else line
        for line in text.splitlines()
    ]
    launcher = tmp_path / LAUNCHER.name
    launcher.write_bytes(("\r\n".join(lines) + "\r\n").encode("ascii"))
    command_processor = Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"
    command = f'"{command_processor}" /d /s /c ""{launcher}" {" ".join(arguments)}"'
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 95, result.stderr
    assert result.stdout.strip() == f"MODE=list-inspect BROWSER={expected_browser}"
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))


@pytest.mark.parametrize("chrome", [False, True])
def test_list_inspection_command_expands_quoted_work_root_and_selected_browser(tmp_path, chrome):
    text = LAUNCHER.read_text(encoding="ascii")
    text = text.replace(
        "\n:new_log\n", '\n:new_log\nset "LOG_FILE=NUL"\ngoto after_dependencies\n', 1
    )
    marker = 'if "%READ_ONLY_LIST_INSPECTION%"=="1" goto start_list_inspection'
    assert marker in text
    text = text.replace(marker, ":after_dependencies\n" + marker, 1)
    inspection_commands = 0
    lines = []
    for line in text.splitlines():
        if line.startswith('"%UV_EXE%"') and " image-monitor list-inspect " in line:
            command = line.split(" image-monitor ", 1)[1].split(' >>"%LOG_FILE%"', 1)[0]
            lines.extend([f"echo COMMAND={command}", "exit /b 95"])
            inspection_commands += 1
        elif line.startswith(('"%UV_EXE%"', "winget.exe ", 'start "" ')):
            lines.append("exit /b 77")
        else:
            lines.append(line)
    assert inspection_commands == 1
    launcher = tmp_path / LAUNCHER.name
    launcher.write_bytes(("\r\n".join(lines) + "\r\n").encode("ascii"))
    environment = os.environ.copy()
    environment["LOCALAPPDATA"] = str(tmp_path / "local 한글 & space")
    command_processor = Path(environment["SYSTEMROOT"]) / "System32" / "cmd.exe"
    arguments = ["--list-inspect"]
    if chrome:
        arguments.append("--chrome")
    command = f'"{command_processor}" /d /s /c ""{launcher}" {" ".join(arguments)}"'
    result = subprocess.run(
        command,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 95, result.stderr
    browser = "chrome" if chrome else "edge"
    expected = (
        f'COMMAND=list-inspect --work-root "{environment["LOCALAPPDATA"]}'
        f'\\ImageMonitorListInspection" --browser "{browser}"'
    )
    assert result.stdout.strip().splitlines()[-1] == expected
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))
    assert not Path(environment["LOCALAPPDATA"]).exists()


@pytest.mark.parametrize(
    "browser_flags,expected_browser", [((), "edge"), (("--chrome",), "chrome")]
)
def test_site_inspection_routes_after_dependencies_without_native_input(
    tmp_path, browser_flags, expected_browser
):
    # Skip setup only in this copied launcher and replace all potentially active
    # commands with an exit guard. Exercise the actual post-dependency branch.
    text = LAUNCHER.read_text(encoding="ascii")
    text = text.replace("\n:new_log\n", "\n:new_log\ngoto after_dependencies\n", 1)
    marker = 'if "%READ_ONLY_INSPECTION%"=="1" goto start_site_inspection'
    assert marker in text
    text = text.replace(marker, ":after_dependencies\n" + marker, 1)
    for label, mode, code in [
        ("start_probe", "native-probe", 92),
        ("start_site_inspection", "site-inspect", 91),
        ("start_post_save", "save-post", 93),
    ]:
        text = text.replace(
            f"\n:{label}\n",
            f"\n:{label}\necho MODE={mode} BROWSER=%TEST_BROWSER%\nexit /b {code}\n",
            1,
        )
    lines = [
        "exit /b 77" if line.startswith(('"%UV_EXE%"', "winget.exe ", 'start "" ')) else line
        for line in text.splitlines()
    ]
    launcher = tmp_path / LAUNCHER.name
    launcher.write_bytes(("\r\n".join(lines) + "\r\n").encode("ascii"))
    command_processor = Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"
    arguments = ("--site-inspect", *browser_flags)
    command = f'"{command_processor}" /d /s /c ""{launcher}" {" ".join(arguments)}"'
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 91, result.stderr
    assert result.stdout.strip() == f"MODE=site-inspect BROWSER={expected_browser}"
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))


@pytest.mark.parametrize(
    "arguments,expected_browser,expected_mode,expected_code,recovers",
    [
        (("--save-post", "--chrome"), "chrome", "save-post", 93, False),
        (
            ("--save-post", "--chrome", "--recover-closed"),
            "chrome",
            "save-post",
            93,
            True,
        ),
        (("--save-post",), "edge", "save-post", 93, False),
        (("--save-post", "--resume-preinput", "--chrome"), "chrome", "save-post", 93, False),
        ((), "edge", "native-probe", 92, False),
        (("--chrome",), "chrome", "native-probe", 92, False),
        (("--recover-closed",), "edge", "native-probe", 92, True),
    ],
)
def test_post_save_and_native_probe_routes_with_only_explicit_recovery(
    tmp_path, arguments, expected_browser, expected_mode, expected_code, recovers
):
    # Exercise the real decision after dependency setup, while every external
    # command and mode body is replaced with an inert guard in this copy.
    text = LAUNCHER.read_text(encoding="ascii")
    text = text.replace(
        "\n:new_log\n", '\n:new_log\nset "LOG_FILE=NUL"\ngoto after_dependencies\n', 1
    )
    marker = 'if "%READ_ONLY_INSPECTION%"=="1" goto start_site_inspection'
    assert marker in text
    text = text.replace(marker, ":after_dependencies\n" + marker, 1)
    for label, mode, code in [
        ("start_probe", "native-probe", 92),
        ("start_site_inspection", "site-inspect", 91),
        ("start_post_save", "save-post", 93),
    ]:
        text = text.replace(
            f"\n:{label}\n",
            f"\n:{label}\necho MODE={mode} BROWSER=%TEST_BROWSER%\nexit /b {code}\n",
            1,
        )
    recovery_calls = 0
    lines = []
    for line in text.splitlines():
        if line.startswith('"%UV_EXE%"') and " image-monitor native-recover " in line:
            recovery_calls += 1
            lines.extend(["echo RECOVERY=native-recover", "cmd.exe /d /c exit /b 0"])
        elif line.startswith(('"%UV_EXE%"', "winget.exe ", 'start "" ')):
            lines.append("exit /b 77")
        elif line.startswith("echo Checking that the previous test browser is closed"):
            continue
        else:
            lines.append(line)
    assert recovery_calls == 1
    launcher = tmp_path / LAUNCHER.name
    launcher.write_bytes(("\r\n".join(lines) + "\r\n").encode("ascii"))
    command_processor = Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"
    command = f'"{command_processor}" /d /s /c ""{launcher}" {" ".join(arguments)}"'
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == expected_code, result.stderr
    expected_lines = [f"MODE={expected_mode} BROWSER={expected_browser}"]
    if recovers:
        expected_lines.insert(0, "RECOVERY=native-recover")
    assert result.stdout.strip().splitlines() == expected_lines
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))


@pytest.mark.parametrize("resume", [False, True])
def test_post_save_command_forwards_resume_without_generic_recovery(tmp_path, resume):
    # Reach the actual save-post command with inert setup/native/UI guards.
    # Its substituted command prints only its CLI arguments, then exits.
    text = LAUNCHER.read_text(encoding="ascii")
    text = text.replace(
        "\n:new_log\n", '\n:new_log\nset "LOG_FILE=NUL"\ngoto after_dependencies\n', 1
    )
    marker = 'if "%READ_ONLY_INSPECTION%"=="1" goto start_site_inspection'
    assert marker in text
    text = text.replace(marker, ":after_dependencies\n" + marker, 1)
    save_commands = 0
    lines = []
    for line in text.splitlines():
        if line.startswith('"%UV_EXE%"') and " image-monitor save-post " in line:
            assert line.endswith(' %POST_SAVE_RESUME_ARGUMENT% >>"%LOG_FILE%" 2>&1')
            command = line.split(" image-monitor ", 1)[1].split(' >>"%LOG_FILE%"', 1)[0]
            lines.extend([f"echo COMMAND={command}", "exit /b 94"])
            save_commands += 1
        elif line.startswith(('"%UV_EXE%"', "winget.exe ", 'start "" ')):
            lines.append("exit /b 77")
        else:
            lines.append(line)
    assert save_commands == 1
    launcher = tmp_path / LAUNCHER.name
    launcher.write_bytes(("\r\n".join(lines) + "\r\n").encode("ascii"))
    command_processor = Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"
    arguments = ["--save-post", "--chrome"]
    if resume:
        arguments.append("--resume-preinput")
    command = f'"{command_processor}" /d /s /c ""{launcher}" {" ".join(arguments)}"'
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 94, result.stderr
    output = result.stdout.strip().splitlines()
    expected = (
        f'COMMAND=save-post --work-root "{os.environ["LOCALAPPDATA"]}\\ImageMonitorPostSave" '
        '--browser "chrome"'
    )
    if resume:
        expected += " --resume-preinput"
    assert output[-1].rstrip() == expected
    assert not list(launcher.parent.glob("WINDOWS_TEST_RESULT-*.txt"))


@contextmanager
def temporary_ci_user_path(value: str):
    # Keep the safety guard inside the helper too, not just in a pytest decorator.
    if not (
        sys.platform == "win32"
        and os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("IMAGE_MONITOR_ALLOW_PATH_TESTS") == "1"
    ):
        raise RuntimeError("User PATH mutation is permitted only in an opted-in Windows CI runner")
    import winreg

    access = winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, access) as key:
        try:
            original, original_type = winreg.QueryValueEx(key, "Path")
            existed = True
        except FileNotFoundError:
            original, original_type, existed = None, None, False
        winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, value)
        try:
            yield
        finally:
            if existed:
                winreg.SetValueEx(key, "Path", 0, original_type, original)
            else:
                winreg.DeleteValue(key, "Path")


def machine_path_has_uv() -> bool:
    import winreg

    machine_key = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, machine_key) as key:
        try:
            value, _kind = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            return False
    return any(
        (Path(os.path.expandvars(part.strip().strip('"'))) / "uv.exe").is_file()
        for part in value.split(";")
        if part.strip()
    )


@pytest.mark.skipif(
    os.environ.get("GITHUB_ACTIONS") != "true"
    or os.environ.get("IMAGE_MONITOR_ALLOW_PATH_TESTS") != "1",
    reason="Persistent PATH fixture is restricted to an explicitly opted-in GitHub Actions runner",
)
def test_stale_process_path_discovers_custom_registered_user_path(tmp_path):
    if machine_path_has_uv():
        pytest.skip("Machine PATH already resolves uv before the isolated User PATH fixture")
    executable = fake_uv(tmp_path / "새 설치 uv & space")
    system32 = Path(os.environ["SystemRoot"]) / "System32"
    # The parent process deliberately omits the new install directory. Only the
    # child resolver's registry refresh can see this custom, nondefault location.
    with temporary_ci_user_path(str(executable.parent)):
        found = run_lookup(path=str(system32))
    assert os.path.normcase(found) == os.path.normcase(str(executable))
