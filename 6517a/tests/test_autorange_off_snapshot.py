"""The explicit OFF probe collects settings without configuring or energizing a device."""

import json
from pathlib import Path

import pytest

from keithley6517a.clock import FakeClock
from keithley6517a.diagnostics import run_diagnostics
from keithley6517a.transport.simulator import SimulatorTransport

QUERIES = (
    ":STAT:QUES:COND?",
    ":SENS:CURR:RANG:AUTO?",
    ":SENS:CURR:RANG?",
    ":SENS:CURR:RANG:AUTO:LLIM?",
    ":SENS:CURR:RANG:AUTO:ULIM?",
)


class SnapshotBus(SimulatorTransport):
    def __init__(self, *, responses=None, faults=None):
        super().__init__(clock=FakeClock(), faults=faults)
        self.responses = dict(responses or {})
        self.output = True

    def query(self, command):
        if command in QUERIES:
            # All new reads must follow model identification and protective OFF.
            assert self.commands[0] == "*IDN?"
            assert ":OUTP1 OFF" in self.commands
            assert self.output is False
        if command in self.responses:
            self._owned()
            self.commands.append(command)
            response = self.responses[command]
            if isinstance(response, Exception):
                raise response
            return response
        return super().query(command)


class Factory:
    def __init__(self, *, responses=None, faults=None):
        self.bus = SnapshotBus(responses=responses, faults=faults)

    def __call__(self, _resource, **_kwargs):
        return self.bus

    @staticmethod
    def list_resources(_backend):
        return ("GPIB0::27::INSTR",)


def run(tmp_path, factory, **options):
    return run_diagnostics(
        **dict(
            dict(
                resource="GPIB0::27::INSTR",
                output_directory=tmp_path,
                transport_factory=factory,
                confirm_off=True,
            ),
            **options,
        )
    )


def strict_json(path):
    return json.loads(
        Path(path).read_text(encoding="utf-8"),
        parse_constant=lambda token: pytest.fail(f"Nonstandard JSON: {token}"),
    )


def test_off_snapshot_preserves_raw_parsed_ranges_and_read_only_transcript(tmp_path):
    responses = {
        ":STAT:QUES:COND?": " +0256 \r\n",
        ":SENS:CURR:RANG:AUTO?": "ON\n",
        ":SENS:CURR:RANG?": "+2.000000E-10\n",
        ":SENS:CURR:RANG:AUTO:LLIM?": "2E-11\n",
        ":SENS:CURR:RANG:AUTO:ULIM?": "2E-3\n",
    }
    factory = Factory(responses=responses)
    report = run(tmp_path, factory)
    assert report["ok"] is True and report["report_saved"] is True
    assert report["output_OFF_confirmed"] is True and report["output_state"] == "OFF"
    assert report["residual_voltage_state"] == "UNVERIFIED"
    snapshot = report["autorange_snapshot"]
    assert snapshot["status"] == "complete"
    assert snapshot["questionable_condition"] == 256
    assert snapshot["calibration_invalid"] is True
    assert snapshot["current_autorange"] is True
    assert snapshot["current_range_A"] == 2e-10
    assert snapshot["current_autorange_min_A"] == 2e-11
    assert snapshot["current_autorange_max_A"] == 2e-3
    assert snapshot["measurement_readiness_verified"] is False
    assert "not calibration" in snapshot["scope"]
    assert snapshot["output_OFF_confirmed"] is True
    assert all(snapshot["queries"][query]["raw"] == raw for query, raw in responses.items())
    assert all(snapshot["queries"][query]["ok"] for query in QUERIES)
    assert strict_json(report["report_path"]) == report
    raw = [
        json.loads(line)
        for line in Path(report["raw_io_path"]).read_text(encoding="utf-8").splitlines()
    ]
    for query in QUERIES:
        assert [
            item["response"]
            for item in raw
            if item["direction"] == "rx" and item["command"] == query
        ] == [responses[query]]
    writes = [command for command in factory.bus.commands if not command.endswith("?")]
    assert set(writes) <= {":OUTP1 OFF", ":TSEQ:ABOR", ":INIT:CONT OFF", ":ABOR"}
    assert ":OUTP1 ON" not in factory.bus.commands
    assert ":READ?" not in factory.bus.commands
    assert not factory.bus.opened and not factory.bus.output


@pytest.mark.parametrize(
    ("condition", "invalid"), [(0, False), (128, False), (256, True), (257, True), (65535, True)]
)
def test_calibration_invalid_is_bit_256_not_register_truthiness(tmp_path, condition, invalid):
    report = run(tmp_path, Factory(responses={QUERIES[0]: str(condition)}))
    assert report["ok"] is True
    assert report["autorange_snapshot"]["calibration_invalid"] is invalid
    assert report["autorange_snapshot"]["questionable_condition"] == condition


@pytest.mark.parametrize(
    ("query", "response", "field"),
    [
        (QUERIES[0], "-1", "questionable_condition"),
        (QUERIES[0], "256.0", "questionable_condition"),
        (QUERIES[0], "65536", "questionable_condition"),
        (QUERIES[0], "unknown", "questionable_condition"),
        (QUERIES[1], "AUTO", "current_autorange"),
        (QUERIES[1], "2", "current_autorange"),
        (QUERIES[2], "nan", "current_range_A"),
        (QUERIES[2], "-2e-10", "current_range_A"),
        (QUERIES[3], "inf", "current_autorange_min_A"),
        (QUERIES[4], "0", "current_autorange_max_A"),
        (QUERIES[4], "not-supported", "current_autorange_max_A"),
    ],
)
def test_bad_query_reply_remains_unknown_with_issue_and_preserved_off(
    tmp_path, query, response, field
):
    factory = Factory(responses={query: response})
    report = run(tmp_path, factory)
    assert report["ok"] is False and report["report_saved"] is True
    assert report["output_OFF_confirmed"] is True and report["output_state"] == "OFF"
    assert report["stage"] == "autorange_off_snapshot"
    snapshot = report["autorange_snapshot"]
    assert snapshot["status"] == "partial"
    assert snapshot[field] is None
    reading = snapshot["queries"][query]
    assert reading["raw"] == response and reading["value"] is None and reading["ok"] is False
    if field == "questionable_condition":
        assert snapshot["calibration_invalid"] is None
    assert any(
        issue.get("command") == query and issue["stage"] == "autorange_off_snapshot"
        for issue in report["issues"]
    )
    assert all(command in factory.bus.commands for command in QUERIES)
    assert strict_json(report["report_path"]) == report
    assert not factory.bus.output and not factory.bus.opened


def test_query_timeout_keeps_off_confirmation_and_other_snapshot_values(tmp_path):
    factory = Factory(responses={QUERIES[3]: TimeoutError("query timeout")})
    report = run(tmp_path, factory)
    assert report["ok"] is False
    assert report["output_OFF_confirmed"] is True and report["output_state"] == "OFF"
    snapshot = report["autorange_snapshot"]
    assert snapshot["current_autorange_min_A"] is None
    assert snapshot["current_autorange_max_A"] == 2e-2
    assert snapshot["queries"][QUERIES[3]]["raw"] is None
    assert snapshot["queries"][QUERIES[3]]["value"] is None
    assert any(
        issue["code"] == "IO_TIMEOUT" and issue.get("command") == QUERIES[3]
        for issue in report["issues"]
    )
    raw = [
        json.loads(line)
        for line in Path(report["raw_io_path"]).read_text(encoding="utf-8").splitlines()
    ]
    assert any(item["direction"] == "tx" and item["command"] == QUERIES[3] for item in raw)
    assert not any(item["direction"] == "rx" and item["command"] == QUERIES[3] for item in raw)
    assert not factory.bus.opened and not factory.bus.output


@pytest.mark.parametrize("mode", ["discovery", "identity"])
def test_discovery_and_identity_only_do_not_query_snapshot(tmp_path, mode):
    factory = Factory()
    report = run(
        tmp_path,
        factory,
        resource=None if mode == "discovery" else "GPIB0::27::INSTR",
        confirm_off=False,
    )
    assert report["ok"] is True and report["autorange_snapshot"] is None
    assert not set(factory.bus.commands) & set(QUERIES)
    assert factory.bus.commands == ([] if mode == "discovery" else ["*IDN?"])
    assert factory.bus.output is True


@pytest.mark.parametrize("failure", ["wrong_model", "off_unknown"])
def test_snapshot_requires_supported_identity_and_confirmed_off(tmp_path, failure):
    faults = (
        {"idn": "KEITHLEY,MODEL 6517B,TEST,1.0"} if failure == "wrong_model" else {"fail_off": True}
    )
    factory = Factory(faults=faults)
    report = run(tmp_path, factory)
    assert report["ok"] is False and report["autorange_snapshot"] is None
    assert not set(factory.bus.commands) & set(QUERIES)
    assert report["output_OFF_confirmed"] is False
    assert factory.bus.output is True and not factory.bus.opened
