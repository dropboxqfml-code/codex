"""Analysis text is a durable four-column projection of every original sample."""

import csv
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from keithley6517a.clock import FakeClock
from keithley6517a.config import RunConfig
from keithley6517a.measurement.runner import MeasurementRunner
from keithley6517a.storage.run_writer import ANALYSIS_HEADER, RunWriter, analysis_line


@pytest.fixture
def writer(tmp_path):
    value = RunWriter(replace(RunConfig(), output_directory=str(tmp_path)), {})
    try:
        yield value
    finally:
        value.close()


def test_analysis_header_is_ready_before_output_enable(writer):
    assert (writer.directory / "analysis.txt").read_bytes() == ANALYSIS_HEADER.encode("ascii")
    assert ANALYSIS_HEADER == "Time (s)\tResistance (Ohm)\tVoltage (V)\tCurrent (A)\n"
    assert json.loads((writer.directory / "run_status.json").read_text())["status"] == "armed"


def test_samples_keep_precision_sign_and_si_units_with_no_other_text(writer, monkeypatch):
    import keithley6517a.storage.run_writer as storage

    synchronized = []
    real_fsync = storage.os.fsync

    def fsync(descriptor):
        synchronized.append(descriptor)
        real_fsync(descriptor)

    monkeypatch.setattr(storage.os, "fsync", fsync)
    row = dict(
        elapsed_s=1.2345678901234567,
        resistance_apparent_ohm=-1.2345678901234567e9,
        voltage_programmed_readback_V=-1.0,
        current_raw_A=8.100000000000001e-10,
        valid_for_summary=False,
        quality_flags=["TRANSIENT"],
    )
    writer.sample(row)
    expected = "1.2345678901234567\t-1234567890.1234567\t-1.0\t8.100000000000001e-10\n"
    # An external reader sees the row while the run is still open.
    assert (writer.directory / "analysis.txt").read_text() == ANALYSIS_HEADER + expected
    assert synchronized == [writer.reading_stream.fileno(), writer.analysis_stream.fileno()]
    with (writer.directory / "readings.csv").open() as stream:
        csv_rows = list(csv.DictReader(stream))
    assert len(csv_rows) == 1 and csv_rows[0]["valid_for_summary"] == "False"
    assert json.loads(csv_rows[0]["quality_flags"]) == ["TRANSIENT"]


def test_native_zero_is_preserved_and_current_is_never_substituted(writer):
    writer.sample(
        dict(
            elapsed_s=-0.0,
            native_r_ohm=0.0,
            resistance_apparent_ohm=99.0,
            voltage_programmed_readback_V=0.0,
            current_raw_A=None,
            current_inferred_A=1e-9,
        )
    )
    assert (writer.directory / "analysis.txt").read_text() == (
        ANALYSIS_HEADER + "-0.0\t0.0\t0.0\tnan\n"
    )


def test_multiple_samples_include_errors_with_one_header_and_no_footer(writer):
    writer.sample(
        dict(
            elapsed_s=1.0,
            resistance_apparent_ohm=1e9,
            voltage_programmed_readback_V=1.0,
            current_raw_A=1e-9,
        )
    )
    writer.sample(dict(phase="ERROR", elapsed_s=3.0, quality_flags=["RUN_ABORTED"]))
    writer.summaries([{"step_index": 0, "mean_current_A": 1e-9}])
    writer.status("aborted", "example failure", "OFF")
    writer.close()
    assert (writer.directory / "analysis.txt").read_text() == (
        ANALYSIS_HEADER + "1.0\t1000000000.0\t1.0\t1e-09\n3.0\tnan\tnan\tnan\n"
    )


def test_csv_numeric_strings_and_blank_native_resistance_use_the_same_projection():
    assert (
        analysis_line(
            {
                "elapsed_s": "1.2",
                "native_r_ohm": "",
                "resistance_apparent_ohm": "1000000000.0",
                "voltage_programmed_readback_V": "1.0",
                "current_raw_A": "",
                "current_inferred_A": "1e-9",
            }
        )
        == "1.2\t1000000000.0\t1.0\tnan\n"
    )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_unclassified_nonfinite_values_are_not_written(writer, value):
    with pytest.raises(ValueError, match="Non-finite"):
        writer.sample(dict(elapsed_s=1.0, current_raw_A=value))
    assert (writer.directory / "analysis.txt").read_text() == ANALYSIS_HEADER
    assert len((writer.directory / "readings.csv").read_text().splitlines()) == 1
    with pytest.raises(ValueError, match="Non-finite"):
        analysis_line(dict(elapsed_s="1", current_raw_A=str(value)))


def prepared_runner(tmp_path):
    config = replace(
        RunConfig(),
        output_directory=str(tmp_path),
        voltages=(1,),
        current_trip_A=1e-8,
        residual_warning_ack=True,
        dwell_s=0.5,
        summary_window_s=0.5,
        sample_interval_s=0.1,
    )
    runner = MeasurementRunner(config, clock=FakeClock())
    runner.connect()
    return runner


def test_analysis_creation_failure_cannot_enable_output(tmp_path, monkeypatch):
    original = RunWriter._open

    def fail_analysis_open(self, name):
        if name == "analysis.txt":
            raise OSError("analysis creation failed")
        return original(self, name)

    monkeypatch.setattr(RunWriter, "_open", fail_analysis_open)
    runner = prepared_runner(tmp_path)
    try:
        with pytest.raises(OSError, match="analysis creation failed"):
            runner.arm()
        assert ":OUTP1 ON" not in runner.instrument.transport.commands
        assert runner.output_state == "OFF"
    finally:
        runner.shutdown()


def test_analysis_write_failure_preserves_existing_abort_and_off_cleanup(tmp_path):
    runner = prepared_runner(tmp_path)

    def failing_write(_):
        raise OSError("analysis disk full")

    try:
        runner.arm()
        runner.writer.analysis_stream = SimpleNamespace(write=failing_write)
        result = runner.start()
        assert result["status"] == "aborted"
        assert "analysis disk full" in result["reason"]
        assert runner.output_state == "OFF"
        assert not runner.instrument.transport.output
    finally:
        runner.shutdown()
