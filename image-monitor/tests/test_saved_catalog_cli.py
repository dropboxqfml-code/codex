"""Pass the optional offline preview root without changing legacy monitor calls."""

import json
import sys

import pytest
from test_monitor_cli import install_app_stub

from image_monitor.__main__ import main


def options(watch_root, save_root):
    return [
        "image-monitor",
        "monitor",
        "--work-root",
        str(watch_root),
        "--save-root",
        str(save_root),
    ]


def test_optional_preview_root_is_forwarded_as_a_path_and_shared_output_stays_private(
    tmp_path, monkeypatch, capsys
):
    watch = tmp_path / "watch 한글 & space"
    save = tmp_path / "saved 한글 & space"
    calls = []
    private = {"status": "monitor_closed", "save_root": str(save), "preview_id": "private-id"}
    public = {"status": "monitor_closed", "saved_files_verified": 1}

    def run(*args, **kwargs):
        calls.append((args, kwargs))
        return private

    def share(report):
        assert report is private
        return public

    install_app_stub(monkeypatch, run=run, share=share)
    monkeypatch.setattr(sys, "argv", options(watch, save))
    assert main() == 0
    assert calls == [((watch,), {"save_root": save})]
    output = capsys.readouterr()
    assert json.loads(output.out) == public
    assert output.err == ""
    assert str(save) not in output.out and "private" not in output.out
    assert not list(tmp_path.iterdir())


def test_preview_help_is_lazy_and_does_not_import_files_native_or_browser_code(monkeypatch, capsys):
    for name in (
        "monitor_app",
        "monitor_controller",
        "saved_catalog",
        "candidate_finish",
        "candidate_save_selection",
        "native_ui",
        "post_worker",
    ):
        monkeypatch.setitem(sys.modules, f"image_monitor.{name}", None)
    monkeypatch.setattr(sys, "argv", ["image-monitor", "monitor", "--help"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 0
    help_text = capsys.readouterr().out
    assert "--save-root" in help_text
    assert "--batch-root" in help_text
    assert "existing monitor-saved images" in help_text
    for unsupported in ("--post-url", "--start", "--resume-preinput", "--recover-closed"):
        assert unsupported not in help_text


@pytest.mark.parametrize(
    "arguments",
    [
        ["monitor", "--work-root", "watch", "--save-root"],
        ["monitor", "--save-root", "save"],
        ["monitor", "--work-root", "watch", "--save-root", "save", "--start"],
        ["monitor", "--work-root", "watch", "--batch-root"],
        ["monitor", "--work-root", "watch", "--save-root", "save", "--post-url", "foreign"],
        ["monitor-finish", "--watch-root", "watch", "--work-root", "save", "--save-root", "extra"],
        ["candidate-test", "--work-root", "watch", "--save-root", "extra"],
    ],
)
def test_preview_option_does_not_enable_extra_actions_or_change_other_commands(
    tmp_path, monkeypatch, arguments
):
    monkeypatch.setitem(sys.modules, "image_monitor.monitor_app", None)
    monkeypatch.setitem(sys.modules, "image_monitor.candidate_finish_runtime", None)
    monkeypatch.setitem(sys.modules, "image_monitor.candidate_runtime", None)
    monkeypatch.setattr(sys, "argv", ["image-monitor", *arguments])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert not list(tmp_path.iterdir())


def test_batch_preview_root_requires_legacy_root_without_opening_application(
    tmp_path, monkeypatch, capsys
):
    install_app_stub(monkeypatch, run=lambda *_a, **_k: pytest.fail("Application started"))
    monkeypatch.setattr(
        sys, "argv", ["image-monitor", "monitor", "--work-root", "watch", "--batch-root", "batch"]
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert "ValueError" in capsys.readouterr().err
    assert not list(tmp_path.iterdir())


def test_batch_preview_roots_forwarded_without_creating_data(tmp_path, monkeypatch, capsys):
    watch, save, batch = (tmp_path / name for name in ("watch", "legacy", "batch"))
    calls = []

    def run(*args, **kwargs):
        calls.append((args, kwargs))
        return {"status": "monitor_closed"}

    install_app_stub(monkeypatch, run=run)
    monkeypatch.setattr(sys, "argv", [*options(watch, save), "--batch-root", str(batch)])
    assert main() == 0
    assert calls == [((watch,), {"save_root": save, "batch_root": batch})]
    assert json.loads(capsys.readouterr().out)["status"] == "monitor_closed"
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "failure,code,expected",
    [
        (OSError("private save root and preview token"), 2, "OSError"),
        (KeyboardInterrupt("private save root"), 130, "cancelled"),
    ],
)
def test_preview_root_does_not_leak_through_exception_messages(
    tmp_path, monkeypatch, capsys, failure, code, expected
):
    def run(*_args, **_kwargs):
        raise failure

    install_app_stub(monkeypatch, run=run)
    monkeypatch.setattr(sys, "argv", options(tmp_path / "watch", tmp_path / "private save"))
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == code
    output = capsys.readouterr()
    assert output.out == "" and expected in output.err
    assert "private" not in output.err and "token" not in output.err
    assert not list(tmp_path.iterdir())
