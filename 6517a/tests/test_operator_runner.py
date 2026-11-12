"""Operator bench workflow uses a fake bus; these tests never access NI hardware."""

import json

import pytest

from keithley6517a import cli
from keithley6517a.clock import FakeClock
from keithley6517a.config import RunConfig
from keithley6517a.driver.instrument import Instrument
from keithley6517a.measurement.runner import MeasurementRunner
from keithley6517a.transport.simulator import SimulatorTransport


class FakeOperatorBus(SimulatorTransport):
    is_simulation = False


def operator_config(tmp_path):
    return RunConfig(
        simulation=False,
        transport="visa",
        resource="GPIB0::27::INSTR",
        setup_policy="operator_low_voltage",
        operator_setup_acknowledged=True,
        sample_id="FAKE-OPERATOR-CONTRACT",
        voltages=(1, 2),
        protocol="list",
        output_directory=str(tmp_path),
        current_trip_A=1e-8,
        residual_warning_ack=True,
        resistive_limit_enabled=False,
        dwell_s=0.5,
        summary_window_s=0.5,
        sample_interval_s=0.1,
        nplc=1,
        range_settle_s=0.01,
    )


def runner_for(config):
    clock = FakeClock()
    bus = FakeOperatorBus(
        clock=clock,
        resistance_ohm=1e9,
        offset_A=0,
        noise_A=0,
        absorption_A=0,
        faults={"cable_absent": True},
    )
    return MeasurementRunner(config, instrument=Instrument(bus, clock), clock=clock), bus


def test_operator_run_records_current_resistance_and_uncertified_setup(tmp_path):
    runner, bus = runner_for(operator_config(tmp_path))
    runner.connect()
    assert runner.can_arm
    assert ":OUTP1 ON" not in bus.commands
    runner.arm()
    assert runner.can_start and not bus.output
    assert not runner.commissioning["ready"]
    result = runner.start()
    assert result["status"] == "completed"
    assert runner.output_state == "OFF" and not bus.output
    assert bus.commands.count(":OUTP1 ON") == 1
    valid = [row for row in runner.rows if row["valid_for_summary"]]
    assert valid
    assert all(row["resistance_apparent_ohm"] == pytest.approx(1e9) for row in valid)
    assert all(row["interlock_query"] == 1 for row in valid)
    metadata = json.loads((runner.run_directory / "metadata.json").read_text())
    assert metadata["setup_policy"] == "operator_low_voltage"
    assert metadata["operator_setup_acknowledged"] is True
    assert metadata["operator_voltage_cap_V"] == 10
    assert metadata["connection_commissioning"]["ready"] is False
    assert metadata["identity"]["hardware_verified"] is False
    assert (runner.run_directory / "readings.csv").is_file()
    assert (runner.run_directory / "summary.csv").is_file()
    runner.shutdown()


def test_operator_live_interlock_failure_stops_before_the_next_voltage(tmp_path):
    runner, bus = runner_for(operator_config(tmp_path))
    runner.connect()
    runner.arm()
    runner.on_sample = lambda row: bus.faults.update(interlock=0)
    result = runner.start()
    assert result["status"] == "aborted"
    assert not bus.output and runner.output_state == "OFF"
    assert ":SOUR:VOLT 2" not in bus.commands
    runner.shutdown()


@pytest.mark.parametrize("answer,expected_status", [("START", 0), ("CANCEL", 2)])
def test_operator_cli_has_explicit_start_without_fixture_document_prompts(
    tmp_path, monkeypatch, answer, expected_status
):
    config = operator_config(tmp_path / "results")
    path = tmp_path / "operator.json"
    path.write_text(json.dumps(config.to_dict()))
    runner, bus = runner_for(config)
    monkeypatch.setattr(cli, "MeasurementRunner", lambda *a, **k: runner)
    prompts = []

    def respond(prompt):
        prompts.append(prompt)
        assert "START" in prompt
        return answer

    monkeypatch.setattr("builtins.input", respond)
    assert cli.main(["measure", "--config", str(path)]) == expected_status
    assert len(prompts) == 1
    assert (":OUTP1 ON" in bus.commands) == (answer == "START")
    assert not bus.output


def test_simulation_uses_selected_reference_model_and_never_constructs_visa(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "keithley6517a.transport.visa.VisaTransport.__init__",
        lambda *a, **k: pytest.fail("SIMULATION must never create VISA"),
    )
    config = RunConfig(
        simulation_resistance_ohm=1e9,
        voltages=(1,),
        dwell_s=0.5,
        summary_window_s=0.5,
        sample_interval_s=0.1,
        current_trip_A=1e-8,
        residual_warning_ack=True,
        output_directory=str(tmp_path),
    )
    runner = MeasurementRunner(config, clock=FakeClock())
    assert runner.instrument.transport.resistance_ohm == 1e9
    runner.connect()
    runner.arm()
    result = runner.start()
    assert result["status"] == "completed"
    assert any(row["current_raw_A"] > 0.9e-9 for row in runner.rows)
    metadata = json.loads((runner.run_directory / "metadata.json").read_text())
    assert metadata["simulation"] is True
    assert metadata["simulation_truth"]["resistance_ohm"] == 1e9
    runner.shutdown()


def test_gui_reference_preset_connect_arm_start_completes_and_saves(tmp_path, qtbot):
    from keithley6517a.ui.main_window import MainWindow
    from keithley6517a.ui.test_setup import TestSetupDialog as SetupDialog

    buses = []

    def factory(config, **callbacks):
        clock = FakeClock()
        bus = FakeOperatorBus(
            clock=clock, resistance_ohm=1e9, noise_A=0, offset_A=0, absorption_A=0
        )
        buses.append(bus)
        return MeasurementRunner(
            config, instrument=Instrument(bus, clock), clock=clock, **callbacks
        )

    window = MainWindow(factory)

    def orderly_close(widget):
        widget.close()
        qtbot.waitUntil(lambda: widget._closed, timeout=10000)

    qtbot.addWidget(window, before_close_func=orderly_close)
    window._enter_real_test()
    window.resource.setText("GPIB0::27::INSTR")
    dialog = SetupDialog(window.config_from_controls(), window)
    qtbot.addWidget(dialog)
    dialog.reference_preset_button.click()
    dialog.operator_ack.setChecked(True)
    dialog.residual_ack.setChecked(True)
    dialog.resistive_limit.setCurrentIndex(1)
    dialog.output_directory.setText(str(tmp_path))
    dialog.dwell.setText("0.5")
    dialog.summary_window.setText("0.5")
    dialog.interval.setText("0.1")
    dialog.accept()
    assert dialog.result_config is not None
    window._load_controls(dialog.result_config.to_dict())
    assert not buses
    window.connect_button.click()
    qtbot.waitUntil(lambda: window._connected and not window._busy, timeout=10000)
    assert window.arm_button.isEnabled()
    assert ":OUTP1 ON" not in buses[0].commands
    window.arm_button.click()
    qtbot.waitUntil(lambda: window.start_button.isEnabled() and not window._busy, timeout=10000)
    assert ":OUTP1 ON" not in buses[0].commands
    window.start_button.click()
    qtbot.waitUntil(
        lambda: (
            bool(window.rows)
            and not window._busy
            and window.worker.runner.writer.closed
            and window.worker.runner.state == "OUTPUT_OFF_CONFIRMED"
        ),
        timeout=10000,
    )
    assert not buses[0].output
    assert any(row["resistance_apparent_ohm"] == pytest.approx(1e9) for row in window.rows)
    assert (window.worker.runner.run_directory / "readings.csv").is_file()
    assert (window.worker.runner.run_directory / "summary.csv").is_file()
