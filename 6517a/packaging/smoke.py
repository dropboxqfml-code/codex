"""Native Windows CI smoke test: synthetic-data CLI + offscreen SIMULATION GUI only."""

from __future__ import annotations

import json
import os
import runpy
import sys
from pathlib import Path


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
