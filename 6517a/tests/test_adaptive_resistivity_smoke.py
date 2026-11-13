"""Native smoke independently rejects wrong adaptive schemas, rho cells, and rho UI."""

import csv
import importlib.util
import json
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("adaptive_smoke", PROJECT / "packaging/smoke.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)

FOUR = "Time (s)\tResistance (Ohm)\tVoltage (V)\tCurrent (A)\n"
FIVE = "Time (s)\tResistance (Ohm)\tResistivity (Ohm m)\tVoltage (V)\tCurrent (A)\n"


def stored_run(directory, *, geometry=False, finite_rho=False, declaration=None):
    directory.mkdir()
    rows = [
        dict(
            elapsed_s=index,
            resistance_apparent_ohm=(index + 1) * 1e9,
            resistivity_ohm_m=(index + 1) * 1e8 if finite_rho and index != 3 else None,
            voltage_programmed_readback_V=1,
            current_raw_A=1e-9 / (index + 1),
            phase="ACQUIRING",
            status_code="N",
            quality_flags="[]",
        )
        for index in range(8)
    ]
    with (directory / "readings.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, rows[0])
        writer.writeheader()
        writer.writerows(rows)
    metadata = {"simulation": True}
    if geometry:
        metadata["sample_geometry"] = {"area_m2": 2e-4, "current_path_length_m": 2e-3}
    if declaration is not None:
        metadata["analysis_text"] = {"include_resistivity": declaration}
    (directory / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    include_rho = finite_rho or (declaration if declaration is not None else geometry)
    text = FIVE if include_rho else FOUR
    for row in rows:
        cells = [row["elapsed_s"], row["resistance_apparent_ohm"]]
        if include_rho:
            cells.append(row["resistivity_ohm_m"])
        cells.extend([row["voltage_programmed_readback_V"], row["current_raw_A"]])
        text += "\t".join("nan" if value is None else str(value) for value in cells) + "\n"
    (directory / "analysis.txt").write_text(text, encoding="utf-8")
    return directory


@pytest.mark.parametrize(
    ("geometry", "finite_rho", "declaration"),
    [
        (False, False, None),
        (True, False, None),
        (False, True, None),
        (False, False, True),
        (True, False, False),
        (False, True, False),
    ],
)
def test_smoke_schema_uses_recorded_geometry_or_values_never_csv_header(
    tmp_path, geometry, finite_rho, declaration
):
    directory = stored_run(
        tmp_path / "run", geometry=geometry, finite_rho=finite_rho, declaration=declaration
    )
    assert smoke.analysis_export_smoke(directory) == 8


@pytest.mark.parametrize("broken", ["four", "extra", "order", "rho", "missing_nan"])
def test_smoke_rejects_wrong_schema_order_rho_or_missing_nan(tmp_path, broken):
    directory = stored_run(tmp_path / "run", geometry=True, finite_rho=True)
    path = directory / "analysis.txt"
    lines = [line.split("\t") for line in path.read_text().splitlines()]
    if broken == "four":
        lines = [line[:2] + line[3:] for line in lines]
    elif broken == "extra":
        lines = [line + ["0"] for line in lines]
    elif broken == "order":
        lines = [line[:2] + [line[3], line[2], line[4]] for line in lines]
    elif broken == "rho":
        lines[1][2] = "999"
    else:
        lines[4][2] = "0"
    path.write_text("\n".join("\t".join(line) for line in lines) + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        smoke.analysis_export_smoke(directory)


def test_smoke_rejects_empty_rho_column_used_to_force_five_column_schema(tmp_path):
    directory = stored_run(tmp_path / "run")
    path = directory / "analysis.txt"
    lines = [line.split("\t") for line in path.read_text().splitlines()]
    lines = [
        line[:2] + ["Resistivity (Ohm m)" if index == 0 else "nan"] + line[2:]
        for index, line in enumerate(lines)
    ]
    path.write_text("\n".join("\t".join(line) for line in lines) + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="headers"):
        smoke.analysis_export_smoke(directory)


@pytest.mark.parametrize(
    "sample_settings",
    [
        {"sample_id": "synthetic-only"},
        {"sample_length_mm": 20},
        {"sample_length_mm": 20, "sample_width_mm": 10, "sample_depth_mm": 2},
    ],
)
def test_smoke_keeps_four_columns_for_id_or_incomplete_geometry(tmp_path, sample_settings):
    directory = stored_run(tmp_path / "run")
    (directory / "config.json").write_text(
        json.dumps({"settings": sample_settings}), encoding="utf-8"
    )
    assert smoke.analysis_export_smoke(directory) == 8


def test_smoke_incomplete_new_geometry_suppresses_legacy_and_metadata_geometry(tmp_path):
    directory = stored_run(tmp_path / "run")
    (directory / "config.json").write_text(
        json.dumps({"settings": {"sample_length_mm": 20, "area_m2": 2e-4, "thickness_m": 2e-3}}),
        encoding="utf-8",
    )
    (directory / "metadata.json").write_text(
        json.dumps({"sample_geometry": {"area_m2": 2e-4, "current_path_length_m": 2e-3}}),
        encoding="utf-8",
    )
    assert smoke.analysis_export_smoke(directory) == 8


def test_native_adaptive_smoke_covers_zero_v_nan_and_unspecified_axis_without_visa(
    tmp_path, monkeypatch
):
    def no_instrument(*args, **kwargs):
        pytest.fail("Adaptive analysis smoke must not open a VISA session")

    monkeypatch.setattr("keithley6517a.transport.visa.VisaTransport.__init__", no_instrument)
    smoke.adaptive_resistivity_analysis_smoke(tmp_path / "runs")


def test_native_review_checks_rho_stats_graph_and_five_column_selection(qtbot, tmp_path):
    directory = stored_run(tmp_path / "run", geometry=True, finite_rho=True)
    assert smoke.saved_result_review_smoke(directory, tmp_path / "selection.txt") == 4
    assert (tmp_path / "selection.txt").read_text().startswith(FIVE)


@pytest.mark.parametrize("broken", ["statistics", "table", "graph"])
def test_native_review_rejects_wrong_rho_statistics_table_or_graph(qtbot, tmp_path, broken):
    from keithley6517a.ui.result_dialog import SavedResultDialog

    class BrokenResistivity(SavedResultDialog):
        def apply_range(self):
            ready = super().apply_range()
            if ready:
                if broken == "statistics":
                    self.statistics["resistivity_mean_ohm_m"] = 999
                elif broken == "table":
                    self.statistics_table.item(2, 1).setText("999 Ω·m")
                else:
                    self.curves["resistivity"].setData([0], [999])
            return ready

    directory = stored_run(tmp_path / "run", geometry=True, finite_rho=True)
    with pytest.raises(RuntimeError, match="statistic differs|resistivity table|resistivity graph"):
        smoke.saved_result_review_smoke(
            directory, tmp_path / "selection.txt", dialog_factory=BrokenResistivity
        )
