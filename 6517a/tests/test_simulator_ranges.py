"""Manual-derived range contracts, not a reproduction of hardware's 158 pA symptom."""

import pytest

from keithley6517a.clock import FakeClock
from keithley6517a.driver.parser import parse_reading
from keithley6517a.transport.base import CommunicationError
from keithley6517a.transport.simulator import SimulatorTransport


@pytest.fixture
def simulator():
    devices = []

    def make(**kwargs):
        settings = dict(offset_A=0, noise_A=0, absorption_A=0)
        settings.update(kwargs)
        device = SimulatorTransport(clock=FakeClock(), **settings)
        device.open()
        device.write(":SYST:ZCH OFF")
        devices.append(device)
        return device

    yield make
    for device in devices:
        device.close()


def read_current(device):
    return parse_reading(device.query(":READ?"), "FVMI_CURRENT")


@pytest.mark.parametrize(
    "voltage,expected_range",
    [(0.1, 2e-9), (0.5, 2e-8), (1, 2e-8), (5, 2e-7), (10, 2e-7)],
)
def test_autorange_measures_100_megohm_without_leaving_nanoamps_on_20_pa_range(
    simulator, voltage, expected_range
):
    device = simulator(resistance_ohm=100e6)
    device.write(":SENS:CURR:RANG 20e-12")
    device.write(":SENS:CURR:RANG:AUTO ON")
    device.write(f":SOUR:VOLT {voltage}")
    device.write(":OUTP1 ON")

    reading = read_current(device)
    actual_range = float(device.query(":SENS:CURR:RANG?"))

    assert reading.value == pytest.approx(voltage / 100e6)
    assert actual_range == expected_range
    assert abs(reading.value) <= 1.05 * actual_range
    assert device.query(":SENS:CURR:RANG:AUTO?") == "1"


def test_autorange_follows_up_and_down_then_retains_range_when_disabled(simulator):
    device = simulator(resistance_ohm=100e6)
    device.write(":OUTP1 ON")
    for voltage, expected_range in [(10, 2e-7), (0.1, 2e-9), (0, 2e-11)]:
        device.write(f":SOUR:VOLT {voltage}")
        assert read_current(device).value == pytest.approx(voltage / 100e6)
        assert float(device.query(":SENS:CURR:RANG?")) == expected_range
    device.write(":SENS:CURR:RANG:AUTO OFF")
    device.write(":SOUR:VOLT 1")
    assert "OVERFLOW" in read_current(device).flags
    assert float(device.query(":SENS:CURR:RANG?")) == 2e-11


def test_numeric_autorange_limits_round_to_nominal_ranges_and_query(simulator):
    device = simulator()
    assert float(device.query(":SENS:CURR:RANG:AUTO:LLIM?")) == 2e-11
    assert float(device.query(":SENS:CURR:RANG:AUTO:ULIM?")) == 2e-2
    device.write(":SENS:CURR:RANG:AUTO:ULIM 1e-3")
    device.write(":SENS:CURR:RANG:AUTO:LLIM 1e-9")
    assert float(device.query(":SENS:CURR:RANG:AUTO:ULIM?")) == 2e-3
    assert float(device.query(":SENS:CURR:RANG:AUTO:LLIM?")) == 2e-9
    assert device.query(":SENS:CURR:RANG:AUTO?") == "1"


@pytest.mark.parametrize("current,expected_range", [(0, 2e-9), (1e-9, 2e-9), (1e-7, 2e-7)])
def test_diagnostic_limits_constrain_actual_selected_range(simulator, current, expected_range):
    device = simulator(offset_A=current)
    device.write(":SENS:CURR:RANG:AUTO:ULIM 200e-9")
    device.write(":SENS:CURR:RANG:AUTO:LLIM 2e-9")
    reading = read_current(device)
    assert reading.value == pytest.approx(current)
    assert float(device.query(":SENS:CURR:RANG?")) == expected_range


def test_upper_limit_overload_is_invalid_instead_of_normal_current_on_smaller_range(simulator):
    device = simulator(offset_A=1e-9)
    device.write(":SENS:CURR:RANG:AUTO:ULIM 200e-12")
    raw = device.query(":READ?")
    assert raw.startswith("+9.90000000E+37OADC,")
    reading = parse_reading(raw, "FVMI_CURRENT")
    assert reading.value is None
    assert "OVERFLOW" in reading.flags
    assert float(device.query(":SENS:CURR:RANG?")) == 2e-10
    assert device.query(":SENS:CURR:RANG:AUTO?") == "1"


@pytest.mark.parametrize("range_key", [":SENS:CURR:RANG", ":SENS:RES:MAN:CRANG"])
def test_manual_range_selects_capable_range_and_disables_its_autorange(simulator, range_key):
    device = simulator()
    assert device.query(range_key + ":AUTO?") == "1"
    device.write(range_key + " 1e-9")
    assert float(device.query(range_key + "?")) == 2e-9
    assert device.query(range_key + ":AUTO?") == "0"


@pytest.mark.parametrize("current", [2.1e-9, -2.1e-9])
def test_fixed_range_allows_105_percent_fullscale(simulator, current):
    device = simulator(offset_A=current)
    device.write(":SENS:CURR:RANG 2e-9")
    assert read_current(device).value == pytest.approx(current)


@pytest.mark.parametrize("current", [2.1001e-9, -2.1001e-9])
def test_fixed_range_above_105_percent_emits_overflow_sentinel(simulator, current):
    device = simulator(offset_A=current)
    device.write(":SENS:CURR:RANG 2e-9")
    raw = device.query(":READ?")
    assert raw.startswith("+9.90000000E+37OADC,")
    assert read_current(device).value is None
    assert float(device.query(":SENS:CURR:RANG?")) == 2e-9


@pytest.mark.parametrize("value", ["-1", "NAN", "INF", "0.022"])
@pytest.mark.parametrize("suffix", ["", ":AUTO:LLIM", ":AUTO:ULIM"])
def test_invalid_numeric_range_does_not_mutate_state(simulator, value, suffix):
    device = simulator()
    key = ":SENS:CURR:RANG" + suffix
    before = dict(device.values)
    with pytest.raises(CommunicationError):
        device.write(f"{key} {value}")
    assert device.values == before


def test_reversed_autorange_limits_are_rejected_without_mutating_state(simulator):
    device = simulator()
    device.write(":SENS:CURR:RANG:AUTO:LLIM 2e-9")
    before = dict(device.values)
    with pytest.raises(CommunicationError, match="lower limit"):
        device.write(":SENS:CURR:RANG:AUTO:ULIM 20e-12")
    assert device.values == before


@pytest.mark.parametrize(
    "fault,status",
    [("overflow_at_read", "O"), ("underflow_at_read", "U"), ("out_of_limit_at_read", "L")],
)
def test_explicit_read_fault_still_overrides_natural_range_status(simulator, fault, status):
    device = simulator(offset_A=1e-9, faults={fault: 1})
    device.write(":SENS:CURR:RANG 20e-12")
    assert f"{status}ADC," in device.query(":READ?")


def test_existing_range_change_fault_is_applied_after_automatic_selection(simulator):
    device = simulator(offset_A=1e-9, faults={"range_change_at_read": 1})
    assert read_current(device).value == pytest.approx(1e-9)
    assert float(device.query(":SENS:CURR:RANG?")) == 2e-8
    assert float(device.query(":SENS:RES:MAN:CRANG?")) == 2e-8


def test_native_manual_vsource_uses_its_own_current_range(simulator):
    device = simulator(resistance_ohm=100e6)
    device.write(":SENS:FUNC 'RES'")
    device.write(":SENS:RES:MAN:CRANG 20e-12")
    device.write(":SOUR:VOLT 1")
    device.write(":OUTP1 ON")
    fixed = parse_reading(device.query(":READ?"), "NATIVE_RESISTANCE")
    assert fixed.value is None
    assert "UNDERFLOW" in fixed.flags
    device.write(":SENS:RES:MAN:CRANG:AUTO ON")
    automatic = parse_reading(device.query(":READ?"), "NATIVE_RESISTANCE")
    assert automatic.value == pytest.approx(100e6)
    assert float(device.query(":SENS:RES:MAN:CRANG?")) == 2e-8
    assert float(device.query(":SENS:CURR:RANG?")) == 2e-9


def test_native_current_range_overload_is_underflow_unless_explicit_fault_overrides(simulator):
    device = simulator(resistance_ohm=1e9, faults={"overflow_at_read": 2})
    device.write(":SENS:FUNC 'RES'")
    device.write(":SENS:RES:MAN:CRANG 20e-12")
    device.write(":SOUR:VOLT 1")
    device.write(":OUTP1 ON")

    raw = device.query(":READ?")
    assert raw.startswith("+0.00000000E+00UOHM,")
    reading = parse_reading(raw, "NATIVE_RESISTANCE")
    assert reading.value is None
    assert reading.flags == ("UNDERFLOW",)
    assert float(device.query(":SENS:RES:MAN:CRANG?")) == 2e-11
    assert device.query(":READ?").startswith("+9.90000000E+37OOHM,")


@pytest.mark.parametrize(
    "faults,expected",
    [
        ({}, "0"),
        ({"calibration_invalid": True}, "256"),
        ({"questionable_condition": 264}, "264"),
        ({"calibration_invalid": True, "questionable_condition": 0}, "0"),
        ({"questionable_condition": "invalid register reply"}, "invalid register reply"),
    ],
)
def test_questionable_condition_query_reports_fault_register_without_inventing_calibration(
    simulator, faults, expected
):
    device = simulator(faults=faults)
    assert device.query(":STAT:QUES:COND?") == expected
