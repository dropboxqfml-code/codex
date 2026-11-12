"""GUI checks use the public worker boundary, never actual VISA hardware."""

import json
import threading
import time

import numpy as np
import pytest

from keithley6517a.clock import FakeClock
from keithley6517a.config import RunConfig
from keithley6517a.measurement.runner import MeasurementRunner
from keithley6517a.ui.main_window import MainWindow, TracePanel


class FakeRunner:
    instances = []

    def __init__(self, config, on_sample, on_event):
        self.config = config
        self.on_sample, self.on_event = on_sample, on_event
        self.state, self.output_state = "DISCONNECTED", "UNKNOWN"
        self.identity = {"model": "6517A", "serial": "SIM", "firmware": "SIM"}
        self.residual_voltage_state = "UNVERIFIED"
        self.run_directory = None
        self.stop = threading.Event()
        self.threads = []
        self.calls = []
        self.commissioning = {"ready": False, "open_observed": False, "closed_observed": False}
        FakeRunner.instances.append(self)

    @property
    def can_arm(self):
        return (
            self.state == "OUTPUT_OFF_CONFIRMED"
            and "start" not in self.calls
            and (self.config.simulation or self.commissioning["ready"])
        )

    @property
    def can_start(self):
        return self.state == "ARMED"

    def connect(self):
        self.threads.append(threading.get_ident())
        self.calls.append("connect")
        self.state, self.output_state = "OUTPUT_OFF_CONFIRMED", "OFF"

    def arm(self):
        self.threads.append(threading.get_ident())
        self.calls.append("arm")
        self.config.validate(for_arm=True)
        self.state = "ARMED"

    def commission_interlock(self, expected):
        self.threads.append(threading.get_ident())
        self.calls.append(f"commission_{expected}")
        if self.state != "OUTPUT_OFF_CONFIRMED" or self.output_state != "OFF":
            raise RuntimeError("Commissioning requires output OFF")
        if expected == 0:
            self.commissioning.update(ready=False, open_observed=True, closed_observed=False)
        elif expected == 1 and self.commissioning["open_observed"]:
            self.commissioning.update(ready=True, closed_observed=True)
        else:
            raise RuntimeError("Observe lid open before closed")
        return self.commissioning

    def start(self):
        self.threads.append(threading.get_ident())
        self.calls.append("start")
        if self.state != "ARMED":
            raise RuntimeError("ARM first")
        self.state, self.output_state = "ACQUIRING", "ON"
        self.on_event({"event": "state", "state": "ACQUIRING"})
        self.on_sample(
            {
                "elapsed_s": 1.0,
                "voltage_programmed_readback_V": 1.0,
                "current_raw_A": -1e-12,
                "resistance_apparent_ohm": -1e12,
                "current_inferred_A": None,
                "wall_time_iso8601": "2026-11-11T00:00:00+00:00",
            }
        )
        while not self.stop.wait(0.01):
            pass
        self.state, self.output_state = "OUTPUT_OFF_CONFIRMED", "OFF"

    def request_stop(self, reason):
        self.calls.append(reason)
        self.stop.set()

    def shutdown(self):
        self.threads.append(threading.get_ident())
        self.calls.append("shutdown")
        self.state, self.output_state = "DISCONNECTED", "OFF"


def close_window(qtbot, window):
    window.close()
    qtbot.waitUntil(lambda: window._closed, timeout=5000)


def test_startup_and_config_load_never_connect_or_output_on(qtbot, tmp_path):
    FakeRunner.instances.clear()
    window = MainWindow(FakeRunner)
    qtbot.addWidget(window)
    try:
        assert "SIMULATION" in window.mode_badge.text()
        assert window.voltages.text() == "0.0"
        assert window.trip.text() == ""
        assert not window.start_button.isEnabled()
        assert not window.commission_open_button.isEnabled()
        assert not window.commission_closed_button.isEnabled()
        assert "Software trip" in window.protection_label.text()
        assert "100 V 범위 10 mA" in window.protection_label.text()
        assert "외부 하드웨어 보호" in window.protection_label.text()
        config_path = tmp_path / "settings.json"
        config_path.write_text(json.dumps(RunConfig().to_dict()), encoding="utf-8")
        window.load_config(config_path)
        assert not FakeRunner.instances
        assert "UNKNOWN" in window.output_label.text()
        assert any(
            "잔류 전압 UNVERIFIED" in label.text()
            for label in window.findChildren(type(window.mode_badge))
        )
    finally:
        close_window(qtbot, window)


def test_real_connection_commissioning_never_arms_or_starts_automatically(qtbot, tmp_path):
    FakeRunner.instances.clear()
    window = MainWindow(FakeRunner)
    qtbot.addWidget(window)
    config = RunConfig.from_dict(
        {
            "simulation": False,
            "transport": "visa",
            "resource": "GPIB0::27::INSTR",
            "output_directory": str(tmp_path),
            "sample_limit_V": 10,
            "fixture_limit_V": 10,
            "cable_limit_V": 10,
            "rating_approval": "UI TEST ONLY — not a physical approval",
            "current_trip_A": 1e-8,
            "resistive_limit_enabled": False,
            "residual_warning_ack": True,
            "commissioning": {
                "installation_confirmed": True,
                "hardware_protection_reviewed": True,
                "lid_open_zero": True,
                "lid_closed_one": True,
                "fixture_id": "FAKE-FIXTURE",
                "approved_by": "test",
            },
        }
    )
    try:
        window._load_controls(config.to_dict())
        assert not FakeRunner.instances
        assert "실제 장비 동작 미검증" in window.mode_badge.text()
        window.connect_button.click()
        qtbot.waitUntil(lambda: window.commission_open_button.isEnabled())
        runner = FakeRunner.instances[-1]
        assert runner.calls == ["connect"]
        assert not window.arm_button.isEnabled()
        assert not window.start_button.isEnabled()
        window.commission_closed_button.click()
        qtbot.waitUntil(lambda: "Observe lid open before closed" in window.log.toPlainText())
        assert not window.arm_button.isEnabled()
        window.commission_open_button.click()
        qtbot.waitUntil(lambda: runner.commissioning["open_observed"])
        qtbot.waitUntil(lambda: window.commission_closed_button.isEnabled())
        assert not window.arm_button.isEnabled()
        window.commission_closed_button.click()
        qtbot.waitUntil(lambda: window.arm_button.isEnabled())
        assert not window.start_button.isEnabled()
        assert "arm" not in runner.calls and "start" not in runner.calls
        assert "0→1 확인" in window.interlock_label.text()
        window.arm_button.click()
        qtbot.waitUntil(lambda: window.start_button.isEnabled())
        assert "start" not in runner.calls
        assert len(set(runner.threads)) == 1
        assert runner.threads[0] != threading.get_ident()
        window.disconnect_button.click()
        qtbot.waitUntil(lambda: not window._connected)
        window.connect_button.click()
        qtbot.waitUntil(lambda: window.commission_open_button.isEnabled())
        fresh = FakeRunner.instances[-1]
        assert fresh is not runner
        assert not fresh.commissioning["ready"]
        assert fresh.calls == ["connect"]
        assert not window.arm_button.isEnabled()
        assert not window.start_button.isEnabled()
    finally:
        close_window(qtbot, window)


def test_real_native_mode_is_explicitly_marked_unsupported(qtbot):
    window = MainWindow(FakeRunner)
    qtbot.addWidget(window)
    try:
        window.transport.setCurrentIndex(1)
        window.mode.setCurrentText("NATIVE_RESISTANCE")
        assert "NATIVE_RESISTANCE 비활성" in window.mode_badge.text()
        assert not window.arm_button.isEnabled()
        assert not window.start_button.isEnabled()
    finally:
        close_window(qtbot, window)


def test_single_worker_owns_io_close_requests_stop_before_shutdown(qtbot):
    FakeRunner.instances.clear()
    window = MainWindow(FakeRunner)
    qtbot.addWidget(window)
    try:
        window.trip.setText("1e-8")
        window.ack.setChecked(True)
        window._connect()
        qtbot.waitUntil(lambda: window.arm_button.isEnabled())
        runner = FakeRunner.instances[-1]
        assert runner.calls == ["connect"]
        assert not window.settings.isEnabled()
        window.arm_button.click()
        qtbot.waitUntil(lambda: window.start_button.isEnabled())
        window.start_button.click()
        qtbot.waitUntil(lambda: len(window.rows) == 1)
        assert runner.output_state == "ON"
        assert "I inferred" in window.live_label.text()
        window.close()
        qtbot.waitUntil(lambda: window._closed, timeout=5000)
        assert runner.calls.index("GUI close") < runner.calls.index("shutdown")
        assert len(set(runner.threads)) == 1
        assert runner.threads[0] != threading.get_ident()
    finally:
        if not window._closed:
            close_window(qtbot, window)


def test_signed_log_preserves_negative_and_zero_points(qtbot):
    panel = TracePanel("test", "t", "i", "time", "current")
    qtbot.addWidget(panel)
    panel.rows = [{"t": 0, "i": -1e-12}, {"t": 1, "i": 0}, {"t": 2, "i": 1e-12}]
    panel.scale.setCurrentIndex(1)
    x, y = panel.curve.getData()
    np.testing.assert_array_equal(x, [0, 1, 2])
    assert y[0] < 0 and y[1] == 0 and y[2] > 0


def test_last_reading_becomes_stale_without_relabeling_timestamp(qtbot):
    window = MainWindow(FakeRunner)
    qtbot.addWidget(window)
    try:
        window._state = "ACQUIRING"
        window._on_sample(
            {"elapsed_s": 1, "current_raw_A": -1e-12, "wall_time_iso8601": "original timestamp"}
        )
        window._last_sample_time = time.monotonic() - 10
        window._mark_stale()
        assert "STALE" in window.live_label.text()
        assert "original timestamp" in window.live_label.text()
    finally:
        close_window(qtbot, window)


def test_actual_simulator_gui_connect_arm_start_complete_and_close(qtbot, tmp_path):
    window = MainWindow(
        lambda config, **callbacks: MeasurementRunner(config, clock=FakeClock(), **callbacks)
    )
    qtbot.addWidget(window)
    config = RunConfig.from_dict(
        {
            "sample_id": "GUI-INTEGRATION-SIM",
            "output_directory": str(tmp_path),
            "voltages": [1],
            "dwell_s": 0.5,
            "summary_window_s": 0.25,
            "sample_interval_s": 0.1,
            "range_settle_s": 0,
            "nplc": 0.1,
            "current_trip_A": 1e-6,
            "residual_warning_ack": True,
        }
    )
    try:
        window._load_controls(config.to_dict())
        assert window._state == "DISCONNECTED"
        assert not window.arm_button.isEnabled()
        window.connect_button.click()
        qtbot.waitUntil(lambda: window.arm_button.isEnabled())
        assert window.output_label.text() == "OUTPUT OFF"
        window.arm_button.click()
        qtbot.waitUntil(lambda: window.start_button.isEnabled())
        window.start_button.click()

        def complete():
            if window._state in {"FAULT", "HV_STATE_UNKNOWN"}:
                pytest.fail(
                    f"Simulation failed: {window._state}\n{window.log.toPlainText()[-4000:]}"
                )
            # FakeClock skips electrical dwell, not durable filesystem writes.
            # Wait for finalization before opening run_status.json on Windows.
            return (
                bool(window.rows)
                and window._state == "OUTPUT_OFF_CONFIRMED"
                and window.worker.runner.writer.closed
            )

        try:
            qtbot.waitUntil(complete, timeout=20000)
        except Exception as exc:
            pytest.fail(
                f"Simulation completion timed out: state={window._state}, "
                f"rows={len(window.rows)}; {exc}\n{window.log.toPlainText()[-4000:]}"
            )
        assert window.output_label.text() == "OUTPUT OFF"
        assert not window.arm_button.isEnabled()
        assert not window.start_button.isEnabled()
        assert "SIMULATED" in window.interlock_label.text()
        status_path = next(tmp_path.glob("*/run_status.json"))
        # OFF confirms the source state; durable finalization follows on the worker.
        # Wait for a terminal persisted status, then fail immediately if it is aborted.
        qtbot.waitUntil(
            lambda: (
                json.loads(status_path.read_text(encoding="utf-8"))["status"]
                in {"completed", "aborted", "interrupted"}
            )
        )
        status = json.loads(status_path.read_text(encoding="utf-8"))
        assert status["status"] == "completed"
        assert status["final_output_state"] == "OFF"
        assert status["residual_voltage_state"] == "UNVERIFIED"
    finally:
        close_window(qtbot, window)
