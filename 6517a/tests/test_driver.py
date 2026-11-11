"""Transport/driver tests use manual-derived ASCII fixtures, never real hardware."""

import threading
from types import SimpleNamespace

import pytest

from keithley6517a.driver import Instrument, ProtocolError, parse_identity, parse_reading
from keithley6517a.transport import SimulatorTransport
from keithley6517a.transport.base import CommunicationError, UnsupportedOperation
from keithley6517a.transport.visa import VisaTransport


class Clock:
    def __init__(self):
        self.t = 0.0

    def monotonic(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


def configured(**faults):
    clock = Clock()
    transport = SimulatorTransport(clock, faults=faults)
    driver = Instrument(transport, clock)
    driver.connect()
    driver.configure(
        SimpleNamespace(
            mode="FVMI_CURRENT",
            current_autorange=True,
            nplc=10,
            line_frequency_hz=60,
            source_range_V=100,
            voltage_ceiling_V=10,
            current_trip_A=1e-8,
        )
    )
    return driver, transport


def test_startup_identify_configure_never_enable_output():
    driver, transport = configured()
    assert not transport.output
    assert ":OUTP1 ON" not in transport.commands
    driver.close()
    driver.connect()
    assert ":OUTP1 ON" not in transport.commands


def test_wrong_model_gets_no_control_writes():
    transport = SimulatorTransport(faults={"idn": "KEITHLEY,MODEL 6517B,123,1.0"})
    driver = Instrument(transport)
    with pytest.raises(UnsupportedOperation):
        driver.connect()
    assert transport.commands == ["*IDN?"]


def test_requires_configuration_and_zero_setpoint_before_start():
    driver, _ = configured()
    driver.set_voltage(1)
    with pytest.raises(RuntimeError):
        driver.output_on()


def test_manual_vsource_and_current_autorange_independent():
    driver, transport = configured()
    assert transport.values[":SENS:RES:VSC"] == "MAN"
    assert transport.values[":SENS:CURR:RANG:AUTO"] == "1"
    driver.authorize_start(driver.config)
    driver.output_on()
    assert driver.set_voltage(1.001) == 1.0
    assert driver.set_voltage(1.004) == 1.005
    assert transport.values[":SENS:RES:VSC"] == "MAN"


@pytest.mark.parametrize("voltage", [float("nan"), float("inf"), -1, 10.001])
def test_voltage_policy(voltage):
    driver, transport = configured()
    with pytest.raises(ValueError):
        driver.set_voltage(voltage)
    assert not any(c.startswith(":SOUR:VOLT ") and c != ":SOUR:VOLT 0" for c in transport.commands)


def test_interlock_and_source_limit_block_voltage():
    driver, transport = configured()
    transport.faults["interlock"] = 0
    with pytest.raises(RuntimeError):
        driver.set_voltage(1)
    transport.faults["interlock"] = 1
    transport.faults["source_current_limit"] = True
    with pytest.raises(RuntimeError):
        driver.set_voltage(1)


def test_readback_clamp_is_not_accepted():
    driver, transport = configured()
    transport.faults["limit_clamp_V"] = 0.5
    with pytest.raises(ProtocolError, match="mismatch"):
        driver.set_voltage(1)


def test_no_retries_after_timeout():
    driver, transport = configured(timeout_at_read=1)
    driver.authorize_start(driver.config)
    driver.output_on()
    with pytest.raises(TimeoutError):
        driver.read()
    assert transport.commands.count(":READ?") == 1


def test_stale_data_aborts_instead_of_becoming_new_sample():
    driver, transport = configured(stale_at_read=2)
    driver.authorize_start(driver.config)
    driver.output_on()
    first = driver.read()
    assert first.reading_number == 1
    with pytest.raises(ProtocolError, match="STALE"):
        driver.read()
    assert transport.commands.count(":READ?") == 2


def test_stop_attempts_off_even_cancel_abort_and_logging_fail():
    driver, transport = configured()
    driver.authorize_start(driver.config)
    driver.output_on()
    transport.faults.update(fail_cancel=True, fail_abort=True)
    driver.io_callback = lambda event: (_ for _ in ()).throw(OSError("disk full"))
    errors = driver.safe_off()
    assert len(errors) == 2
    assert driver.output_state == "OFF"
    assert transport.commands[-2:] == [":OUTP1 OFF", ":OUTP1?"]


def test_off_failure_preserves_unknown():
    driver, transport = configured()
    driver.authorize_start(driver.config)
    driver.output_on()
    transport.faults["fail_off"] = True
    errors = driver.safe_off()
    assert errors
    assert driver.output_state == "UNKNOWN"


def test_disconnect_does_not_claim_off():
    driver, transport = configured(disconnect_at_read=1)
    driver.authorize_start(driver.config)
    driver.output_on()
    with pytest.raises(CommunicationError):
        driver.read()
    assert transport.output  # A disconnected source may remain energized.
    assert driver.safe_off()
    assert driver.output_state == "UNKNOWN"


@pytest.mark.parametrize(
    "status,expected",
    [
        ("Z", "ZERO_CHECK"),
        ("O", "OVERFLOW"),
        ("U", "UNDERFLOW"),
        ("R", "REFERENCE"),
        ("L", "OUT_OF_LIMIT"),
    ],
)
def test_status_is_not_a_valid_measurement(status, expected):
    reading = parse_reading(f"+1e-11{status}ADC,+00001rdg#,+10Vsrc", "FVMI_CURRENT")
    assert reading.value is None
    assert expected in reading.flags


@pytest.mark.parametrize(
    "raw",
    [
        "+1NADC,1,+0Vsrc,extra",
        "+1NADC,bad,+0Vsrc",
        "+1NOHM,1,+0Vsrc",
        "NaNNADC,1,+0Vsrc",
        "+1NADC,1,broken",
    ],
)
def test_parser_does_not_guess_or_replace_bad_tokens(raw):
    with pytest.raises(ProtocolError):
        parse_reading(raw, "FVMI_CURRENT")


def test_sentinel_and_signed_values():
    assert parse_reading("+9.91E37ZADC,+00001rdg#,+0Vsrc", "FVMI_CURRENT").value is None
    assert parse_reading("-1.2e-11NADC,+00002rdg#,+10Vsrc", "FVMI_CURRENT").value == -1.2e-11
    assert parse_reading("0NADC,+00003rdg#,+0Vsrc", "FVMI_CURRENT").value == 0


def test_transport_change_cannot_bypass_real_authorization():
    driver, transport = configured()
    transport.is_simulation = False
    with pytest.raises(UnsupportedOperation):
        driver.authorize_start(driver.config)
    assert ":OUTP1 ON" not in transport.commands


def test_range_and_query_time_metadata():
    driver, transport = configured(range_change_at_read=1)
    driver.read()
    status = driver.safety_status()
    assert status["current_range"] == 2e-8
    assert status["atomic_snapshot"] is False
    assert status["query_end_monotonic_s"] >= status["query_start_monotonic_s"]


def test_split_response_is_not_combined_with_new_query():
    driver, transport = configured(split_response_at_read=1)
    with pytest.raises(ProtocolError):
        driver.read()
    assert transport.commands.count(":READ?") == 1


def test_cable_absent_is_not_deduced_from_interlock_query_one():
    driver, transport = configured(cable_absent=True)
    status = driver.safety_status()
    assert status["interlock"] == 1
    assert status["fixture_installation_confirmed"] is False


def test_visa_unlock_failure_still_closes_session_and_manager():
    calls = []

    class Session:
        def unlock(self):
            calls.append("unlock")
            raise RuntimeError("unlock failed")

        def close(self):
            calls.append("session close")

    class Manager:
        def close(self):
            calls.append("manager close")

    transport = VisaTransport("GPIB0::27::INSTR", backend=None)
    transport.session = Session()
    transport.manager = Manager()
    transport.owner = threading.get_ident()
    transport.lock_acquired = True
    with pytest.raises(CommunicationError, match="unlock failed"):
        transport.close()
    assert calls == ["unlock", "session close", "manager close"]
    assert transport.session is None and transport.manager is None


def test_parse_identity_is_reusable_without_io():
    identity = parse_identity("KEITHLEY INSTRUMENTS INC., MODEL 6517A, SERIAL1, A01")
    assert identity["serial"] == "SERIAL1"
    assert identity["firmware"] == "A01"
    with pytest.raises(UnsupportedOperation):
        parse_identity("KEITHLEY,MODEL 6517B,S1,A01")


def test_zero_check_failure_cannot_delay_off():
    driver, transport = configured()
    driver.authorize_start(driver.config)
    driver.output_on()
    transport.faults["fail_zero_check"] = True
    assert driver.safe_off() == []
    assert driver.output_state == "OFF"
