"""Optional sample dimensions persist without granting any measurement permission."""

import json
from dataclasses import replace

import pytest
from PySide6.QtWidgets import QFormLayout

from keithley6517a.config import ConfigurationError, RunConfig
from keithley6517a.ui.main_window import MainWindow
from keithley6517a.ui.sample_geometry import SampleGeometryFields
from keithley6517a.ui.test_setup import TestSetupDialog as SetupDialog


def dimensions(widget, *, length="20", width="10", depth="2", axis="D"):
    widget.length.setText(length)
    widget.width.setText(width)
    widget.depth.setText(depth)
    widget.axis.setCurrentIndex(widget.axis.findData(axis))


@pytest.fixture
def window(qtbot):
    value = MainWindow(lambda *a, **kw: pytest.fail("Editing geometry must not connect"))

    def close(widget):
        widget.close()
        qtbot.waitUntil(lambda: widget._closed, timeout=20000)

    qtbot.addWidget(value, before_close_func=close)
    return value


def test_geometry_is_below_sample_id_in_both_forms_and_optional_by_default(window, qtbot):
    dialog = SetupDialog(RunConfig())
    qtbot.addWidget(dialog)
    for form in (window, dialog):
        fields = form.sample_geometry
        layout = next(
            layout
            for layout in form.findChildren(QFormLayout)
            if layout.labelForField(fields) is not None
        )
        id_row, _ = layout.getWidgetPosition(form.sample_id)
        geometry_row, _ = layout.getWidgetPosition(fields)
        assert geometry_row == id_row + 1
        assert layout.labelForField(fields).text() == "치수 (mm)"
        assert fields.config_values() == dict(
            sample_length_mm=None,
            sample_width_mm=None,
            sample_depth_mm=None,
            current_path_axis=None,
        )
        assert "전극" in fields.axis.toolTip()
    assert window.config_from_controls().simulation
    assert window.config_from_controls().voltages == (0.0,)
    assert not window.arm_button.isEnabled() and not window.start_button.isEnabled()
    assert window.worker.runner is None


def test_main_dimensions_roundtrip_clear_and_partial_metadata(window, tmp_path):
    dimensions(window.sample_geometry)
    window.sample_id.setText("FILM-A")
    config = window.config_from_controls()
    assert config.effective_geometry_m == pytest.approx((2e-4, 2e-3))
    assert config.sample_length_mm == 20 and config.sample_depth_mm == 2
    path = tmp_path / "sample-config.json"
    path.write_text(json.dumps(config.to_dict()))
    window.sample_geometry.length.clear()
    assert window.config_from_controls().effective_geometry_m == (None, None)
    assert window.resistivity_label.isHidden()
    window.load_config(path)
    assert window.config_from_controls() == config
    assert window.sample_geometry.axis.currentData() == "D"
    for field in window.sample_geometry.fields.values():
        field.clear()
    window.sample_geometry.axis.setCurrentIndex(0)
    assert window.config_from_controls().effective_geometry_m == (None, None)
    assert window.worker.runner is None


def test_setup_dimensions_change_only_metadata_and_are_saved_in_result(qtbot, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Sample dimensions must never open an instrument")

    monkeypatch.setattr("keithley6517a.transport.visa.VisaTransport.open", forbidden)
    original = replace(
        RunConfig(),
        sample_length_mm=20,
        sample_width_mm=10,
        sample_depth_mm=2,
        current_path_axis="D",
    )
    dialog = SetupDialog(original)
    qtbot.addWidget(dialog)
    assert dialog.build_config() == original
    dimensions(dialog.sample_geometry, axis="L")
    dialog.accept()
    assert dialog.result_config.current_path_axis == "L"
    assert dialog.result_config.effective_geometry_m == pytest.approx((2e-5, 2e-2))
    assert dialog.result_config.voltages == (0.0,)
    assert dialog.result_config.current_trip_A is None
    assert not dialog.result_config.residual_warning_ack
    assert not dialog.result_config.operator_setup_acknowledged


def test_visa_selection_preserves_sample_dimensions_but_resets_electrical_approvals(window):
    window.voltages.setText("3")
    window.trip.setText("1e-8")
    window.ack.setChecked(True)
    window.sample_id.setText("FILM-B")
    dimensions(window.sample_geometry, axis="W")
    window.transport.setCurrentIndex(1)
    config = window.config_from_controls()
    assert config.sample_id == "FILM-B"
    assert config.current_path_axis == "W" and config.sample_width_mm == 10
    assert config.effective_geometry_m == pytest.approx((4e-5, 1e-2))
    assert config.transport == "visa" and not config.simulation
    assert config.voltages == (0.0,) and config.current_trip_A is None
    assert not config.residual_warning_ack and not config.operator_setup_acknowledged
    assert window.worker.runner is None


def test_invalid_pending_dimension_does_not_prevent_safe_visa_reset(window):
    window.voltages.setText("3")
    window.trip.setText("1e-8")
    window.sample_geometry.length.setText("not a number")
    window.transport.setCurrentIndex(1)
    assert window.sample_geometry.length.text() == "not a number"
    assert window.transport.currentData() == "visa"
    assert window.voltages.text() == "0.0" and window.trip.text() == ""
    assert not window.operator_setup_ack.isChecked() and not window.ack.isChecked()
    with pytest.raises(ConfigurationError, match="길이 L"):
        window.config_from_controls()
    assert window.worker.runner is None


@pytest.mark.parametrize("invalid", ["nan", "not a number"])
def test_bad_dimension_has_field_specific_error(qtbot, invalid):
    widget = SampleGeometryFields()
    qtbot.addWidget(widget)
    widget.depth.setText(invalid)
    with pytest.raises(ConfigurationError, match="두께 D"):
        widget.config_values()


def test_resistivity_readout_uses_saved_row_and_never_fabricates_zero(window):
    dimensions(window.sample_geometry)
    assert not window.resistivity_label.isHidden()
    window._on_sample(
        dict(
            elapsed_s=1,
            current_raw_A=1e-9,
            resistance_apparent_ohm=1e9,
            resistance_corrected_ohm=2e9,
            resistivity_ohm_m=2e8,
        )
    )
    assert window.resistivity_label.text() == "ρ 200 MΩ·m"
    assert "보정 저항" in window.resistivity_label.toolTip()
    window._mark_stale()
    assert window.resistivity_label.text() == "ρ 200 MΩ·m"
    assert window.reading_state_label.property("stale") is True
    window._on_sample(dict(elapsed_s=2, resistivity_ohm_m=None))
    assert window.resistivity_label.text() == "ρ — Ω·m"
    window._on_sample(dict(elapsed_s=3, resistivity_ohm_m=2e8))
    window.sample_geometry.width.clear()
    assert window.resistivity_label.isHidden()
    assert window.resistivity_label.text() == "ρ — Ω·m"


def test_legacy_geometry_is_preserved_without_inventing_dimensions(window):
    legacy = replace(RunConfig(), area_m2=2e-4, thickness_m=2e-3)
    window._load_controls(legacy.to_dict())
    assert all(not field.text() for field in window.sample_geometry.fields.values())
    assert window.sample_geometry.axis.currentText() == "미지정"
    assert "기존 설정" in window.sample_geometry.toolTip()
    assert not window.resistivity_label.isHidden()
    assert window.config_from_controls() == legacy
    window.sample_geometry.length.setText("20")
    assert window.config_from_controls().effective_geometry_m == (None, None)
    assert window.resistivity_label.isHidden()
    window.sample_geometry.length.clear()
    assert window.config_from_controls().effective_geometry_m == legacy.effective_geometry_m
    assert not window.resistivity_label.isHidden()
