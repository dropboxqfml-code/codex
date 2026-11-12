"""The portable GUI enters automatic checks; CLI tools keep their explicit behavior."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("startup_launcher", PROJECT / "packaging/launch.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def test_gui_launcher_routes_through_automatic_checks_once(tmp_path, monkeypatch):
    called = []
    module = ModuleType("keithley6517a.ui.startup_checks")
    module.run_gui = lambda root: called.append(root) or 0
    monkeypatch.setitem(launcher.sys.modules, module.__name__, module)
    monkeypatch.setattr(launcher, "bundle_root", lambda: tmp_path)
    monkeypatch.setattr(launcher, "configure_optional_extension", lambda root: None)
    monkeypatch.setattr(launcher, "configure_qt_environment", lambda root: None)
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(PROJECT / "src"))
    assert launcher.main(["gui"]) == 0
    assert called == [tmp_path]


def test_gui_rejects_supplied_settings_before_startup_checks(tmp_path, monkeypatch):
    called = []
    module = ModuleType("keithley6517a.ui.startup_checks")
    module.run_gui = lambda root: called.append(root) or 0
    monkeypatch.setitem(launcher.sys.modules, module.__name__, module)
    monkeypatch.setattr(launcher, "bundle_root", lambda: tmp_path)
    monkeypatch.setattr(launcher, "configure_optional_extension", lambda root: None)
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(PROJECT / "src"))
    with pytest.raises(ValueError, match="no configuration"):
        launcher.main(["gui", "--config", "old-measurement.json"])
    assert not called
