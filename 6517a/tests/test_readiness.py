"""Readiness explanations collect input gaps but cannot confer session permissions."""

from dataclasses import replace

import pytest

from keithley6517a.config import ConfigurationError, RunConfig
from keithley6517a.ui.readiness import configuration_issues, humanize_issue


def operator_config(**changes):
    values = dict(
        simulation=False,
        transport="visa",
        setup_policy="operator_low_voltage",
        resource="GPIB0::27::INSTR",
        current_trip_A=1e-8,
        residual_warning_ack=True,
        resistive_limit_enabled=False,
        operator_setup_acknowledged=True,
    )
    return RunConfig.from_dict(dict(values, **changes))


def test_operator_draft_reports_every_missing_input_at_once_without_changing_it():
    config = RunConfig(simulation=False, transport="visa", setup_policy="operator_low_voltage")
    before = config.to_dict()
    issues = configuration_issues(config)
    assert {item["field"] for item in issues} == {
        "current_trip_A",
        "residual_warning_ack",
        "operator_setup_acknowledged",
        "resistive_limit_enabled",
        "resource",
    }
    assert len(issues) == 5
    assert all(set(item) == {"code", "field", "message"} for item in issues)
    assert len({item["code"] for item in issues}) == len(issues)
    assert all(item["message"].endswith("세요.") for item in issues)
    assert config.to_dict() == before
    with pytest.raises(ConfigurationError):
        config.validate(for_arm=True)


def test_operator_preset_still_explains_the_three_remaining_choices():
    config = operator_config(
        operator_setup_acknowledged=False,
        residual_warning_ack=False,
        resistive_limit_enabled=None,
    )
    issues = configuration_issues(config)
    assert {item["field"] for item in issues} == {
        "operator_setup_acknowledged",
        "residual_warning_ack",
        "resistive_limit_enabled",
    }
    assert len(issues) == 3
    assert any("ON/OFF" in item["message"] for item in issues)


def test_strict_mode_reports_each_missing_record_instead_of_the_first_error_only():
    config = operator_config(setup_policy="verified_fixture")
    issues = configuration_issues(config)
    assert {item["field"] for item in issues} == {
        "sample_limit_V",
        "fixture_limit_V",
        "cable_limit_V",
        "rating_approval",
        "commissioning.installation_confirmed",
        "commissioning.lid_open_zero",
        "commissioning.lid_closed_one",
        "commissioning.hardware_protection_reviewed",
        "commissioning.fixture_id",
        "commissioning.approved_by",
    }
    assert len(issues) == 10
    assert config.commissioning == {}


def test_simulation_does_not_request_physical_connection_inputs():
    config = RunConfig()
    assert {item["field"] for item in configuration_issues(config)} == {
        "current_trip_A",
        "residual_warning_ack",
    }
    complete = replace(config, current_trip_A=1e-8, residual_warning_ack=True)
    assert configuration_issues(complete) == []
    complete.validate(for_arm=True)


@pytest.mark.parametrize("setup_policy", ["operator_low_voltage", "verified_fixture"])
def test_complete_configuration_agrees_with_core_validation(setup_policy):
    config = operator_config(setup_policy=setup_policy)
    if setup_policy == "verified_fixture":
        config = replace(
            config,
            sample_limit_V=10,
            fixture_limit_V=10,
            cable_limit_V=10,
            rating_approval="software test only",
            commissioning={
                "installation_confirmed": True,
                "lid_open_zero": True,
                "lid_closed_one": True,
                "hardware_protection_reviewed": True,
                "fixture_id": "FAKE-FIXTURE",
                "approved_by": "test",
            },
        )
    assert configuration_issues(config) == []
    config.validate(for_arm=True)
    # This helper neither connects nor fabricates the live fixture observation.
    assert "ready" not in config.commissioning


def test_real_native_mode_is_reported_even_when_other_inputs_are_missing():
    config = operator_config(
        mode="NATIVE_RESISTANCE", current_trip_A=None, operator_setup_acknowledged=False
    )
    issues = configuration_issues(config)
    assert {item["field"] for item in issues} == {
        "mode",
        "current_trip_A",
        "operator_setup_acknowledged",
    }
    assert next(item for item in issues if item["field"] == "mode")["code"] == (
        "UNSUPPORTED_REAL_MODE"
    )


def test_uncovered_future_core_validation_cannot_silently_report_ready(monkeypatch):
    config = operator_config()

    def reject(self, for_arm=True):
        raise ConfigurationError("New core validation failure")

    monkeypatch.setattr(RunConfig, "validate", reject)
    issues = configuration_issues(config)
    assert len(issues) == 1
    assert issues[0]["code"] == "INVALID_CONFIGURATION"
    assert issues[0]["message"] == "New core validation failure"


def test_invalid_numeric_value_is_still_rejected_and_identifies_its_field():
    config = operator_config()
    # A viewer must remain conservative even if an externally constructed object is invalid.
    object.__setattr__(config, "current_trip_A", float("nan"))
    issues = configuration_issues(config)
    assert len(issues) == 1
    assert issues[0]["field"] == "current_trip_A"
    assert "유한한 숫자" in issues[0]["message"]


@pytest.mark.parametrize(
    "error, expected",
    [
        ("current_trip_A must be positive", "0보다 큰 값"),
        ("nplc must be finite numeric SI units", "유한한 숫자"),
        ("Operator setup acknowledgment is required to ARM", "사용자 관리 시험 확인"),
        ("Residual-charge warning acknowledgment is required", "잔류 전압 확인"),
        ("Real ARM requires an explicit resistive-limit policy", "ON/OFF"),
        ("Operator low-voltage mode requires the 100 V source range", "100 V"),
        ("Operator low-voltage mode has an absolute 10 V ceiling", "10 V 이하"),
        ("Requested/quantized voltage exceeds approved ceiling/range", "전압 상한"),
        ("source range must be 100/1000 V; NPLC must be 0.01..10", "0.01~10"),
        ("summary_window_s cannot exceed dwell_s", "측정 시간 이하"),
        ("could not convert string to float: 'bad'", "숫자 입력란"),
        ("", "설정값을 확인"),
        (ConfigurationError("시료 이름을 확인하세요."), "시료 이름을 확인"),
    ],
)
def test_numeric_and_common_errors_are_actionable_in_korean(error, expected):
    assert expected in humanize_issue(error)
