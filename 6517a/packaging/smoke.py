"""Native Windows CI smoke test: synthetic-data CLI + offscreen SIMULATION GUI only."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import os
import runpy
import shutil
import sys
import tempfile
from itertools import zip_longest
from pathlib import Path


def analysis_export_smoke(directory: Path) -> int:
    """Check delivered numeric text against every saved CSV row, including excluded data."""
    header = ["Time (s)", "Resistance (Ohm)", "Voltage (V)", "Current (A)"]
    count = 0
    with (
        (directory / "readings.csv").open(encoding="utf-8", newline="") as source,
        (directory / "analysis.txt").open(encoding="utf-8", newline="") as exported,
    ):
        reader = csv.DictReader(source)
        data = csv.reader(exported, delimiter="\t")
        if next(data, None) != header:
            raise RuntimeError("Analysis text must have exactly the four quantity/unit headers")
        for count, (row, values) in enumerate(zip_longest(reader, data), start=1):
            if row is None or values is None or len(values) != 4:
                raise RuntimeError("Analysis text must have one four-column row per CSV reading")
            resistance = row.get("native_r_ohm")
            if resistance in (None, ""):
                resistance = row.get("resistance_apparent_ohm")
            expected = (
                row.get("elapsed_s"),
                resistance,
                row.get("voltage_programmed_readback_V"),
                row.get("current_raw_A"),
            )
            for original, cell in zip(expected, values, strict=True):
                actual = float(cell)
                if original in (None, ""):
                    matches = math.isnan(actual)
                else:
                    value = float(original)
                    matches = math.isfinite(value) and actual == value
                if not matches:
                    raise RuntimeError(f"Analysis text differs from CSV at reading {count}")
    if count == 0:
        raise RuntimeError("Analysis export smoke requires at least one saved reading")
    return count


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
        # Windows TEMP may use an 8.3 alias; the installer returns canonical paths.
        trial = Path(temporary).resolve()
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-optional-installer", action="store_true")
    args = parser.parse_args(argv)
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
    default_readings = list((root / "native-smoke-results").glob("*/readings.csv"))
    if len(default_readings) != 1:
        raise RuntimeError("Default simulation did not create exactly one run")
    analysis_export_smoke(default_readings[0].parent)
    reference_results = root / "native-smoke-results/reference-1gohm"
    status = cli_main(
        [
            "simulate",
            "--config",
            str(root / "app/examples/simulation_1gohm_config.json"),
            "--fast",
            "--output",
            str(reference_results),
        ]
    )
    if status:
        return status
    metadata_files = list(reference_results.glob("*/metadata.json"))
    if len(metadata_files) != 1:
        raise RuntimeError("Reference simulation did not create exactly one run")
    reference = json.loads(metadata_files[0].read_text(encoding="utf-8"))
    if (
        reference.get("simulation") is not True
        or reference.get("simulation_truth", {}).get("resistance_ohm") != 1e9
    ):
        raise RuntimeError("Bundled 1 Gohm simulation used the wrong reference model")
    analysis_export_smoke(metadata_files[0].parent)
    if not args.skip_optional_installer:
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
                "reference_1gohm_simulation_verified": True,
                "analysis_text_export_verified": True,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
