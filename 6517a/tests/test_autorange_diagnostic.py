"""Manual-derived AUTO/CAL regression fixtures; no NI bus or physical source is used."""

import csv
import json

import pytest

from keithley6517a.clock import FakeClock
from keithley6517a.config import ConfigurationError, RunConfig
from keithley6517a.driver.instrument import Instrument
from keithley6517a.driver.parser import ProtocolError
from keithley6517a.measurement.runner import MeasurementRunner
from keithley6517a.transport.simulator import SimulatorTransport


class DiagnosticBus(SimulatorTransport):
    """Exercise the real driver policy with explicitly synthetic condition replies."""

    is_simulation = False

    def __init__(self, *args, condition="0", mismatch=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.condition = str(condition)
        self.mismatch = mismatch
        # Retained narrow AUTO limits must be widened before requesting the 2 nA floor.
        self.values[":SENS:CURR:RANG:AUTO:LLIM"] = "2e-11"
        self.values[":SENS:CURR:RANG:AUTO:ULIM"] = "2e-11"

    def query(self, command):
        command = self._canonical(command)
        if command == ":STAT:QUES:COND?":
            self._owned()
            self.commands.append(command)
            return self.condition
        response = super().query(command)
        key = command.removesuffix("?")
        written = any(item.startswith(key + " ") for item in self.commands)
        if command.endswith("?") and written:
            if self.mismatch == "lower" and key == ":SENS:CURR:RANG:AUTO:LLIM":
                return "2e-11"
            if self.mismatch == "upper" and key == ":SENS:CURR:RANG:AUTO:ULIM":
                return "2e-6"
            if self.mismatch == "zero_range" and key == ":SENS:CURR:RANG":
                return "2e-10"
            if (
                self.mismatch == "auto_on"
                and key == ":SENS:CURR:RANG:AUTO"
                and self.values[key] == "1"
            ):
                return "0"
        return response


def operator_config(tmp_path, **changes):
    values = dict(
        simulation=False,
        transport="visa",
        resource="GPIB0::27::INSTR",
        setup_policy="operator_low_voltage",
        operator_setup_acknowledged=True,
        voltages=(1,),
        source_range_V=100,
        current_trip_A=1e-8,
        residual_warning_ack=True,
        resistive_limit_enabled=False,
        dwell_s=0.6,
        summary_window_s=0.6,
        sample_interval_s=0.1,
        nplc=1,
        range_settle_s=0,
        output_directory=str(tmp_path),
    )
    values.update(changes)
    return RunConfig(**values)


def runner_for(config, **options):
    clock = FakeClock()
    bus = DiagnosticBus(
        clock=clock,
        resistance_ohm=1e9,
        offset_A=0,
        noise_A=0,
        absorption_A=0,
        **options,
    )
    runner = MeasurementRunner(config, instrument=Instrument(bus, clock), clock=clock)
    runner.connect()
    return runner, bus


def test_old_config_defaults_retain_full_auto_range_without_diagnostic_mode():
    config = RunConfig.from_dict({"current_autorange": True})
    assert config.current_autorange_min_A == 20e-12
    assert config.current_autorange_max_A == 20e-3
    assert config.calibration_diagnostic_only is False
    assert RunConfig.from_dict(config.to_dict()) == config


@pytest.mark.parametrize(
    "changes",
    [
        {"current_autorange_min_A": 0},
        {"current_autorange_min_A": True},
        {"current_autorange_min_A": float("nan")},
        {"current_autorange_max_A": float("inf")},
        {"current_autorange_min_A": 2e-12},
        {"current_autorange_max_A": 0.2},
        {"current_autorange_min_A": 3e-9},
        {"current_autorange_min_A": 200e-9, "current_autorange_max_A": 2e-9},
    ],
)
def test_invalid_or_unordered_auto_limits_are_rejected_before_connect(tmp_path, changes):
    with pytest.raises(ConfigurationError):
        operator_config(tmp_path, **changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"setup_policy": "verified_fixture"},
        {"mode": "NATIVE_RESISTANCE"},
        {"source_range_V": 1000},
        {"voltages": (1.005,)},
        {"voltages": (-1.005,), "bipolar_authorized": True},
    ],
)
def test_calibration_diagnostic_cannot_extend_its_explicit_one_volt_policy(tmp_path, changes):
    with pytest.raises(ConfigurationError):
        operator_config(tmp_path, calibration_diagnostic_only=True, **changes)


@pytest.mark.parametrize("condition", [256, 257, 768, "+256"])
def test_normal_cal_invalid_blocks_arm_before_zero_correct_or_output(tmp_path, condition):
    runner, bus = runner_for(operator_config(tmp_path), condition=condition)
    try:
        with pytest.raises(ProtocolError, match="Calibration|교정|B8"):
            runner.arm()
        assert ":SYST:ZCOR ON" not in bus.commands
        assert ":SYST:ZCOR:ACQ" not in bus.commands
        assert ":OUTP1 ON" not in bus.commands
        assert not bus.output and runner.output_state == "OFF"
        assert not runner.can_start
    finally:
        runner.shutdown()


@pytest.mark.parametrize("condition", ["", "-1", "65536", "256.5", "nan", "ERROR"])
def test_invalid_condition_response_is_not_treated_as_calibration_valid(tmp_path, condition):
    runner, bus = runner_for(operator_config(tmp_path), condition=condition)
    try:
        with pytest.raises(ProtocolError, match="condition"):
            runner.arm()
        assert ":SYST:ZCOR ON" not in bus.commands and ":OUTP1 ON" not in bus.commands
        assert not bus.output and runner.output_state == "OFF"
    finally:
        runner.shutdown()


def test_auto_interval_zero_range_and_readbacks_are_established_before_start(tmp_path):
    config = operator_config(
        tmp_path,
        calibration_diagnostic_only=True,
        current_autorange_min_A=2e-9,
        current_autorange_max_A=200e-9,
    )
    runner, bus = runner_for(config, condition=256)
    try:
        runner.arm()
        assert runner.can_start and not bus.output
        assert ":OUTP1 ON" not in bus.commands
        commands = bus.commands
        limit_writes = [
            (index, command.split(" ", 1)[0], float(command.split(" ", 1)[1]))
            for index, command in enumerate(commands)
            if command.startswith((":SENS:CURR:RANG:AUTO:LLIM ", ":SENS:CURR:RANG:AUTO:ULIM "))
        ]
        assert [(key.rsplit(":", 1)[1], value) for _, key, value in limit_writes] == [
            ("ULIM", 20e-3),
            ("LLIM", 2e-9),
            ("ULIM", 200e-9),
        ]
        range_index = next(
            index
            for index, command in enumerate(commands)
            if command.startswith(":SENS:CURR:RANG ")
        )
        assert float(commands[range_index].split(" ", 1)[1]) == 2e-9
        assert commands.index(":SENS:CURR:RANG:AUTO OFF") < limit_writes[0][0]
        assert limit_writes[-1][0] < range_index < commands.index(":SYST:ZCOR ON")
        assert commands.index(":SYST:ZCOR ON") < commands.index(":SENS:CURR:RANG:AUTO ON")
        for index, key, _ in limit_writes:
            assert key + "?" in commands[index + 1 :]
        metadata = json.loads((runner.run_directory / "metadata.json").read_text())
        settings = metadata["settings_readback"]
        assert settings["current_autorange_limits"] == {
            "before_A": {"lower": 20e-12, "upper": 20e-12},
            "lower_A": 2e-9,
            "upper_A": 200e-9,
        }
        assert settings["zero_correct_range_A"] == 2e-9
        assert settings["current_autorange_min_A"] == 2e-9
        assert settings["current_autorange_max_A"] == 200e-9
        assert settings["calibration_diagnostic_only"] is True
        assert settings["questionable_condition"] == 256
        assert settings["calibration_invalid"] is True
    finally:
        runner.shutdown()


def test_fixed_range_does_not_program_auto_limits_or_change_its_zero_range(tmp_path):
    config = operator_config(
        tmp_path,
        current_autorange=False,
        current_range_A=20e-9,
        current_autorange_min_A=2e-9,
        current_autorange_max_A=200e-9,
    )
    runner, bus = runner_for(config)
    try:
        runner.arm()
        assert not any(
            ":RANG:AUTO:LLIM" in item or ":RANG:AUTO:ULIM" in item for item in bus.commands
        )
        settings = json.loads((runner.run_directory / "metadata.json").read_text())[
            "settings_readback"
        ]
        assert settings["zero_correct_range_A"] == 20e-9
        assert settings["current_autorange_limits"] is None
        assert bus.values[":SENS:CURR:RANG:AUTO"] == "0"
        assert ":OUTP1 ON" not in bus.commands
    finally:
        runner.shutdown()


@pytest.mark.parametrize("mismatch", ["lower", "upper", "zero_range", "auto_on"])
def test_any_auto_or_zero_range_readback_mismatch_blocks_output(tmp_path, mismatch):
    config = operator_config(
        tmp_path,
        current_autorange_min_A=2e-9,
        current_autorange_max_A=200e-9,
    )
    runner, bus = runner_for(config, mismatch=mismatch)
    try:
        with pytest.raises(ProtocolError, match="mismatch"):
            runner.arm()
        assert ":OUTP1 ON" not in bus.commands
        assert not bus.output and runner.output_state == "OFF"
        assert not runner.can_start
    finally:
        runner.shutdown()


def test_explicit_diagnostic_does_not_ignore_existing_513_error_queue(tmp_path):
    runner, bus = runner_for(
        operator_config(tmp_path, calibration_diagnostic_only=True), condition=256
    )
    bus.errors.append('513,"Calibration failed"')
    try:
        with pytest.raises(ProtocolError, match="513"):
            runner.arm()
        assert ":SYST:ZCOR ON" not in bus.commands and ":OUTP1 ON" not in bus.commands
        assert not bus.output and runner.output_state == "OFF"
    finally:
        runner.shutdown()


@pytest.mark.parametrize("condition", [0, 256])
def test_diagnostic_keeps_numbers_but_excludes_every_sample_from_summary(tmp_path, condition):
    runner, bus = runner_for(
        operator_config(
            tmp_path,
            calibration_diagnostic_only=True,
            current_autorange_min_A=2e-9,
            current_autorange_max_A=200e-9,
        ),
        condition=condition,
    )
    try:
        runner.arm()
        result = runner.start()
        assert result["status"] == "completed" and not bus.output
        assert runner.rows
        for row in runner.rows:
            assert "CALIBRATION_DIAGNOSTIC_ONLY" in row["quality_flags"]
            assert ("CALIBRATION_INVALID" in row["quality_flags"]) is bool(condition & 256)
            assert row["valid_for_summary"] is False
            assert row["current_raw_A"] == pytest.approx(1e-9)
            assert row["resistance_apparent_ohm"] == pytest.approx(1e9)
        assert runner.summaries and all(summary["N"] == 0 for summary in runner.summaries)
        with (runner.run_directory / "readings.csv").open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == len(runner.rows)
        assert all("CALIBRATION_DIAGNOSTIC_ONLY" in row["quality_flags"] for row in rows)
    finally:
        runner.shutdown()


def test_diagnostic_error_row_is_never_mistaken_for_normal_measurement(tmp_path):
    runner, bus = runner_for(
        operator_config(tmp_path, calibration_diagnostic_only=True),
        condition=256,
        faults={"timeout_at_read": 2},
    )
    try:
        runner.arm()
        result = runner.start()
        assert result["status"] == "aborted" and not bus.output
        assert any(row["phase"] == "ERROR" for row in runner.rows)
        assert all("CALIBRATION_DIAGNOSTIC_ONLY" in row["quality_flags"] for row in runner.rows)
        assert all("CALIBRATION_INVALID" in row["quality_flags"] for row in runner.rows)
        assert not any(row["valid_for_summary"] for row in runner.rows)
    finally:
        runner.shutdown()


def test_normal_calibration_valid_run_remains_eligible_for_summary(tmp_path):
    runner, bus = runner_for(operator_config(tmp_path))
    try:
        runner.arm()
        result = runner.start()
        assert result["status"] == "completed" and not bus.output
        assert any(row["valid_for_summary"] for row in runner.rows)
        assert all("CALIBRATION_DIAGNOSTIC_ONLY" not in row["quality_flags"] for row in runner.rows)
        assert any(summary["N"] > 0 for summary in runner.summaries)
    finally:
        runner.shutdown()


def test_normal_start_rechecks_calibration_before_output_enable(tmp_path):
    runner, bus = runner_for(operator_config(tmp_path))
    try:
        runner.arm()
        bus.condition = "256"
        result = runner.start()
        assert result["status"] == "aborted"
        assert ":OUTP1 ON" not in bus.commands
        assert not bus.output and runner.output_state == "OFF"
    finally:
        runner.shutdown()


def test_diagnostic_driver_caps_hardware_and_direct_source_calls_to_one_volt(tmp_path):
    config = operator_config(tmp_path, calibration_diagnostic_only=True, voltage_ceiling_V=10)
    runner, bus = runner_for(config, condition=256)
    try:
        runner.arm()
        assert float(bus.values[":SOUR:VOLT:LIM"]) == 1
        settings = json.loads((runner.run_directory / "metadata.json").read_text())[
            "settings_readback"
        ]
        assert settings["voltage_ceiling_V"] == 1
        # A direct public-driver caller must obey the diagnostic cap too,
        # even after obtaining an explicit one-use START permit.
        driver = runner.instrument
        driver.authorize_start(config)
        driver.output_on()
        before = len(bus.commands)
        with pytest.raises(ValueError, match="ceiling"):
            driver.set_voltage(2)
        assert not any(command.startswith(":SOUR:VOLT ") for command in bus.commands[before:])
        assert bus.voltage == 0
    finally:
        runner.shutdown()


def test_normal_driver_blocks_source_write_if_calibration_changes_after_start(tmp_path):
    config = operator_config(tmp_path)
    runner, bus = runner_for(config)
    try:
        runner.arm()
        driver = runner.instrument
        driver.authorize_start(config)
        driver.output_on()
        bus.condition = "256"
        before = len(bus.commands)
        with pytest.raises(ProtocolError, match="Calibration|B8|교정"):
            driver.set_voltage(1)
        assert not any(command.startswith(":SOUR:VOLT ") for command in bus.commands[before:])
        assert bus.voltage == 0
    finally:
        runner.shutdown()


def test_normal_driver_blocks_read_if_calibration_changes_after_configuration(tmp_path):
    config = operator_config(tmp_path)
    runner, bus = runner_for(config)
    try:
        runner.arm()
        driver = runner.instrument
        driver.authorize_start(config)
        driver.output_on()
        driver.set_voltage(1)
        bus.condition = "256"
        before = len(bus.commands)
        with pytest.raises(ProtocolError, match="Calibration|B8|교정"):
            driver.read()
        assert ":STAT:QUES:COND?" in bus.commands[before:]
        assert ":READ?" not in bus.commands[before:]
        assert bus.read_count == 0
    finally:
        runner.shutdown()
