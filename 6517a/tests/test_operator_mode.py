"""Operator bench policy uses a local fake bus and never contacts physical hardware."""

from dataclasses import replace

import pytest

from keithley6517a.clock import FakeClock
from keithley6517a.config import ConfigurationError, RunConfig
from keithley6517a.driver.instrument import Instrument
from keithley6517a.driver.parser import ProtocolError
from keithley6517a.transport.simulator import SimulatorTransport


class FakeRealBus(SimulatorTransport):
    is_simulation = False


def operator_config(**changes):
    values = dict(
        simulation=False,
        transport="visa",
        setup_policy="operator_low_voltage",
        operator_setup_acknowledged=True,
        resource="GPIB0::27::INSTR",
        voltages=[1],
        current_trip_A=1e-8,
        residual_warning_ack=True,
        resistive_limit_enabled=False,
    )
    return RunConfig.from_dict(dict(values, **changes))


def connected():
    clock = FakeClock()
    bus = FakeRealBus(clock=clock, noise_A=0, absorption_A=0)
    instrument = Instrument(bus, clock)
    instrument.connect()
    return instrument, bus


def configured():
    instrument, bus = connected()
    config = operator_config()
    readback = instrument.configure(config)
    return instrument, bus, config, readback


def test_operator_configuration_is_explicit_and_does_not_invent_fixture_records():
    assert RunConfig().setup_policy == "verified_fixture"
    assert RunConfig().operator_setup_acknowledged is False
    assert RunConfig().simulation_resistance_ohm == 1e12
    config = operator_config()
    config.validate(for_arm=True)
    assert config.commissioning == {}
    assert config.sample_limit_V is config.fixture_limit_V is config.cable_limit_V is None
    assert config.rating_approval == ""
    assert config.effective_ceiling == 10


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"setup_policy": "unknown"}, "setup_policy"),
        ({"setup_policy": 1}, "setup_policy"),
        ({"operator_setup_acknowledged": 1}, "boolean"),
        ({"simulation_resistance_ohm": 0}, "positive"),
        ({"simulation_resistance_ohm": -1}, "positive"),
        ({"simulation_resistance_ohm": float("inf")}, "finite"),
        ({"simulation_resistance_ohm": True}, "finite"),
        ({"simulation_resistance_ohm": "1e9"}, "finite"),
        ({"source_range_V": 1000}, "100 V source range"),
        ({"voltage_ceiling_V": 10.001}, "10 V ceiling"),
        ({"voltages": [10.001]}, "ceiling"),
        ({"voltages": [-10.001], "bipolar_authorized": True}, "ceiling"),
    ],
)
def test_invalid_operator_settings_are_rejected_before_any_hardware_use(changes, message):
    with pytest.raises(ConfigurationError, match=message):
        operator_config(**changes)


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"operator_setup_acknowledged": False}, "acknowledgment"),
        ({"current_trip_A": None}, "current trip"),
        ({"residual_warning_ack": False}, "Residual-charge"),
        ({"resistive_limit_enabled": None}, "resistive-limit"),
        ({"mode": "NATIVE_RESISTANCE"}, "native resistance"),
    ],
)
def test_draft_can_load_but_cannot_arm_without_the_remaining_execution_inputs(changes, message):
    config = operator_config(**changes)
    with pytest.raises(ConfigurationError, match=message):
        config.validate(for_arm=True)
    instrument, bus = connected()
    start = len(bus.commands)
    with pytest.raises((ConfigurationError, RuntimeError), match=message):
        instrument.configure(config)
    assert ":OUTP1 ON" not in bus.commands
    assert not any(command.startswith(":SOUR:VOLT ") for command in bus.commands[start:])
    instrument.close()


def test_operator_configure_stays_off_and_requires_a_separate_one_use_start():
    instrument, bus, config, readback = configured()
    assert not bus.output
    assert instrument.output_state == "OFF"
    assert instrument.voltage_programmed == 0
    assert float(bus.values[":SOUR:VOLT:LIM"]) == 10
    assert readback["setup_policy"] == "operator_low_voltage"
    assert readback["operator_setup_acknowledged"] is True
    assert readback["hardware_verified"] is False
    assert readback["commissioning"]["ready"] is False
    assert instrument.safety_status()["fixture_installation_confirmed"] is False
    with pytest.raises(RuntimeError, match="one-use START"):
        instrument.output_on()
    assert ":OUTP1 ON" not in bus.commands
    instrument.authorize_start(config)
    assert not bus.output
    instrument.output_on()
    assert bus.output
    instrument.set_voltage(1)
    assert bus.voltage == 1
    assert instrument.safety_status()["fixture_installation_confirmed"] is False
    with pytest.raises(RuntimeError, match="one-use START"):
        instrument.output_on()
    assert bus.commands.count(":OUTP1 ON") == 1
    instrument.close()
    assert not bus.output


@pytest.mark.parametrize("interlock", [0, "invalid"])
def test_device_interlock_blocks_operator_configuration_before_source_settings(interlock):
    instrument, bus = connected()
    bus.faults["interlock"] = interlock
    start = len(bus.commands)
    with pytest.raises(ProtocolError):
        instrument.configure(operator_config())
    assert not instrument.configured
    assert not bus.output
    assert ":OUTP1 ON" not in bus.commands
    assert not any(command.startswith(":SOUR:") for command in bus.commands[start:])
    instrument.close()


def test_operator_mode_still_fails_closed_on_interlock_query_error():
    instrument, bus = connected()
    original_query = bus.query

    def query(command):
        if command == ":SYST:INT?":
            raise TimeoutError("Injected interlock query timeout")
        return original_query(command)

    bus.query = query
    start = len(bus.commands)
    with pytest.raises(TimeoutError, match="interlock"):
        instrument.configure(operator_config())
    assert not bus.output
    assert not any(command.startswith(":SOUR:") for command in bus.commands[start:])
    instrument.close()


def test_operator_configuration_does_not_become_ready_while_source_limit_is_active():
    instrument, bus = connected()
    bus.faults["source_current_limit"] = True
    with pytest.raises(ProtocolError, match="required safe state"):
        instrument.configure(operator_config())
    assert not instrument.configured
    assert not bus.output
    assert ":OUTP1 ON" not in bus.commands
    instrument.close()


@pytest.mark.parametrize("fault", ["interlock", "source_current_limit", "zero_check"])
def test_operator_start_rechecks_live_device_faults_instead_of_trusting_acknowledgment(fault):
    instrument, bus, config, _ = configured()
    bus.faults[fault] = 0 if fault == "interlock" else True
    with pytest.raises(RuntimeError, match="START"):
        instrument.authorize_start(config)
    assert ":OUTP1 ON" not in bus.commands
    assert not bus.output
    instrument.close()


def test_opening_interlock_after_authorization_consumes_the_permit_without_enabling_output():
    instrument, bus, config, _ = configured()
    instrument.authorize_start(config)
    bus.faults["interlock"] = 0
    with pytest.raises(RuntimeError, match="START"):
        instrument.output_on()
    bus.faults["interlock"] = 1
    with pytest.raises(RuntimeError, match="one-use START"):
        instrument.output_on()
    assert ":OUTP1 ON" not in bus.commands
    assert not bus.output
    instrument.close()


def test_operator_source_writes_keep_the_absolute_cap_and_any_tighter_user_rating():
    instrument, bus, config, _ = configured()
    instrument.authorize_start(config)
    instrument.output_on()
    start = len(bus.commands)
    for voltage in (10.001, 1000):
        with pytest.raises(ValueError, match="ceiling"):
            instrument.set_voltage(voltage)
    assert not any(command.startswith(":SOUR:VOLT ") for command in bus.commands[start:])
    instrument.close()
    config = operator_config(sample_limit_V=0.5, voltages=[0.5])
    assert config.effective_ceiling == 0.5
    instrument, bus = connected()
    instrument.configure(config)
    assert float(bus.values[":SOUR:VOLT:LIM"]) == 0.5
    instrument.authorize_start(config)
    instrument.output_on()
    with pytest.raises(ValueError, match="ceiling"):
        instrument.set_voltage(1)
    instrument.close()


def test_switching_the_immutable_policy_after_configuration_invalidates_start():
    instrument, bus, config, _ = configured()
    different = replace(config, current_trip_A=2e-8)
    with pytest.raises(RuntimeError, match="exact configured"):
        instrument.authorize_start(different)
    assert ":OUTP1 ON" not in bus.commands
    instrument.close()
