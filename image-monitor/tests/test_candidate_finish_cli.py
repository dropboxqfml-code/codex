"""Keep completed-candidate verification local, lazy, and explicit."""

import json
import sys
from types import ModuleType

import pytest

from image_monitor.__main__ import main


def install_runtime_stub(monkeypatch, *, run, share=lambda report: report):
    module = ModuleType("image_monitor.candidate_finish_runtime")
    module.run_candidate_finish_trial = run
    module.share_candidate_finish_report = share
    monkeypatch.setitem(sys.modules, module.__name__, module)


def arguments(watch_root, work_root):
    return [
        "image-monitor",
        "candidate-finish",
        "--watch-root",
        str(watch_root),
        "--work-root",
        str(work_root),
    ]


@pytest.mark.parametrize("options", [["--help"], ["candidate-finish", "--help"]])
def test_help_never_imports_finish_native_or_browser_runtime(monkeypatch, capsys, options):
    for module in (
        "candidate_finish_runtime",
        "candidate_finish",
        "candidate_save_runtime",
        "candidate_browser",
        "native_ui",
        "native_probe",
        "native_state",
        "post_worker",
    ):
        monkeypatch.setitem(sys.modules, f"image_monitor.{module}", None)
    monkeypatch.setattr(sys, "argv", ["image-monitor", *options])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 0
    output = capsys.readouterr().out
    assert "candidate-finish" in output
    if options[0] == "candidate-finish":
        for native_option in ("--browser", "--post-url", "--resume-preinput"):
            assert native_option not in output


@pytest.mark.parametrize(
    "options",
    [
        [],
        ["--watch-root", "watch"],
        ["--work-root", "save"],
        ["--watch-root", "watch", "--work-root", "save", "--browser", "chrome"],
        ["--watch-root", "watch", "--work-root", "save", "--post-url", "unused"],
        ["--watch-root", "watch", "--work-root", "save", "--resume-preinput"],
        ["--watch-root", "watch", "--work-root", "save", "--confirm-browser-closed"],
    ],
)
def test_invalid_options_stop_before_import(monkeypatch, options):
    monkeypatch.setitem(sys.modules, "image_monitor.candidate_finish_runtime", None)
    monkeypatch.setattr(sys, "argv", ["image-monitor", "candidate-finish", *options])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2


def test_cli_forwards_only_both_roots_and_shares_only_public_output(tmp_path, monkeypatch, capsys):
    watch, save = tmp_path / "watch 한글 & space", tmp_path / "save 한글 & space"
    calls = []
    private = {
        "status": "candidate_finish_completed",
        "title": "private title",
        "source_url": "https://private.example/image?token=secret",
        "run_directory": str(save),
    }
    public = {"status": "candidate_finish_completed", "files_preserved": True}

    def run(*args, **kwargs):
        calls.append((args, kwargs))
        return private

    def share(report):
        assert report is private
        return public

    install_runtime_stub(monkeypatch, run=run, share=share)
    monkeypatch.setattr(sys, "argv", arguments(watch, save))
    assert main() == 0
    assert calls == [((watch, save), {})]
    output = capsys.readouterr()
    assert json.loads(output.out) == public
    assert output.err == "" and "private" not in output.out
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    ("report", "code"),
    [
        ({"status": "candidate_finish_completed"}, 0),
        ({"status": "candidate_finish_no_pending"}, 0),
        ({"status": "candidate_finish_busy"}, 0),
        ({"status": "candidate_finish_manual_review"}, 2),
        ({"status": "candidate_finish_failed"}, 2),
        ({"status": "unexpected"}, 2),
        ({"status": "candidate_finish_cancelled"}, 130),
        ({"status": "candidate_finish_manual_review", "error_type": "KeyboardInterrupt"}, 130),
    ],
)
def test_status_controls_exit_code(tmp_path, monkeypatch, capsys, report, code):
    install_runtime_stub(monkeypatch, run=lambda *_: report)
    monkeypatch.setattr(sys, "argv", arguments(tmp_path / "watch", tmp_path / "save"))
    assert main() == code
    assert json.loads(capsys.readouterr().out) == report
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("stage", ["run", "share"])
@pytest.mark.parametrize(
    ("failure", "code", "message"),
    [
        (RuntimeError("private title author source URL token"), 2, "RuntimeError"),
        (type("NativeUIError", (RuntimeError,), {})("private file path"), 2, "NativeUIError"),
        (KeyboardInterrupt("private source URL token"), 130, "cancelled"),
    ],
)
def test_external_failure_messages_stay_private(
    tmp_path, monkeypatch, capsys, stage, failure, code, message
):
    def fail(*_):
        raise failure

    install_runtime_stub(
        monkeypatch,
        run=fail if stage == "run" else lambda *_: {"status": "candidate_finish_completed"},
        share=fail if stage == "share" else lambda report: report,
    )
    monkeypatch.setattr(sys, "argv", arguments(tmp_path / "watch", tmp_path / "save"))
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == code
    output = capsys.readouterr()
    assert output.out == "" and message in output.err
    assert not any(secret in output.err for secret in ("private", "author", "URL", "token"))
    assert not list(tmp_path.iterdir())


def test_missing_runtime_import_does_not_create_state(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "image_monitor.candidate_finish_runtime", None)
    monkeypatch.setattr(sys, "argv", arguments(tmp_path / "watch", tmp_path / "save"))
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    output = capsys.readouterr()
    assert output.out == "" and "ModuleNotFoundError" in output.err
    assert not list(tmp_path.iterdir())
