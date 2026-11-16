"""Keep the local monitor entry point lazy and its result output bounded by sharing."""

import json
import sys
from types import ModuleType

import pytest

from image_monitor.__main__ import main


def install_app_stub(monkeypatch, *, run, share=lambda report: report):
    module = ModuleType("image_monitor.monitor_app")
    module.run_monitor_app = run
    module.share_monitor_report = share
    monkeypatch.setitem(sys.modules, module.__name__, module)


@pytest.mark.parametrize("options", [["--help"], ["monitor", "--help"]])
def test_monitor_help_never_imports_runtime_or_native_code(monkeypatch, capsys, options):
    for module in (
        "monitor_app",
        "monitor_controller",
        "watch_runtime",
        "watch_browser",
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
    assert "monitor" in output
    if options[0] == "monitor":
        for unsupported in ("--browser", "--post-url", "--resume-preinput", "--interval-seconds"):
            assert unsupported not in output


@pytest.mark.parametrize(
    "options",
    [
        [],
        ["--work-root", "watch", "--browser", "chrome"],
        ["--work-root", "watch", "--post-url", "unused"],
        ["--work-root", "watch", "--resume-preinput"],
        ["--work-root", "watch", "--confirm-browser-closed"],
        ["--work-root", "watch", "--interval-seconds", "1"],
        ["--work-root", "watch", "--start"],
    ],
)
def test_invalid_monitor_options_stop_before_runtime_import(monkeypatch, options):
    monkeypatch.setitem(sys.modules, "image_monitor.monitor_app", None)
    monkeypatch.setattr(sys, "argv", ["image-monitor", "monitor", *options])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2


def test_monitor_forwards_only_work_root_and_shares_only_public_output(
    tmp_path, monkeypatch, capsys
):
    root = tmp_path / "watch 한글 & space"
    calls = []
    private = {
        "status": "monitor_closed",
        "ui_url": "http://127.0.0.1:12345/private-capability/",
        "candidate_title": "private title",
        "work_root": str(root),
    }
    public = {"status": "monitor_closed", "completed_cycles": 2, "new_candidates": 6}

    def run(*args, **kwargs):
        calls.append((args, kwargs))
        return private

    def share(report):
        assert report is private
        return public

    install_app_stub(monkeypatch, run=run, share=share)
    monkeypatch.setattr(sys, "argv", ["image-monitor", "monitor", "--work-root", str(root)])
    assert main() == 0
    assert calls == [((root,), {})]
    output = capsys.readouterr()
    assert json.loads(output.out) == public
    assert output.err == ""
    assert "private" not in output.out and str(root) not in output.out
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    ("report", "code"),
    [
        ({"status": "monitor_closed"}, 0),
        ({"status": "monitor_busy"}, 0),
        ({"status": "monitor_failed"}, 2),
        ({"status": "monitor_manual_review"}, 2),
        ({"status": "unexpected"}, 2),
        ({"status": "monitor_cancelled"}, 130),
        ({"status": "monitor_failed", "error_type": "KeyboardInterrupt"}, 130),
    ],
)
def test_monitor_status_controls_exit_code(tmp_path, monkeypatch, capsys, report, code):
    install_app_stub(monkeypatch, run=lambda *_: report)
    monkeypatch.setattr(sys, "argv", ["image-monitor", "monitor", "--work-root", str(tmp_path)])
    assert main() == code
    assert json.loads(capsys.readouterr().out) == report
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("stage", ["run", "share"])
@pytest.mark.parametrize(
    ("failure", "code", "message"),
    [
        (RuntimeError("private title token http://127.0.0.1/private/"), 2, "RuntimeError"),
        (type("NativeUIError", (RuntimeError,), {})("private profile path"), 2, "NativeUIError"),
        (KeyboardInterrupt("private title URL token"), 130, "cancelled"),
    ],
)
def test_monitor_external_failure_text_is_redacted(
    tmp_path, monkeypatch, capsys, stage, failure, code, message
):
    def fail(*_):
        raise failure

    install_app_stub(
        monkeypatch,
        run=fail if stage == "run" else lambda *_: {"status": "monitor_closed"},
        share=fail if stage == "share" else lambda report: report,
    )
    monkeypatch.setattr(sys, "argv", ["image-monitor", "monitor", "--work-root", str(tmp_path)])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == code
    output = capsys.readouterr()
    assert output.out == "" and message in output.err
    assert not any(secret in output.err for secret in ("private", "token", "127.0.0.1", "profile"))
    assert not list(tmp_path.iterdir())


def test_missing_monitor_runtime_import_creates_no_state(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "image_monitor.monitor_app", None)
    monkeypatch.setattr(sys, "argv", ["image-monitor", "monitor", "--work-root", str(tmp_path)])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    output = capsys.readouterr()
    assert output.out == "" and "ModuleNotFoundError" in output.err
    assert not list(tmp_path.iterdir())
