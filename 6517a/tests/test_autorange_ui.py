"""AUTO limits and explicit comparison diagnosis never connect or grant user approval."""

import json
from dataclasses import replace

import pytest

from keithley6517a.config import ConfigurationError, RunConfig
from keithley6517a.ui.main_window import MainWindow


@pytest.fixture
def window(qtbot):
    widget = MainWindow(lambda *a, **kw: pytest.fail("Range edits must not open hardware"))

    def close(value):
        if not value._closed:
            value.close()
            qtbot.waitUntil(lambda: value._closed, timeout=20000)

    qtbot.addWidget(widget, before_close_func=close)
    return widget


def test_default_auto_limits_and_diagnostic_controls_stay_in_advanced_page(window):
    config = window.config_from_controls()
    assert config.current_autorange_min_A == 20e-12
    assert config.current_autorange_max_A == 20e-3
    assert not config.calibration_diagnostic_only
    advanced = window.setting_pages.widget(1)
    for control in (
        window.autorange_min,
        window.autorange_max,
        window.calibration_diagnostic_only,
        window.comparison_preset_button,
    ):
        assert advanced.isAncestorOf(control)
    assert window.setting_pages.currentIndex() == 0
    assert window.calibration_diagnostic_label.isHidden()
    assert "정확도 판정 제외" in window.calibration_diagnostic_only.text()
    assert "복구 기능이 아니" in window.calibration_diagnostic_only.toolTip()
    assert window.worker.runner is None


def test_auto_limits_and_diagnostic_mode_roundtrip_saved_configuration(window, tmp_path):
    config = replace(
        RunConfig(),
        setup_policy="operator_low_voltage",
        protocol="list",
        voltages=(0, 0.1, 0.5),
        current_autorange_min_A=2e-9,
        current_autorange_max_A=200e-9,
        calibration_diagnostic_only=True,
    )
    window._load_controls(config.to_dict())
    assert window.config_from_controls() == config
    assert not window.calibration_diagnostic_label.isHidden()
    path = tmp_path / "comparison.json"
    path.write_text(json.dumps(window.config_from_controls().to_dict()), encoding="utf-8")
    window._load_controls(RunConfig().to_dict())
    assert window.calibration_diagnostic_label.isHidden()
    window.load_config(path)
    assert window.config_from_controls() == config
    assert window.worker.runner is None


def test_legacy_configuration_gets_full_auto_range_and_normal_measurement_mode(window):
    legacy = RunConfig().to_dict()
    for key in (
        "current_autorange_min_A",
        "current_autorange_max_A",
        "calibration_diagnostic_only",
    ):
        legacy.pop(key)
    window._load_controls(legacy)
    assert window.config_from_controls() == RunConfig()


@pytest.mark.parametrize("low,high", [("2e-7", "2e-9"), ("1e-10", "2e-7")])
def test_invalid_auto_limits_remain_visible_and_cannot_be_used(window, low, high):
    window.autorange_min.setText(low)
    window.autorange_max.setText(high)
    with pytest.raises(ConfigurationError):
        window.config_from_controls()
    assert "설정 입력" in window.plan_summary.text()
    assert not window.arm_button.isEnabled() and not window.start_button.isEnabled()
    assert window.worker.runner is None


@pytest.mark.parametrize("trip", [None, 1e-6, 1e-8, 3.141592653589793e-12])
def test_comparison_preset_sets_low_voltage_auto_plan_without_raising_trip_or_approving(
    window, trip
):
    config = replace(
        RunConfig(),
        simulation=False,
        transport="visa",
        resource="GPIB0::27::INSTR",
        visa_backend="@ivi",
        sample_id="KEEP-SAMPLE",
        output_directory="keep-results",
        current_trip_A=trip,
        current_autorange=False,
    )
    window._load_controls(config.to_dict())
    window.comparison_preset_button.click()
    actual = window.config_from_controls()
    assert actual.setup_policy == "operator_low_voltage"
    assert actual.mode == "FVMI_CURRENT" and actual.protocol == "list"
    assert actual.current_autorange is True
    assert actual.current_autorange_min_A == 2e-9
    assert actual.current_autorange_max_A == 200e-9
    assert actual.voltages == (0, 0.1, 0.5)
    assert actual.dwell_s == 30 and actual.summary_window_s == 30 and actual.nplc == 10
    assert actual.source_range_V == 100 and actual.voltage_ceiling_V == 1
    assert actual.current_trip_A == (1e-8 if trip is None else min(trip, 1e-8))
    assert actual.calibration_diagnostic_only
    for field in ("simulation", "transport", "resource", "visa_backend", "sample_id"):
        assert getattr(actual, field) == getattr(config, field)
    assert actual.output_directory == config.output_directory
    assert actual.resistive_limit_enabled is None
    assert not actual.operator_setup_acknowledged and not actual.residual_warning_ack
    assert actual.commissioning == config.commissioning
    assert window.worker.runner is None
    assert not window.arm_button.isEnabled() and not window.start_button.isEnabled()


def test_preset_keeps_a_lower_voltage_ceiling_and_does_not_transfer_ignored_operator_ack(window):
    config = replace(RunConfig(), voltage_ceiling_V=0.1, operator_setup_acknowledged=True)
    window._load_controls(config.to_dict())
    window.comparison_preset_button.click()
    assert window.ceiling.value() == 0.1
    assert not window.operator_setup_ack.isChecked()
    assert window.worker.runner is None


@pytest.mark.parametrize("trip", ["not-a-number", "nan", "0", "-1e-9"])
def test_invalid_trip_does_not_get_silently_replaced_by_comparison_preset(window, trip):
    window.trip.setText(trip)
    before = (window.voltages.text(), window.autorange_min.text(), window.autorange_max.text())
    window.comparison_preset_button.click()
    assert window.trip.text() == trip
    assert before == (
        window.voltages.text(),
        window.autorange_min.text(),
        window.autorange_max.text(),
    )
    assert not window.calibration_diagnostic_only.isChecked()
    assert "ERROR" in window.log.toPlainText()


@pytest.mark.parametrize("flag", ["_connected", "_busy", "_closing"])
def test_comparison_controls_and_preset_are_blocked_outside_preparation(window, flag):
    before = window.config_from_controls()
    setattr(window, flag, True)
    try:
        window._update_buttons()
        for control in (
            window.comparison_preset_button,
            window.autorange_min,
            window.autorange_max,
            window.calibration_diagnostic_only,
        ):
            assert not control.isEnabled()
        window._apply_comparison_diagnostic_preset()
        assert window.config_from_controls() == before
        assert window.worker.runner is None
    finally:
        setattr(window, flag, False)
        window._update_buttons()


def test_comparison_notice_stays_visible_without_replacing_workflow_guidance(window):
    window.comparison_preset_button.click()
    window.show()
    assert window.calibration_diagnostic_label.isVisible()
    assert window.calibration_diagnostic_label.text() == "비교 진단 · 정확도 미검증"
    assert "필수 항목" in window.workflow_label.text()
    assert window.calibration_diagnostic_label.parent() is window.workflow_label.parent()
    window._on_status(
        dict(
            state="OUTPUT_OFF_CONFIRMED",
            output_state="OFF",
            can_arm=False,
            can_start=False,
            calibration_diagnostic_only=True,
        )
    )
    window.calibration_diagnostic_only.setChecked(False)
    assert window.calibration_diagnostic_label.isVisible()
    assert "ARM 비활성" in window.workflow_label.text()
