"""Keep the bounded batch commands fixed and lazy at the CLI boundary."""

import json
import sys
from types import ModuleType

import pytest

from image_monitor.__main__ import main

COMMANDS = {
    "monitor-save-batch": (
        "monitor_batch_runtime",
        "run_monitor_batch",
        "share_batch_report",
        "monitor_batch_completed",
    ),
    "monitor-batch-finish": (
        "monitor_batch_finish",
        "run_monitor_batch_finish",
        "share_batch_finish_report",
        "batch_finish_completed",
    ),
}


def arguments(command, watch="watch", legacy="legacy", work="batch"):
    return [
        "image-monitor",
        command,
        "--watch-root",
        str(watch),
        "--legacy-root",
        str(legacy),
        "--work-root",
        str(work),
    ]


def stub(monkeypatch, command, *, run, share=lambda report: report):
    module_name, runner, sharer, _ = COMMANDS[command]
    module = ModuleType(f"image_monitor.{module_name}")
    setattr(module, runner, run)
    setattr(module, sharer, share)
    monkeypatch.setitem(sys.modules, module.__name__, module)


@pytest.mark.parametrize("command", COMMANDS)
def test_batch_help_never_imports_native_runtime_or_ledger(monkeypatch, capsys, command):
    for module in (
        "monitor_batch_runtime",
        "monitor_batch_finish",
        "monitor_save_ledger",
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
    for required in ("--watch-root", "--legacy-root", "--work-root"):
        assert required in output
    for unsupported in ("--browser", "--post-url", "--max-tasks", "--task-id", "--scope"):
        assert unsupported not in output


@pytest.mark.parametrize("command", COMMANDS)
@pytest.mark.parametrize(
    "extra",
    [
        ["--browser", "chrome"],
        ["--browser", "edge"],
        ["--max-tasks", "999"],
        ["--task-id", "foreign"],
        ["--scope", "other watch"],
        ["--post-url", "https://foreign.example"],
        ["--resume-preinput"],
        ["--recover-closed"],
        ["--confirm-browser-closed"],
    ],
)
def test_batch_options_cannot_select_targets_or_bypass_fixed_limits(monkeypatch, command, extra):
    for module, _, _, _ in COMMANDS.values():
        monkeypatch.setitem(sys.modules, f"image_monitor.{module}", None)
    monkeypatch.setattr(sys, "argv", arguments(command) + extra)
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2


@pytest.mark.parametrize("command", COMMANDS)
@pytest.mark.parametrize("missing", ["--watch-root", "--legacy-root", "--work-root"])
def test_batch_commands_require_each_of_three_roots(monkeypatch, command, missing):
    values = arguments(command)
    index = values.index(missing)
    del values[index : index + 2]
    monkeypatch.setattr(sys, "argv", values)
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2


@pytest.mark.parametrize("command", COMMANDS)
def test_batch_entrypoints_pass_only_three_paths_and_share_only_public_report(
    tmp_path, monkeypatch, capsys, command
):
    roots = [
        tmp_path / name
        for name in ("watch 한글 & space", "legacy 한글 & space", "batch 한글 & space")
    ]
    calls = []
    private = {"status": COMMANDS[command][3], "title": "private source", "task_id": "private-id"}
    public = {"status": COMMANDS[command][3], "browser_closed": True}

    def run(*args, **kwargs):
        calls.append((args, kwargs))
        return private

    def share(report):
        assert report is private
        return public

    stub(monkeypatch, command, run=run, share=share)
    monkeypatch.setattr(sys, "argv", arguments(command, *roots))
    assert main() == 0
    assert calls == [(tuple(roots), {})]
    output = capsys.readouterr()
    assert json.loads(output.out) == public and output.err == ""
    assert "private" not in output.out
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    ("command", "status", "code"),
    [
        ("monitor-save-batch", "monitor_batch_completed", 0),
        ("monitor-save-batch", "monitor_batch_waiting", 0),
        ("monitor-save-batch", "monitor_batch_busy", 0),
        ("monitor-save-batch", "monitor_batch_no_candidates", 0),
        ("monitor-save-batch", "monitor_batch_manual_review", 2),
        ("monitor-save-batch", "monitor_batch_failed", 2),
        ("monitor-save-batch", "monitor_batch_cancelled", 130),
        ("monitor-save-batch", "batch_finish_completed", 2),
        ("monitor-batch-finish", "batch_finish_completed", 0),
        ("monitor-batch-finish", "batch_finish_no_pending", 0),
        ("monitor-batch-finish", "batch_finish_busy", 0),
        ("monitor-batch-finish", "batch_finish_manual_review", 2),
        ("monitor-batch-finish", "batch_finish_cancelled", 130),
        ("monitor-batch-finish", "monitor_batch_completed", 2),
        ("monitor-batch-finish", "unknown", 2),
    ],
)
def test_batch_statuses_control_exit_without_accepting_another_mode(
    monkeypatch, capsys, command, status, code
):
    report = {"status": status}
    stub(monkeypatch, command, run=lambda *_args: report)
    monkeypatch.setattr(sys, "argv", arguments(command))
    assert main() == code
    assert json.loads(capsys.readouterr().out) == report


@pytest.mark.parametrize("command", COMMANDS)
def test_keyboard_interrupt_field_overrides_a_success_status(monkeypatch, capsys, command):
    report = {"status": COMMANDS[command][3], "error_type": "KeyboardInterrupt"}
    stub(monkeypatch, command, run=lambda *_args: report)
    monkeypatch.setattr(sys, "argv", arguments(command))
    assert main() == 130
    assert json.loads(capsys.readouterr().out) == report


@pytest.mark.parametrize("command", COMMANDS)
@pytest.mark.parametrize("stage", ["run", "share"])
@pytest.mark.parametrize(
    ("failure", "code", "message"),
    [
        (OSError("private source URL and path"), 2, "OSError"),
        (KeyboardInterrupt("private"), 130, "cancelled"),
    ],
)
def test_batch_external_error_text_is_redacted(
    monkeypatch, capsys, command, stage, failure, code, message
):
    def fail(*_args):
        raise failure

    stub(
        monkeypatch,
        command,
        run=fail if stage == "run" else lambda *_args: {},
        share=fail if stage == "share" else lambda report: report,
    )
    monkeypatch.setattr(sys, "argv", arguments(command))
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == code
    output = capsys.readouterr()
    assert output.out == "" and message in output.err
    assert not any(secret in output.err for secret in ("private", "source URL", "path"))
