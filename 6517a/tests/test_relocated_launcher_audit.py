"""The Windows audit invokes the real CMD probe and rejects incomplete launch evidence."""

import importlib.util
import json
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "launcher_audit", PROJECT / "scripts/verify_relocated_bundle.py"
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def evidence(**changes):
    result = {
        "status": "passed",
        "hardware_verified": False,
        "automatic_output_enable": False,
        "start_gui_cmd_verified": True,
        "visible_main_window_verified": True,
        "gui_normal_close_verified": True,
        "gui_exit_code": 0,
    }
    result.update(changes)
    return result


def fake_child(monkeypatch, root, report):
    calls = []

    def run(directory, arguments, **options):
        calls.append((directory, arguments, options))
        target = root / "diagnostics/cmd-launcher-verification.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report), encoding="utf-8")

    monkeypatch.setattr(audit, "run_child", run)
    return calls


def test_launcher_probe_uses_real_cmd_script_and_preserves_korean_space_path(tmp_path, monkeypatch):
    root = tmp_path / "공백 포함 bundle"
    calls = fake_child(monkeypatch, root, evidence())
    assert audit.verify_cmd_launcher(root) == evidence()
    directory, args, options = calls[0]
    assert directory == root and options["timeout"] == 180
    assert args[0] == "powershell.exe"
    assert args[args.index("-Root") + 1] == root
    assert Path(args[args.index("-File") + 1]) == PROJECT / "scripts/verify_gui_launcher.ps1"
    script = (PROJECT / "scripts/verify_gui_launcher.ps1").read_bytes()
    assert script.startswith(b"\xef\xbb\xbf")  # Windows PowerShell 5.1 decodes Hangul correctly.
    decoded = script.decode("utf-8-sig")
    assert "& $env:ComSpec /d /c Start-GUI.cmd" in decoded
    assert "$baseline -contains $process.Id" in decoded
    assert "CloseMainWindow()" in decoded and "$main.ExitCode -ne 0" in decoded


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "failed"},
        {"hardware_verified": True},
        {"automatic_output_enable": True},
        {"start_gui_cmd_verified": False},
        {"visible_main_window_verified": False},
        {"gui_normal_close_verified": False},
        {"gui_exit_code": 1},
        {"visible_main_window_verified": None},
    ],
)
def test_native_audit_rejects_unconfirmed_or_failed_gui_launch(tmp_path, monkeypatch, changes):
    fake_child(monkeypatch, tmp_path, evidence(**changes))
    with pytest.raises(RuntimeError, match="CMD/GUI launch was not verified"):
        audit.verify_cmd_launcher(tmp_path)
