"""Durable samples and separate command, output, and residual-charge state."""

import csv
import json
import math
import os
import uuid
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
            atomic_json(self.directory / "metadata.json", metadata)
            self.reading_stream = self._open("readings.csv")
            self.csv = csv.DictWriter(self.reading_stream, fieldnames=READING_FIELDS)
            self.csv.writeheader()
            self.reading_stream.flush()
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
        self.csv.writerow(output)
        self.reading_stream.flush()
        os.fsync(self.reading_stream.fileno())

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
