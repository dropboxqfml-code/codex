"""Test the finite candidate inspection CLI with inert lazy imports; never launch a browser."""

import json
import sys
from types import ModuleType

import pytest

from image_monitor.__main__ import main


def install_runtime_stub(monkeypatch, *, run, share=lambda output: output):
    module = ModuleType("image_monitor.candidate_runtime")
    module.run_candidate_trial = run
    module.share_candidate_report = share
    monkeypatch.setitem(sys.modules, module.__name__, module)


@pytest.mark.parametrize("arguments", [["--help"], ["candidate-test", "--help"]])
def test_candidate_trial_help_imports_no_runtime_browser_or_native_code(
    monkeypatch, capsys, arguments
):
    for module in (
        "candidate_runtime",
        "watch_commands",
        "candidate_browser",
        "candidate_store",
        "candidate_policy",
        "list_inspection",
        "native_ui",
        "native_probe",
        "post_worker",
    ):
        monkeypatch.setitem(sys.modules, f"image_monitor.{module}", None)
    monkeypatch.setattr(sys, "argv", ["image-monitor", *arguments])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 0
    output = capsys.readouterr().out
    assert "candidate-test" in output
    assert "--max-candidates" not in output and "--interval-seconds" not in output


@pytest.mark.parametrize(
    "arguments",
    [
        ["candidate-test"],
        ["candidate-test", "--work-root", "unused", "--browser", "firefox"],
        ["candidate-test", "--work-root", "unused", "--max-candidates", "1"],
        ["candidate-test", "--work-root", "unused", "--interval-seconds", "0"],
        ["candidate-test", "--work-root", "unused", "--resume-preinput"],
    ],
)
def test_candidate_trial_rejects_invalid_arguments_before_runtime_import(monkeypatch, arguments):
    monkeypatch.setitem(sys.modules, "image_monitor.candidate_runtime", None)
    monkeypatch.setattr(sys, "argv", ["image-monitor", *arguments])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2


@pytest.mark.parametrize("browser", [None, "chrome", "edge"])
def test_candidate_trial_uses_runtime_timing_defaults_and_shares_only_public_output(
    tmp_path, monkeypatch, capsys, browser
):
    calls = []
    private = {
        "status": "candidate_test_completed",
        "raw_title": "private title",
        "author": "private author",
        "cursor": "private cursor",
    }
    public = {
        "status": "candidate_test_completed",
        "candidates_completed": 2,
        "images_saved": False,
    }

    def run(*args, **kwargs):
        calls.append((args, kwargs))
        return private

    def share(report):
        assert report is private
        return public

    install_runtime_stub(monkeypatch, run=run, share=share)
    for module in ("native_probe", "native_state", "native_ui", "post_worker"):
        monkeypatch.setitem(sys.modules, f"image_monitor.{module}", None)
    arguments = ["image-monitor", "candidate-test", "--work-root", str(tmp_path)]
    if browser:
        arguments.extend(["--browser", browser])
    monkeypatch.setattr(sys, "argv", arguments)
    assert main() == 0
    assert calls == [((tmp_path, browser or "chrome"), {})]
    output = capsys.readouterr()
    assert json.loads(output.out) == public
    assert output.err == "" and "private" not in output.out
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    ("report", "expected_code"),
    [
        ({"status": "candidate_test_completed"}, 0),
        ({"status": "candidate_waiting", "browser_started": False}, 0),
        ({"status": "candidate_busy", "browser_started": False}, 0),
        ({"status": "candidate_no_pending"}, 0),
        ({"status": "candidate_no_baseline"}, 0),
        ({"status": "candidate_test_partial"}, 2),
        ({"status": "candidate_test_failed"}, 2),
        ({"status": "candidate_test_cancelled"}, 130),
        ({"status": "candidate_test_failed", "error_type": "KeyboardInterrupt"}, 130),
        ({"status": "unexpected"}, 2),
    ],
)
def test_candidate_trial_forwards_report_status_to_exit_code(
    tmp_path, monkeypatch, capsys, report, expected_code
):
    install_runtime_stub(monkeypatch, run=lambda *_args: report)
    monkeypatch.setattr(
        sys, "argv", ["image-monitor", "candidate-test", "--work-root", str(tmp_path)]
    )
    assert main() == expected_code
    assert json.loads(capsys.readouterr().out) == report
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("stage", ["run", "share"])
@pytest.mark.parametrize(
    ("failure", "expected_code", "expected_message"),
    [
        (RuntimeError("private URL token title author cursor"), 2, "RuntimeError"),
        (type("NativeUIError", (RuntimeError,), {})("private native details"), 2, "NativeUIError"),
        (KeyboardInterrupt("private URL token title author cursor"), 130, "cancelled"),
    ],
)
def test_candidate_trial_external_errors_are_redacted(
    tmp_path, monkeypatch, capsys, stage, failure, expected_code, expected_message
):
    def fail(*_args):
        raise failure

    install_runtime_stub(
        monkeypatch,
        run=fail if stage == "run" else lambda *_args: {"status": "candidate_test_completed"},
        share=fail if stage == "share" else lambda output: output,
    )
    monkeypatch.setattr(
        sys, "argv", ["image-monitor", "candidate-test", "--work-root", str(tmp_path)]
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == expected_code
    output = capsys.readouterr()
    assert output.out == ""
    assert expected_message in output.err
    assert not any(word in output.err for word in ("private", "token", "author", "cursor"))
    assert not list(tmp_path.iterdir())


def test_candidate_trial_runtime_import_error_is_redacted(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "image_monitor.candidate_runtime", None)
    monkeypatch.setattr(
        sys, "argv", ["image-monitor", "candidate-test", "--work-root", str(tmp_path)]
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "ModuleNotFoundError" in output.err
    assert not list(tmp_path.iterdir())
