"""End-user trial entry points: discovery, diagnosis, form setup, and common safety policy."""

import json
import threading
from dataclasses import replace

import pytest

from keithley6517a import cli
from keithley6517a.clock import FakeClock
from keithley6517a.config import ConfigurationError, RunConfig
from keithley6517a.measurement.runner import MeasurementRunner
from keithley6517a.ui.main_window import MainWindow


def close_window(qtbot, window):
    window.close()
    qtbot.waitUntil(lambda: window._closed)


def test_resource_list_does_not_auto_select_connect_or_arm(qtbot, monkeypatch):
    calls = []
    ui_thread = threading.get_ident()

    def resources(backend):
        calls.append((backend, threading.get_ident()))
        return ("GPIB0::27::INSTR", "GPIB1::5::INSTR")

    monkeypatch.setattr("keithley6517a.transport.visa.VisaTransport.list_resources", resources)
    window = MainWindow(lambda *a, **k: pytest.fail("Discovery must not connect"))
    qtbot.addWidget(window)
    try:
        window.backend.setText("@ivi")
        window.discover_button.click()
        qtbot.waitUntil(lambda: window.resource_choices.count() == 3 and not window._busy)
        assert calls == [("@ivi", calls[0][1])]
        assert calls[0][1] != ui_thread
        assert window.resource.text() == ""
        window._select_resource(1)
        assert window.resource.text() == "GPIB0::27::INSTR"
        assert window.worker.runner is None
        assert not window.arm_button.isEnabled()
        assert not window.start_button.isEnabled()
    finally:
        close_window(qtbot, window)


def test_gui_diagnosis_is_explicit_and_off_check_requires_real_selection(
    qtbot, monkeypatch, tmp_path
):
    calls = []
    ui_thread = threading.get_ident()
    report_path = tmp_path / "diagnostic.json"

    def diagnose(**options):
        calls.append((options, threading.get_ident()))
        return dict(
            ok=True,
            mode="OUTPUT_OFF_CHECK" if options["confirm_off"] else "IDN_ONLY",
            output_state="OFF" if options["confirm_off"] else "UNKNOWN",
            report_path=str(report_path),
        )

    monkeypatch.setattr("keithley6517a.diagnostics.run_diagnostics", diagnose)
    window = MainWindow(lambda *a, **k: pytest.fail("Diagnosis must not create a measurement"))
    qtbot.addWidget(window)
    try:
        window.resource.setText("GPIB0::27::INSTR")
        window.backend.setText("@ivi")
        window.output_dir.setText(str(tmp_path))
        assert not window.off_check_button.isEnabled()
        window._diagnose(True)
        assert not calls
        window.diagnose_button.click()
        qtbot.waitUntil(lambda: len(calls) == 1 and not window._busy)
        assert calls[0][0]["confirm_off"] is False
        assert calls[0][0]["resource"] == "GPIB0::27::INSTR"
        assert calls[0][0]["backend"] == "@ivi"
        assert calls[0][1] != ui_thread
        assert "UNKNOWN" in window.diagnostic_label.text()
        assert window.worker.runner is None
        window.transport.setCurrentIndex(1)
        assert window.off_check_button.isEnabled()
        window.off_check_button.click()
        qtbot.waitUntil(lambda: len(calls) == 2 and not window._busy)
        assert calls[1][0]["confirm_off"] is True
        assert "OFF" in window.diagnostic_label.text()
        assert "UNVERIFIED" in window.diagnostic_label.text()
        assert not window.arm_button.isEnabled()
        assert not window.start_button.isEnabled()
    finally:
        close_window(qtbot, window)


def test_connected_worker_disables_separate_diagnostic_sessions(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "keithley6517a.transport.visa.VisaTransport.list_resources",
        lambda *a: pytest.fail("Cannot open a second session"),
    )
    window = MainWindow(lambda cfg, **cb: MeasurementRunner(cfg, clock=FakeClock(), **cb))
    qtbot.addWidget(window)
    try:
        config = replace(RunConfig(), output_directory=str(tmp_path))
        window._load_controls(config.to_dict())
        window.connect_button.click()
        qtbot.waitUntil(lambda: window._connected and not window._busy)
        assert not window.discover_button.isEnabled()
        assert not window.diagnose_button.isEnabled()
        assert not window.off_check_button.isEnabled()
        assert not window.setup_button.isEnabled()
        window._discover()
    finally:
        close_window(qtbot, window)


def test_trial_form_result_only_changes_settings_without_connection(qtbot, monkeypatch):
    prepared = replace(RunConfig(), sample_id="FORM-EDITED")

    class Dialog:
        result_config = prepared

        def __init__(self, config, parent, **kwargs):
            assert config.simulation is True

        def exec(self):
            return 1

    monkeypatch.setattr("keithley6517a.ui.test_setup.TestSetupDialog", Dialog)
    window = MainWindow(lambda *a, **k: pytest.fail("Applying a form must never connect"))
    qtbot.addWidget(window)
    try:
        window.setup_button.click()
        assert window.sample_id.text() == "FORM-EDITED"
        assert window.transport.currentData() == "simulation"
        assert window.voltages.text() == "0.0"
        assert window.worker.runner is None
        assert not window.arm_button.isEnabled()
        assert not window.start_button.isEnabled()
    finally:
        close_window(qtbot, window)


def test_cli_diagnosis_passes_explicit_options_without_measurement(monkeypatch, tmp_path, capsys):
    calls = []

    def diagnose(**options):
        calls.append(options)
        return {"ok": True, "output_state": "OFF", "report_path": "test.json"}

    monkeypatch.setattr("keithley6517a.diagnostics.run_diagnostics", diagnose)
    monkeypatch.setattr(
        cli, "MeasurementRunner", lambda *a, **k: pytest.fail("Diagnostic CLI cannot ARM")
    )
    assert (
        cli.main(
            [
                "diagnose",
                "--resource",
                "GPIB0::27::INSTR",
                "--backend",
                "@ivi",
                "--timeout-ms",
                "1500",
                "--confirm-off",
                "--no-eoi",
                "--read-termination",
                "NONE",
                "--write-termination",
                "CRLF",
                "--report-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert calls == [
        dict(
            resource="GPIB0::27::INSTR",
            backend="@ivi",
            timeout_ms=1500,
            confirm_off=True,
            output_directory=str(tmp_path),
            read_termination=None,
            write_termination="\r\n",
            send_end=False,
        )
    ]
    assert json.loads(capsys.readouterr().out)["ok"] is True


@pytest.mark.parametrize(
    "message,code",
    [
        ("VI_ERROR_INTF_NUM_NCONFIG", "GPIB_INTERFACE_NOT_CONFIGURED"),
        ("VI_ERROR_RSRC_NFOUND", "GPIB_RESOURCE_NOT_FOUND"),
    ],
)
def test_ni_driver_and_address_errors_give_ni_max_actions(tmp_path, message, code):
    from keithley6517a.diagnostics import run_diagnostics

    class Missing:
        @staticmethod
        def list_resources(backend):
            raise RuntimeError(message)

    report = run_diagnostics(output_directory=tmp_path, transport_factory=Missing)
    assert not report["ok"]
    assert report["issues"][0]["code"] == code
    assert "NI MAX" in report["issues"][0]["action"]


def test_independent_hardware_protection_review_is_required_outside_gui(tmp_path):
    config = RunConfig.from_dict(
        dict(
            simulation=False,
            transport="visa",
            resource="GPIB0::27::INSTR",
            resistive_limit_enabled=False,
            current_trip_A=1e-8,
            residual_warning_ack=True,
            rating_approval="test approval",
            sample_limit_V=10,
            fixture_limit_V=10,
            cable_limit_V=10,
            output_directory=str(tmp_path),
            commissioning=dict(
                installation_confirmed=True,
                lid_open_zero=True,
                lid_closed_one=True,
                fixture_id="TEST-FIXTURE",
                approved_by="test",
            ),
        )
    )
    with pytest.raises(ConfigurationError, match="hardware protection"):
        config.validate(for_arm=True)
