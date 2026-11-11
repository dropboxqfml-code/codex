"""The connection guide presents evidence without owning or authorizing device I/O."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy

from keithley6517a.ui.connection_guide import ConnectionGuide

RESOURCE = "GPIB0::27::INSTR"


@pytest.fixture
def guide(qtbot):
    widget = ConnectionGuide()
    qtbot.addWidget(widget)
    return widget


def real(guide, **updates):
    guide.set_context(**dict(simulation=False, resource=RESOURCE, backend="@ivi", **updates))


def report(**updates):
    result = dict(
        ok=True,
        mode="IDN_ONLY",
        simulation=False,
        transport_origin="visa",
        settings={"resource": RESOURCE, "backend": "@ivi"},
        identity={"model": "6517A", "serial": "TEST-SERIAL", "firmware": "TEST-FW"},
        output_state="UNKNOWN",
        output_OFF_confirmed=False,
        report_path="/tmp/trial-report/diagnostic.json",
        issues=[],
    )
    result.update(updates)
    return result


def test_initial_simulation_requires_one_explicit_real_mode_intent(guide):
    real_request = QSignalSpy(guide.request_real_mode)
    identify_request = QSignalSpy(guide.request_identify)
    off_request = QSignalSpy(guide.request_off_check)
    assert guide.current_step == 0
    assert "정상" in guide.context_label.text()
    assert not guide.identify_button.isEnabled()
    assert not guide.off_check_button.isEnabled()
    assert real_request.count() == identify_request.count() == off_request.count() == 0
    guide.real_mode_button.click()
    assert real_request.count() == 1
    assert identify_request.count() == off_request.count() == 0
    assert "SIMULATION" in guide.context_label.text()  # Only the parent changes the mode.


def test_resource_discovery_never_selects_or_identifies_a_device(guide):
    guide.set_context(simulation=False)
    identify = QSignalSpy(guide.request_identify)
    guide.update_resources([RESOURCE, "GPIB0::5::INSTR"])
    assert guide.current_step == 2
    assert "주소 미선택" in guide.context_label.text()
    assert not guide.identify_button.isEnabled()
    assert identify.count() == 0
    real(guide)
    assert guide.current_step == 3
    assert guide.identify_button.isEnabled()
    assert not guide.off_check_button.isEnabled()


def test_idn_observation_enables_only_explicit_protective_off_step(guide):
    real(guide)
    off = QSignalSpy(guide.request_off_check)
    guide.update_diagnostic(report())
    assert guide.current_step == 4
    assert "6517A 응답 확인" in guide.next_label.text()
    assert "TEST-SERIAL" in guide.detail_label.text()
    assert "TEST-FW" in guide.detail_label.text()
    assert off.count() == 0
    guide.off_check_button.click()
    assert off.count() == 1


@pytest.mark.parametrize("updates", [{"simulation": True}, {"transport_origin": "injected"}])
def test_simulator_or_injected_report_is_not_real_instrument_proof(guide, updates):
    real(guide)
    guide.update_diagnostic(report(**updates))
    assert guide.current_step == 3
    assert not guide.off_check_button.isEnabled()
    assert "가상/주입" in guide.detail_label.text()


def test_other_model_report_is_not_accepted_as_6517a(guide):
    real(guide)
    guide.update_diagnostic(report(identity={"model": "6517B"}))
    assert guide.current_step == 3
    assert not guide.off_check_button.isEnabled()


@pytest.mark.parametrize("field,value", [("resource", "GPIB1::5::INSTR"), ("backend", "@py")])
def test_old_diagnostic_cannot_be_reused_for_another_target_or_backend(guide, field, value):
    real(guide)
    guide.update_diagnostic(report())
    assert guide.current_step == 4
    context = dict(simulation=False, resource=RESOURCE, backend="@ivi")
    context[field] = value
    guide.set_context(**context)
    assert guide.current_step == 3
    assert not guide.off_check_button.isEnabled()
    assert "TEST-SERIAL" not in guide.detail_label.text()


def test_off_diagnostic_is_historical_and_never_grants_session_start(guide):
    real(guide)
    guide.update_diagnostic(
        report(mode="OUTPUT_OFF_CHECK", output_state="OFF", output_OFF_confirmed=True)
    )
    assert guide.current_step == 5
    assert "진단 시 OFF 관찰" in guide.next_label.text()
    assert "현재 연결의 승인 상태가 아닙니다" in guide.detail_label.text()
    assert "ARM" in guide.detail_label.text() and "START" in guide.detail_label.text()
    assert not hasattr(guide, "request_start")
    assert not hasattr(guide, "request_arm")


def test_live_session_approval_disappears_on_disconnect(guide):
    real(guide)
    guide.update_diagnostic(report())
    guide.update_status(
        dict(
            state="ARMED",
            output_state="OFF",
            identity={"model": "6517A", "simulation": False},
            commissioning={"ready": True, "session_id": "test"},
            can_arm=False,
            can_start=True,
        )
    )
    assert guide.current_step == 6
    assert "직접 누르세요" in guide.next_label.text()
    assert not guide.off_check_button.isEnabled()
    guide.update_status(dict(state="DISCONNECTED", can_start=True, commissioning={"ready": True}))
    assert guide.current_step == 3
    assert not guide.off_check_button.isEnabled()
    assert "ARM 완료" not in guide.next_label.text()


def test_unknown_output_does_not_become_ready_from_an_inconsistent_status(guide):
    real(guide)
    guide.update_status(state="ARMED", output_state="UNKNOWN", can_start=True)
    assert "UNKNOWN" in guide.next_label.text()
    assert "잔류 전압" in guide.next_label.text()
    assert guide.current_step != 6


def test_off_failure_shows_prioritized_action_and_report_location(guide):
    real(guide)
    guide.update_diagnostic(
        report(
            ok=False,
            issues=[
                {"code": "IO_TIMEOUT", "action": "주소를 확인하세요."},
                {"code": "OUTPUT_OFF_UNCONFIRMED", "action": "독립 차단을 확인하세요."},
            ],
        )
    )
    assert "OUTPUT_OFF_UNCONFIRMED" in guide.detail_label.text()
    assert "독립 차단" in guide.detail_label.text()
    assert "diagnostic.json" in guide.detail_label.text()
    assert "/tmp/trial-report/diagnostic.json" in guide.detail_label.toolTip()
    assert guide.detail_label.textFormat() == Qt.TextFormat.PlainText
    assert not guide.off_check_button.isEnabled()


@pytest.mark.parametrize("flags", [{"busy": True}, {"closing": True}])
def test_busy_or_closing_cannot_issue_additional_actions(guide, flags):
    real(guide)
    guide.update_diagnostic(report())
    real(guide, **flags)
    assert all(
        not button.isEnabled()
        for button in (
            guide.real_mode_button,
            guide.discover_button,
            guide.identify_button,
            guide.off_check_button,
            guide.settings_button,
        )
    )


def test_simulated_connection_requires_disconnect_before_switching_to_hardware(guide):
    guide.update_status(state="OUTPUT_OFF_CONFIRMED", output_state="OFF", can_arm=True)
    assert "시뮬레이션 연결을 종료" in guide.next_label.text()
    assert not guide.real_mode_button.isEnabled()


def test_target_change_while_connected_does_not_reuse_old_ready_state(guide):
    real(guide)
    guide.update_status(state="ARMED", output_state="OFF", can_start=True)
    guide.set_context(simulation=False, resource="GPIB2::4::INSTR", backend="@ivi")
    assert "연결 종료" in guide.next_label.text()
    assert guide.current_step != 6
    assert not guide.off_check_button.isEnabled()
