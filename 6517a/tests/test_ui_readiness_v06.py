"""Main-screen preparation reasons stay consistent with the worker's frozen plan."""

import time
from dataclasses import replace

import pytest

from keithley6517a.config import RunConfig
from keithley6517a.ui.main_window import MainWindow
from keithley6517a.ui.readiness import configuration_issues


class TrackingRunner:
    """No instrument I/O; deliberately permissive permissions test the GUI gate."""

    def __init__(self, config, **callbacks):
        self.config = config
        self.state, self.output_state = "DISCONNECTED", "UNKNOWN"
        self.identity = {"model": "6517A", "serial": "TEST", "simulation": True}
        self.instrument = None
        self.commissioning = {"ready": False}
        self._started = False
        self.calls = []

    @property
    def can_arm(self):
        return self.state == "OUTPUT_OFF_CONFIRMED" and not self._started

    @property
    def can_start(self):
        return self.state == "ARMED" and not self._started

    def connect(self):
        self.calls.append("connect")
        self.state, self.output_state = "OUTPUT_OFF_CONFIRMED", "OFF"

    def arm(self):
        self.calls.append("arm")
        self.config.validate(for_arm=True)
        self.state = "ARMED"

    def request_stop(self, reason):
        self.calls.append("stop")

    def shutdown(self):
        self.calls.append("shutdown")
        self.state, self.output_state = "DISCONNECTED", "OFF"


@pytest.fixture
def window(qtbot, tmp_path):
    widget = MainWindow(TrackingRunner)

    def close_cleanly(value):
        if not value._closed:
            value.close()
            qtbot.waitUntil(lambda: value._closed)

    qtbot.addWidget(widget, before_close_func=close_cleanly)
    widget.output_dir.setText(str(tmp_path))
    return widget


def ready_operator_config(**changes):
    values = dict(
        simulation=False,
        transport="visa",
        resource="GPIB0::27::INSTR",
        setup_policy="operator_low_voltage",
        operator_setup_acknowledged=True,
        current_trip_A=1e-8,
        residual_warning_ack=True,
        resistive_limit_enabled=False,
    )
    values.update(changes)
    return replace(RunConfig(), **values)


def connected_status(config, **changes):
    values = dict(
        state="OUTPUT_OFF_CONFIRMED",
        output_state="OFF",
        configuration_issues=configuration_issues(config),
        can_arm=True,
        can_start=False,
        interlock_query=1,
        run_started=False,
    )
    values.update(changes)
    return values


def test_connected_draft_shows_every_missing_operator_condition_from_worker(window):
    draft = ready_operator_config(
        resource="",
        current_trip_A=None,
        operator_setup_acknowledged=False,
        residual_warning_ack=False,
        resistive_limit_enabled=None,
    )
    # Visible controls may contain another plan; only the connected snapshot can explain ARM.
    window._load_controls(ready_operator_config().to_dict())
    window._on_status(connected_status(draft))
    assert len(window._preparation_issues) == 5
    for issue in configuration_issues(draft):
        assert issue["message"] in window.blockers_label.text()
    assert "미완료 5개" in window.setup_status_label.text()
    assert "ARM 비활성" in window.workflow_label.text()
    assert not window.arm_button.isEnabled() and not window.start_button.isEnabled()
    assert window.repair_button.isEnabled()


def test_permissive_simulation_permission_never_enables_arm_for_a_draft(window, qtbot):
    window.connect_button.click()
    qtbot.waitUntil(lambda: window._state == "OUTPUT_OFF_CONFIRMED")
    assert window.worker.runner.can_arm is True
    assert not window.arm_button.isEnabled() and not window.start_button.isEnabled()
    assert "미완료" in window.workflow_label.text()
    assert "current trip" in window.blockers_label.text()
    assert window.worker.runner.calls == ["connect"]


def test_complete_connected_configuration_enables_arm_then_explicit_start(window, qtbot):
    window._load_controls(ready_operator_config().to_dict())
    window.connect_button.click()
    qtbot.waitUntil(lambda: window.arm_button.isEnabled())
    runner = window.worker.runner
    assert not window.start_button.isEnabled()
    assert "3. ARM" in window.workflow_label.text()
    assert runner.calls == ["connect"]
    window.arm_button.click()
    qtbot.waitUntil(lambda: window.start_button.isEnabled())
    assert not window.arm_button.isEnabled()
    assert "4. START" in window.workflow_label.text()
    assert runner.calls == ["connect", "arm"]
    assert window.output_label.text() == "OUTPUT OFF"


def test_abort_event_reason_remains_visible_on_main_screen(window):
    config = ready_operator_config()
    window._load_controls(config.to_dict())
    window._on_status(connected_status(config, state="ACQUIRING", can_arm=False))
    reason = "Software current trip (not programmable compliance)"
    window._on_event({"event": "abort", "reason": reason})
    window._on_status(connected_status(config, state="FAULT", can_arm=False, run_started=True))
    assert reason in window.workflow_label.text()
    assert not window.arm_button.isEnabled() and not window.start_button.isEnabled()


@pytest.mark.parametrize("completion", [False, True])
def test_main_readout_marks_old_values_without_changing_values_or_timestamp(window, completion):
    config = ready_operator_config()
    window._on_status(connected_status(config, state="ACQUIRING", can_arm=False))
    window._on_sample(
        dict(
            elapsed_s=1,
            current_raw_A=1e-9,
            voltage_programmed_readback_V=1,
            resistance_apparent_ohm=1e9,
            wall_time_iso8601="original timestamp",
        )
    )
    original = {key: label.text() for key, label in window.value_labels.items()}
    if completion:
        window._on_status(connected_status(config, can_arm=False, run_started=True))
        assert "측정 완료" in window.workflow_label.text()
    else:
        window._last_sample_time = time.monotonic() - 10
        window._mark_stale()
    assert window.reading_state_label.property("stale") is True
    assert "현재 실시간 값 아님" in window.reading_state_label.text()
    assert original == {key: label.text() for key, label in window.value_labels.items()}
    assert "original timestamp" in window.live_label.text()


def test_repair_disconnects_before_opening_settings_without_arming(window, qtbot, monkeypatch):
    window._load_controls(ready_operator_config(current_trip_A=None).to_dict())
    window.connect_button.click()
    qtbot.waitUntil(lambda: window._state == "OUTPUT_OFF_CONFIRMED")
    runner = window.worker.runner
    opened = []

    def open_settings():
        opened.append((window._state, window.worker.runner, tuple(runner.calls)))

    monkeypatch.setattr(window, "_setup_test", open_settings)
    assert not window.arm_button.isEnabled() and window.repair_button.isEnabled()
    window.repair_button.click()
    qtbot.waitUntil(lambda: bool(opened))
    assert opened == [("DISCONNECTED", None, ("connect", "shutdown"))]
    assert runner.calls == ["connect", "shutdown"]
    assert window.worker.runner is None
    assert not window.arm_button.isEnabled() and not window.start_button.isEnabled()
