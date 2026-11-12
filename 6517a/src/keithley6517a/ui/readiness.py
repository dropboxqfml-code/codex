"""Read-only explanations of configuration prerequisites, separate from session permissions."""

from __future__ import annotations

import re

from ..config import RunConfig

_FIELD_LABELS = {
    "current_trip_A": "Software current trip (A)",
    "residual_warning_ack": "잔류 전압 확인",
    "operator_setup_acknowledged": "사용자 관리 시험 확인",
    "resistive_limit_enabled": "Resistive-limit 정책",
    "resource": "GPIB 주소",
    "source_range_V": "V-Source 범위",
    "voltage_ceiling_V": "전압 상한",
    "voltages": "요청 전압",
    "sample_id": "시료 ID",
    "output_directory": "저장 폴더",
    "sample_limit_V": "시료 정격 전압",
    "fixture_limit_V": "Fixture 정격 전압",
    "cable_limit_V": "케이블 정격 전압",
    "dwell_s": "측정 시간",
    "summary_window_s": "요약 시간 창",
    "sample_interval_s": "판독 간격",
    "range_settle_s": "범위 변경 후 대기 시간",
    "exclude_initial_s": "초기 제외 시간",
    "current_range_A": "전류 범위",
    "nplc": "NPLC",
    "line_frequency_hz": "전원 주파수",
    "simulation_resistance_ohm": "SIM 저항 모델",
    "timeout_ms": "통신 제한 시간",
}

# The messages remain display-only. RunConfig.validate is the execution authority.
_KNOWN_ERRORS = {
    "Explicit software current trip is required to ARM": (
        "current_trip_A",
        "Software current trip (A)을 입력하세요.",
    ),
    "Residual-charge warning acknowledgment is required": (
        "residual_warning_ack",
        "잔류 전압 확인을 체크하세요.",
    ),
    "Operator setup acknowledgment is required to ARM": (
        "operator_setup_acknowledged",
        "사용자 관리 시험 확인을 체크하세요.",
    ),
    "Real ARM requires an explicit resistive-limit policy": (
        "resistive_limit_enabled",
        "Resistive-limit ON/OFF를 선택하세요.",
    ),
    "A selected VISA GPIB resource is required": ("resource", "GPIB 주소를 선택하세요."),
    "All physical voltage ratings are required": (
        "physical_voltage_ratings",
        "시료·fixture·케이블 정격 전압을 입력하세요.",
    ),
    "Experiment/rating approval record is required": (
        "rating_approval",
        "정격·실험 승인 기록을 입력하세요.",
    ),
    "Installed interlock and OFF-state 0/1 transition commissioning required": (
        "commissioning",
        "설치 확인과 인터록 열림·닫힘 검증 기록을 확인하세요.",
    ),
    "Independent hardware protection review is required": (
        "commissioning.hardware_protection_reviewed",
        "독립 보호 검토 확인을 체크하세요.",
    ),
    "Commissioning fixture identity and approver required": (
        "commissioning_identity",
        "Fixture ID와 승인 담당자를 입력하세요.",
    ),
    "Operator low-voltage mode requires the 100 V source range": (
        "source_range_V",
        "사용자 관리 모드의 V-Source 범위를 100 V로 선택하세요.",
    ),
    "Operator low-voltage mode has an absolute 10 V ceiling": (
        "voltage_ceiling_V",
        "사용자 관리 모드의 전압 상한은 10 V 이하로 입력하세요.",
    ),
    "Requested/quantized voltage exceeds approved ceiling/range": (
        "voltages",
        "요청 전압을 전압 상한과 V-Source 범위 안으로 입력하세요.",
    ),
    "source range must be 100/1000 V; NPLC must be 0.01..10": (
        "source_range_V",
        "V-Source 범위는 100/1000 V, NPLC는 0.01~10으로 입력하세요.",
    ),
    "summary_window_s cannot exceed dwell_s": (
        "summary_window_s",
        "요약 시간 창을 측정 시간 이하로 입력하세요.",
    ),
    "Dwell cannot be shorter than minimum/excluded interval": (
        "dwell_s",
        "측정 시간을 최소 대기·초기 제외 시간 이상으로 입력하세요.",
    ),
    "Real native resistance disabled: measured-current trip unverified": (
        "mode",
        "실장비 측정 모드를 FVMI_CURRENT로 선택하세요.",
    ),
    "line_frequency_hz must be explicitly 50 or 60 Hz": (
        "line_frequency_hz",
        "전원 주파수를 50 Hz 또는 60 Hz로 선택하세요.",
    ),
    "sample_id and output_directory are required": (
        "sample_id",
        "시료 ID와 저장 폴더를 입력하세요.",
    ),
    "constant protocol requires exactly one voltage": (
        "voltages",
        "정전압 시험에는 전압을 한 개만 입력하세요.",
    ),
    "Negative voltage requires bipolar authorization": (
        "voltages",
        "음전압은 양극성 설정을 확인한 뒤 입력하세요.",
    ),
    "Voltages must be finite numbers": ("voltages", "요청 전압에 유한한 숫자를 입력하세요."),
    "Provide 1..100000 voltages": ("voltages", "요청 전압을 한 개 이상 입력하세요."),
    "Plan exceeds maximum total duration": (
        "dwell_s",
        "전압 개수·반복 횟수·측정 시간을 줄이거나 전체 시간 상한을 확인하세요.",
    ),
}


def humanize_issue(error: str | Exception) -> str:
    """Translate execution validation errors without changing their meaning or state."""
    text = str(error).strip()
    known = _KNOWN_ERRORS.get(text)
    if known:
        return known[1]
    match = re.fullmatch(
        r"([A-Za-z_]+) (must be positive|must be nonnegative|must be finite numeric SI units|"
        r"must be a boolean|must be an integer|is required)",
        text,
    )
    if match:
        field, condition = match.groups()
        label = _FIELD_LABELS.get(field, field)
        return {
            "must be positive": f"{label}에 0보다 큰 값을 입력하세요.",
            "must be nonnegative": f"{label}에 0 이상의 값을 입력하세요.",
            "must be finite numeric SI units": f"{label}에 유한한 숫자를 입력하세요.",
            "must be a boolean": f"{label}의 확인 상태를 선택하세요.",
            "must be an integer": f"{label}에 정수를 입력하세요.",
            "is required": f"{label}을 입력하세요.",
        }[condition]
    if text.startswith("could not convert string to float"):
        return "숫자 입력란을 확인하세요. 예: 전압 1, current trip 1e-8."
    return text or "설정값을 확인하세요."


def configuration_issues(config: RunConfig) -> list[dict[str, str]]:
    """List every missing ARM input. A complete configuration is not a START permission."""
    issues: list[dict[str, str]] = []

    def missing(field: str, message: str, *, code: str | None = None):
        issues.append(
            {
                "code": code or "MISSING_" + field.upper().replace(".", "_"),
                "field": field,
                "message": message,
            }
        )

    if config.current_trip_A is None:
        missing(
            "current_trip_A", humanize_issue("Explicit software current trip is required to ARM")
        )
    if not config.residual_warning_ack:
        missing(
            "residual_warning_ack",
            humanize_issue("Residual-charge warning acknowledgment is required"),
        )
    if not config.simulation:
        if config.resistive_limit_enabled is None:
            missing(
                "resistive_limit_enabled",
                humanize_issue("Real ARM requires an explicit resistive-limit policy"),
            )
        if not config.resource or not config.resource.upper().startswith("GPIB"):
            missing("resource", humanize_issue("A selected VISA GPIB resource is required"))
        if config.setup_policy == "operator_low_voltage":
            if not config.operator_setup_acknowledged:
                missing(
                    "operator_setup_acknowledged",
                    humanize_issue("Operator setup acknowledgment is required to ARM"),
                )
        else:
            for field in ("sample_limit_V", "fixture_limit_V", "cable_limit_V"):
                if getattr(config, field) is None:
                    missing(field, f"{_FIELD_LABELS[field]}을 입력하세요.")
            if not config.rating_approval.strip():
                missing(
                    "rating_approval",
                    humanize_issue("Experiment/rating approval record is required"),
                )
            for field, message in (
                ("installation_confirmed", "Fixture 설치 확인을 체크하세요."),
                ("lid_open_zero", "인터록 열림 검증 기록을 확인하세요."),
                ("lid_closed_one", "인터록 닫힘 검증 기록을 확인하세요."),
                ("hardware_protection_reviewed", "독립 보호 검토 확인을 체크하세요."),
            ):
                if config.commissioning.get(field) is not True:
                    missing("commissioning." + field, message)
            for field, label in (("fixture_id", "Fixture ID"), ("approved_by", "승인 담당자")):
                value = config.commissioning.get(field)
                if not isinstance(value, str) or not value.strip():
                    missing("commissioning." + field, f"{label}를 입력하세요.")
        if config.mode == "NATIVE_RESISTANCE":
            missing(
                "mode",
                humanize_issue("Real native resistance disabled: measured-current trip unverified"),
                code="UNSUPPORTED_REAL_MODE",
            )

    try:
        config.validate(for_arm=True)
    except (ValueError, TypeError) as exc:
        text = str(exc).strip()
        numeric_field = re.match(r"([A-Za-z_]+) (?:must be |is required)", text)
        field = _KNOWN_ERRORS.get(
            text,
            (numeric_field[1] if numeric_field else "configuration", ""),
        )[0]
        covered_fields = {issue["field"] for issue in issues}
        aggregates = {
            "physical_voltage_ratings": {"sample_limit_V", "fixture_limit_V", "cable_limit_V"},
            "commissioning": {
                "commissioning.installation_confirmed",
                "commissioning.lid_open_zero",
                "commissioning.lid_closed_one",
            },
            "commissioning_identity": {"commissioning.fixture_id", "commissioning.approved_by"},
        }
        if field not in covered_fields and not (aggregates.get(field, set()) & covered_fields):
            missing(field, humanize_issue(exc), code="INVALID_CONFIGURATION")
    return issues
