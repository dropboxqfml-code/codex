"""Operator preparation and displayed state never issue an implicit hardware action."""

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from keithley6517a.config import RunConfig
from keithley6517a.ui.main_window import InstrumentWorker, MainWindow


@pytest.fixture
def window(qtbot, tmp_path):
    widget = MainWindow(lambda *a, **k: pytest.fail("Preparation must not open hardware"))

    def close_cleanly(window):
        if not window._closed:
            window.close()
            qtbot.waitUntil(lambda: window._closed)

    qtbot.addWidget(widget, before_close_func=close_cleanly)
    widget.output_dir.setText(str(tmp_path))
    return widget


def operator_config(**values):
    return replace(
        RunConfig(),
        simulation=False,
        transport="visa",
        resource="GPIB0::27::INSTR",
        visa_backend="@ivi",
        setup_policy="operator_low_voltage",
        **values,
    )


def test_real_entry_prepares_unacknowledged_operator_zero_without_io(window):
    window.resource.setText("GPIB0::27::INSTR")
    window.connection_guide.real_mode_button.click()
    config = window.config_from_controls()
    assert not config.simulation
    assert config.setup_policy == "operator_low_voltage"
    assert config.voltages == (0,)
    assert config.current_trip_A is None
    assert not config.operator_setup_acknowledged
    assert not config.residual_warning_ack and not config.commissioning
    assert window.worker.runner is None
    assert not window.arm_button.isEnabled() and not window.start_button.isEnabled()
    assert "최대 10 V" in window.mode_badge.text()


def test_loading_saved_strict_plan_does_not_convert_or_clamp_it(window):
    window._enter_real_test()
    config = replace(
        RunConfig(),
        simulation=False,
        transport="visa",
        resource="GPIB0::27::INSTR",
        setup_policy="verified_fixture",
        voltages=(20,),
        source_range_V=1000,
        voltage_ceiling_V=100,
        current_trip_A=1e-7,
    )
    window._load_controls(config.to_dict())
    assert window.config_from_controls() == config
    assert window.ceiling.maximum() == 1000
    assert window.source_range.isEnabled()
    assert window.worker.runner is None


def test_operator_draft_load_retains_missing_values_without_connecting(window, tmp_path):
    config = operator_config()
    path = tmp_path / "operator-draft.json"
    path.write_text(json.dumps(config.to_dict()), encoding="utf-8")
    window.load_config(path)
    assert window.config_from_controls() == config
    assert "준비 초안" in window.setup_status_label.text()
    assert window.worker.runner is None
    assert not window.arm_button.isEnabled() and not window.start_button.isEnabled()
    assert not window.operator_setup_ack.isChecked()


def test_snapshot_and_guide_preserve_unverified_fixture_in_operator_mode(window):
    config = operator_config(
        operator_setup_acknowledged=True,
        current_trip_A=1e-8,
        residual_warning_ack=True,
        resistive_limit_enabled=False,
    )
    window._load_controls(config.to_dict())
    worker = InstrumentWorker(lambda *a, **k: pytest.fail("No I/O during snapshot"))
    commissioning = {"ready": False, "open_observed": False, "closed_observed": False}
    worker.runner = SimpleNamespace(
        config=config,
        state="OUTPUT_OFF_CONFIRMED",
        output_state="OFF",
        residual_voltage_state="UNVERIFIED",
        identity={"model": "6517A", "simulation": False},
        commissioning=commissioning,
        can_arm=True,
        can_start=False,
        instrument=SimpleNamespace(last_safety={"interlock": 1}),
    )
    observations = []
    worker.status.connect(observations.append)
    worker.snapshot()
    observed = observations[0]
    assert observed["setup_policy"] == "operator_low_voltage"
    assert observed["operator_setup_acknowledged"] is True
    assert observed["commissioning"]["ready"] is False
    assert commissioning["ready"] is False
    assert "물리 인터록 인증 미수행" in observed["fixture_commissioning"]
    window._on_status(observed)
    assert "사용자 관리" in window.interlock_label.text()
    assert "0→1" not in window.connection_guide.next_label.text()
    assert "ARM" in window.connection_guide.next_label.text()
    assert not window.commission_open_button.isEnabled()
    assert not window.commission_closed_button.isEnabled()


def test_interlock_zero_does_not_display_a_ready_start_from_stale_flags(window):
    window._load_controls(operator_config(operator_setup_acknowledged=True).to_dict())
    window._on_status(
        dict(
            state="ARMED",
            output_state="OFF",
            setup_policy="operator_low_voltage",
            operator_setup_acknowledged=True,
            interlock_query=0,
            can_arm=True,
            can_start=True,
        )
    )
    assert not window.arm_button.isEnabled() and not window.start_button.isEnabled()
    assert "인터록 조회 0" in window.connection_guide.next_label.text()
    assert "직접 누르세요" not in window.connection_guide.next_label.text()


def test_switching_policy_does_not_copy_acknowledgment_or_approve_fixture(window):
    config = replace(
        RunConfig(),
        simulation=False,
        transport="visa",
        voltages=(1,),
        source_range_V=1000,
        voltage_ceiling_V=100,
        commissioning={"installation_confirmed": False},
    )
    window._load_controls(config.to_dict())
    window.setup_policy.setCurrentIndex(window.setup_policy.findData("operator_low_voltage"))
    assert window.source_range.currentText() == "100"
    assert window.ceiling.value() == 10
    assert not window.operator_setup_ack.isChecked()
    window.operator_setup_ack.setChecked(True)
    assert window.config_from_controls().commissioning["installation_confirmed"] is False
    window.setup_policy.setCurrentIndex(window.setup_policy.findData("verified_fixture"))
    assert not window.operator_setup_ack.isChecked()
    assert window.worker.runner is None
