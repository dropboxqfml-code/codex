"""Native startup smoke validates both reports before constructing the real GUI."""

import importlib.util
from pathlib import Path

import pytest
from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QWidget

from keithley6517a.transport.visa import VisaTransport

PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "startup_bundle_smoke", PROJECT / "packaging/smoke.py"
)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)

VALID_REPORTS = {
    "bundle": {"status": "passed", "hardware_verified": False, "verified_files": 3},
    "simulation": {"status": "completed", "output_state": "OFF", "reading_count": 3},
}


def startup_factory(reports, windows):
    class Startup(QWidget):
        checks_passed = Signal()
        checks_failed = Signal(str)

        def __init__(self, root, main_window_factory):
            super().__init__()
            self.stage_results = reports
            self.create_main_window = main_window_factory
            QTimer.singleShot(0, self.checked)

        def checked(self):
            try:
                window = self.create_main_window()
                windows.append(window)
                window.show()
                self.checks_passed.emit()
            except Exception as exc:
                self.checks_failed.emit(str(exc))

    return Startup


def test_startup_smoke_checks_the_real_main_graphs_and_closes_its_worker(qtbot, tmp_path):
    windows = []
    previous = VisaTransport.__init__
    result = smoke.startup_checks_smoke(
        tmp_path, startup_factory(VALID_REPORTS, windows), timeout_ms=5000
    )
    assert result == {"automatic_startup_checks_verified": True, "graph_order_verified": True}
    assert len(windows) == 1 and windows[0]._closed
    assert windows[0].worker.runner is None
    assert windows[0].config_from_controls().simulation
    assert VisaTransport.__init__ is previous


@pytest.mark.parametrize(
    "reports",
    [
        {"bundle": {"status": "failed", "hardware_verified": False}},
        dict(
            VALID_REPORTS,
            simulation={"status": "completed", "output_state": "ON", "reading_count": 3},
        ),
    ],
)
def test_startup_smoke_rejects_incomplete_reports_before_constructing_main_window(
    qtbot, tmp_path, reports
):
    windows = []
    previous = VisaTransport.__init__
    with pytest.raises(RuntimeError, match="before both checks passed"):
        smoke.startup_checks_smoke(tmp_path, startup_factory(reports, windows), timeout_ms=5000)
    assert not windows
    assert VisaTransport.__init__ is previous


def test_startup_smoke_has_a_finite_deadline_and_restores_instrument_boundary(qtbot, tmp_path):
    class WaitingStartup(QWidget):
        checks_passed = Signal()
        checks_failed = Signal(str)

        def __init__(self, root, main_window_factory):
            super().__init__()

    previous = VisaTransport.__init__
    with pytest.raises(RuntimeError, match="exceeded its deadline"):
        smoke.startup_checks_smoke(tmp_path, WaitingStartup, timeout_ms=20)
    assert VisaTransport.__init__ is previous
