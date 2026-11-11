"""6517A manual Rev. D, printed 3-75..3-78, Figure 3-19 ASCII parser.

The configured element set is READing, STATus, UNITs, RNUMber, VSOurce.
The manual fixes their returned order independent of the command argument order.
Status and unit attach to the reading. RNUM uses ``rdg#`` (not ``RDNG#``).
Fixtures follow the manufacturer's format; no real-device transcript is claimed.
"""

import math
import re
from dataclasses import dataclass
from decimal import Decimal


class ProtocolError(RuntimeError):
    pass


NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?"
READING = re.compile(rf"(?P<value>{NUMBER})(?P<status>[NZOURL])(?P<unit>ADC|OHM)")
RNUM = re.compile(r"([+-]?\d+)rdg#", re.IGNORECASE)
VSOURCE = re.compile(rf"({NUMBER})Vsrc", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedReading:
    value: float | None
    unit: str
    status: str
    reading_number: int
    voltage_reported: float
    raw: str
    flags: tuple[str, ...] = ()
    timestamp: float | None = None


def parse_reading(response: str, mode: str) -> ParsedReading:
    if mode not in {"FVMI_CURRENT", "NATIVE_RESISTANCE"}:
        raise ProtocolError(f"Unknown acquisition mode: {mode!r}")
    if not isinstance(response, str):
        raise ProtocolError("ASCII response must be text")
    fields = response.strip().split(",")
    if len(fields) != 3:
        raise ProtocolError("Expected reading+status+unit, reading number, source field")
    reading, number, source = (p.strip() for p in fields)
    match = READING.fullmatch(reading)
    count = RNUM.fullmatch(number)
    voltage = VSOURCE.fullmatch(source)
    if not match or not count or not voltage:
        raise ProtocolError(f"Malformed ASCII response: {response!r}")
    expected = "OHM" if mode == "NATIVE_RESISTANCE" else "ADC"
    if match["unit"] != expected:
        raise ProtocolError(f"Mode requires {expected}, received {match['unit']}")
    value, volts = float(match["value"]), float(voltage[1])
    if not math.isfinite(value) or not math.isfinite(volts):
        raise ProtocolError("Non-finite numeric response")
    if (value == 0 and not Decimal(match["value"]).is_zero()) or (
        volts == 0 and not Decimal(voltage[1]).is_zero()
    ):
        raise ProtocolError("Numeric token underflows the software float format")
    status = match["status"]
    flags = []
    status_flags = {
        "Z": "ZERO_CHECK",
        "O": "OVERFLOW",
        "U": "UNDERFLOW",
        "R": "REFERENCE",
        "L": "OUT_OF_LIMIT",
    }
    if status in status_flags:
        flags.append(status_flags[status])
    expected_sentinel = {"O": 9.9e37, "L": 9.9e37, "Z": 9.91e37, "U": 0.0}
    if status in expected_sentinel and value != expected_sentinel[status]:
        flags.append("STATUS_VALUE_MISMATCH")
    if abs(value) >= 9.9e37:
        flags.append(
            "ZERO_CHECK_SENTINEL" if math.isclose(abs(value), 9.91e37, rel_tol=1e-6) else "SENTINEL"
        )
    if flags:
        value = None
    try:
        reading_number = int(count[1])
    except ValueError as exc:
        raise ProtocolError("Invalid reading number") from exc
    return ParsedReading(
        value, match["unit"], status, reading_number, volts, response, tuple(flags)
    )
