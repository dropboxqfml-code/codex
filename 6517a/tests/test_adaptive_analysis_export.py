"""Resistivity exports retain one run-level schema and original sample values."""

import csv
import json
from dataclasses import replace

import pytest

from keithley6517a.config import RunConfig
from keithley6517a.storage.analysis_export import export_analysis
from keithley6517a.storage.run_writer import (
    ANALYSIS_HEADER,
    ANALYSIS_RESISTIVITY_HEADER,
    RunWriter,
    analysis_header,
    analysis_includes_resistivity,
    analysis_line,
)

DIMENSIONS = {
    "sample_length_mm": 20.0,
    "sample_width_mm": 10.0,
    "sample_depth_mm": 2.0,
    "current_path_axis": "D",
}
FIELDS = [
    "elapsed_s",
    "native_r_ohm",
    "resistance_apparent_ohm",
    "resistivity_ohm_m",
    "voltage_programmed_readback_V",
    "current_raw_A",
]


def write_csv(path, rows, *, include_rho=True):
    fields = FIELDS if include_rho else [key for key in FIELDS if key != "resistivity_ohm_m"]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.mark.parametrize(
    ("settings", "expected"),
    [({}, False), ({"sample_id": "known-name"}, False), (DIMENSIONS, True)],
)
def test_run_schema_and_recorded_flag_are_ready_before_first_sample(tmp_path, settings, expected):
    metadata = {"operator": "operator", "analysis_text": {"previous": "caller-owned"}}
    original = json.loads(json.dumps(metadata))
    config = replace(RunConfig(), output_directory=str(tmp_path), **settings)
    writer = RunWriter(config, metadata)
    try:
        assert (writer.directory / "analysis.txt").read_text() == analysis_header(expected)
        saved = json.loads((writer.directory / "metadata.json").read_text())
        assert saved["analysis_text"] == {"include_resistivity": expected}
        assert saved["operator"] == "operator"
        assert metadata == original
        assert json.loads((writer.directory / "run_status.json").read_text())["status"] == "armed"
    finally:
        writer.close()


def test_partial_dimensions_do_not_reuse_legacy_geometry(tmp_path):
    config = replace(
        RunConfig(),
        output_directory=str(tmp_path),
        sample_length_mm=20,
        area_m2=1e-4,
        thickness_m=1e-3,
    )
    writer = RunWriter(config, {})
    try:
        assert (writer.directory / "analysis.txt").read_text() == ANALYSIS_HEADER
        assert not analysis_includes_resistivity([], settings=config.to_dict())
    finally:
        writer.close()


def test_five_column_run_keeps_missing_zero_voltage_and_error_rows(tmp_path):
    writer = RunWriter(replace(RunConfig(), output_directory=str(tmp_path), **DIMENSIONS), {})
    try:
        writer.sample(dict(elapsed_s=0.0, voltage_programmed_readback_V=0.0, current_raw_A=0.0))
        writer.sample(
            dict(
                elapsed_s=1.0,
                resistance_apparent_ohm=100.0,
                resistivity_ohm_m=-7.123456789012345,
                voltage_programmed_readback_V=-1.0,
                current_raw_A=-0.01,
            )
        )
        writer.sample(dict(phase="ERROR", elapsed_s=2.0, quality_flags=["RUN_ABORTED"]))
        writer.status("stopped", "STOP", "OFF")
        assert (writer.directory / "analysis.txt").read_text() == (
            ANALYSIS_RESISTIVITY_HEADER
            + "0.0\tnan\tnan\t0.0\t0.0\n"
            + "1.0\t100.0\t-7.123456789012345\t-1.0\t-0.01\n"
            + "2.0\tnan\tnan\tnan\tnan\n"
        )
    finally:
        writer.close()


def test_stored_resistivity_is_not_recomputed_from_apparent_or_native_resistance():
    row = dict(
        elapsed_s=-0.0,
        native_r_ohm=0.0,
        resistance_apparent_ohm=99.0,
        resistance_corrected_ohm=-1.2345678901234567e9,
        resistivity_ohm_m=-123456.78901234567,
        voltage_programmed_readback_V=-2.0,
        current_raw_A=None,
        current_inferred_A=1e-9,
    )
    assert analysis_line(row, include_resistivity=True) == (
        "-0.0\t0.0\t-123456.78901234567\t-2.0\tnan\n"
    )
    assert analysis_line(row) == "-0.0\t0.0\t-2.0\tnan\n"


@pytest.mark.parametrize("rho", [0, -0.0, "0", -1.2e11])
def test_any_finite_recorded_resistivity_enables_schema_even_if_declared_four(rho):
    assert analysis_includes_resistivity(
        [{"resistivity_ohm_m": None}, {"resistivity_ohm_m": rho}],
        metadata={"analysis_text": {"include_resistivity": False}},
    )


@pytest.mark.parametrize("declared", [True, False])
def test_explicit_new_schema_is_authoritative_when_all_resistivity_is_unknown(declared):
    assert (
        analysis_includes_resistivity(
            [{"resistivity_ohm_m": ""}],
            metadata={"analysis_text": {"include_resistivity": declared}},
            settings=DIMENSIONS,
        )
        is declared
    )


@pytest.mark.parametrize("rho", ["nan", "Infinity", float("-inf"), "bad", True, [1]])
def test_invalid_resistivity_is_rejected_even_after_a_finite_row(rho):
    with pytest.raises(ValueError):
        analysis_includes_resistivity(
            [{"resistivity_ohm_m": 1.0}, {"resistivity_ohm_m": rho}],
            metadata={"analysis_text": {"include_resistivity": True}},
        )


@pytest.mark.parametrize(
    "context",
    [
        {"metadata": {"analysis_text": {"include_resistivity": True}}},
        {"settings": {"settings": DIMENSIONS, "unrelated": "ignored"}},
        {"metadata": {"settings": DIMENSIONS}},
        {"settings": {"area_m2": 0.0002, "thickness_m": 0.002}},
        {
            "metadata": {
                "sample_geometry": {
                    "complete": True,
                    "area_m2": 0.0002,
                    "current_path_length_m": 0.002,
                }
            }
        },
    ],
)
def test_header_only_and_zero_voltage_legacy_runs_remember_geometry(context):
    assert analysis_includes_resistivity([], **context)
    assert analysis_includes_resistivity([{"resistivity_ohm_m": None}], **context)


def test_csv_resistivity_column_alone_does_not_enable_five_columns(tmp_path):
    source = write_csv(tmp_path / "readings.csv", [{"elapsed_s": 0}])
    export_analysis(source)
    assert (tmp_path / "analysis.txt").read_text() == ANALYSIS_HEADER + "0.0\tnan\tnan\tnan\n"


def test_cli_scans_entire_legacy_csv_then_preserves_all_original_sources(tmp_path):
    source = write_csv(
        tmp_path / "readings.csv",
        [
            {"elapsed_s": 0, "voltage_programmed_readback_V": 0, "current_raw_A": 0},
            {
                "elapsed_s": "1.2345678901234567",
                "native_r_ohm": "0",
                "resistance_apparent_ohm": "1e9",
                "resistivity_ohm_m": "-7.123456789012345",
                "voltage_programmed_readback_V": "-1",
                "current_raw_A": "-1e-9",
            },
        ],
    )
    (tmp_path / "metadata.json").write_text('{"sample_id": "test"}', encoding="utf-8")
    (tmp_path / "config.json").write_text('{"unknown_future_field": true}', encoding="utf-8")
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    result = export_analysis(source)
    assert result["rows"] == 2
    assert (tmp_path / "analysis.txt").read_text() == (
        ANALYSIS_RESISTIVITY_HEADER
        + "0.0\tnan\tnan\t0.0\t0.0\n"
        + "1.2345678901234567\t0.0\t-7.123456789012345\t-1.0\t-1e-09\n"
    )
    assert all((tmp_path / name).read_bytes() == value for name, value in before.items())
    original = (tmp_path / "analysis.txt").read_bytes()
    with pytest.raises(FileExistsError):
        export_analysis(source)
    assert (tmp_path / "analysis.txt").read_bytes() == original


@pytest.mark.parametrize("header_only", [False, True])
def test_cli_legacy_config_preserves_five_columns_when_all_rho_unknown(tmp_path, header_only):
    source = write_csv(tmp_path / "readings.csv", [] if header_only else [{"elapsed_s": 0}])
    (tmp_path / "config.json").write_text(
        json.dumps({"settings": {**DIMENSIONS, "transport": "future-transport"}}),
        encoding="utf-8",
    )
    export_analysis(source)
    text = (tmp_path / "analysis.txt").read_text()
    assert text == ANALYSIS_RESISTIVITY_HEADER + (
        "" if header_only else "0.0\tnan\tnan\tnan\tnan\n"
    )


def test_legacy_csv_without_resistivity_column_stays_four_columns(tmp_path):
    source = write_csv(tmp_path / "readings.csv", [{"elapsed_s": 1}], include_rho=False)
    export_analysis(source)
    assert (tmp_path / "analysis.txt").read_text() == ANALYSIS_HEADER + "1.0\tnan\tnan\tnan\n"


@pytest.mark.parametrize("filename", ["metadata.json", "config.json"])
@pytest.mark.parametrize("payload", ["{bad", "[]", '{"bad": NaN}'])
def test_invalid_sidecars_fail_without_output_or_source_changes(tmp_path, filename, payload):
    source = write_csv(tmp_path / "readings.csv", [{"elapsed_s": 1}])
    sidecar = tmp_path / filename
    sidecar.write_text(payload, encoding="utf-8")
    original = source.read_bytes()
    with pytest.raises(ValueError):
        export_analysis(source)
    assert not (tmp_path / "analysis.txt").exists()
    assert source.read_bytes() == original
    assert sidecar.read_text() == payload


def test_invalid_csv_rho_never_leaves_a_silently_downgraded_output(tmp_path):
    source = write_csv(tmp_path / "readings.csv", [{"elapsed_s": 1, "resistivity_ohm_m": "nan"}])
    with pytest.raises(ValueError, match="Non-finite"):
        export_analysis(source)
    assert not (tmp_path / "analysis.txt").exists()
