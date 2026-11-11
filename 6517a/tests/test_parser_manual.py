"""Manual Rev. D Fig. 3-19 derived fixtures; no live hardware transcripts."""

import re

import pytest

from keithley6517a.clock import FakeClock
from keithley6517a.driver.parser import ProtocolError, parse_reading
from keithley6517a.transport.base import CommunicationError
from keithley6517a.transport.simulator import SimulatorTransport


def test_manual_selected_element_order_and_attached_status_unit():
    raw = "+1234.567E-14NADC,+01234rdg#,+0010.000Vsrc\r\n"
    reading = parse_reading(raw, "FVMI_CURRENT")
    assert reading.value == pytest.approx(1.234567e-11)
    assert reading.unit == "ADC"
    assert reading.status == "N"
    assert reading.reading_number == 1234
    assert reading.voltage_reported == 10
    assert reading.flags == ()
    assert reading.raw == raw


@pytest.mark.parametrize("count", ["+00000rdg#", "00001rdg#", "-00001rdg#"])
def test_manual_counter_fields_include_signed_pretrigger_representation(count):
    reading = parse_reading(f"+1E+12NOHM,{count},+0010.000Vsrc", "NATIVE_RESISTANCE")
    assert reading.reading_number == int(count[:-4])
    assert reading.unit == "OHM"


@pytest.mark.parametrize(
    "value,status,flag",
    [
        ("+9.91E37", "Z", "ZERO_CHECK_SENTINEL"),
        ("+9.9E37", "O", "OVERFLOW"),
        ("0.00E00", "U", "UNDERFLOW"),
        ("-1.23E-11", "R", "REFERENCE"),
        ("+9.9E37", "L", "OUT_OF_LIMIT"),
    ],
)
def test_manual_status_and_sentinel_values_never_become_normal_numbers(value, status, flag):
    reading = parse_reading(f"{value}{status}ADC,+00001rdg#,+0001.000Vsrc", "FVMI_CURRENT")
    assert reading.value is None
    assert flag in reading.flags
    assert "STATUS_VALUE_MISMATCH" not in reading.flags


def test_inconsistent_sentinel_and_status_remain_explicitly_invalid():
    normal_sentinel = parse_reading("+9.9E37NADC,+00001rdg#,+10Vsrc", "FVMI_CURRENT")
    assert normal_sentinel.value is None and "SENTINEL" in normal_sentinel.flags
    bad_underflow = parse_reading("+1E-8UADC,+00001rdg#,+10Vsrc", "FVMI_CURRENT")
    assert bad_underflow.value is None and "STATUS_VALUE_MISMATCH" in bad_underflow.flags


@pytest.mark.parametrize(
    "raw",
    [
        "+1E-11NADC,+00001RDNG#,+0010.000Vsrc",  # former provisional typo
        "+1E-11NADC,+00001,+0010.000Vsrc",  # units required by configured format
        "+1E-11NADC,+00001rdg#,+0010.000VSO",  # element name is not the unit
        "+1E-11,N,ADC,+00001rdg#,+0010.000Vsrc",
        "+1E-11NOHM,+00001rdg#,+0010.000Vsrc",
        "+1E-11QADC,+00001rdg#,+0010.000Vsrc",
        "+1E-11NADC,+00001rdg#,+0010.000Vsrc,additional",
        "+1E-999NADC,+00001rdg#,+0010.000Vsrc",
        "+1E999NADC,+00001rdg#,+0010.000Vsrc",
        "NaNNADC,+00001rdg#,+0010.000Vsrc",
    ],
)
def test_unconfigured_or_corrupt_tokens_are_not_guessed(raw):
    with pytest.raises(ProtocolError):
        parse_reading(raw, "FVMI_CURRENT")


def test_unknown_mode_is_not_silently_treated_as_current():
    with pytest.raises(ProtocolError, match="Unknown"):
        parse_reading("+1NADC,+00001rdg#,+0Vsrc", "mistyped")


def simulator(**faults):
    clock = FakeClock()
    transport = SimulatorTransport(clock=clock, faults=faults, noise_A=0, absorption_A=0)
    transport.open()
    return transport, clock


def test_simulator_emits_fig319_suffix_and_standby_vsource_zero():
    transport, _ = simulator()
    transport.write(":SYST:ZCH OFF")
    transport.write(":SOUR:VOLT 10")
    raw = transport.query(":READ?")
    assert re.fullmatch(r"[^,]+NADC,\+\d+rdg#,\+0\.0+E\+00Vsrc", raw)
    assert parse_reading(raw, "FVMI_CURRENT").voltage_reported == 0
    transport.write(":OUTP1 ON")
    reading = parse_reading(transport.query(":READ?"), "FVMI_CURRENT")
    assert reading.voltage_reported == 10


@pytest.mark.parametrize(
    "fault,status,value",
    [
        ("overflow_at_read", "O", "+9.90000000E+37"),
        ("underflow_at_read", "U", "+0.00000000E+00"),
        ("out_of_limit_at_read", "L", "+9.90000000E+37"),
    ],
)
def test_simulator_matches_manual_invalid_value_for_each_status(fault, status, value):
    transport, _ = simulator(**{fault: 1})
    transport.write(":SYST:ZCH OFF")
    raw = transport.query(":READ?")
    assert raw.startswith(value + status + "ADC,")
    reading = parse_reading(raw, "FVMI_CURRENT")
    assert reading.value is None
    assert "STATUS_VALUE_MISMATCH" not in reading.flags


def test_simulator_rejects_unverified_layer1_delay_vocabulary_and_responds_opc():
    transport, _ = simulator()
    for command in (":ARM:LAY1:DEL 0", ":ARM:DEL 0", ":ARM:LAY1:SOUR IMM"):
        with pytest.raises(CommunicationError):
            transport.write(command)
    transport.write(":ARM:SOUR IMM")
    transport.write(":ARM:COUN 1")
    transport.write(":ARM:LAY2:DEL 0")
    assert transport.query("*OPC?") == "1"
    assert transport.query(":ARM:SOUR?") == "IMM"


def test_simulator_function_specific_native_integration_is_not_current_nplc():
    transport, clock = simulator()
    transport.write(":SENS:FUNC 'RES'")
    transport.write(":SENS:RES:NPLC 1")
    transport.write(":SYST:ZCH OFF")
    before = clock.monotonic()
    raw = transport.query(":READ?")
    assert clock.monotonic() - before == pytest.approx(1 / 60)
    assert "OHM," in raw
    assert transport.values[":SENS:CURR:NPLC"] == "10"


def test_simulator_source_limit_query_is_separate_from_reading_status():
    transport, _ = simulator(source_current_limit=True)
    transport.write(":SYST:ZCH OFF")
    assert transport.query(":SOUR:CURR:LIM:STAT?") == "1"
    # A source-limit query is a separate observation; its truth must not be inferred
    # from the ADC token alone by the safety state machine.
    reading = parse_reading(transport.query(":READ?"), "FVMI_CURRENT")
    assert reading.status == "N"
