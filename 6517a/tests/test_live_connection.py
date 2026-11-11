"""Live-connection UI integration uses only explicit mocked diagnostic observations."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from keithley6517a.config import RunConfig
from keithley6517a.diagnostics import run_diagnostics
from keithley6517a.transport.ni4882 import NIBackendError
from keithley6517a.ui.main_window import MainWindow


@pytest.fixture
def window(qtbot, tmp_path):
    window = MainWindow(lambda *a, **k: pytest.fail("Connection guidance must not open a run"))

    def orderly_close(widget):
        if not widget._closed:
            widget.close()
            qtbot.waitUntil(lambda: widget._closed)

    qtbot.addWidget(window, before_close_func=orderly_close)
    window.output_dir.setText(str(tmp_path))
    yield window


@pytest.mark.parametrize("entry", ["guide", "mode_selector"])
def test_real_entry_clears_simulated_voltage_trip_and_approvals(window, entry, tmp_path):
    simulated = replace(
        RunConfig(),
        voltages=(8,),
        current_trip_A=1e-6,
        residual_warning_ack=True,
        sample_limit_V=100,
        fixture_limit_V=100,
        cable_limit_V=100,
        rating_approval="simulation-only approval",
        commissioning={"installation_confirmed": True},
        resource="GPIB1::5::INSTR",
        output_directory=str(tmp_path),
    )
    window._load_controls(simulated.to_dict())
    if entry == "guide":
        window.connection_guide.real_mode_button.click()
    else:
        window.transport.setCurrentIndex(1)
    real = window.config_from_controls()
    assert not real.simulation
    assert real.voltages == (0.0,)
    assert real.current_trip_A is None
    assert real.sample_limit_V is None and real.fixture_limit_V is None
    assert real.cable_limit_V is None and real.rating_approval == ""
    assert not real.residual_warning_ack and not real.commissioning
    assert real.resource == "GPIB1::5::INSTR"
    assert real.visa_backend == "@ivi"
    assert real.output_directory == str(tmp_path)
    assert window.worker.runner is None
    assert not window.arm_button.isEnabled() and not window.start_button.isEnabled()


def test_loading_real_review_settings_preserves_requested_plan_without_starting(window):
    settings = replace(
        RunConfig(),
        simulation=False,
        transport="visa",
        resource="GPIB1::5::INSTR",
        visa_backend="@ivi",
        voltages=(1,),
        current_trip_A=5e-9,
        sample_limit_V=5,
    )
    window._load_controls(settings.to_dict())
    assert window.config_from_controls() == settings
    assert window.worker.runner is None
    assert not window.arm_button.isEnabled()


def test_optional_backend_choice_is_configuration_only_and_default_stays_native(
    window, monkeypatch
):
    monkeypatch.setattr(
        "keithley6517a.transport.visa.prepare_backend",
        lambda *a, **k: pytest.fail("Selecting a profile must not load a driver"),
    )
    assert window.config_from_controls().visa_backend is None
    window.backend_profiles.setCurrentIndex(1)
    assert window.backend.text() == "@py"
    assert window.config_from_controls().simulation
    assert window.worker.runner is None
    window.backend_profiles.setCurrentIndex(0)
    assert window.backend.text() == "@ivi"
    assert window.worker.runner is None


def test_guide_idn_and_off_are_separate_commands_and_never_arm(
    window, qtbot, monkeypatch, tmp_path
):
    resource = "GPIB1::5::INSTR"
    calls = []

    def diagnose(**options):
        calls.append(options)
        return dict(
            ok=True,
            mode="OUTPUT_OFF_CHECK" if options["confirm_off"] else "IDN_ONLY",
            settings={"resource": resource, "backend": "@ivi"},
            simulation=False,
            transport_origin="visa",
            identity={"model": "6517A", "serial": "TEST", "firmware": "TEST-FW"},
            output_OFF_confirmed=options["confirm_off"],
            output_state="OFF" if options["confirm_off"] else "UNKNOWN",
            residual_voltage_state="UNVERIFIED",
            issues=[],
            report_path=str(tmp_path / "diagnostic.json"),
        )

    monkeypatch.setattr("keithley6517a.diagnostics.run_diagnostics", diagnose)
    window.connection_guide.real_mode_button.click()
    window.resource.setText(resource)
    window.connection_guide.identify_button.click()
    qtbot.waitUntil(lambda: len(calls) == 1 and not window._busy)
    assert calls[0]["confirm_off"] is False
    assert window.connection_guide.current_step == 4
    assert "TEST-FW" in window.connection_guide.detail_label.text()
    window.connection_guide.off_check_button.click()
    qtbot.waitUntil(lambda: len(calls) == 2 and not window._busy)
    assert calls[1]["confirm_off"] is True
    assert window.connection_guide.current_step == 5
    assert window.worker.runner is None
    assert not window.arm_button.isEnabled() and not window.start_button.isEnabled()
    window.resource.setText("GPIB1::6::INSTR")
    assert window.connection_guide.current_step == 3
    assert not window.connection_guide.off_check_button.isEnabled()


def test_discovery_failure_is_saved_and_displayed_without_a_second_session(
    window, qtbot, monkeypatch, tmp_path
):
    def missing(_):
        raise NIBackendError("NI_DRIVER_UNAVAILABLE", "test driver missing")

    monkeypatch.setattr("keithley6517a.transport.visa.VisaTransport.list_resources", missing)
    window.connection_guide.real_mode_button.click()
    window.backend_profiles.setCurrentIndex(1)
    window.connection_guide.discover_button.click()
    qtbot.waitUntil(
        lambda: (
            not window._busy
            and "NI_DRIVER_UNAVAILABLE" in window.connection_guide.detail_label.text()
        )
    )
    assert window.worker.runner is None
    reports = list(tmp_path.glob("connection_checks/*/diagnostic.json"))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text())
    assert report["output_state"] == "UNKNOWN"
    assert not report["output_ON_sent"]
    assert not report["measurement_started"]


@pytest.mark.parametrize(
    "code",
    [
        "NI_DRIVER_UNAVAILABLE",
        "NI_BACKEND_DEPENDENCY_MISSING",
        "NI_BACKEND_ARCHITECTURE_MISMATCH",
        "NI_BACKEND_INCOMPATIBLE",
    ],
)
def test_ni_preflight_failures_keep_stable_actionable_codes(tmp_path, code):
    class Factory:
        @staticmethod
        def list_resources(_):
            raise NIBackendError(code, "mock preflight failure")

    report = run_diagnostics(backend="@py", output_directory=tmp_path, transport_factory=Factory)
    assert report["issues"][0]["code"] == code
    assert report["issues"][0]["action"]
    assert report["report_saved"]
    assert not report["ok"] and report["output_state"] == "UNKNOWN"
    assert Path(report["raw_io_path"]).read_text() == ""
