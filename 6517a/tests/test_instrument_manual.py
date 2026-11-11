"""Manual-derived contract tests with a fake VISA device, never real hardware."""

from dataclasses import replace

import pytest

from keithley6517a.clock import FakeClock
from keithley6517a.config import RunConfig
from keithley6517a.driver.commands import MANUAL_SHA256, MANUAL_VERIFIED
from keithley6517a.driver.instrument import Instrument
from keithley6517a.driver.parser import ProtocolError
from keithley6517a.transport.base import CommunicationError
from keithley6517a.transport.simulator import SimulatorTransport


class FakeVisaDevice(SimulatorTransport):
    """Exercises the real control branch with an entirely local command emulator."""

    is_simulation = False


def real_config(**updates):
    settings = dict(
        simulation=False,
        transport="visa",
        resource="GPIB0::27::INSTR",
        current_trip_A=1e-8,
        sample_limit_V=10,
        fixture_limit_V=10,
        cable_limit_V=10,
        rating_approval="Contract test only; no hardware approval",
        residual_warning_ack=True,
        resistive_limit_enabled=False,
        commissioning=dict(
            installation_confirmed=True,
            hardware_protection_reviewed=True,
            lid_open_zero=True,
            lid_closed_one=True,
            fixture_id="FAKE-FIXTURE",
            approved_by="TEST OPERATOR",
        ),
    )
    return RunConfig.from_dict(dict(settings, **updates))


def connected():
    clock = FakeClock()
    transport = FakeVisaDevice(clock)
    instrument = Instrument(transport, clock)
    instrument.connect()
    return instrument, transport


def commissioned():
    instrument, transport = connected()
    transport.faults["interlock"] = 0
    assert not instrument.commission_interlock(0, "FAKE-FIXTURE", "TEST OPERATOR")["ready"]
    transport.faults["interlock"] = 1
    assert instrument.commission_interlock(1, "FAKE-FIXTURE", "TEST OPERATOR")["ready"]
    return instrument, transport


def armed():
    instrument, transport = commissioned()
    config = real_config()
    readback = instrument.configure(config)
    return instrument, transport, config, readback


def test_manual_verified_is_separate_from_hardware_verified():
    instrument, _ = connected()
    assert MANUAL_VERIFIED
    assert instrument.identity["manual_verified"]
    assert not instrument.identity["hardware_verified"]
    assert instrument.identity["manual_sha256"] == MANUAL_SHA256


def test_query_one_and_saved_history_cannot_replace_live_commissioning():
    instrument, transport = connected()
    start = len(transport.commands)
    with pytest.raises(RuntimeError, match="this connection"):
        instrument.configure(real_config())
    assert ":OUTP1 ON" not in transport.commands
    assert not any(c.startswith(":SOUR:VOLT ") for c in transport.commands[start:])
    with pytest.raises(RuntimeError, match="lid-open=0"):
        instrument.commission_interlock(1, "FAKE-FIXTURE", "TEST OPERATOR")


def test_commissioning_has_no_voltage_writes_and_is_fixture_bound():
    instrument, transport = commissioned()
    assert ":OUTP1 ON" not in transport.commands
    assert not any(c.startswith(":SOUR:VOLT ") for c in transport.commands)
    different = dict(real_config().to_dict()["commissioning"], fixture_id="OTHER")
    with pytest.raises(RuntimeError, match="this connection"):
        instrument.configure(real_config(commissioning=different))


def test_manual_profile_has_no_fictitious_arm_layer_one_delay():
    instrument, transport, _, readback = armed()
    assert not transport.output
    assert ":ARM:SOUR IMM" in transport.commands
    assert ":ARM:COUN 1" in transport.commands
    assert ":ARM:LAY2:DEL 0" in transport.commands
    assert ":TRIG:DEL 0" in transport.commands
    assert not any(":ARM:LAY1:DEL" in c for c in transport.commands)
    assert ":SENS:CURR:REF:STAT OFF" in transport.commands
    assert ":SENS:RES:IREF OFF" in transport.commands
    assert ":TSEQ:ABOR" in transport.commands
    assert ":TRAC:FEED:CONT NEV" in transport.commands
    assert ":ROUT:SCAN:LSEL NONE" in transport.commands
    assert ":SYST:HLC ON" in transport.commands
    assert readback["manual_sha256"] == MANUAL_SHA256
    assert not readback["hardware_verified"]
    assert instrument.output_state == "OFF"


def test_manual_zero_correction_sequence_and_lowest_autorange_calibration():
    _, transport, _, readback = armed()
    commands = transport.commands
    acquisition = commands.index(":SYST:ZCOR:ACQ")
    check_off = commands.index(":SYST:ZCH OFF")
    correct_on = commands.index(":SYST:ZCOR ON")
    assert acquisition < check_off < correct_on < commands.index(":SENS:CURR:RANG:AUTO ON")
    assert commands[acquisition + 1] == "*OPC?"
    assert readback["zero_correct_range_A"] == 20e-12
    assert readback["zero_correct_valid_for_uprange_per_manual"]


def test_start_requires_one_use_authorization_even_after_configure():
    instrument, transport, config, _ = armed()
    with pytest.raises(RuntimeError, match="authorization"):
        instrument.output_on()
    assert not transport.output
    instrument.authorize_start(config)
    assert not transport.output
    instrument.output_on()
    assert transport.output
    with pytest.raises(RuntimeError, match="authorization"):
        instrument.output_on()
    assert transport.commands.count(":OUTP1 ON") == 1


def test_start_authorization_checks_exact_snapshot():
    instrument, transport, config, _ = armed()
    with pytest.raises(RuntimeError, match="snapshot"):
        instrument.authorize_start(replace(config, current_trip_A=1e-7))
    assert ":OUTP1 ON" not in transport.commands


def test_fresh_output_state_checked_before_configuration_and_enable():
    instrument, transport = commissioned()
    transport.output = True  # an independent front-panel action after last OFF query
    with pytest.raises(ProtocolError, match="mismatch"):
        instrument.configure(real_config())
    instrument.safe_off()
    instrument, transport, config, _ = armed()
    instrument.authorize_start(config)
    transport.output = True
    with pytest.raises(RuntimeError, match="safety"):
        instrument.output_on()
    assert ":OUTP1 ON" not in transport.commands


def test_source_zero_is_requeried_immediately_before_enable():
    instrument, transport, config, _ = armed()
    instrument.authorize_start(config)
    transport.voltage = 1  # front-panel change after START authorization
    with pytest.raises(ProtocolError, match="mismatch"):
        instrument.output_on()
    assert ":OUTP1 ON" not in transport.commands


@pytest.mark.parametrize("failure", ["open", "query"])
def test_interlock_fault_latches_and_cannot_resume_on_lid_close(failure):
    instrument, transport, config, _ = armed()
    instrument.authorize_start(config)
    if failure == "open":
        transport.faults["interlock"] = 0
        instrument.safety_status()
    else:
        transport.faults["output_query_failure"] = True
        with pytest.raises(CommunicationError):
            instrument.safety_status()
        del transport.faults["output_query_failure"]
    transport.faults["interlock"] = 1
    assert not instrument.commissioning["ready"]
    with pytest.raises(RuntimeError):
        instrument.output_on()
    with pytest.raises(RuntimeError):
        instrument.authorize_start(config)
    assert ":OUTP1 ON" not in transport.commands


def test_reopening_commissioning_invalidates_old_config_and_start_permit():
    instrument, transport, config, _ = armed()
    instrument.authorize_start(config)
    transport.faults["interlock"] = 0
    instrument.commission_interlock(0, "FAKE-FIXTURE", "TEST OPERATOR")
    transport.faults["interlock"] = 1
    instrument.commission_interlock(1, "FAKE-FIXTURE", "TEST OPERATOR")
    with pytest.raises(RuntimeError):
        instrument.output_on()
    assert not instrument.configured


def test_reconnect_drops_commissioning_permit_and_never_replays_on():
    instrument, transport, config, _ = armed()
    instrument.authorize_start(config)
    previous = instrument.commissioning["session_id"]
    instrument.close()
    instrument.connect()
    assert not instrument.commissioning["ready"]
    assert instrument.commissioning["session_id"] != previous
    assert ":OUTP1 ON" not in transport.commands


def test_readback_accepts_documented_canonical_forms_and_element_order():
    instrument, transport = commissioned()
    original = transport.query
    responses = {
        ":SENS:FUNC?": '"CURR:DC"',
        ":FORM:DATA?": "ASCII",
        ":SENS:RES:VSC?": "MANUAL",
        ":SENS:RES:MSEL?": "NORMAL",
        ":ARM:SOUR?": "IMMEDIATE",
        ":FORM:ELEM?": "READ,RNUM,UNIT,STAT,VSO",
    }
    transport.query = lambda command: responses.get(command, original(command))
    instrument.configure(real_config())
    assert instrument.configured
    assert not transport.output


def test_io_guard_after_log_callback_prevents_the_ordinary_write_but_not_off():
    instrument, transport, config, _ = armed()
    instrument.authorize_start(config)
    stopping = False

    def record(event):
        nonlocal stopping
        if event.get("command") == ":OUTP1 ON":
            stopping = True

    def guard():
        if stopping:
            raise RuntimeError("STOP arrived during logging callback")

    instrument.io_callback = record
    instrument.io_guard = guard
    with pytest.raises(RuntimeError, match="STOP"):
        instrument.output_on()
    assert ":OUTP1 ON" not in transport.commands
    assert instrument.safe_off() == []
    assert instrument.output_state == "OFF"


def test_native_real_remains_blocked_despite_manual_verified_and_commissioning():
    instrument, transport = commissioned()
    with pytest.raises(ValueError, match="native resistance"):
        instrument.configure(real_config(mode="NATIVE_RESISTANCE"))
    assert ":OUTP1 ON" not in transport.commands
