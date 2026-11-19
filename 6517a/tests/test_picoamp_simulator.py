import pytest

from keithley6517a.clock import FakeClock
from keithley6517a.driver import parse_reading
from keithley6517a.transport.base import CommunicationError
from keithley6517a.transport.simulator import SimulatorTransport


def current_meter(resistance_ohm, **faults):
    meter = SimulatorTransport(
        clock=FakeClock(),
        faults=faults,
        resistance_ohm=resistance_ohm,
        noise_A=0,
        offset_A=0,
        absorption_A=0,
    )
    meter.open()
    meter.write(":SYST:ZCH OFF")
    meter.write(":OUTP1 ON")
    return meter


def read_current(meter):
    return parse_reading(meter.query(":READ?"), "FVMI_CURRENT")


@pytest.mark.parametrize(
    ("resistance_ohm", "current_A", "range_A"), [(2e11, 5e-12, 2e-11), (1e10, 1e-10, 2e-10)]
)
def test_autorange_preserves_small_currents(resistance_ohm, current_A, range_A):
    meter = current_meter(resistance_ohm)
    meter.write(":SOUR:VOLT 1")
    reading = read_current(meter)
    assert reading.status == "N"
    assert reading.value == pytest.approx(current_A, abs=0, rel=1e-9)
    assert float(meter.query(":SENS:CURR:RANG?")) == range_A


def test_autorange_limits_constrain_range_and_fixed_write_turns_auto_off():
    meter = current_meter(1e9)
    meter.write(":SENS:CURR:RANG:AUTO:LLIM 2e-10")
    meter.write(":SENS:CURR:RANG:AUTO:ULIM 2e-10")
    assert float(meter.query(":SENS:CURR:RANG:AUTO:LLIM?")) == 2e-10
    assert float(meter.query(":SENS:CURR:RANG:AUTO:ULIM?")) == 2e-10
    with pytest.raises(CommunicationError, match="lower limit exceeds upper limit"):
        meter.write(":SENS:CURR:RANG:AUTO:LLIM 2e-9")

    meter.write(":SOUR:VOLT 0.205")
    assert read_current(meter).value == pytest.approx(205e-12, abs=0, rel=1e-9)
    meter.write(":SOUR:VOLT 0.22")
    reading = read_current(meter)
    assert reading.value is None and "OVERFLOW" in reading.flags

    meter.write(":SENS:CURR:RANG 2e-9")
    assert meter.query(":SENS:CURR:RANG:AUTO?") == "0"
    assert read_current(meter).value == pytest.approx(220e-12, abs=0, rel=1e-9)
    assert float(meter.query(":SENS:CURR:RANG?")) == 2e-9


def test_simulated_plateau_is_normal_status_only_at_nonzero_voltage_with_auto():
    meter = current_meter(1e9, picoamp_autorange_plateau=True)
    assert read_current(meter).value == 0
    meter.write(":SOUR:VOLT -1")
    reading = read_current(meter)
    assert reading.status == "N"
    assert reading.value == -158e-12
    assert float(meter.query(":SENS:CURR:RANG?")) == 2e-10

    meter.write(":SENS:CURR:RANG 2e-9")
    reading = read_current(meter)
    assert reading.status == "N"
    assert reading.value == -1e-9
