"""Range settings and device range displays share the normal GUI workflows."""

import json
from dataclasses import replace

import pytest

from keithley6517a.config import RunConfig
from keithley6517a.ui.main_window import MainWindow


@pytest.fixture
def window(qtbot):
    widget = MainWindow(lambda *args, **kwargs: pytest.fail("Range editing must not open I/O"))

    def close_cleanly(value):
        if not value._closed:
            value.close()
            qtbot.waitUntil(lambda: value._closed)

    qtbot.addWidget(widget, before_close_func=close_cleanly)
    return widget


def test_manual_and_saved_range_settings_are_equivalent(window, tmp_path, monkeypatch):
    window.autorange_min.setText("2e-9")
    window.autorange_max.setText("2e-7")
    window.current_range.setText("2e-8")
    manual = window.config_from_controls()
    path = tmp_path / "range.json"
    monkeypatch.setattr(
        "keithley6517a.ui.main_window.QFileDialog.getSaveFileName",
        lambda *args: (str(path), "JSON (*.json)"),
    )
    window._choose_save()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["current_autorange_min_A"] == 2e-9
    assert saved["current_autorange_max_A"] == 2e-7
    assert saved["current_range_A"] == 2e-8

    window.autorange_min.setText("2e-11")
    window.load_config(path)
    assert window.config_from_controls() == manual

    saved["current_autorange_min_A"] = 2e-8
    window.advanced.setPlainText(json.dumps(saved))
    window.advanced_apply.click()
    assert window.config_from_controls() == replace(manual, current_autorange_min_A=2e-8)

    del saved["current_autorange_min_A"], saved["current_autorange_max_A"]
    path.write_text(json.dumps(saved), encoding="utf-8")
    window.load_config(path)
    assert window.config_from_controls() == replace(
        manual, current_autorange_min_A=20e-12, current_autorange_max_A=20e-3
    )


def test_gui_explains_invalid_autorange_limits(window):
    window.autorange_max.setText("2e-9")
    window.autorange_min.setText("2e-8")
    assert "하한은 상한 이하여야 합니다" in window.blockers_label.text()
    assert not window.arm_button.isEnabled()
    assert not window.start_button.isEnabled()


@pytest.mark.parametrize("invalid_minimum", ["2e-6", ""])
def test_fixed_range_preset_recovers_invalid_autorange_draft(window, invalid_minimum):
    initial = replace(RunConfig(), current_autorange_min_A=2e-9, current_autorange_max_A=2e-7)
    window._load_controls(initial.to_dict())
    window.autorange_min.setText(invalid_minimum)
    window.fixed_range_preset.click()
    assert window.config_from_controls() == replace(
        initial, current_autorange=False, current_range_A=2e-7
    )


def test_range_presets_change_only_the_chosen_range_settings(window):
    initial = replace(
        RunConfig(),
        transport="visa",
        simulation=False,
        setup_policy="operator_low_voltage",
        resource="GPIB0::27::INSTR",
        voltages=(0, 1),
        protocol="list",
        current_trip_A=1e-8,
        operator_setup_acknowledged=False,
        residual_warning_ack=True,
    )
    window._load_controls(initial.to_dict())
    window.auto_range_preset.click()
    auto = replace(initial, current_autorange_min_A=2e-9, current_autorange_max_A=2e-7)
    assert window.config_from_controls() == auto

    window.fixed_range_preset.click()
    fixed = replace(auto, current_autorange=False, current_range_A=2e-7)
    assert window.config_from_controls() == fixed

    window._on_status({"state": "OUTPUT_OFF_CONFIRMED", "output_state": "OFF"})
    assert not window.auto_range_preset.isEnabled()
    assert not window.fixed_range_preset.isEnabled()
    assert not window.autorange_min.isEnabled()
    assert not window.autorange_max.isEnabled()
    window._apply_current_range_preset(True)
    assert window.config_from_controls() == fixed


def test_bounded_auto_controls_are_unavailable_in_native_mode(window):
    window.mode.setCurrentText("NATIVE_RESISTANCE")
    initial = window.config_from_controls()
    assert not window.autorange_min.isEnabled()
    assert not window.autorange_max.isEnabled()
    assert not window.auto_range_preset.isEnabled()
    assert window.fixed_range_preset.isEnabled()
    window._apply_current_range_preset(True)
    assert window.config_from_controls() == initial

    window.fixed_range_preset.click()
    assert window.config_from_controls() == replace(
        initial, current_autorange=False, current_range_A=2e-7
    )
    window.mode.setCurrentText("FVMI_CURRENT")
    assert window.autorange_min.isEnabled()
    assert window.autorange_max.isEnabled()
    assert window.auto_range_preset.isEnabled()


def test_range_display_clears_for_failed_arm_and_disconnect(window):
    status = {
        "state": "ARMED",
        "output_state": "OFF",
        "settings_readback": {
            "current_autorange": False,
            "current_range_A": 2e-7,
            "zero_correct_range_A": 2e-7,
        },
    }
    window._on_status(status)
    assert "고정 200 nA · Zero Correct 200 nA" in window.current_range_label.text()
    window._on_sample({"current_range_A": 2e-7})
    assert "판독 직후 200 nA" in window.current_range_label.text()

    window._on_status(dict(status, state="FAULT", arm_failure_report={"ok": False}))
    assert window.current_range_label.isHidden()
    assert not window.current_range_label.text()

    window._on_status(status)
    window._on_status({"state": "DISCONNECTED"})
    assert window.current_range_label.isHidden()
    assert not window.current_range_label.text()
