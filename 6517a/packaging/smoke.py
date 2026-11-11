"""Native Windows CI smoke test: synthetic-data CLI + offscreen SIMULATION GUI only."""

from __future__ import annotations

import importlib.util
import json
import os
import runpy
import shutil
import sys
import tempfile
from pathlib import Path


def optional_installer_smoke(root: Path, installer=None):
    """Exercise bundled pip outside the release payload without importing a GPIB backend."""
    if installer is None:
        helper = root / "tools/install_ni_only.py"
        spec = importlib.util.spec_from_file_location("_6517a_optional_install_smoke", helper)
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
    optional_before = {
        name
        for name in sys.modules
        if name == "gpib_ctypes"
        or name.startswith("gpib_ctypes.")
        or name == "pyvisa_py"
        or name.startswith("pyvisa_py.")
    }
    with tempfile.TemporaryDirectory(prefix="6517a-ni-extension-smoke-") as temporary:
        trial = Path(temporary)
        if trial.resolve().is_relative_to(root.resolve()):
            raise RuntimeError("Optional installation smoke must stay outside the bundle")
        (trial / "app").mkdir()
        shutil.copy2(root / "app/ni-only-requirements.txt", trial / "app/ni-only-requirements.txt")
        extension = installer.install(trial)
        if installer.installed_extension(trial) != extension:
            raise RuntimeError("Optional installation completion manifest was not verified")
        versions = installer.inspect_payload(extension)
    optional_after = {
        name
        for name in sys.modules
        if name == "gpib_ctypes"
        or name.startswith("gpib_ctypes.")
        or name == "pyvisa_py"
        or name.startswith("pyvisa_py.")
    }
    if optional_after != optional_before:
        raise RuntimeError("Optional installer smoke must not import a GPIB backend")
    report = dict(
        optional_install_smoke="passed",
        versions=versions,
        temporary_extension_removed=not trial.exists(),
        driver_IO=False,
        optional_driver_imported=False,
        hardware_verified=False,
    )
    if not report["temporary_extension_removed"]:
        raise RuntimeError("Optional installation smoke files were not cleaned up")
    print(json.dumps(report))
    return report


def main() -> int:
    if sys.platform != "win32":
        raise RuntimeError("Native smoke test must run on Windows")
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    sys.path.insert(0, str(root / "app/src"))
    launch = runpy.run_path(str(root / "tools/launch.py"), run_name="bundle_launch_support")
    launch["configure_qt_environment"](root)
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from keithley6517a.cli import main as cli_main

    status = cli_main(
        [
            "simulate",
            "--config",
            str(root / "app/examples/simulation_config.json"),
            "--fast",
            "--output",
            str(root / "native-smoke-results"),
        ]
    )
    if status:
        return status
    optional_installer_smoke(root)
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from keithley6517a.ui.main_window import MainWindow

    app = QApplication([])
    window = MainWindow()
    if not window.config_from_controls().simulation or window.worker.runner is not None:
        raise RuntimeError("GUI startup must be disconnected and in SIMULATION")
    window.show()
    QTimer.singleShot(100, window.close)
    QTimer.singleShot(10000, lambda: app.exit(3))
    status = app.exec()
    if status or not window._closed:
        raise RuntimeError("GUI did not close its worker normally")
    print(
        json.dumps(
            {
                "status": "passed",
                "scope": "native Windows synthetic CLI and GUI",
                "hardware_verified": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
