"""Native Windows CI smoke test: synthetic-data CLI + offscreen SIMULATION GUI only."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
import runpy
import shutil
import sys
import tempfile
import zipfile
from dataclasses import replace
from itertools import zip_longest
from pathlib import Path
from statistics import mean, stdev


def _recorded_resistivity_schema(directory: Path, rows: list[dict]) -> bool:
    """Infer the expected schema independently of the application's export helpers."""
    for row in rows:
        value = row.get("resistivity_ohm_m")
        if value not in (None, "") and math.isfinite(float(value)):
            return True

    def read_object(name):
        path = directory / name
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}

    metadata = read_object("metadata.json")
    declared = metadata.get("analysis_text", {}).get("include_resistivity")
    if isinstance(declared, bool):
        return declared

    def positive(value):
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and value > 0
        )

    snapshot = read_object("config.json")
    settings = snapshot.get("settings", snapshot) if snapshot else metadata.get("settings", {})
    names = ("sample_length_mm", "sample_width_mm", "sample_depth_mm")
    dimensions = [settings.get(name) for name in names]
    axis = settings.get("current_path_axis")
    if any(value is not None for value in dimensions) or axis is not None:
        return all(positive(value) for value in dimensions) and axis in {"L", "W", "D"}
    area, length = settings.get("area_m2"), settings.get("thickness_m")
    if area is not None or length is not None:
        return positive(area) and positive(length)
    geometry = metadata.get("sample_geometry", {})
    return (
        geometry.get("complete") is not False
        and positive(geometry.get("area_m2"))
        and positive(geometry.get("current_path_length_m"))
    )


def _analysis_header(include_resistivity):
    header = ["Time (s)", "Resistance (Ohm)"]
    if include_resistivity:
        header.append("Resistivity (Ohm m)")
    return header + ["Voltage (V)", "Current (A)"]


def _analysis_values(row, include_resistivity):
    resistance = row.get("native_r_ohm")
    if resistance in (None, ""):
        resistance = row.get("resistance_apparent_ohm")
    values = [row.get("elapsed_s"), resistance]
    if include_resistivity:
        values.append(row.get("resistivity_ohm_m"))
    return values + [row.get("voltage_programmed_readback_V"), row.get("current_raw_A")]


def analysis_export_smoke(directory: Path) -> int:
    """Check delivered numeric text against every saved CSV row, including excluded data."""
    with (directory / "readings.csv").open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    include_resistivity = _recorded_resistivity_schema(directory, rows)
    header = _analysis_header(include_resistivity)
    count = 0
    with (directory / "analysis.txt").open(encoding="utf-8", newline="") as exported:
        data = csv.reader(exported, delimiter="\t")
        if next(data, None) != header:
            raise RuntimeError("Analysis text quantity/unit headers differ from recorded geometry")
        for count, (row, values) in enumerate(zip_longest(rows, data), start=1):
            if row is None or values is None or len(values) != len(header):
                raise RuntimeError("Analysis text must have one fixed-width row per CSV reading")
            expected = _analysis_values(row, include_resistivity)
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


def verify_sample_geometry(directory: Path) -> int:
    """Independently verify saved mm geometry, SI conversion, and the five-column TXT."""
    snapshot = json.loads((directory / "config.json").read_text(encoding="utf-8"))
    settings = snapshot.get("settings", {})
    expected_dimensions = dict(sample_length_mm=20, sample_width_mm=10, sample_depth_mm=2)
    if any(settings.get(key) != value for key, value in expected_dimensions.items()) or (
        settings.get("current_path_axis") != "D"
    ):
        raise RuntimeError("Sample geometry settings were not saved in mm with their current axis")
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    geometry = metadata.get("sample_geometry", {})
    try:
        units_match = math.isclose(geometry.get("area_m2"), 2e-4, rel_tol=1e-12) and math.isclose(
            geometry.get("current_path_length_m"), 2e-3, rel_tol=1e-12
        )
    except (TypeError, ValueError):
        units_match = False
    if (
        geometry.get("dimensions_mm") != {"L": 20, "W": 10, "D": 2}
        or geometry.get("current_path_axis") != "D"
        or not units_match
    ):
        raise RuntimeError("Sample geometry metadata must record its mm inputs and SI geometry")
    count = 0
    with (directory / "readings.csv").open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            resistance = row.get("resistance_corrected_ohm")
            rho = row.get("resistivity_ohm_m")
            if resistance in (None, ""):
                if rho not in (None, ""):
                    raise RuntimeError("Resistivity must be absent when resistance is unavailable")
                continue
            if (
                rho in (None, "")
                or not math.isfinite(float(rho))
                or not math.isclose(float(rho), float(resistance) * 0.1, rel_tol=1e-12)
            ):
                raise RuntimeError("Saved resistivity must equal R * (20 mm * 10 mm) / 2 mm")
            count += 1
    if count == 0:
        raise RuntimeError("Sample geometry smoke requires at least one finite resistivity reading")
    analysis_export_smoke(directory)
    with (directory / "analysis.txt").open(encoding="utf-8", newline="") as stream:
        if next(csv.reader(stream, delimiter="\t")) != _analysis_header(True):
            raise RuntimeError("Complete sample geometry must create a five-column analysis TXT")
    return count


def sample_geometry_resistivity_smoke(output_directory: Path) -> Path:
    """Exercise rectangular D-axis resistivity with synthetic readings only."""
    from keithley6517a.clock import FakeClock
    from keithley6517a.config import RunConfig
    from keithley6517a.measurement.runner import MeasurementRunner

    config = replace(
        RunConfig(),
        output_directory=str(output_directory),
        voltages=(1,),
        simulation_resistance_ohm=1e9,
        current_trip_A=1e-8,
        residual_warning_ack=True,
        dwell_s=0.5,
        summary_window_s=0.5,
        sample_interval_s=0.1,
        nplc=0.1,
        sample_length_mm=20,
        sample_width_mm=10,
        sample_depth_mm=2,
        current_path_axis="D",
    )
    runner = MeasurementRunner(config, clock=FakeClock())
    try:
        runner.connect()
        runner.arm()
        result = runner.start()
        if result.get("status") != "completed" or result.get("output_state") != "OFF":
            raise RuntimeError("Synthetic sample geometry run did not complete with output OFF")
        verify_sample_geometry(runner.run_directory)
        return runner.run_directory
    finally:
        runner.shutdown()


def adaptive_resistivity_analysis_smoke(output_directory: Path) -> None:
    """Exercise fixed schemas for complete zero-V and incomplete sample geometry."""
    from keithley6517a.clock import FakeClock
    from keithley6517a.config import RunConfig
    from keithley6517a.measurement.runner import MeasurementRunner

    base = replace(
        RunConfig(),
        output_directory=str(output_directory),
        simulation_resistance_ohm=1e9,
        current_trip_A=1e-8,
        residual_warning_ack=True,
        dwell_s=0.5,
        summary_window_s=0.5,
        sample_interval_s=0.1,
        nplc=0.1,
        sample_length_mm=20,
        sample_width_mm=10,
        sample_depth_mm=2,
    )
    for name, config, include_resistivity in (
        ("zero-voltage", replace(base, voltages=(0,), current_path_axis="D"), True),
        ("axis-unspecified", replace(base, voltages=(1,), current_path_axis=None), False),
    ):
        runner = MeasurementRunner(
            replace(config, output_directory=str(output_directory / name)), clock=FakeClock()
        )
        try:
            runner.connect()
            runner.arm()
            status = runner.start()
            if status.get("status") != "completed" or status.get("output_state") != "OFF":
                raise RuntimeError("Adaptive analysis synthetic run did not complete with OFF")
            analysis_export_smoke(runner.run_directory)
            with (runner.run_directory / "analysis.txt").open(
                encoding="utf-8", newline=""
            ) as stream:
                rows = list(csv.reader(stream, delimiter="\t"))
            if rows[0] != _analysis_header(include_resistivity):
                raise RuntimeError("Adaptive analysis chose the wrong geometry-dependent schema")
            if include_resistivity and not all(math.isnan(float(row[2])) for row in rows[1:]):
                raise RuntimeError("Complete zero-V geometry must retain an all-nan rho column")
        finally:
            runner.shutdown()


def startup_checks_smoke(root: Path, startup_factory=None, *, timeout_ms=120000):
    """Exercise the delivered automatic checks before showing a disconnected GUI."""
    from PySide6.QtCore import QEventLoop, QProcess, QTimer
    from PySide6.QtWidgets import QApplication

    from keithley6517a.transport.visa import VisaTransport
    from keithley6517a.ui.main_window import MainWindow

    if startup_factory is None:
        from keithley6517a.ui.startup_checks import StartupChecks

        startup_factory = StartupChecks
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("Startup smoke requires the existing QApplication")
    loop = QEventLoop()
    failures, windows = [], []
    passed = []
    previous_quit = app.quitOnLastWindowClosed()
    original_visa_init = VisaTransport.__init__

    def no_instrument(*args, **kwargs):
        raise RuntimeError("Automatic startup attempted to connect a VISA instrument")

    def main_window():
        reports = startup.stage_results
        bundle, simulation = reports.get("bundle", {}), reports.get("simulation", {})
        if (
            bundle.get("status") != "passed"
            or bundle.get("hardware_verified") is not False
            or bundle.get("verified_files", 0) <= 0
            or simulation.get("status") != "completed"
            or simulation.get("output_state") != "OFF"
            or simulation.get("reading_count", 0) <= 0
        ):
            raise RuntimeError("Automatic startup opened its GUI before both checks passed")
        window = MainWindow()
        windows.append(window)
        config = window.config_from_controls()
        if not config.simulation or config.voltages != (0.0,) or window.worker.runner is not None:
            raise RuntimeError(
                "Automatic startup must leave the GUI disconnected at SIMULATION 0 V"
            )
        titles = [window.graph_tabs.tabText(index) for index in range(window.graph_tabs.count())]
        if titles != ["R(t)", "I(t)", "I–V", "R–V"] or window.graph_tabs.currentIndex() != 0:
            raise RuntimeError("The main graph order/default must be R, I, I-V, R-V")
        if [trace.y_key for trace in window.traces] != [
            "_display_r",
            "current_raw_A",
            "current_raw_A",
            "_display_r",
        ]:
            raise RuntimeError("Graph labels do not match the plotted resistance/current data")
        return window

    def failed(message):
        failures.append(str(message))
        loop.quit()

    def checked():
        passed.append(True)
        if len(windows) != 1:
            failed("Automatic startup did not create exactly one main window")
        else:
            QTimer.singleShot(100, windows[0].close)

    def poll():
        if windows and windows[0]._closed:
            loop.quit()

    timer, deadline = QTimer(), QTimer()
    timer.setInterval(20)
    timer.timeout.connect(poll)
    deadline.setSingleShot(True)
    deadline.timeout.connect(lambda: failed("Automatic startup smoke exceeded its deadline"))
    startup = None
    app.setQuitOnLastWindowClosed(False)
    VisaTransport.__init__ = no_instrument
    try:
        startup = startup_factory(root, main_window_factory=main_window)
        startup.checks_passed.connect(checked)
        startup.checks_failed.connect(failed)
        startup.show()
        timer.start()
        deadline.start(timeout_ms)
        loop.exec()
        if failures:
            raise RuntimeError("Automatic startup failed: " + "; ".join(failures))
        if len(passed) != 1 or len(windows) != 1 or not windows[0]._closed:
            raise RuntimeError("Automatic startup did not complete and close its worker normally")
        return {"automatic_startup_checks_verified": True, "graph_order_verified": True}
    finally:
        timer.stop()
        deadline.stop()
        if startup is not None:
            startup.close()
            process = getattr(startup, "process", None)
            if process is not None and process.state() != QProcess.ProcessState.NotRunning:
                cleanup_process = QEventLoop()
                process.finished.connect(cleanup_process.quit)
                QTimer.singleShot(5000, cleanup_process.quit)
                cleanup_process.exec()
        for window in windows:
            if not window._closed:
                window.close()
                cleanup = QEventLoop()
                watcher = QTimer()
                watcher.setInterval(20)
                watcher.timeout.connect(
                    lambda window=window, cleanup=cleanup: (
                        cleanup.quit() if window._closed else None
                    )
                )
                QTimer.singleShot(5000, cleanup.quit)
                watcher.start()
                cleanup.exec()
                watcher.stop()
        VisaTransport.__init__ = original_visa_init
        app.setQuitOnLastWindowClosed(previous_quit)


def user_stop_smoke(output_directory: Path) -> Path:
    """A partial synthetic run is stopped, saved, and OFF without becoming a device fault."""
    from keithley6517a.clock import FakeClock
    from keithley6517a.config import RunConfig
    from keithley6517a.measurement.runner import MeasurementRunner

    config = replace(
        RunConfig(),
        output_directory=str(output_directory),
        voltages=(1,),
        simulation_resistance_ohm=1e9,
        dwell_s=300,
        summary_window_s=30,
        sample_interval_s=1,
        current_trip_A=1e-8,
        residual_warning_ack=True,
    )
    samples = []

    def stop_after_two(row):
        samples.append(row)
        if len(samples) == 2:
            runner.request_stop("user stop smoke")

    runner = MeasurementRunner(config, clock=FakeClock(), on_sample=stop_after_two)
    try:
        runner.connect()
        runner.arm()
        result = runner.start()
        directory = runner.run_directory
        status = json.loads((directory / "run_status.json").read_text(encoding="utf-8"))
        if (
            result.get("status") != "stopped"
            or result.get("output_state") != "OFF"
            or result.get("reading_count") != 2
            or runner.state != "OUTPUT_OFF_CONFIRMED"
            or runner.can_arm
            or runner.can_start
            or status.get("status") != "stopped"
            or status.get("final_output_state") != "OFF"
            or any(row.get("phase") == "ERROR" for row in samples)
        ):
            raise RuntimeError("Partial user STOP was not saved as stopped with confirmed OFF")
        if analysis_export_smoke(directory) != 2:
            raise RuntimeError("Partial STOP did not preserve every CSV/TXT reading")
        if (directory / "summary.csv").read_bytes():
            raise RuntimeError("Partial STOP fabricated a completed step summary")
    finally:
        runner.shutdown()
    after_shutdown = json.loads((directory / "run_status.json").read_text(encoding="utf-8"))
    if after_shutdown.get("status") != "stopped":
        raise RuntimeError("Disconnect changed a confirmed user STOP into another outcome")
    return directory


def saved_result_review_smoke(directory: Path, output: Path, dialog_factory=None) -> int:
    """Exercise the delivered offline dialog and compare its interval with source CSV values."""
    from PySide6.QtWidgets import QApplication

    from keithley6517a.measurement.runner import MeasurementRunner
    from keithley6517a.transport.visa import VisaTransport

    originals = {path: path.read_bytes() for path in directory.iterdir() if path.is_file()}
    with (directory / "readings.csv").open(encoding="utf-8", newline="") as stream:
        original_rows = list(csv.DictReader(stream))
    include_resistivity = _recorded_resistivity_schema(directory, original_rows)
    times = [float(row["elapsed_s"]) for row in original_rows]
    if len(times) < 3 or max(times) <= min(times):
        raise RuntimeError("Offline review smoke requires a nonempty time interval")
    original_runner_init, original_visa_init = MeasurementRunner.__init__, VisaTransport.__init__

    def no_instrument(*args, **kwargs):
        raise RuntimeError("Offline result review attempted to create an instrument session")

    dialog = None
    MeasurementRunner.__init__ = VisaTransport.__init__ = no_instrument
    try:
        if dialog_factory is None:
            from keithley6517a.ui.result_dialog import SavedResultDialog

            dialog_factory = SavedResultDialog
        dialog = dialog_factory()
        if not dialog.load_path(directory):
            raise RuntimeError("Offline result dialog could not load saved readings")
        low, high = min(times), max(times)
        dialog.start_time.setValue(low + (high - low) / 4)
        dialog.end_time.setValue(low + 3 * (high - low) / 4)
        if not dialog.apply_range():
            raise RuntimeError("Offline result dialog could not select a time interval")
        dialog.show()
        QApplication.processEvents()
        lower, upper = dialog.start_time.value(), dialog.end_time.value()
        expected = [row for row in original_rows if lower <= float(row["elapsed_s"]) <= upper]
        if not expected or len(expected) >= len(original_rows):
            raise RuntimeError("Offline result review did not select a proper subset")
        if len(dialog.selected_rows) != len(expected):
            raise RuntimeError("Offline result review selected the wrong rows")
        for column, count_key, mean_key, std_key in (
            ("current_raw_A", "current_count", "current_mean_A", "current_std_A"),
            (
                "resistance_apparent_ohm",
                "resistance_count",
                "resistance_mean_ohm",
                "resistance_std_ohm",
            ),
            (
                "resistivity_ohm_m",
                "resistivity_count",
                "resistivity_mean_ohm_m",
                "resistivity_std_ohm_m",
            ),
        ):
            values = []
            for row in expected:
                value = row.get(column)
                if column == "resistance_apparent_ohm" and row.get("native_r_ohm") not in (
                    None,
                    "",
                ):
                    value = row["native_r_ohm"]
                if value not in (None, "") and math.isfinite(float(value)):
                    values.append(float(value))
            if dialog.statistics.get(count_key) != len(values):
                raise RuntimeError("Offline result review statistic has the wrong sample count")
            for key, target in (
                (mean_key, mean(values) if values else None),
                (std_key, stdev(values) if len(values) > 1 else None),
            ):
                actual = dialog.statistics.get(key)
                if (actual is None) != (target is None) or (
                    target is not None
                    and not math.isclose(actual, target, rel_tol=1e-12, abs_tol=1e-30)
                ):
                    raise RuntimeError(f"Offline result review statistic differs from CSV: {key}")
        if (
            dialog.statistics_table.rowCount() != 3
            or dialog.statistics_table.item(2, 0).text() != "비저항"
            or dialog.statistics_table.item(2, 3).text()
            != str(dialog.statistics["resistivity_count"])
            or dialog.graph_tabs.count() != 3
            or "ρ(t)" not in dialog.graph_tabs.tabText(2)
        ):
            raise RuntimeError("Offline result review is missing its resistivity table or graph")
        rho_pairs = [
            (float(row["elapsed_s"]), float(row["resistivity_ohm_m"]))
            for row in expected
            if row.get("resistivity_ohm_m") not in (None, "")
            and math.isfinite(float(row["resistivity_ohm_m"]))
        ]
        xs, ys = dialog.curves["resistivity"].getData()
        drawn = [] if xs is None else list(zip(xs, ys, strict=True))
        if drawn != rho_pairs:
            raise RuntimeError("Offline resistivity graph differs from stored CSV values")
        for column, key in ((1, "resistivity_mean_ohm_m"), (2, "resistivity_std_ohm_m")):
            text = dialog.statistics_table.item(2, column).text()
            target = dialog.statistics[key]
            if target is None:
                matches = text == "—"
            else:
                number, unit = text.split()
                prefix = unit.removesuffix("Ω·m")
                scale = {
                    "P": 1e15,
                    "T": 1e12,
                    "G": 1e9,
                    "M": 1e6,
                    "k": 1e3,
                    "": 1,
                    "m": 1e-3,
                    "µ": 1e-6,
                    "n": 1e-9,
                    "p": 1e-12,
                    "f": 1e-15,
                }.get(prefix)
                matches = (
                    unit.endswith("Ω·m")
                    and scale is not None
                    and math.isclose(float(number) * scale, target, rel_tol=1e-5, abs_tol=1e-30)
                )
            if not matches:
                raise RuntimeError("Offline resistivity table differs from computed statistics")
        if not dialog.export_to(output):
            raise RuntimeError("Offline result review could not export its selected interval")
        with output.open(encoding="utf-8", newline="") as stream:
            data = list(csv.reader(stream, delimiter="\t"))
        header = _analysis_header(include_resistivity)
        if data[0] != header:
            raise RuntimeError("Offline selected export changed its geometry-dependent header")
        if len(data) != len(expected) + 1:
            raise RuntimeError("Offline selected export has the wrong row count")
        for row, fields in zip(expected, data[1:], strict=True):
            desired = _analysis_values(row, include_resistivity)
            if len(fields) != len(header):
                raise RuntimeError("Offline selected export changed its fixed column count")
            for value, cell in zip(desired, fields, strict=True):
                actual = float(cell)
                if value in (None, ""):
                    matches = math.isnan(actual)
                else:
                    matches = actual == float(value)
                if not matches:
                    raise RuntimeError("Offline selected export differs from source CSV")
        payload = output.read_bytes()
        if dialog.export_to(output) is not None or output.read_bytes() != payload:
            raise RuntimeError("Offline selected export replaced an existing file")
        if any(path.read_bytes() != original for path, original in originals.items()):
            raise RuntimeError("Offline review changed original run files")
        return len(expected)
    finally:
        MeasurementRunner.__init__, VisaTransport.__init__ = (
            original_runner_init,
            original_visa_init,
        )
        if dialog is not None:
            dialog.close()


def analysis_comparison_session_smoke(first: Path, second: Path, output: Path, dialog_factory=None):
    """Verify actual overlaid curves and a restored analysis session against two CSVs."""
    from PySide6.QtWidgets import QApplication

    from keithley6517a.measurement.runner import MeasurementRunner
    from keithley6517a.transport.visa import VisaTransport
    from keithley6517a.ui.result_dialog import SavedResultDialog

    output.mkdir(parents=True, exist_ok=True)
    sources = [first / "readings.csv", second / "readings.csv"]
    originals = {
        path: path.read_bytes()
        for directory in (first, second)
        for path in directory.iterdir()
        if path.is_file()
    }
    readings = []
    for source in sources:
        with source.open(encoding="utf-8", newline="") as stream:
            readings.append(list(csv.DictReader(stream)))
    low = max(min(float(row["elapsed_s"]) for row in rows) for rows in readings)
    high = min(max(float(row["elapsed_s"]) for row in rows) for rows in readings)
    if low >= high:
        raise RuntimeError("Comparison smoke requires two overlapping elapsed-time ranges")
    previous_runner, previous_visa = MeasurementRunner.__init__, VisaTransport.__init__
    dialogs = []

    def no_instrument(*args, **kwargs):
        raise RuntimeError("Saved comparison/session opened an instrument session")

    MeasurementRunner.__init__ = VisaTransport.__init__ = no_instrument
    try:
        factory = dialog_factory or SavedResultDialog
        dialog = factory()
        dialogs.append(dialog)
        if not dialog.load_path(first) or not dialog.add_paths([sources[1]]):
            raise RuntimeError("Saved comparison could not load two runs")
        dialog.start_time.setValue(math.floor(low * 1e6) / 1e6)
        dialog.end_time.setValue(math.ceil(high * 1e6) / 1e6)
        if not dialog.apply_range() or not dialog.select_source(1):
            raise RuntimeError("Saved comparison could not select its interval/active run")
        dialog.graph_tabs.setCurrentIndex(2)
        dialog.show()
        QApplication.processEvents()
        lower, upper = dialog.start_time.value(), dialog.end_time.value()
        expected = [
            [row for row in rows if lower <= float(row["elapsed_s"]) <= upper] for rows in readings
        ]
        if len(dialog.saved_runs) != 2 or any(not rows for rows in expected):
            raise RuntimeError("Saved comparison lost a source or selected no readings")
        for index, rows in enumerate(expected):
            for key in ("current", "resistance", "resistivity"):
                desired = []
                for row in rows:
                    if key == "resistance":
                        value = row.get("native_r_ohm") or row.get("resistance_apparent_ohm")
                    else:
                        field = "current_raw_A" if key == "current" else "resistivity_ohm_m"
                        value = row.get(field)
                    if value not in (None, "") and math.isfinite(float(value)):
                        desired.append((float(row["elapsed_s"]), float(value)))
                xs, ys = dialog.comparison_curves[index][key].getData()
                actual = [] if xs is None else list(zip(xs, ys, strict=True))
                if actual != desired:
                    raise RuntimeError("Comparison curve differs from its own stored CSV")
        rho = [
            float(row["resistivity_ohm_m"])
            for row in expected[1]
            if row.get("resistivity_ohm_m") not in (None, "")
        ]
        if not rho or not math.isclose(
            dialog.statistics["resistivity_mean_ohm_m"], mean(rho), rel_tol=1e-12
        ):
            raise RuntimeError("Active comparison statistics differ from selected source")
        session = output / "analysis-session.json"
        if not dialog.save_session_to(session):
            raise RuntimeError("Analysis session could not be saved")
        session_before = session.read_bytes()
        if dialog.save_session_to(session) or session.read_bytes() != session_before:
            raise RuntimeError("Analysis session overwrote an existing file")
        restored = factory()
        dialogs.append(restored)
        if not restored.load_session_path(session):
            raise RuntimeError("Analysis session could not be reopened")
        if (
            [saved.source_path.resolve() for saved in restored.saved_runs]
            != [path.resolve() for path in sources]
            or restored.active_index != 1
            or restored.start_time.value() != lower
            or restored.end_time.value() != upper
            or restored.graph_tabs.currentIndex() != 2
        ):
            raise RuntimeError("Analysis session did not restore paths/interval/active quantity")
        selected = output / "session-selected-analysis.txt"
        if not restored.export_to(selected):
            raise RuntimeError("Restored session could not export its active run")
        with selected.open(encoding="utf-8", newline="") as stream:
            text = list(csv.reader(stream, delimiter="\t"))
        if text[0] != _analysis_header(True) or len(text) != len(expected[1]) + 1:
            raise RuntimeError("Session selected export mixed source rows or changed schema")
        for row, values in zip(expected[1], text[1:], strict=True):
            for source, cell in zip(_analysis_values(row, True), values, strict=True):
                if source in (None, ""):
                    valid = math.isnan(float(cell))
                else:
                    valid = float(source) == float(cell)
                if not valid:
                    raise RuntimeError("Session selected text differs from its active CSV")
        bad_session = output / "invalid-session.json"
        bad_session.write_text('{"schema_version":999}', encoding="utf-8")
        if restored.load_session_path(bad_session) or len(restored.saved_runs) != 2:
            raise RuntimeError("Invalid session replaced the current analysis")
        if any(path.read_bytes() != content for path, content in originals.items()):
            raise RuntimeError("Comparison/session review changed original measurement files")
        return {"analysis_comparison_session_verified": True}
    finally:
        MeasurementRunner.__init__, VisaTransport.__init__ = previous_runner, previous_visa
        for dialog in dialogs:
            dialog.close()


def progress_and_diagnostic_smoke(window, run_directory: Path, output: Path):
    """Exercise displayed estimates and local diagnostic ZIP using a disconnected GUI."""
    from PySide6.QtWidgets import QApplication

    output.mkdir(parents=True, exist_ok=True)
    config = replace(
        window.config_from_controls(),
        protocol="list",
        voltages=(1, 2),
        cycles=2,
        dwell_s=10,
        summary_window_s=10,
    )
    window._set_progress_plan(config)
    window._progress.start()
    window._progress.update_step(1, 0)
    window._progress.update_sample(
        dict(cycle_index=1, step_index=0, time_since_voltage_command_s=4, elapsed_s=24)
    )
    estimate = window._progress.estimate()
    if estimate is None or estimate.total_steps != 4 or estimate.step_number != 3:
        raise RuntimeError("Progress did not count voltage points and cycles")
    if not math.isclose(estimate.remaining_s, 16):
        raise RuntimeError("Progress remaining dwell differs from its schedule")
    window._on_status(dict(state="ACQUIRING", output_state="ON", worker_busy=True))
    QApplication.processEvents()
    if "예상" not in window.progress_label.text() or "16" not in window.progress_label.text():
        raise RuntimeError("GUI did not show the estimated remaining time")
    window._progress.update_step(1, 1)
    window._progress.update_sample(
        dict(cycle_index=1, step_index=1, time_since_voltage_command_s=11, elapsed_s=41)
    )
    window._on_status(dict(state="ACQUIRING", output_state="ON", worker_busy=True))
    if "종료" not in window.progress_label.text() or window.progress_bar.value() >= 100:
        raise RuntimeError("Zero ETA was shown as completed before output/save confirmation")
    window._on_status(dict(state="DISCONNECTED", output_state="UNKNOWN", worker_busy=False))
    diagnostic = output / "connection"
    diagnostic.mkdir()
    (diagnostic / "diagnostic.json").write_text('{"synthetic":true}', encoding="utf-8")
    (diagnostic / "raw_io.jsonl").write_text('{"scope":"synthetic"}\n', encoding="utf-8")
    (diagnostic / "unrelated-secret.txt").write_text("must not be copied", encoding="utf-8")
    window._last_run_directory = str(run_directory)
    window._last_diagnostic_directory = str(diagnostic)
    window.log.appendPlainText("synthetic diagnostic export smoke")
    originals = {
        path: path.read_bytes()
        for directory in (run_directory, diagnostic)
        for path in directory.iterdir()
        if path.is_file()
    }
    archive = output / "diagnostics.zip"
    result = window.export_diagnostics_to(archive)
    if not result or window.worker.runner is not None:
        raise RuntimeError("Diagnostic ZIP failed or opened an instrument session")
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip() is not None or "manifest.json" not in bundle.namelist():
            raise RuntimeError("Diagnostic ZIP has invalid contents")
        json.loads(bundle.read("manifest.json"))
        for name in ("readings.csv", "config.json", "metadata.json", "raw_io.jsonl"):
            original = (run_directory / name).read_bytes()
            exported = bundle.read("source/run/" + name)
            if hashlib.sha256(exported).digest() != hashlib.sha256(original).digest():
                raise RuntimeError("Diagnostic ZIP changed a selected run file")
        if bundle.read("source/diagnostic/diagnostic.json") != b'{"synthetic":true}':
            raise RuntimeError("Diagnostic ZIP omitted the selected connection diagnostic")
        if b"synthetic diagnostic export smoke" not in bundle.read("gui/log.txt"):
            raise RuntimeError("Diagnostic ZIP omitted its GUI log")
        if any("unrelated-secret" in name for name in bundle.namelist()):
            raise RuntimeError("Diagnostic ZIP included an unrelated file")
    previous = archive.read_bytes()
    if window.export_diagnostics_to(archive) is not None or archive.read_bytes() != previous:
        raise RuntimeError("Diagnostic ZIP overwrote an existing file")
    if any(path.read_bytes() != content for path, content in originals.items()):
        raise RuntimeError("Diagnostic ZIP changed original measurement/connection files")
    return {"estimated_progress_verified": True, "diagnostic_zip_export_verified": True}


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
    user_stop_smoke(root / "native-smoke-results/user-stop")
    geometry_run = sample_geometry_resistivity_smoke(root / "native-smoke-results/sample-geometry")
    adaptive_resistivity_analysis_smoke(root / "native-smoke-results/adaptive-analysis")
    if not args.skip_optional_installer:
        optional_installer_smoke(root)
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from keithley6517a.ui.main_window import MainWindow

    app = QApplication([])
    startup_checks_smoke(root)
    saved_result_review_smoke(
        metadata_files[0].parent, root / "native-smoke-results/selected-analysis.txt"
    )
    saved_result_review_smoke(
        geometry_run, root / "native-smoke-results/selected-resistivity-analysis.txt"
    )
    analysis_comparison_session_smoke(
        metadata_files[0].parent, geometry_run, root / "native-smoke-results/comparison"
    )
    window = MainWindow()
    if not window.config_from_controls().simulation or window.worker.runner is not None:
        raise RuntimeError("GUI startup must be disconnected and in SIMULATION")
    progress_and_diagnostic_smoke(
        window, geometry_run, root / "native-smoke-results/progress-and-diagnostics"
    )
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
                "saved_result_review_verified": True,
                "user_stop_classification_verified": True,
                "automatic_startup_checks_verified": True,
                "graph_order_verified": True,
                "sample_geometry_resistivity_verified": True,
                "adaptive_resistivity_analysis_verified": True,
                "analysis_comparison_session_verified": True,
                "estimated_progress_verified": True,
                "diagnostic_zip_export_verified": True,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
