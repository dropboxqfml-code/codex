"""Documented front-panel zero correction, verified with an independent device spy."""

from dataclasses import replace

import pytest

from keithley6517a.clock import FakeClock
from keithley6517a.config import RunConfig
from keithley6517a.driver.instrument import Instrument
from keithley6517a.driver.parser import ProtocolError
from keithley6517a.measurement.runner import MeasurementRunner
from keithley6517a.transport.simulator import SimulatorTransport


class ZeroCorrectDevice(SimulatorTransport):
    """Local device double exercises real-control approval without any VISA session."""

    is_simulation = False

    def __init__(self, clock, *, enable_error=None, bad_readback=False, timeout=False):
        super().__init__(clock)
        self.enable_error = enable_error
        self.bad_readback = bad_readback
        self.enable_timeout = timeout
        self.captures = []
        self.enable_seen = False

    def write(self, command):
        if command == ":SYST:ZCOR:ACQ":
            self._owned()
            self.commands.append(command)
            self.errors.append('-200,"Execution error"')
            return
        if command == ":SYST:ZCOR ON":
            self.enable_seen = True
            capture = dict(
                function=self.values[":SENS:FUNC"],
                range_A=float(self.values[":SENS:CURR:RANG"]),
                auto=self.values[":SENS:CURR:RANG:AUTO"],
                zero_check=self.values[":SYST:ZCH"],
                output=self.output,
            )
            self.captures.append(capture)
            if self.enable_timeout:
                self.commands.append(command)
                raise TimeoutError("zero correct completion timeout")
            if self.enable_error or capture["zero_check"] != "1" or capture["output"]:
                self.commands.append(command)
                self.errors.append(self.enable_error or '-200,"Execution error"')
                return
        super().write(command)

    def query(self, command):
        value = super().query(command)
        if command == ":SYST:ZCOR?" and self.enable_seen and self.bad_readback:
            return "0"
        return value


def settings(tmp_path, **updates):
    return replace(
        RunConfig(),
        **(
            dict(
                simulation=False,
                transport="visa",
                resource="GPIB0::27::INSTR",
                setup_policy="operator_low_voltage",
                operator_setup_acknowledged=True,
                current_trip_A=1e-8,
                residual_warning_ack=True,
                resistive_limit_enabled=False,
                voltages=(1,),
                dwell_s=0.5,
                summary_window_s=0.5,
                sample_interval_s=0.1,
                nplc=0.1,
                range_settle_s=0.1,
                output_directory=str(tmp_path),
            )
            | updates
        ),
    )


@pytest.mark.parametrize(
    ("auto", "requested", "expected"),
    [(True, 2e-9, 20e-12), (False, 2e-9, 2e-9), (False, 20e-12, 20e-12)],
)
def test_front_panel_method_captures_zero_with_required_function_range_and_state(
    tmp_path, auto, requested, expected
):
    clock = FakeClock()
    device = ZeroCorrectDevice(clock)
    driver = Instrument(device, clock)
    driver.connect()
    try:
        readback = driver.configure(
            settings(tmp_path, current_autorange=auto, current_range_A=requested)
        )
        assert device.captures == [
            dict(function="CURR", range_A=expected, auto="0", zero_check="1", output=False)
        ]
        commands = device.commands
        on = commands.index(":SYST:ZCOR ON")
        off = commands.index(":SYST:ZCH OFF")
        assert on < off
        assert ":SYST:ZCOR?" in commands[on:off]
        assert commands[on + 1] == "*OPC?"
        assert ":SYST:ZCOR:ACQ" not in commands
        if auto:
            assert off < commands.index(":SENS:CURR:RANG:AUTO ON")
        else:
            assert ":SENS:CURR:RANG:AUTO ON" not in commands
        assert readback["zero_correct_method"] == "enable_while_zero_check_on"
        assert readback["zero_correct_range_A"] == expected
        assert driver.configured and driver.output_state == "OFF"
        assert device.values[":SYST:ZCOR"] == "1" and device.values[":SYST:ZCH"] == "0"
        assert ":OUTP1 ON" not in commands
        assert not any(command.startswith(("*CLS", "*RST", ":CAL:")) for command in commands)
    finally:
        driver.close()


@pytest.mark.parametrize(
    ("device_options", "message"),
    [
        ({"enable_error": '-200,"Execution error"'}, "zero correction enable"),
        ({"enable_error": '+513,"Calibration data lost"'}, "Calibration data lost"),
        ({"bad_readback": True}, "Setting mismatch :SYST:ZCOR"),
        ({"timeout": True}, "zero correct completion timeout"),
    ],
)
def test_rejected_or_unconfirmed_zero_correction_still_aborts_arm_and_confirms_off(
    tmp_path, device_options, message
):
    clock = FakeClock()
    device = ZeroCorrectDevice(clock, **device_options)
    driver = Instrument(device, clock)
    runner = MeasurementRunner(settings(tmp_path), driver, clock)
    try:
        runner.connect()
        with pytest.raises((ProtocolError, TimeoutError), match=message):
            runner.arm()
        assert runner.state == "FAULT" and runner.output_state == "OFF"
        assert not runner.can_start and not driver.configured
        assert device.commands.count(":SYST:ZCOR ON") == 1
        assert ":SYST:ZCOR:ACQ" not in device.commands
        assert ":OUTP1 ON" not in device.commands
        assert device.commands[-1] == ":OUTP1?"
    finally:
        runner.shutdown()


@pytest.mark.parametrize("error", ['-200,"Execution error"', '+513,"Calibration data lost"'])
def test_existing_instrument_errors_are_reported_before_new_configuration(tmp_path, error):
    clock = FakeClock()
    device = ZeroCorrectDevice(clock)
    driver = Instrument(device, clock)
    driver.connect()
    device.errors.append(error)
    before = len(device.commands)
    try:
        with pytest.raises(ProtocolError, match="before configuration") as exception:
            driver.configure(settings(tmp_path))
        assert error in str(exception.value)
        assert ":INIT:CONT OFF" not in device.commands[before:]
        assert ":SYST:ZCOR ON" not in device.commands
        assert ":OUTP1 ON" not in device.commands
        assert not driver.configured and driver.output_state == "OFF"
    finally:
        driver.close()


def test_native_simulation_retains_documented_acquire_then_enable_path(tmp_path):
    clock = FakeClock()
    device = SimulatorTransport(clock)
    driver = Instrument(device, clock)
    config = replace(
        settings(tmp_path), simulation=True, transport="simulation", mode="NATIVE_RESISTANCE"
    )
    driver.connect()
    try:
        readback = driver.configure(config)
        acquire = device.commands.index(":SYST:ZCOR:ACQ")
        check_off = device.commands.index(":SYST:ZCH OFF")
        enable = device.commands.index(":SYST:ZCOR ON")
        assert acquire < check_off < enable
        assert readback["zero_correct_method"] == "acquire_then_enable"
        assert ":OUTP1 ON" not in device.commands
    finally:
        driver.close()
