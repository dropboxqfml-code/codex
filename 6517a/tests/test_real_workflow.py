"""Real-profile software contract tests against a fake bus, never physical hardware."""

import json
from dataclasses import replace

import pytest

from keithley6517a import cli
from keithley6517a.clock import FakeClock
from keithley6517a.config import ConfigurationError, RunConfig
from keithley6517a.driver.instrument import Instrument
from keithley6517a.measurement.runner import MeasurementError, MeasurementRunner
from keithley6517a.transport.simulator import SimulatorTransport


class FakeVisaBus(SimulatorTransport):
    """Exercises the real driver branch while every byte still stays in this test process."""

    is_simulation = False


def real_config(tmp_path, **updates):
    values = dict(
        simulation=False,
        transport="visa",
        resource="GPIB0::27::INSTR",
        sample_id="FAKE-VISA-TEST",
        output_directory=str(tmp_path),
        voltages=[1, 2],
        protocol="list",
        dwell_s=0.5,
        summary_window_s=0.5,
        sample_interval_s=0.1,
        nplc=1,
        current_trip_A=1e-7,
        voltage_ceiling_V=10,
        sample_limit_V=10,
        fixture_limit_V=10,
        cable_limit_V=10,
        resistive_limit_enabled=False,
        rating_approval="software-test-only",
        residual_warning_ack=True,
        commissioning=dict(
            installation_confirmed=True,
            hardware_protection_reviewed=True,
            lid_open_zero=True,
            lid_closed_one=True,
            fixture_id="FAKE-FIXTURE",
            approved_by="test",
        ),
    )
    return RunConfig.from_dict(dict(values, **updates))


def runner_for(config):
    clock = FakeClock()
    bus = FakeVisaBus(clock=clock, noise_A=0, absorption_A=0)
    runner = MeasurementRunner(config, instrument=Instrument(bus, clock), clock=clock)
    return runner, bus


def observe_lid(runner, bus):
    bus.faults["interlock"] = 0
    runner.commission_interlock(0)
    assert not runner.can_arm
    assert ":OUTP1 ON" not in bus.commands
    bus.faults["interlock"] = 1
    runner.commission_interlock(1)
    assert runner.can_arm


def test_config_flags_and_interlock_one_cannot_replace_connection_observations(tmp_path):
    runner, bus = runner_for(real_config(tmp_path))
    runner.connect()
    assert not runner.can_arm
    with pytest.raises(RuntimeError, match="(?i)commission|interlock"):
        runner.arm()
    assert ":OUTP1 ON" not in bus.commands
    assert not bus.output
    runner.shutdown()


def test_real_fvmi_uses_manual_profile_only_after_observations_and_explicit_start(tmp_path):
    runner, bus = runner_for(real_config(tmp_path))
    runner.connect()
    observe_lid(runner, bus)
    proof = runner.commissioning
    assert proof["ready"] and proof["fixture_id"] == "FAKE-FIXTURE"
    runner.arm()
    assert not bus.output
    assert ":OUTP1 ON" not in bus.commands
    result = runner.start()
    assert result["status"] == "completed"
    assert runner.output_state == "OFF"
    assert runner.residual_voltage_state == "UNVERIFIED"
    assert bus.commands.count(":OUTP1 ON") == 1
    assert ":ARM:LAY1:DEL 0" not in bus.commands
    assert ":ARM:COUN 1" in bus.commands
    assert ":SENS:CURR:REF:STAT OFF" in bus.commands
    assert ":TSEQ:ABOR" in bus.commands
    metadata = json.loads((runner.run_directory / "metadata.json").read_text())
    assert metadata["identity"]["manual_verified"] is True
    assert metadata["connection_commissioning"]["ready"] is True
    assert all("rdg#" in r["raw_response"] for r in runner.rows)
    runner.shutdown()


def test_reconnect_invalidates_interlock_proof_and_never_replays_on(tmp_path):
    runner, bus = runner_for(real_config(tmp_path))
    runner.connect()
    observe_lid(runner, bus)
    session = runner.commissioning["session_id"]
    runner.shutdown()
    runner.connect()
    assert not runner.commissioning["ready"]
    assert runner.commissioning["session_id"] != session
    assert not runner.can_arm
    assert ":OUTP1 ON" not in bus.commands
    runner.shutdown()


def test_current_limit_or_lid_open_aborts_real_profile_without_next_voltage(tmp_path):
    runner, bus = runner_for(real_config(tmp_path))
    runner.connect()
    observe_lid(runner, bus)
    runner.arm()
    runner.on_sample = lambda row: bus.faults.update(interlock=0)
    result = runner.start()
    assert result["status"] == "aborted"
    assert not runner.commissioning["ready"]
    assert ":SOUR:VOLT 2" not in bus.commands
    assert not bus.output
    bus.faults["interlock"] = 1
    with pytest.raises(MeasurementError):
        runner.start()
    assert bus.commands.count(":OUTP1 ON") == 1


def test_cli_requires_typed_start_after_off_only_observations(tmp_path, monkeypatch, capsys):
    config = real_config(tmp_path / "runs")
    path = tmp_path / "real-config.json"
    path.write_text(json.dumps(config.to_dict()))
    runner, bus = runner_for(config)
    monkeypatch.setattr(cli, "MeasurementRunner", lambda *a, **k: runner)
    actions = iter(("OPEN", "CLOSED", "START"))

    def answer(prompt):
        assert not bus.output
        action = next(actions)
        if action == "OPEN":
            bus.faults["interlock"] = 0
        elif action == "CLOSED":
            bus.faults["interlock"] = 1
        return action

    monkeypatch.setattr("builtins.input", answer)
    assert cli.main(["measure", "--config", str(path)]) == 0
    assert '"status": "completed"' in capsys.readouterr().out
    assert not bus.output


def test_cli_cancel_after_arm_never_enables_output(tmp_path, monkeypatch):
    config = real_config(tmp_path / "runs")
    path = tmp_path / "real-config.json"
    path.write_text(json.dumps(config.to_dict()))
    runner, bus = runner_for(config)
    monkeypatch.setattr(cli, "MeasurementRunner", lambda *a, **k: runner)
    actions = iter(("OPEN", "CLOSED", "CANCEL"))

    def answer(prompt):
        action = next(actions)
        bus.faults["interlock"] = 0 if action == "OPEN" else 1
        return action

    monkeypatch.setattr("builtins.input", answer)
    assert cli.main(["measure", "--config", str(path)]) == 2
    assert ":OUTP1 ON" not in bus.commands
    assert not bus.output


def test_real_policy_and_transport_settings_are_strict(tmp_path):
    with pytest.raises(ConfigurationError, match="resistive"):
        replace(real_config(tmp_path), resistive_limit_enabled=None).validate()
    with pytest.raises(ConfigurationError, match="native|Native"):
        replace(real_config(tmp_path), mode="NATIVE_RESISTANCE").validate()
    for changes in (
        {"resistive_limit_enabled": "ON"},
        {"send_end": 1},
        {"read_termination": ["\n"]},
        {"visa_backend": 1},
    ):
        with pytest.raises(ConfigurationError):
            real_config(tmp_path, **changes)
    config = real_config(tmp_path, read_termination=None, write_termination=None, send_end=True)
    config.validate()
