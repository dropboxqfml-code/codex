"""Synthetic checks for the observed N-status pA plateau and real small currents."""

import csv
import json
from datetime import datetime

import pytest

from keithley6517a.clock import FakeClock
from keithley6517a.config import RunConfig
from keithley6517a.driver.instrument import Instrument
from keithley6517a.measurement.runner import MeasurementRunner
from keithley6517a.transport.simulator import SimulatorTransport


def run_current(
    tmp_path,
    volts,
    resistance,
    *,
    plateau=False,
    trip=10e-9,
    dwell=1.2,
    stop=False,
    transport_type=SimulatorTransport,
):
    clock = FakeClock()
    transport = transport_type(
        clock,
        resistance_ohm=resistance,
        offset_A=0,
        noise_A=0,
        absorption_A=0,
        faults={"picoamp_autorange_plateau": plateau},
    )
    config = RunConfig(
        output_directory=str(tmp_path),
        protocol="list",
        voltages=volts,
        dwell_s=dwell,
        summary_window_s=dwell,
        sample_interval_s=0.2,
        nplc=1,
        range_settle_s=0.1,
        current_trip_A=trip,
        bipolar_authorized=any(voltage < 0 for voltage in volts),
        residual_warning_ack=True,
    )
    runner = MeasurementRunner(config, instrument=Instrument(transport, clock), clock=clock)
    if stop:
        # Cancel during the reference settle period, after successful range readback.
        runner.on_event = lambda item: (
            runner.request_stop("stop during comparison")
            if item.get("state") == "SETTLING" and runner._picoamp_reference_range_A
            else None
        )
    try:
        runner.connect()
        runner.arm()
        assert ":OUTP1 ON" not in transport.commands
        result = runner.start()
        folder = runner.run_directory
        return (
            result,
            list(runner.rows),
            list(runner.events),
            list(transport.commands),
            folder,
        )
    finally:
        runner.shutdown()


def test_healthy_auto_uses_20_and_200_pa_for_real_low_signals(tmp_path):
    result, rows, events, _, _ = run_current(tmp_path, (0.1, 0.5, 1), 10e9)
    assert result["status"] == "completed"
    assert result["output_state"] == "OFF"
    assert not any(event["event"].startswith("picoamp_comparison") for event in events)
    expected = {0.1: (10e-12, 20e-12), 0.5: (50e-12, 200e-12), 1: (100e-12, 200e-12)}
    assert {row["voltage_requested_V"] for row in rows} == set(expected)
    for row in rows:
        current, measurement_range = expected[row["voltage_requested_V"]]
        assert row["current_raw_A"] == pytest.approx(current, abs=1e-16)
        assert row["current_range_A"] == measurement_range


@pytest.mark.parametrize(
    "resistance,volts,expected_first", [(100e6, (0.1, 0.5), 1e-9), (1e9, (0.1,), 100e-12)]
)
def test_false_plateau_is_remeasured_at_same_voltage_even_for_a_smaller_true_current(
    tmp_path, resistance, volts, expected_first
):
    result, rows, events, commands, folder = run_current(tmp_path, volts, resistance, plateau=True)
    assert result["status"] == "completed"
    assert result["output_state"] == "OFF"
    original, reference = [e for e in events if e["event"].startswith("picoamp_comparison")]
    assert original["original_current_A"] == pytest.approx(158e-12, abs=1e-16)
    assert original["original_range_after_A"] == 200e-12
    assert reference["reference_current_A"] == pytest.approx(expected_first, abs=1e-16)
    assert reference["reference_reading_number"] == original["original_reading_number"] + 1
    assert reference["reference_response"] == rows[0]["raw_response"]
    assert reference["reference_reading_minus_original_A"] == pytest.approx(
        expected_first - 158e-12
    )
    assert commands.count(":OUTP1 ON") == 1
    assert commands.count(":SENS:CURR:RANG 2E-09") == 1
    assert commands.count(":SENS:CURR:RANG:AUTO ON") == 1
    for row in rows:
        assert row["current_raw_A"] == pytest.approx(
            row["voltage_requested_V"] / resistance, abs=1e-16
        )
        assert row["current_range_A"] == (2e-9 if row["voltage_requested_V"] == 0.1 else 20e-9)
    raw = [
        json.loads(line)
        for line in (folder / "raw_io.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert any(entry.get("response") == original["original_response"] for entry in raw)
    with (folder / "analysis.txt").open(encoding="utf-8", newline="") as stream:
        exported = list(csv.DictReader(stream, delimiter="\t"))
    assert [float(row["Current (A)"]) for row in exported] == [row["current_raw_A"] for row in rows]


@pytest.mark.parametrize("sign", [-1, 1])
@pytest.mark.parametrize("current", [149.999e-12, 150e-12, 158e-12, 200e-12])
def test_genuine_near_full_scale_pa_survives_comparison(tmp_path, sign, current):
    voltage = sign * 0.5
    result, rows, events, _, _ = run_current(tmp_path, (voltage,), 0.5 / current, trip=1e-9)
    assert result["status"] == "completed"
    comparisons = [e for e in events if e["event"].startswith("picoamp_comparison")]
    should_compare = current >= 150e-12
    assert len(comparisons) == (2 if should_compare else 0)
    if should_compare:
        assert comparisons[0]["original_current_A"] == comparisons[1]["reference_current_A"]
        assert comparisons[1]["reference_current_A"] == pytest.approx(sign * current, abs=1e-16)
        assert comparisons[1]["source_voltage_setting_V"] == voltage
        assert comparisons[1]["original_range_after_A"] == 200e-12
        assert comparisons[1]["reference_range_before_A"] == 2e-9
        assert comparisons[1]["reference_range_after_A"] == 2e-9
    assert all(row["current_raw_A"] == pytest.approx(sign * current, abs=1e-16) for row in rows)
    assert all(row["status_code"] == "N" for row in rows)
    assert all(row["current_range_A"] == (2e-9 if should_compare else 200e-12) for row in rows)


def test_deferred_pair_retains_actual_read_intervals_instead_of_off_time(tmp_path):
    result, rows, events, _, folder = run_current(tmp_path, (0.1,), 100e6, plateau=True)
    assert result["status"] == "completed"
    pair = next(e for e in events if e["event"] == "picoamp_comparison_readback")
    stopped = next(e for e in events if e["event"] == "output_stop")
    assert pair["read_time_basis"] == "HOST_READ_CALL_NOT_INDEPENDENT_ADC_TIMING"
    assert (
        pair["original_read_start_monotonic_s"]
        < pair["original_read_end_monotonic_s"]
        < pair["reference_read_start_monotonic_s"]
        < pair["reference_read_end_monotonic_s"]
        < stopped["monotonic_s"]
        <= pair["monotonic_s"]
    )
    raw = [json.loads(line) for line in (folder / "raw_io.jsonl").read_text().splitlines()]
    reads = [entry for entry in raw if entry["command"] == ":READ?"]
    for prefix, start, end in (("original", reads[0], reads[1]), ("reference", reads[2], reads[3])):
        assert start["direction"] == "tx" and end["direction"] == "rx"
        assert pair[f"{prefix}_response"] == end["response"]
        assert pair[f"{prefix}_read_start_monotonic_s"] == start["monotonic_s"]
        assert pair[f"{prefix}_read_end_monotonic_s"] == end["monotonic_s"]
        assert pair[f"{prefix}_read_start_wall_time_iso8601"] == start["wall_time_iso8601"]
        assert pair[f"{prefix}_read_end_wall_time_iso8601"] == end["wall_time_iso8601"]
        assert (
            datetime.fromisoformat(pair[f"{prefix}_read_start_wall_time_iso8601"])
            < datetime.fromisoformat(pair[f"{prefix}_read_end_wall_time_iso8601"])
            < datetime.fromisoformat(pair["wall_time_iso8601"])
        )
        assert pair[f"{prefix}_voltage_reported_by_instrument_V"] == 0.1
    assert pair["reference_read_start_monotonic_s"] == rows[0]["read_start_monotonic_s"]
    assert pair["reference_read_end_monotonic_s"] == rows[0]["read_end_monotonic_s"]


class RecordedRecoveryTransport(SimulatorTransport):
    """Replay the recorded same-voltage pair, not a model of the physical fault."""

    def _reading(self):
        super()._reading()
        if self.read_count == 1:
            return "+157.8983E-12NADC,+02633rdng#,+0000.100Vsrc"
        return f"+0.788739E-09NADC,+{2632 + self.read_count:05d}rdng#,+0000.100Vsrc"


def test_recorded_100_megohm_trial_pair_preserves_both_acquisitions(tmp_path):
    result, rows, events, commands, _ = run_current(
        tmp_path, (0.1,), 100e6, plateau=True, transport_type=RecordedRecoveryTransport
    )
    assert result["status"] == "completed"
    pair = next(e for e in events if e["event"] == "picoamp_comparison_readback")
    assert pair["original_reading_number"] == 2633
    assert pair["reference_reading_number"] == 2634
    assert pair["original_current_A"] == pytest.approx(157.8983e-12)
    assert pair["reference_current_A"] == pytest.approx(788.739e-12)
    assert pair["reference_reading_minus_original_A"] == pytest.approx(630.8407e-12)
    assert pair["original_range_before_A"] == 20e-12
    assert pair["original_range_after_A"] == 200e-12
    assert pair["reference_range_before_A"] == pair["reference_range_after_A"] == 2e-9
    assert all(row["current_raw_A"] == pytest.approx(788.739e-12) for row in rows)
    assert all(row["current_range_A"] == 2e-9 for row in rows)
    switch = commands.index(":SENS:CURR:RANG 2E-09")
    assert not any(command.startswith(":SOUR:VOLT ") for command in commands[switch:])
    assert commands.count(":SYST:ZCOR ON") == 1


def test_later_overflow_can_raise_reference_past_200_na(tmp_path):
    result, rows, events, commands, _ = run_current(
        tmp_path, (0.01, 5), 10e6, plateau=True, trip=1e-6
    )
    assert result["status"] == "completed"
    assert result["output_state"] == "OFF"
    assert any(e["event"] == "picoamp_reference_overflow" for e in events)
    assert commands.count(":SENS:CURR:RANG 2E-09") == 1
    assert commands.count(":SENS:CURR:RANG 2E-06") == 1
    pair = next(e for e in events if e["event"] == "picoamp_comparison_readback")
    later_overflow = next(e for e in events if e["event"] == "picoamp_reference_overflow")
    assert pair["source_voltage_setting_V"] == 0.01
    assert pair["original_voltage_reported_by_instrument_V"] == 0.01
    assert pair["reference_voltage_reported_by_instrument_V"] == 0.01
    assert pair["reference_range_A"] == 2e-9
    assert pair["reference_range_before_A"] == pair["reference_range_after_A"] == 2e-9
    assert pair["reference_reading_number"] == rows[0]["reading_number"]
    assert pair["reference_read_end_monotonic_s"] < later_overflow["monotonic_s"]
    expected = {0.01: (1e-9, 2e-9), 5: (500e-9, 2e-6)}
    for row in rows:
        current, measurement_range = expected[row["voltage_requested_V"]]
        assert row["current_raw_A"] == pytest.approx(current, abs=1e-16)
        assert row["current_range_A"] == measurement_range


def test_reference_overflow_above_trip_capacity_stops_without_promotion(tmp_path):
    result, rows, events, commands, _ = run_current(
        tmp_path, (1, 0.5), 100e6, plateau=True, trip=1e-9
    )
    assert result["status"] == "aborted"
    assert result["output_state"] == "OFF"
    assert rows[0]["status_code"] == "O"
    assert not rows[0]["valid_for_summary"]
    assert not any(e["event"] == "picoamp_reference_overflow" for e in events)
    assert ":SOUR:VOLT 0.5" not in commands


@pytest.mark.parametrize("trip,reference_taken", [(5e-9, True), (100e-12, False)])
def test_trip_still_applies_to_original_and_reference_reads(tmp_path, trip, reference_taken):
    result, rows, events, commands, _ = run_current(
        tmp_path, (1, 0.5), 100e6, plateau=True, trip=trip
    )
    assert result["status"] == "aborted"
    assert result["output_state"] == "OFF"
    assert "Software current trip" in result["reason"]
    first = rows[0]
    assert "SOFTWARE_CURRENT_TRIP" in first["quality_flags"]
    assert not first["valid_for_summary"]
    assert ":SOUR:VOLT 0.5" not in commands
    comparison_events = [e["event"] for e in events if e["event"].startswith("picoamp_comparison")]
    assert bool(comparison_events) == reference_taken
    if reference_taken:
        assert first["current_raw_A"] == pytest.approx(10e-9, abs=1e-16)
        names = [e["event"] for e in events]
        assert names.index("output_stop") < names.index("picoamp_comparison_readback")
        pair = next(e for e in events if e["event"] == "picoamp_comparison_readback")
        stopped = next(e for e in events if e["event"] == "output_stop")
        assert pair["reference_read_end_monotonic_s"] == stopped["monotonic_s"]
    else:
        assert first["current_raw_A"] == pytest.approx(158e-12, abs=1e-16)


def test_user_stop_during_comparison_never_retries_or_publishes_original(tmp_path):
    result, rows, events, commands, _ = run_current(
        tmp_path, (0.1, 0.5), 100e6, plateau=True, stop=True
    )
    assert result["status"] == "stopped"
    assert result["output_state"] == "OFF"
    assert not rows
    assert commands.count(":READ?") == 1
    assert commands.count(":OUTP1 ON") == 1
    assert any(e["event"] == "picoamp_comparison_started" for e in events)
    assert not any(e["event"] == "picoamp_comparison_readback" for e in events)
