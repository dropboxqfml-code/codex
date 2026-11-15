"""Exercise discovery CLI boundaries with inert, lazily imported command stubs."""

import json
import sys
from types import ModuleType

import pytest

from image_monitor.__main__ import main


def install_command_stub(monkeypatch, module_name, **functions):
    module = ModuleType(module_name)
    for name, function in functions.items():
        setattr(module, name, function)
    monkeypatch.setitem(sys.modules, module_name, module)


def test_discovery_help_does_not_import_browser_or_watch_commands(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "image_monitor.list_inspection", None)
    monkeypatch.setitem(sys.modules, "image_monitor.watch_commands", None)
    monkeypatch.setattr(sys, "argv", ["image-monitor", "--help"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 0
    output = capsys.readouterr().out
    assert "list-inspect" in output and "watch-demo" in output


@pytest.mark.parametrize("browser", [None, "edge"])
@pytest.mark.parametrize("list_url", [None, "https://example.invalid/list?token=private"])
def test_list_inspection_forwards_options_and_shares_only_public_report(
    tmp_path, monkeypatch, capsys, browser, list_url
):
    calls = []
    private_report = {"status": "inspection_completed", "url": "private-url-value"}
    public_report = {"status": "inspection_completed", "read_only": True}

    def run(*args, **kwargs):
        calls.append((args, kwargs))
        return private_report

    def share(report):
        assert report is private_report
        return public_report

    install_command_stub(
        monkeypatch,
        "image_monitor.list_inspection",
        run_list_inspection=run,
        share_report=share,
    )
    arguments = ["image-monitor", "list-inspect", "--work-root", str(tmp_path)]
    if browser:
        arguments.extend(["--browser", browser])
    if list_url:
        arguments.extend(["--list-url", list_url])
    monkeypatch.setattr(sys, "argv", arguments)
    assert main() == 0
    assert calls == [((tmp_path, browser or "chrome"), {"url": list_url} if list_url else {})]
    assert json.loads(capsys.readouterr().out) == public_report
    assert not list(tmp_path.iterdir())


def test_list_inspection_failure_report_returns_failure_status(tmp_path, monkeypatch, capsys):
    report = {"status": "inspection_failed", "read_only": True}
    install_command_stub(
        monkeypatch,
        "image_monitor.list_inspection",
        run_list_inspection=lambda *_args, **_kwargs: report,
        share_report=lambda output: output,
    )
    monkeypatch.setattr(
        sys, "argv", ["image-monitor", "list-inspect", "--work-root", str(tmp_path)]
    )
    assert main() == 2
    assert json.loads(capsys.readouterr().out) == report


@pytest.mark.parametrize(
    ("failure", "expected_code", "expected_message"),
    [
        (RuntimeError("private URL token author"), 2, "RuntimeError"),
        (KeyboardInterrupt("private URL token author"), 130, "cancelled"),
    ],
)
def test_list_inspection_external_errors_are_redacted(
    tmp_path, monkeypatch, capsys, failure, expected_code, expected_message
):
    def run(*_args, **_kwargs):
        raise failure

    install_command_stub(
        monkeypatch,
        "image_monitor.list_inspection",
        run_list_inspection=run,
        share_report=lambda output: output,
    )
    monkeypatch.setattr(
        sys, "argv", ["image-monitor", "list-inspect", "--work-root", str(tmp_path)]
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == expected_code
    output = capsys.readouterr()
    assert output.out == ""
    assert expected_message in output.err
    assert "private" not in output.err and "token" not in output.err
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "arguments",
    [
        ["list-inspect"],
        ["list-inspect", "--work-root", "unused", "--browser", "firefox"],
        ["watch-demo"],
    ],
)
def test_discovery_required_arguments_are_validated_before_import(monkeypatch, arguments):
    monkeypatch.setitem(sys.modules, "image_monitor.list_inspection", None)
    monkeypatch.setitem(sys.modules, "image_monitor.watch_commands", None)
    monkeypatch.setattr(sys, "argv", ["image-monitor", *arguments])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2


def test_watch_demo_dispatches_only_to_local_synthetic_command(tmp_path, monkeypatch, capsys):
    database = tmp_path / "synthetic.sqlite"
    calls = []

    def demo(path):
        calls.append(path)
        return {"synthetic_only": True, "browser_started": False, "files_downloaded": 0}

    install_command_stub(monkeypatch, "image_monitor.watch_commands", watch_demo=demo)
    monkeypatch.setattr(sys, "argv", ["image-monitor", "watch-demo", "--db", str(database)])
    assert main() == 0
    assert calls == [database]
    assert json.loads(capsys.readouterr().out) == {
        "synthetic_only": True,
        "browser_started": False,
        "files_downloaded": 0,
    }
    assert not database.exists()


@pytest.mark.parametrize(
    ("failure", "expected_code", "expected_message"),
    [
        (OSError("private database details"), 2, "OSError"),
        (KeyboardInterrupt("private database details"), 130, "cancelled"),
    ],
)
def test_watch_demo_external_errors_are_redacted(
    tmp_path, monkeypatch, capsys, failure, expected_code, expected_message
):
    def demo(_database):
        raise failure

    install_command_stub(monkeypatch, "image_monitor.watch_commands", watch_demo=demo)
    monkeypatch.setattr(
        sys, "argv", ["image-monitor", "watch-demo", "--db", str(tmp_path / "synthetic.sqlite")]
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == expected_code
    output = capsys.readouterr()
    assert output.out == ""
    assert expected_message in output.err and "private" not in output.err
    assert not list(tmp_path.iterdir())
