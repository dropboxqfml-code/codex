"""The trial settings dialog never connects, commissions, arms, or starts hardware."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from keithley6517a.config import ConfigurationError, RunConfig
from keithley6517a.driver.instrument import Instrument
from keithley6517a.measurement.runner import MeasurementRunner
from keithley6517a.transport.visa import VisaTransport
from keithley6517a.ui.test_setup import TestSetupDialog as SetupDialog


def dialog_for(qtbot, config=None, **kwargs):
    dialog = SetupDialog(config or RunConfig(), **kwargs)
    qtbot.addWidget(dialog)
    return dialog


def fill_real(dialog):
    dialog.real_mode.setChecked(True)
    dialog.resource.setCurrentText("GPIB0::27::INSTR")
    dialog.sample_id.setText("TEST-SAMPLE")
    dialog.current_trip.setText("1e-8")
    dialog.sample_rating.setText("5")
    dialog.fixture_rating.setText("10")
    dialog.cable_rating.setText("20")
    dialog.ceiling.setText("5")
    dialog.fixture_id.setText("FIXTURE-TEST-ONLY")
    dialog.approved_by.setText("test operator")
    dialog.rating_approval.setText("software-test-only approval")
    dialog.resistive_limit.setCurrentIndex(1)
    for checkbox in (
        dialog.installation,
        dialog.hardware_protection,
        dialog.lid_open,
        dialog.lid_closed,
        dialog.residual_ack,
    ):
        checkbox.setChecked(True)


def test_default_preserves_simulation_zero_and_missing_approvals_without_io(qtbot, monkeypatch):
    actions = []

    def forbidden(*args, **kwargs):
        actions.append("hardware call")
        raise AssertionError("A settings dialog must not perform instrument I/O")

    monkeypatch.setattr(VisaTransport, "open", forbidden)
    monkeypatch.setattr(Instrument, "connect", forbidden)
    monkeypatch.setattr(MeasurementRunner, "connect", forbidden)
    monkeypatch.setattr(MeasurementRunner, "arm", forbidden)
    monkeypatch.setattr(MeasurementRunner, "start", forbidden)
    original = RunConfig()
    dialog = dialog_for(qtbot, original, resources=["GPIB0::27::INSTR"])
    assert not dialog.real_mode.isChecked()
    assert not dialog.installation.isChecked()
    assert not dialog.hardware_protection.isChecked()
    assert not dialog.lid_open.isChecked()
    assert not dialog.lid_closed.isChecked()
    assert not dialog.residual_ack.isChecked()
    assert dialog.current_trip.text() == ""
    assert dialog.resistive_limit.currentData() is None
    assert dialog.build_config() == original
    assert dialog.result_config is None
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.result_config == original
    assert not actions


def test_explicit_real_form_creates_snapshot_but_never_live_commissioning(qtbot):
    dialog = dialog_for(qtbot)
    fill_real(dialog)
    dialog.voltages.setText("0, 1, 2")
    dialog.visa_backend.setText("C:\\Program Files\\Vendor\\visa64.dll")
    dialog.send_end.setChecked(True)
    dialog.line_frequency.setCurrentText("50")
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    config = dialog.result_config
    config.validate(for_arm=True)
    assert config.simulation is False and config.transport == "visa"
    assert config.voltages == (0, 1, 2)
    assert config.protocol == "list"
    assert config.current_trip_A == 1e-8
    assert config.effective_ceiling == 5
    assert config.line_frequency_hz == 50
    assert config.visa_backend == "C:\\Program Files\\Vendor\\visa64.dll"
    assert config.resistive_limit_enabled is False
    assert config.commissioning["hardware_protection_reviewed"] is True
    assert "ready" not in config.commissioning
    assert "session_id" not in config.commissioning
    assert "연결" in dialog.status_label.text()


def test_real_missing_records_can_be_applied_as_draft_but_cannot_arm(qtbot, monkeypatch):
    monkeypatch.setattr(
        MeasurementRunner, "connect", lambda *a: pytest.fail("Draft apply must not connect")
    )
    monkeypatch.setattr(
        MeasurementRunner, "arm", lambda *a: pytest.fail("Draft apply must not ARM")
    )
    dialog = dialog_for(qtbot)
    dialog.real_mode.setChecked(True)
    dialog.resource.setCurrentText("GPIB0::27::INSTR")
    dialog.accept()
    assert dialog.result_config is not None
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert "초안 적용 가능" in dialog.status_label.text()
    with pytest.raises(ConfigurationError):
        dialog.result_config.validate(for_arm=True)
    assert not dialog.hardware_protection.isChecked()
    fill_real(dialog)
    dialog.lid_closed.setChecked(False)
    dialog.accept()
    assert dialog.result_config is not None
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert not dialog.result_config.commissioning.get("lid_closed_one", False)
    with pytest.raises(ConfigurationError, match="commissioning"):
        dialog.result_config.validate(for_arm=True)


@pytest.mark.parametrize(
    "field,value",
    [
        ("current_trip", "NaN"),
        ("fixture_rating", "-10"),
        ("dwell", "0"),
        ("voltages", "1,,2"),
        ("ceiling", "inf"),
        ("current_trip", "nonsense"),
        ("reference_resistance", "-1"),
        ("simulation_resistance", "0"),
    ],
)
def test_numeric_errors_are_visible_and_cannot_be_applied(qtbot, field, value):
    dialog = dialog_for(qtbot)
    fill_real(dialog)
    getattr(dialog, field).setText(value)
    with pytest.raises(ConfigurationError):
        dialog.build_config()
    dialog.accept()
    assert dialog.result_config is None
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert "설정 적용 안 됨" in dialog.status_label.text()


def test_cancel_preserves_original_and_explicit_loaded_approval_values(qtbot):
    dialog = dialog_for(qtbot)
    fill_real(dialog)
    prepared = dialog.build_config()
    original = RunConfig.from_dict(
        dict(
            prepared.to_dict(),
            sample_metadata={"material": "test"},
            temperature_C=23.4,
            current_autorange=False,
            current_range_A=2e-10,
            read_termination=None,
            write_termination="CUSTOM",
            seed=1234,
        )
    )
    loaded = dialog_for(qtbot, original)
    assert loaded.installation.isChecked()
    assert loaded.hardware_protection.isChecked()
    assert loaded.lid_open.isChecked() and loaded.lid_closed.isChecked()
    assert loaded.build_config() == original
    loaded.sample_id.setText("edited only in dialog")
    loaded.reject()
    assert loaded.result_config is None
    assert original.sample_id == "TEST-SAMPLE"
    assert original.sample_metadata["material"] == "test"


def test_native_real_cannot_be_applied_and_request_quantization_is_visible(qtbot):
    dialog = dialog_for(qtbot)
    fill_real(dialog)
    dialog.voltages.setText("1.001")
    assert "1.001" in dialog.status_label.text()
    assert "1.0" in dialog.status_label.text()
    dialog.mode.setCurrentText("NATIVE_RESISTANCE")
    dialog.accept()
    assert dialog.result_config is None
    assert "FVMI_CURRENT" in dialog.status_label.text()


def test_eoi_only_terminators_and_selection_are_preserved(qtbot):
    dialog = dialog_for(qtbot, resources=["GPIB0::4::INSTR", "GPIB0::5::INSTR"])
    assert dialog.resource.count() == 2
    dialog.resource.setCurrentText("GPIB0::5::INSTR")
    for combo in (dialog.read_termination, dialog.write_termination):
        combo.setCurrentIndex(next(i for i in range(combo.count()) if combo.itemData(i) is None))
    config = dialog.build_config()
    assert config.resource == "GPIB0::5::INSTR"
    assert config.read_termination is None and config.write_termination is None
    assert config.send_end is True


def fill_operator(dialog):
    dialog.real_mode.setChecked(True)
    dialog.setup_policy.setCurrentIndex(1)
    dialog.resource.setCurrentText("GPIB0::27::INSTR")
    dialog.current_trip.setText("1e-8")
    dialog.residual_ack.setChecked(True)
    dialog.resistive_limit.setCurrentIndex(1)
    dialog.operator_ack.setChecked(True)


def test_operator_form_uses_explicit_ack_without_inventing_fixture_approval(qtbot):
    dialog = dialog_for(qtbot)
    fill_operator(dialog)
    dialog.accept()
    config = dialog.result_config
    config.validate(for_arm=True)
    assert config.setup_policy == "operator_low_voltage"
    assert config.operator_setup_acknowledged is True
    assert config.source_range_V == 100
    assert config.effective_ceiling == 10
    assert config.sample_limit_V is None and config.fixture_limit_V is None
    assert config.cable_limit_V is None and config.rating_approval == ""
    assert not any(config.commissioning.values())
    assert not dialog.installation.isChecked()
    assert not dialog.hardware_protection.isChecked()
    assert not dialog.lid_open.isChecked() and not dialog.lid_closed.isChecked()
    assert "선택 입력" in dialog.approval_note.text()
    assert not dialog.source_range.model().item(1).isEnabled()


def test_operator_draft_applies_without_ack_but_readiness_stays_incomplete(qtbot):
    dialog = dialog_for(qtbot)
    fill_operator(dialog)
    dialog.operator_ack.setChecked(False)
    assert "ARM 준비 미완료" in dialog.status_label.text()
    dialog.accept()
    assert dialog.result_config is not None
    assert dialog.result_config.operator_setup_acknowledged is False
    with pytest.raises(ConfigurationError):
        dialog.result_config.validate(for_arm=True)


@pytest.mark.parametrize("field,value", [("ceiling", "11"), ("voltages", "10.005")])
def test_operator_out_of_range_values_cannot_be_applied(qtbot, field, value):
    dialog = dialog_for(qtbot)
    fill_operator(dialog)
    getattr(dialog, field).setText(value)
    dialog.accept()
    assert dialog.result_config is None
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert "설정 적용 안 됨" in dialog.status_label.text()


def test_operator_cannot_apply_programmatic_1000v_range_or_silently_fix_high_ceiling(qtbot):
    dialog = dialog_for(qtbot)
    dialog.ceiling.setText("20")
    dialog.source_range.setCurrentText("1000")
    dialog.setup_policy.setCurrentIndex(1)
    assert dialog.source_range.currentText() == "100"
    assert dialog.ceiling.text() == "20"
    with pytest.raises(ConfigurationError):
        dialog.build_config()
    dialog.ceiling.setText("10")
    dialog.source_range.setCurrentIndex(1)
    with pytest.raises(ConfigurationError):
        dialog.build_config()


@pytest.mark.parametrize("real", [False, True])
def test_reference_preset_only_populates_values_and_never_grants_execution(
    qtbot, monkeypatch, real
):
    def forbidden(*args, **kwargs):
        pytest.fail("Reference preset must not access or start hardware")

    monkeypatch.setattr(VisaTransport, "open", forbidden)
    monkeypatch.setattr(Instrument, "connect", forbidden)
    monkeypatch.setattr(MeasurementRunner, "start", forbidden)
    dialog = dialog_for(qtbot)
    dialog.real_mode.setChecked(real)
    dialog.setup_policy.setCurrentIndex(1)
    dialog.reference_preset_button.click()
    config = dialog.build_config()
    assert config.simulation is not real
    assert config.setup_policy == "operator_low_voltage"
    assert config.voltages == (1,)
    assert config.current_trip_A == 1e-8
    assert config.source_range_V == 100 and config.voltage_ceiling_V == 10
    assert config.sample_metadata["reference_resistance_ohm"] == 1e9
    assert config.simulation_resistance_ohm == 1e9
    assert config.operator_setup_acknowledged is False
    assert config.residual_warning_ack is False
    assert config.resistive_limit_enabled is None
    assert not any(config.commissioning.values())
    assert "1 nA" in dialog.reference_current_label.text()
    assert "실측값 아님" in dialog.reference_current_label.text()
    assert "ARM 준비 미완료" in dialog.status_label.text()
    with pytest.raises(ConfigurationError):
        config.validate(for_arm=True)


def test_reference_expected_current_uses_programmed_resolution_and_keeps_sign(qtbot):
    config = RunConfig(bipolar_authorized=True)
    dialog = dialog_for(qtbot, config)
    dialog.reference_resistance.setText("1e9")
    dialog.voltages.setText("1.001, -1, 0")
    label = dialog.reference_current_label.text()
    assert "설정 분해능 기준" in label
    assert "1 V → 1 nA" in label
    assert "-1 V → -1 nA" in label
    assert "0 V → 0 A" in label


def test_default_apply_shows_every_missing_operator_setting_without_applying(qtbot, monkeypatch):
    monkeypatch.setattr(
        VisaTransport, "open", lambda *a, **k: pytest.fail("Settings must not open VISA")
    )
    dialog = dialog_for(qtbot)
    dialog.real_mode.setChecked(True)
    dialog.setup_policy.setCurrentIndex(1)
    dialog.resource.setCurrentText("GPIB0::27::INSTR")
    assert dialog.ready_button.text() == "측정 설정 적용"
    fields = {
        dialog.issue_list.item(i).data(Qt.ItemDataRole.UserRole)
        for i in range(dialog.issue_list.count())
    }
    assert {
        "current_trip_A",
        "operator_setup_acknowledged",
        "residual_warning_ack",
        "resistive_limit_enabled",
    } <= fields
    dialog.ready_button.click()
    assert dialog.result_config is None
    assert dialog.applied_as_draft is None
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert "필수 설정" in dialog.status_label.text()
    assert dialog.issue_list.count() >= 4


def test_ready_apply_and_draft_apply_have_distinct_results_without_hardware(qtbot, monkeypatch):
    monkeypatch.setattr(
        Instrument, "connect", lambda *a, **k: pytest.fail("Apply must not connect")
    )
    draft = dialog_for(qtbot)
    draft.real_mode.setChecked(True)
    draft.setup_policy.setCurrentIndex(1)
    draft.resource.setCurrentText("GPIB0::27::INSTR")
    draft.draft_button.click()
    assert draft.result() == QDialog.DialogCode.Accepted
    assert draft.result_config is not None and draft.applied_as_draft is True
    with pytest.raises(ConfigurationError):
        draft.result_config.validate(for_arm=True)
    ready = dialog_for(qtbot)
    fill_operator(ready)
    ready.ready_button.click()
    assert ready.result() == QDialog.DialogCode.Accepted
    assert ready.result_config is not None and ready.applied_as_draft is False
    ready.result_config.validate(for_arm=True)
    assert not any(ready.result_config.commissioning.values())


def test_operator_required_controls_share_the_basic_page(qtbot):
    dialog = dialog_for(qtbot)
    fill_operator(dialog)
    for field in (
        "current_trip_A",
        "operator_setup_acknowledged",
        "residual_warning_ack",
        "resistive_limit_enabled",
    ):
        assert dialog.focus_field(field)
        assert dialog.tabs.currentIndex() == 0
    assert dialog.focus_field("commissioning.fixture_id")
    assert dialog.tabs.currentIndex() == 2


def test_focus_argument_opens_requested_field_and_preserves_values(qtbot):
    dialog = dialog_for(qtbot, focus_field="nplc")
    dialog.show()
    qtbot.waitUntil(lambda: dialog.tabs.currentIndex() == 1)
    assert dialog.focusWidget() == dialog.nplc
    assert dialog.nplc.text() == "10.0"
    assert dialog.result_config is None
