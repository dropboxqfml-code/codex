"""Route monitor save/finish commands to the exact existing monitor scope."""

import json
import sys
from types import ModuleType

import pytest

from image_monitor.__main__ import main
from image_monitor.watch_store import WatchScope

MONITOR_SCOPE = WatchScope("목록 감시", "normal", "comic_new6", "ai", "search_subject_memo")
COMMANDS = (
    (
        "monitor-save-test",
        "candidate_save_runtime",
        "run_candidate_save_trial",
        "share_candidate_save_report",
    ),
    (
        "monitor-finish",
        "candidate_finish_runtime",
        "run_candidate_finish_trial",
        "share_candidate_finish_report",
    ),
)


def stub(monkeypatch, command, *, run, share=lambda report: report):
    _, module_name, runner, sharer = next(item for item in COMMANDS if item[0] == command)
    module = ModuleType(f"image_monitor.{module_name}")
    setattr(module, runner, run)
    setattr(module, sharer, share)
    monkeypatch.setitem(sys.modules, module.__name__, module)


def arguments(command, watch_root, save_root):
    return [
        "image-monitor",
        command,
        "--watch-root",
        str(watch_root),
        "--work-root",
        str(save_root),
    ]


@pytest.mark.parametrize("command", [item[0] for item in COMMANDS])
def test_monitor_save_and_finish_help_import_no_native_or_browser_code(
    monkeypatch, capsys, command
):
    for module in (
        "candidate_save_runtime",
        "candidate_finish_runtime",
        "candidate_save_policy",
        "candidate_save_selection",
        "monitor_controller",
        "watch_store",
        "native_ui",
        "native_probe",
        "native_state",
        "post_worker",
    ):
        monkeypatch.setitem(sys.modules, f"image_monitor.{module}", None)
    monkeypatch.setattr(sys, "argv", ["image-monitor", command, "--help"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 0
    output = capsys.readouterr().out
    assert command in output
    for unsupported in ("--scope", "--post-url", "--resume-preinput", "--confirm-browser-closed"):
        assert unsupported not in output
    if command == "monitor-finish":
        assert "--browser" not in output


@pytest.mark.parametrize("command", [item[0] for item in COMMANDS])
@pytest.mark.parametrize(
    "extra",
    [
        ["--scope", "previous trial"],
        ["--post-url", "https://foreign.example"],
        ["--resume-preinput"],
        ["--recover-closed"],
        ["--max-images", "3"],
        ["--browser", "edge"],
        ["--confirm-browser-closed"],
    ],
)
def test_monitor_commands_refuse_target_changes_before_runtime_import(monkeypatch, command, extra):
    for _, module, _, _ in COMMANDS:
        monkeypatch.setitem(sys.modules, f"image_monitor.{module}", None)
    monkeypatch.setattr(sys, "argv", arguments(command, "watch", "save") + extra)
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2


@pytest.mark.parametrize("command", [item[0] for item in COMMANDS])
@pytest.mark.parametrize("missing", ["--watch-root", "--work-root"])
def test_monitor_commands_require_both_distinct_root_arguments(monkeypatch, command, missing):
    options = arguments(command, "watch", "save")
    index = options.index(missing)
    del options[index : index + 2]
    monkeypatch.setattr(sys, "argv", options)
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2


@pytest.mark.parametrize("command", [item[0] for item in COMMANDS])
def test_monitor_commands_pass_only_roots_browser_and_fixed_scope(
    tmp_path, monkeypatch, capsys, command
):
    watch = tmp_path / "watch 한글 & space"
    save = tmp_path / "save 한글 & space"
    calls = []
    status = (
        "candidate_save_completed"
        if command == "monitor-save-test"
        else "candidate_finish_completed"
    )
    private = {"status": status, "title": "private title", "output_directory": str(save)}
    public = {"status": status, "browser_closed": True}

    def run(*args, **kwargs):
        calls.append((args, kwargs))
        return private

    def share(report):
        assert report is private
        return public

    stub(monkeypatch, command, run=run, share=share)
    monkeypatch.setattr(sys, "argv", arguments(command, watch, save))
    assert main() == 0
    expected = (watch, save, "chrome") if command == "monitor-save-test" else (watch, save)
    assert calls == [(expected, {"scope": MONITOR_SCOPE})]
    output = capsys.readouterr()
    assert json.loads(output.out) == public
    assert output.err == "" and "private" not in output.out
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    ("command", "report", "code"),
    [
        ("monitor-save-test", {"status": "candidate_save_completed"}, 0),
        ("monitor-save-test", {"status": "candidate_save_waiting"}, 0),
        ("monitor-save-test", {"status": "candidate_save_busy"}, 0),
        ("monitor-save-test", {"status": "candidate_save_no_candidate"}, 0),
        ("monitor-save-test", {"status": "candidate_save_manual_review"}, 2),
        ("monitor-save-test", {"status": "candidate_save_cancelled"}, 130),
        ("monitor-finish", {"status": "candidate_finish_completed"}, 0),
        ("monitor-finish", {"status": "candidate_finish_no_pending"}, 0),
        ("monitor-finish", {"status": "candidate_finish_busy"}, 0),
        ("monitor-finish", {"status": "candidate_finish_manual_review"}, 2),
        ("monitor-finish", {"status": "candidate_finish_cancelled"}, 130),
        ("monitor-finish", {"status": "unexpected"}, 2),
    ],
)
def test_monitor_status_and_cancellation_control_exit_code(
    tmp_path, monkeypatch, capsys, command, report, code
):
    stub(monkeypatch, command, run=lambda *args, **kwargs: report)
    monkeypatch.setattr(sys, "argv", arguments(command, tmp_path / "watch", tmp_path / "save"))
    assert main() == code
    assert json.loads(capsys.readouterr().out) == report
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("command", [item[0] for item in COMMANDS])
@pytest.mark.parametrize("stage", ["run", "share"])
@pytest.mark.parametrize(
    ("failure", "code", "message"),
    [
        (RuntimeError("private title author URL token"), 2, "RuntimeError"),
        (KeyboardInterrupt("private title URL token"), 130, "cancelled"),
    ],
)
def test_monitor_native_failures_are_redacted(
    tmp_path, monkeypatch, capsys, command, stage, failure, code, message
):
    def fail(*args, **kwargs):
        raise failure

    stub(
        monkeypatch,
        command,
        run=fail if stage == "run" else lambda *args, **kwargs: {},
        share=fail if stage == "share" else lambda report: report,
    )
    monkeypatch.setattr(sys, "argv", arguments(command, tmp_path / "watch", tmp_path / "save"))
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == code
    output = capsys.readouterr()
    assert output.out == "" and message in output.err
    assert not any(secret in output.err for secret in ("private", "author", "URL", "token"))
    assert not list(tmp_path.iterdir())
