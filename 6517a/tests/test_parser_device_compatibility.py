"""User-reported RNUM spelling compatibility; no live hardware test is claimed."""

import math

import pytest

from keithley6517a.driver.parser import ProtocolError, parse_reading


def test_user_screenshot_response_is_preserved_and_parsed_without_numeric_rescaling():
    # Transcribed from the user's error screenshot, rather than a captured I/O file.
    raw = "+064.8960E-12NADC,+01122rdng#,+0001.000Vsrc"
    reading = parse_reading(raw, "FVMI_CURRENT")
    assert reading.value == 6.4896e-11
    assert reading.reading_number == 1122
    assert reading.voltage_reported == 1.0
    assert reading.unit == "ADC" and reading.status == "N" and reading.flags == ()
    assert reading.raw == raw


@pytest.mark.parametrize("suffix", ["rdg#", "RDG#", "rDg#", "rdng#", "RDNG#", "rDnG#"])
@pytest.mark.parametrize(("mode", "unit"), [("FVMI_CURRENT", "ADC"), ("NATIVE_RESISTANCE", "OHM")])
def test_only_the_counter_spelling_changes_between_supported_device_responses(mode, unit, suffix):
    raw = f"-1.23456789012345E-11N{unit},+00123{suffix},-2.5Vsrc\r\n"
    reading = parse_reading(raw, mode)
    assert reading.value == -1.23456789012345e-11
    assert reading.reading_number == 123
    assert reading.voltage_reported == -2.5
    assert reading.raw == raw and reading.flags == ()


@pytest.mark.parametrize("count", ["+00000", "00000", "-00001", "+112233"])
def test_rdng_counter_retains_signed_integer_values(count):
    reading = parse_reading(f"+0NADC,{count}rdng#,+0Vsrc", "FVMI_CURRENT")
    assert reading.reading_number == int(count)
    assert reading.value == 0 and reading.voltage_reported == 0


@pytest.mark.parametrize("suffix", ["rdg#", "rdng#"])
def test_negative_zero_current_and_voltage_are_not_changed_by_counter_alias(suffix):
    reading = parse_reading(f"-0NADC,+00001{suffix},-0Vsrc", "FVMI_CURRENT")
    assert reading.value == 0 and math.copysign(1, reading.value) == -1
    assert reading.voltage_reported == 0 and math.copysign(1, reading.voltage_reported) == -1


@pytest.mark.parametrize("suffix", ["rdg#", "rdng#"])
@pytest.mark.parametrize(
    ("token", "flag"),
    [
        ("+9.91E37ZADC", "ZERO_CHECK_SENTINEL"),
        ("+9.9E37OADC", "OVERFLOW"),
        ("0UADC", "UNDERFLOW"),
        ("+1E-11RADC", "REFERENCE"),
        ("+9.9E37LADC", "OUT_OF_LIMIT"),
        ("+1E-11OADC", "STATUS_VALUE_MISMATCH"),
        ("+9.9E37NADC", "SENTINEL"),
    ],
)
def test_counter_alias_does_not_make_invalid_status_or_sentinel_a_valid_reading(
    suffix, token, flag
):
    raw = f"{token},+00001{suffix},+1Vsrc"
    reading = parse_reading(raw, "FVMI_CURRENT")
    assert reading.value is None and flag in reading.flags
    assert reading.reading_number == 1 and reading.raw == raw


@pytest.mark.parametrize(
    "count",
    [
        "+00001reading#",
        "+00001readng#",
        "+00001rng#",
        "+00001rdn#",
        "+00001rddng#",
        "+00001rdng",
        "+00001rdng##",
        "+00001rdg##",
        "+00001rdng#extra",
        "+00001rd ng#",
        "+1.5rdng#",
        "rdng#",
    ],
)
def test_unrecognized_or_malformed_counter_fields_remain_rejected(count):
    with pytest.raises(ProtocolError, match="Malformed ASCII"):
        parse_reading(f"+1E-11NADC,{count},+1Vsrc", "FVMI_CURRENT")


@pytest.mark.parametrize(
    "raw",
    [
        "+1E-11NADC,+00001rdng#",  # source field missing
        "+1E-11NADC,+00001rdng#,+1Vsrc,extra",  # an unconfigured field
        "+1E-11,N,ADC,+00001rdng#,+1Vsrc",  # separated status/unit
        "+1E-11QADC,+00001rdng#,+1Vsrc",  # unsupported status
        "+1E-11NADC,+00001rdng#,+1VSO",  # wrong source unit
        "+1E-11NADC,+00001rdng#,+1Vsrcjunk",
        "+1E-11Nadc,+00001rdng#,+1Vsrc",  # no relaxation of reading unit case
        "+1E-11NOHM,+00001rdng#,+1Vsrc",  # wrong acquisition unit
        "+1E-999NADC,+00001rdng#,+1Vsrc",  # software float underflow
        "+1E999NADC,+00001rdng#,+1Vsrc",  # nonfinite conversion
        "+1E-11NADC,+00001rdng#,+1E999Vsrc",
    ],
)
def test_rdng_compatibility_keeps_existing_framing_units_and_numeric_validation(raw):
    with pytest.raises(ProtocolError):
        parse_reading(raw, "FVMI_CURRENT")
