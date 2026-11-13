"""Durable samples and separate command, output, and residual-charge state."""

import csv
import json
import math
import os
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from .. import __version__

READING_FIELDS = """run_id sample_id mode step_index cycle_index phase wall_time_iso8601
elapsed_s time_since_voltage_command_s read_start_monotonic_s read_end_monotonic_s
actual_sample_interval_s voltage_requested_V voltage_programmed_readback_V
voltage_reported_by_instrument_V voltage_dut_estimated_V voltage_basis current_raw_A
current_background_A current_corrected_A current_inferred_A resistance_apparent_ohm
resistance_corrected_ohm native_r_ohm resistance_lower_bound_ohm resistivity_ohm_m
current_range_A source_range_V nplc source_output_state source_current_limit_state
interlock_query zero_check_state zero_correct_state status_code reading_number
temperature_C relative_humidity_percent valid_for_summary quality_flags raw_response
status_query_start_monotonic_s status_query_end_monotonic_s""".split()

ANALYSIS_HEADER = "Time (s)\tResistance (Ohm)\tVoltage (V)\tCurrent (A)\n"
ANALYSIS_RESISTIVITY_HEADER = (
    "Time (s)\tResistance (Ohm)\tResistivity (Ohm m)\tVoltage (V)\tCurrent (A)\n"
)


def analysis_header(include_resistivity=False):
    """The fixed SI-unit schema chosen for an entire run or export."""
    return ANALYSIS_RESISTIVITY_HEADER if include_resistivity else ANALYSIS_HEADER


def _analysis_number(value):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise ValueError("Analysis data must be finite numeric SI units or null")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Analysis data must be finite numeric SI units or null") from exc
    if not math.isfinite(number):
        raise ValueError("Non-finite sample must be classified and stored as null")
    return number


def _geometry_number(value):
    """Sidecar geometry is typed JSON data, rather than user-editable CSV text."""
    if value is None:
        return None
    if type(value) not in (int, float):
        raise ValueError("Recorded sample geometry must contain finite positive numbers")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError("Recorded sample geometry must contain finite positive numbers") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError("Recorded sample geometry must contain finite positive numbers")
    return number


def _complete_geometry(area, length):
    if area is None or length is None:
        return False
    if not math.isfinite(area) or not math.isfinite(length) or area <= 0 or length <= 0:
        raise ValueError("Recorded sample geometry cannot represent finite resistivity")
    ratio = area / length
    if not math.isfinite(ratio) or ratio <= 0:
        raise ValueError("Recorded sample geometry cannot represent finite resistivity")
    return True


def _settings_geometry(settings):
    """Return None for absent geometry, otherwise its effective completeness."""
    dimensions = {
        axis: _geometry_number(settings.get(name))
        for axis, name in (
            ("L", "sample_length_mm"),
            ("W", "sample_width_mm"),
            ("D", "sample_depth_mm"),
        )
    }
    axis = settings.get("current_path_axis")
    if axis is not None and axis not in ("L", "W", "D"):
        raise ValueError("Recorded current path axis must be L, W, D, or null")
    if axis is not None or any(value is not None for value in dimensions.values()):
        if axis is None or any(value is None for value in dimensions.values()):
            return False
        transverse = [value * 1e-3 for key, value in dimensions.items() if key != axis]
        return _complete_geometry(transverse[0] * transverse[1], dimensions[axis] * 1e-3)
    area = _geometry_number(settings.get("area_m2"))
    length = _geometry_number(settings.get("thickness_m"))
    if area is None and length is None:
        return None
    return _complete_geometry(area, length)


def analysis_includes_resistivity(rows, metadata=None, settings=None):
    """Choose one schema using stored values or recorded geometry, without I/O.

    Every supplied rho value is checked even when metadata already specifies a
    schema. Empty cells mean unknown; a finite zero is still a measured value.
    New run metadata is authoritative if every stored rho is unknown. Older
    runs can recover the same decision from their geometry snapshot.
    """
    found = False
    for row in rows:
        if _analysis_number(row.get("resistivity_ohm_m")) is not None:
            found = True
    metadata = {} if metadata is None else metadata
    if not isinstance(metadata, Mapping):
        raise ValueError("Run metadata must be a JSON object")
    schema = metadata.get("analysis_text")
    if schema is not None:
        if not isinstance(schema, Mapping):
            raise ValueError("Run analysis_text metadata must be a JSON object")
        if "include_resistivity" in schema and type(schema["include_resistivity"]) is not bool:
            raise ValueError("Run analysis_text.include_resistivity must be a boolean")
    if found:
        return True
    if schema is not None and "include_resistivity" in schema:
        return schema["include_resistivity"]

    if settings is not None and not isinstance(settings, Mapping):
        raise ValueError("Run settings must be a JSON object")
    if settings is None or not settings:
        settings = metadata.get("settings", {})
    if not isinstance(settings, Mapping):
        raise ValueError("Run settings must be a JSON object")
    if "settings" in settings:
        settings = settings["settings"]
        if not isinstance(settings, Mapping):
            raise ValueError("Run settings must be a JSON object")
    effective = _settings_geometry(settings)
    if effective is not None:
        return effective
    geometry = metadata.get("sample_geometry", {})
    if not isinstance(geometry, Mapping):
        raise ValueError("Run sample_geometry metadata must be a JSON object")
    complete = geometry.get("complete")
    if complete is not None and type(complete) is not bool:
        raise ValueError("Recorded sample geometry completeness must be a boolean")
    area = _geometry_number(geometry.get("area_m2"))
    length = _geometry_number(geometry.get("current_path_length_m"))
    return complete is not False and _complete_geometry(area, length)


def analysis_line(row, include_resistivity=False):
    """One SI-unit data row; missing values remain numeric NaN, never inferred values."""
    resistance = row.get("native_r_ohm")
    if resistance is None or (isinstance(resistance, str) and not resistance.strip()):
        resistance = row.get("resistance_apparent_ohm")
    values = [row.get("elapsed_s"), resistance]
    if include_resistivity:
        values.append(row.get("resistivity_ohm_m"))
    values.extend((row.get("voltage_programmed_readback_V"), row.get("current_raw_A")))
    fields = []
    for value in values:
        number = _analysis_number(value)
        if number is None:
            fields.append("nan")
            continue
        fields.append(repr(number))
    return "\t".join(fields) + "\n"


def strict_json(value):
    """Never encode nonstandard NaN/Infinity; callers must classify invalid numeric data."""
    return json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)


def atomic_json(path: Path, value):
    payload = strict_json(value)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(payload + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def recover_incomplete_runs(root):
    """Mark abandoned runs; never restart I/O or infer that output became OFF."""
    recovered = []
    root = Path(root)
    if not root.exists():
        return recovered
    for path in root.glob("*/run_status.json"):
        if path.is_symlink() or path.parent.is_symlink():
            continue
        status = json.loads(path.read_text(encoding="utf-8"))
        if status.get("status") in ("running", "armed"):
            status.update(
                status="interrupted",
                reason="Previous process did not finalize run",
                final_output_state="UNKNOWN",
                residual_voltage_state="UNVERIFIED",
            )
            atomic_json(path, status)
            recovered.append(str(path.parent))
    return recovered


class RunWriter:
    def __init__(self, config, metadata):
        root = Path(config.output_directory).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        self.run_id = stamp + "_" + uuid.uuid4().hex
        self.directory = root / self.run_id
        self.directory.mkdir()  # no exist_ok: a run must never overwrite another
        self.handles = []
        self.closed = False
        area, length = config.effective_geometry_m
        self.include_resistivity = area is not None and length is not None
        try:
            software = {
                "version": metadata.get("software_version") or __version__,
                "commit": metadata.get("software_commit"),
            }
            for field, key in (
                ("source_sha256", "software_source_sha256"),
                ("working_tree_dirty", "software_working_tree_dirty"),
            ):
                if metadata.get(key) is not None:
                    software[field] = metadata[key]
            atomic_json(
                self.directory / "config.json",
                {
                    "schema_version": 1,
                    "software": software,
                    "settings": config.to_dict(),
                },
            )
            stored_metadata = dict(metadata)
            stored_metadata["analysis_text"] = {"include_resistivity": self.include_resistivity}
            atomic_json(self.directory / "metadata.json", stored_metadata)
            self.reading_stream = self._open("readings.csv")
            self.csv = csv.DictWriter(self.reading_stream, fieldnames=READING_FIELDS)
            self.csv.writeheader()
            self.reading_stream.flush()
            self.analysis_stream = self._open("analysis.txt")
            self.analysis_stream.write(analysis_header(self.include_resistivity))
            self.analysis_stream.flush()
            os.fsync(self.analysis_stream.fileno())
            self.event_stream = self._open("events.jsonl")
            self.io_stream = self._open("raw_io.jsonl")
            self._open("summary.csv").close()
            self.status("armed", "Files prepared before output enable", "OFF")
        except BaseException:
            self.close()
            raise

    def _open(self, name):
        stream = (self.directory / name).open("w", encoding="utf-8", newline="")
        self.handles.append(stream)
        return stream

    def _line(self, stream, item):
        payload = json.dumps(item, ensure_ascii=False, allow_nan=False)
        stream.write(payload + "\n")
        stream.flush()
        os.fsync(stream.fileno())

    def event(self, item):
        self._line(self.event_stream, item)

    def raw_io(self, item):
        self._line(self.io_stream, item)

    def sample(self, row):
        output = {key: row.get(key) for key in READING_FIELDS}
        output["run_id"] = self.run_id
        output["quality_flags"] = json.dumps(output.get("quality_flags") or [], allow_nan=False)
        for value in output.values():
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("Non-finite sample must be classified and stored as null")
        analysis = analysis_line(output, include_resistivity=self.include_resistivity)
        self.csv.writerow(output)
        self.reading_stream.flush()
        os.fsync(self.reading_stream.fileno())
        self.analysis_stream.write(analysis)
        self.analysis_stream.flush()
        os.fsync(self.analysis_stream.fileno())

    def summaries(self, rows):
        if not rows:
            return
        fields = list(dict.fromkeys(key for row in rows for key in row))
        with (self.directory / "summary.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        k: json.dumps(v, allow_nan=False) if isinstance(v, (dict, list)) else v
                        for k, v in row.items()
                    }
                )
            stream.flush()
            os.fsync(stream.fileno())

    def status(self, status, reason, output_state, **extra):
        atomic_json(
            self.directory / "run_status.json",
            dict(
                status=status,
                reason=reason,
                final_output_state=output_state,
                residual_voltage_state="UNVERIFIED",
                **extra,
            ),
        )

    def close(self):
        for stream in self.handles:
            try:
                stream.close()
            except OSError:
                pass
        self.closed = True
