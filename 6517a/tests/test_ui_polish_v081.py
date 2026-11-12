"""Graph order and transport wording preserve the same explicit measurement boundary."""

import numpy as np
import pytest
from PySide6.QtCore import Qt

from keithley6517a.config import RunConfig
from keithley6517a.ui.main_window import MainWindow
from keithley6517a.ui.test_setup import TestSetupDialog as SetupDialog


@pytest.fixture
def window(qtbot):
    widget = MainWindow(lambda *a, **kw: pytest.fail("UI choices must not open an instrument"))

    def close_cleanly(value):
        if not value._closed:
            value.close()
            qtbot.waitUntil(lambda: value._closed, timeout=20000)

    qtbot.addWidget(widget, before_close_func=close_cleanly)
    return widget


def test_resistance_is_the_first_visible_graph_with_the_matching_data(window):
    assert [window.graph_tabs.tabText(i) for i in range(4)] == ["R(t)", "I(t)", "I–V", "R–V"]
    assert window.graph_tabs.currentIndex() == 0
    assert window.graph_tabs.currentWidget() is window.traces[0]
    assert [(panel.x_key, panel.y_key) for panel in window.traces] == [
        ("elapsed_s", "_display_r"),
        ("elapsed_s", "current_raw_A"),
        ("voltage_programmed_readback_V", "current_raw_A"),
        ("voltage_programmed_readback_V", "_display_r"),
    ]
    for t, current, resistance in [(0, -1e-9, -1e9), (1, 0, 0), (2, 1e-9, 1e9)]:
        window._on_sample(
            dict(
                elapsed_s=t,
                voltage_programmed_readback_V=1,
                current_raw_A=current,
                resistance_apparent_ohm=resistance,
            )
        )
    x, resistance = window.traces[0].curve.getOriginalDataset()
    np.testing.assert_array_equal(x, [0, 1, 2])
    np.testing.assert_array_equal(resistance, [-1e9, 0, 1e9])
    _, current = window.traces[1].curve.getOriginalDataset()
    np.testing.assert_array_equal(current, [-1e-9, 0, 1e-9])


def test_transport_names_explain_virtual_test_and_default_stays_disconnected(window):
    assert window.transport.itemText(0) == "시뮬레이션 (가상 시험)"
    assert window.transport.itemText(1) == "VISA · USB–GPIB"
    virtual_help = window.transport.itemData(0, Qt.ItemDataRole.ToolTipRole)
    visa_help = window.transport.itemData(1, Qt.ItemDataRole.ToolTipRole)
    assert "가상 데이터" in virtual_help and "GPIB 통신은 하지 않습니다" in virtual_help
    assert "연결 → ARM → START" in visa_help
    assert "SIMULATION" in window.mode_badge.text()
    assert "장비 미연결" in window.mode_badge.text()
    config = window.config_from_controls()
    assert config.simulation and config.transport == "simulation"
    assert config.voltages == (0,) and config.current_trip_A is None
    assert window.worker.runner is None
    assert not window.arm_button.isEnabled() and not window.start_button.isEnabled()


def test_selecting_visa_still_requires_manual_settings_connection_and_start(window):
    window.transport.setCurrentIndex(window.transport.findData("visa"))
    config = window.config_from_controls()
    assert not config.simulation and config.transport == "visa"
    assert config.voltages == (0,) and config.current_trip_A is None
    assert not config.operator_setup_acknowledged and not config.residual_warning_ack
    assert window.worker.runner is None
    assert not window.arm_button.isEnabled() and not window.start_button.isEnabled()


def test_settings_checkbox_uses_the_same_connection_name_and_virtual_explanation(qtbot):
    dialog = SetupDialog(RunConfig())
    qtbot.addWidget(dialog)
    assert dialog.real_mode.text() == "VISA · USB–GPIB 사용"
    assert "장비 연결 없이" in dialog.real_mode.toolTip()
    assert "시뮬레이션" in dialog.real_mode.toolTip()
    assert not dialog.real_mode.isChecked()
    assert dialog.result_config is None
