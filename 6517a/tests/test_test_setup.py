"""The trial settings dialog never connects, commissions, arms, or starts hardware."""

import pytest
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


def test_real_missing_records_are_rejected_and_not_auto_checked(qtbot):
    dialog = dialog_for(qtbot)
    dialog.real_mode.setChecked(True)
    dialog.resource.setCurrentText("GPIB0::27::INSTR")
    dialog.accept()
    assert dialog.result_config is None
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert "설정 적용 안 됨" in dialog.status_label.text()
    assert not dialog.hardware_protection.isChecked()
    fill_real(dialog)
    dialog.lid_closed.setChecked(False)
    dialog.accept()
    assert dialog.result_config is None
    assert dialog.result() == QDialog.DialogCode.Rejected


@pytest.mark.parametrize(
    "field,value",
    [
        ("current_trip", "NaN"),
        ("fixture_rating", "-10"),
        ("dwell", "0"),
        ("voltages", "1,,2"),
        ("ceiling", "inf"),
        ("current_trip", "nonsense"),
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
    assert "native" in dialog.status_label.text().lower()


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
