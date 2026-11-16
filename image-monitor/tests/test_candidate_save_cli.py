"""Keep the candidate native-save CLI lazy and its shared output bounded."""

import json
import sys
from types import ModuleType

import pytest

from image_monitor.__main__ import main


def install_runtime_stub(monkeypatch, *, run, share=lambda report: report):
    module = ModuleType("image_monitor.candidate_save_runtime")
    module.run_candidate_save_trial = run
    module.share_candidate_save_report = share
    monkeypatch.setitem(sys.modules, module.__name__, module)


def arguments(watch_root, work_root):
    return [
        "image-monitor",
        "candidate-save-test",
        "--watch-root",
        str(watch_root),
        "--work-root",
        str(work_root),
    ]


@pytest.mark.parametrize("options", [["--help"], ["candidate-save-test", "--help"]])
def test_help_does_not_import_runtime_native_browser_or_inspection(monkeypatch, capsys, options):
    for module in (
        "candidate_save_runtime",
        "candidate_save_policy",
        "candidate_save_selection",
        "candidate_browser",
        "candidate_runtime",
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
    assert "candidate-save-test" in output
    assert "--post-url" not in output and "--resume-preinput" not in output


@pytest.mark.parametrize(
    "options",
    [
        [],
        ["--watch-root", "watch"],
        ["--work-root", "save"],
        ["--watch-root", "watch", "--work-root", "save", "--browser", "edge"],
        ["--watch-root", "watch", "--work-root", "save", "--post-url", "unused"],
        ["--watch-root", "watch", "--work-root", "save", "--resume-preinput"],
        ["--watch-root", "watch", "--work-root", "save", "--max-images", "3"],
    ],
)
def test_invalid_options_fail_before_runtime_import(monkeypatch, options):
    monkeypatch.setitem(sys.modules, "image_monitor.candidate_save_runtime", None)
    monkeypatch.setattr(sys, "argv", ["image-monitor", "candidate-save-test", *options])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2


@pytest.mark.parametrize("explicit_chrome", [False, True])
def test_runtime_receives_both_distinct_roots_and_shares_only_public_output(
    tmp_path, monkeypatch, capsys, explicit_chrome
):
    watch = tmp_path / "watch 한글 & space"
    save = tmp_path / "save 한글 & space"
    calls = []
    private = {
        "status": "candidate_save_completed",
        "source_url": "https://private.example/image?token=private",
        "title": "private title",
        "output_directory": str(save),
    }
    public = {"status": "candidate_save_completed", "job_counts": {"completed": 2}}

    def run(*args, **kwargs):
        calls.append((args, kwargs))
        return private

    def share(report):
        assert report is private
        return public

    install_runtime_stub(monkeypatch, run=run, share=share)
    options = arguments(watch, save)
    if explicit_chrome:
        options += ["--browser", "chrome"]
    monkeypatch.setattr(sys, "argv", options)
    assert main() == 0
    assert calls == [((watch, save, "chrome"), {})]
    output = capsys.readouterr()
    assert json.loads(output.out) == public
    assert output.err == "" and "private" not in output.out
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    ("report", "code"),
    [
        ({"status": "candidate_save_completed"}, 0),
        ({"status": "candidate_save_waiting"}, 0),
        ({"status": "candidate_save_busy"}, 0),
        ({"status": "candidate_save_no_candidate"}, 0),
        ({"status": "candidate_save_failed"}, 2),
        ({"status": "candidate_save_partial"}, 2),
        ({"status": "manual_review"}, 2),
        ({"status": "unexpected"}, 2),
        ({"status": "candidate_save_cancelled"}, 130),
        ({"status": "manual_review", "error_type": "KeyboardInterrupt"}, 130),
    ],
)
def test_runtime_status_controls_exit_code(tmp_path, monkeypatch, capsys, report, code):
    install_runtime_stub(monkeypatch, run=lambda *_args: report)
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
def test_external_failures_are_redacted(
    tmp_path, monkeypatch, capsys, stage, failure, code, message
):
    def fail(*_):
        raise failure

    install_runtime_stub(
        monkeypatch,
        run=fail if stage == "run" else lambda *_: {"status": "candidate_save_completed"},
        share=fail if stage == "share" else lambda report: report,
    )
    monkeypatch.setattr(sys, "argv", arguments(tmp_path / "watch", tmp_path / "save"))
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == code
    output = capsys.readouterr()
    assert output.out == ""
    assert message in output.err
    assert not any(secret in output.err for secret in ("private", "author", "URL", "token"))
    assert not list(tmp_path.iterdir())


def test_missing_runtime_import_is_redacted(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "image_monitor.candidate_save_runtime", None)
    monkeypatch.setattr(sys, "argv", arguments(tmp_path / "watch", tmp_path / "save"))
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    output = capsys.readouterr()
    assert output.out == "" and "ModuleNotFoundError" in output.err
    assert not list(tmp_path.iterdir())
