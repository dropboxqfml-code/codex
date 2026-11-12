"""Simulation CLI feedback stays visible without changing JSON output or opening VISA."""

import io
import json
from dataclasses import replace

from keithley6517a import cli
from keithley6517a.config import RunConfig
from keithley6517a.measurement.runner import MeasurementRunner


def simulation_file(tmp_path, **changes):
    values = dict(
        voltages=(1, 2),
        protocol="list",
        simulation_resistance_ohm=1e9,
        dwell_s=0.3,
        summary_window_s=0.3,
        sample_interval_s=0.1,
        range_settle_s=0.01,
        nplc=1,
        current_trip_A=1e-8,
        residual_warning_ack=True,
        output_directory=str(tmp_path / "results"),
    )
    values.update(changes)
    config = replace(RunConfig(), **values)
    path = tmp_path / "simulation.json"
    path.write_text(json.dumps(config.to_dict()), encoding="utf-8")
    return path


def test_default_simulation_stdout_is_still_one_json_report(tmp_path, capsys):
    path = simulation_file(tmp_path)
    assert cli.main(["simulate", "--config", str(path), "--fast"]) == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["status"] == "completed"
    assert report["output_state"] == "OFF"
    assert captured.err == ""


def test_progress_precedes_connect_arm_and_start_and_keeps_json_stdout(
    tmp_path, capsys, monkeypatch
):
    path = simulation_file(tmp_path)
    stderr = io.StringIO()
    monkeypatch.setattr(cli.sys, "stderr", stderr)
    observed = []

    class ObservedRunner(MeasurementRunner):
        def connect(self):
            assert "[CONNECT]" in stderr.getvalue()
            observed.append("connect")
            return super().connect()

        def arm(self):
            assert "[ARM]" in stderr.getvalue()
            assert "[START]" not in stderr.getvalue()
            observed.append("arm")
            return super().arm()

        def start(self):
            assert "[START]" in stderr.getvalue()
            observed.append("start")
            return super().start()

    monkeypatch.setattr(cli, "MeasurementRunner", ObservedRunner)
    assert cli.main(["simulate", "--config", str(path), "--fast", "--progress"]) == 0
    assert observed == ["connect", "arm", "start"]
    output = capsys.readouterr().out
    report = json.loads(output)
    progress = stderr.getvalue()
    assert report["status"] == "completed"
    assert progress.index("[CONNECT]") < progress.index("[ARM]") < progress.index("[START]")
    assert progress.index("[START]") < progress.index("[READ]") < progress.index("[PASS]")
    assert "voltage 1/2" in progress and "voltage 2/2" in progress
    assert "I=" in progress and "R=" in progress and "OUTPUT OFF" in progress
    assert report["run_directory"] in progress


def test_progress_option_never_turns_real_configuration_into_simulation_or_visa(
    tmp_path, capsys, monkeypatch
):
    real = RunConfig(simulation=False, transport="visa", resource="GPIB0::27::INSTR")
    path = tmp_path / "real.json"
    path.write_text(json.dumps(real.to_dict()))

    def forbidden(*args, **kwargs):
        raise AssertionError("A rejected simulation must not construct or connect an instrument")

    monkeypatch.setattr(cli, "MeasurementRunner", forbidden)
    monkeypatch.setattr("keithley6517a.transport.visa.VisaTransport.__init__", forbidden)
    assert cli.main(["simulate", "--config", str(path), "--progress"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "never opens a real instrument" in json.loads(captured.err)["error"]
    assert "[PASS]" not in captured.err


def test_failed_acquisition_is_reported_as_fail_and_still_finishes_off(tmp_path, capsys):
    path = simulation_file(tmp_path, current_trip_A=1e-15)
    assert cli.main(["simulate", "--config", str(path), "--fast", "--progress"]) == 2
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["status"] == "aborted"
    assert report["output_state"] == "OFF"
    assert "[ABORT]" in captured.err and "[FAIL]" in captured.err
    assert "[PASS]" not in captured.err


def test_failed_arm_does_not_print_start_or_pass(tmp_path, capsys):
    path = simulation_file(tmp_path, current_trip_A=None)
    assert cli.main(["simulate", "--config", str(path), "--fast", "--progress"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[ARM]" in captured.err and "[FAIL]" in captured.err
    assert "[START]" not in captured.err and "[PASS]" not in captured.err


def test_many_samples_are_throttled_but_new_steps_and_elapsed_time_remain_visible(
    monkeypatch, capsys
):
    now = [0.0]
    monkeypatch.setattr(cli.time, "monotonic", lambda: now[0])
    progress = cli.SimulationProgress(RunConfig())
    row = dict(cycle_index=0, step_index=0, elapsed_s=0, current_raw_A=1e-9)
    for _ in range(10000):
        progress.sample(row)
    assert capsys.readouterr().err.count("[READ]") == 1
    now[0] = 0.6
    progress.sample(row)
    progress.sample(dict(row, step_index=1))
    assert capsys.readouterr().err.count("[READ]") == 2
    assert progress.sample_count == 10002
