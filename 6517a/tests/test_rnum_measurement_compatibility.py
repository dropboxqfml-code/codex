"""Screenshot-derived rdng# records pass through acquisition without changing measured data."""

import csv
import json
from dataclasses import replace

import pytest

from keithley6517a.clock import FakeClock
from keithley6517a.config import RunConfig
from keithley6517a.driver.instrument import Instrument
from keithley6517a.measurement.runner import MeasurementRunner
from keithley6517a.transport.simulator import SimulatorTransport

SCREENSHOT_CURRENT_A = 64.8960e-12


class ReportedSuffixDevice(SimulatorTransport):
    """Local format fixture transcribed from the user screenshot, not a hardware session."""

    def __init__(self, clock, *, fault=None):
        super().__init__(clock, resistance_ohm=1e9)
        self.fault = fault
        self.responses = []

    def _reading(self):
        # Preserve the simulator's ownership, conversion time and read counter.
        super()._reading()
        number = 1121 + self.read_count
        current, status, source, suffix = "+064.8960E-12", "N", "+0001.000", "rdng#"
        if self.read_count == 2:
            if self.fault == "duplicate":
                number -= 1
            elif self.fault == "source":
                source = "+0002.000"
            elif self.fault == "trip":
                current = "+020.0000E-09"
            elif self.fault == "reference":
                status = "R"
            elif self.fault == "suffix":
                suffix = "readng#"
        response = f"{current}{status}ADC,{number:+06d}{suffix},{source}Vsrc"
        self.responses.append(response)
        return response


def configuration(tmp_path, *, geometry=False):
    settings = dict(
        output_directory=str(tmp_path),
        sample_id="SCREENSHOT-FORMAT-FIXTURE",
        voltages=(1,),
        current_trip_A=1e-8,
        current_autorange=False,
        current_range_A=2e-9,
        residual_warning_ack=True,
        simulation_resistance_ohm=1e9,
        dwell_s=0.3,
        summary_window_s=0.3,
        sample_interval_s=0.1,
        nplc=0.1,
        range_settle_s=0,
    )
    if geometry:
        settings.update(
            sample_length_mm=20,
            sample_width_mm=10,
            sample_depth_mm=2,
            current_path_axis="D",
        )
    return replace(RunConfig(), **settings)


def acquire(tmp_path, *, geometry=False, fault=None):
    clock = FakeClock()
    device = ReportedSuffixDevice(clock, fault=fault)
    driver = Instrument(device, clock)
    runner = MeasurementRunner(configuration(tmp_path, geometry=geometry), driver, clock)
    try:
        runner.connect()
        runner.arm()
        assert ":OUTP1 ON" not in device.commands
        result = runner.start()
        assert result["output_state"] == "OFF" and not device.output
        directory = runner.run_directory
    finally:
        runner.shutdown()
    return result, directory, device


@pytest.mark.parametrize("geometry", [False, True])
def test_reported_suffix_completes_and_preserves_raw_current_in_csv_and_analysis(
    tmp_path, geometry
):
    result, directory, device = acquire(tmp_path, geometry=geometry)
    assert result["status"] == "completed"
    assert device.responses[0] == "+064.8960E-12NADC,+01122rdng#,+0001.000Vsrc"
    with (directory / "readings.csv").open(encoding="utf-8", newline="") as stream:
        readings = list(csv.DictReader(stream))
    with (directory / "analysis.txt").open(encoding="utf-8", newline="") as stream:
        analysis = list(csv.reader(stream, delimiter="\t"))
    assert len(readings) == len(device.responses) >= 3
    assert len(analysis) == len(readings) + 1
    if geometry:
        assert analysis[0] == [
            "Time (s)",
            "Resistance (Ohm)",
            "Resistivity (Ohm m)",
            "Voltage (V)",
            "Current (A)",
        ]
    else:
        assert analysis[0] == ["Time (s)", "Resistance (Ohm)", "Voltage (V)", "Current (A)"]
    elapsed = [float(row["elapsed_s"]) for row in readings]
    assert elapsed == sorted(elapsed) and len(set(elapsed)) == len(elapsed)
    for index, (row, text) in enumerate(zip(readings, analysis[1:], strict=True)):
        assert row["raw_response"] == device.responses[index]
        assert int(row["reading_number"]) == 1122 + index
        assert row["status_code"] == "N"
        assert float(row["current_raw_A"]) == SCREENSHOT_CURRENT_A
        assert float(row["current_raw_A"]) != 1e-9
        assert row["current_inferred_A"] == ""
        assert float(row["voltage_programmed_readback_V"]) == 1
        assert float(row["voltage_reported_by_instrument_V"]) == 1
        expected_resistance = 1 / SCREENSHOT_CURRENT_A
        assert float(row["resistance_apparent_ohm"]) == pytest.approx(expected_resistance)
        assert float(text[0]) == float(row["elapsed_s"])
        assert float(text[1]) == float(row["resistance_apparent_ohm"])
        if geometry:
            assert float(row["resistivity_ohm_m"]) == pytest.approx(expected_resistance * 0.1)
            assert float(text[2]) == float(row["resistivity_ohm_m"])
        else:
            assert row["resistivity_ohm_m"] == ""
        assert float(text[-2]) == 1 and float(text[-1]) == SCREENSHOT_CURRENT_A


@pytest.mark.parametrize(
    ("fault", "reason"),
    [
        ("duplicate", "STALE_READING"),
        ("source", "Reported source setting mismatch"),
        ("trip", "Software current trip"),
        ("reference", "Invalid instrument state/reading"),
        ("suffix", "Malformed ASCII response"),
    ],
)
def test_reported_suffix_does_not_weaken_invalid_reading_abort_and_raw_error_records(
    tmp_path, fault, reason
):
    result, directory, device = acquire(tmp_path, fault=fault)
    assert result["status"] == "aborted" and reason in result["reason"]
    assert device.read_count == 2
    with (directory / "raw_io.jsonl").open(encoding="utf-8") as stream:
        transcript = [json.loads(line) for line in stream]
    replies = [
        item["response"]
        for item in transcript
        if item.get("direction") == "rx" and item.get("command") == ":READ?"
    ]
    assert replies == device.responses
    assert len(replies) == 2
    status = json.loads((directory / "run_status.json").read_text(encoding="utf-8"))
    assert status["status"] == "aborted" and status["final_output_state"] == "OFF"
    with (directory / "readings.csv").open(encoding="utf-8", newline="") as stream:
        readings = list(csv.DictReader(stream))
    assert float(readings[0]["current_raw_A"]) == SCREENSHOT_CURRENT_A
    assert readings[-1]["phase"] == "ERROR"
    assert any(reason in flag for flag in json.loads(readings[-1]["quality_flags"]))
