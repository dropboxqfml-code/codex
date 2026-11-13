"""Analysis sessions preserve file identity and selections without touching measurements."""

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from keithley6517a.analysis import session as session_module
from keithley6517a.analysis.session import (
    AnalysisSession,
    load_session,
    save_session,
    source_fingerprints,
)


def inputs(tmp_path):
    paths = []
    for index in range(2):
        folder = tmp_path / "자료" / f"sample-{index}"
        folder.mkdir(parents=True)
        source = folder / "readings.csv"
        source.write_text(
            "elapsed_s,current_raw_A,resistance_apparent_ohm,voltage_programmed_readback_V\n"
            f"0,1e-9,{(index + 1) * 1e9},1\n",
            encoding="utf-8",
        )
        (folder / "metadata.json").write_text('{"simulation": true}', encoding="utf-8")
        (folder / "config.json").write_text('{"settings": {}}', encoding="utf-8")
        paths.append(source)
    return tuple(paths)


def settings(tmp_path):
    return AnalysisSession(inputs(tmp_path), 1.23456789012345, 20.75, 1, "resistivity")


def snapshot(directory):
    return {
        path.relative_to(directory): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }


def test_roundtrip_preserves_order_interval_quantity_and_relative_paths(tmp_path):
    selected = settings(tmp_path)
    before = snapshot(tmp_path)
    path = tmp_path / "analysis-settings.json"
    result = save_session(selected, path)
    assert result == {"session_file": str(path), "source_count": 2}
    assert load_session(path) == selected
    document = json.loads(path.read_text())
    assert document["kind"] == "6517A-analysis-session" and document["schema_version"] == 1
    assert [item["path"] for item in document["sources"]] == [
        "자료/sample-0/readings.csv",
        "자료/sample-1/readings.csv",
    ]
    assert all(not Path(item["path"]).is_absolute() for item in document["sources"])
    assert document["sources"][0]["sidecars"]["run_status.json"] is None
    assert all((tmp_path / name).read_bytes() == data for name, data in before.items())


def test_session_and_results_can_move_together_without_path_rewrites(tmp_path):
    root = tmp_path / "original"
    root.mkdir()
    selected = settings(root)
    save_session(selected, root / "settings.json")
    moved = tmp_path / "moved"
    shutil.copytree(root, moved)
    shutil.rmtree(root)
    restored = load_session(moved / "settings.json")
    assert restored.sources == tuple(moved / path.relative_to(root) for path in selected.sources)
    assert restored.start_s == selected.start_s and restored.end_s == selected.end_s
    assert restored.active_index == 1 and restored.quantity == "resistivity"


def test_cross_drive_relpath_failure_uses_absolute_source_paths(tmp_path, monkeypatch):
    selected = settings(tmp_path)

    def different_drive(*args):
        raise ValueError("path is on a different drive")

    monkeypatch.setattr(session_module.os.path, "relpath", different_drive)
    path = tmp_path / "settings.json"
    save_session(selected, path)
    document = json.loads(path.read_text())
    assert all(Path(item["path"]).is_absolute() for item in document["sources"])
    assert load_session(path) == selected


@pytest.mark.parametrize(
    "target", ["readings.csv", "metadata.json", "config.json", "run_status.json"]
)
@pytest.mark.parametrize("operation", ["change", "remove"])
def test_missing_or_changed_analysis_inputs_are_not_silently_reopened(tmp_path, target, operation):
    selected = settings(tmp_path)
    target_path = selected.sources[0].parent / target
    if target == "run_status.json":
        target_path.write_text('{"status": "completed"}', encoding="utf-8")
    path = tmp_path / "settings.json"
    save_session(selected, path)
    if operation == "change":
        target_path.write_text("changed input", encoding="utf-8")
    else:
        target_path.unlink()
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match="分析|분석 원본"):
        load_session(path)
    assert snapshot(tmp_path) == before


def test_newly_appearing_optional_sidecar_is_also_detected(tmp_path):
    selected = settings(tmp_path)
    path = tmp_path / "settings.json"
    save_session(selected, path)
    (selected.sources[1].parent / "run_status.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="변경"):
        load_session(path)


def test_save_checks_load_time_fingerprints_before_creating_settings(tmp_path):
    selected = settings(tmp_path)
    loaded = tuple(source_fingerprints(path) for path in selected.sources)
    path = tmp_path / "settings.json"
    save_session(selected, path, expected_fingerprints=loaded)
    selected.sources[0].write_text("data changed while viewing", encoding="utf-8")
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match="불러온 분석 원본이 변경"):
        save_session(selected, tmp_path / "stale-settings.json", expected_fingerprints=loaded)
    assert snapshot(tmp_path) == before


def test_existing_session_and_original_csv_are_never_overwritten(tmp_path):
    selected = settings(tmp_path)
    path = tmp_path / "settings.json"
    save_session(selected, path)
    before = snapshot(tmp_path)
    with pytest.raises(FileExistsError):
        save_session(replace(selected, quantity="resistance"), path)
    with pytest.raises(ValueError, match="측정 원본"):
        save_session(selected, selected.sources[0])
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "name",
    [
        "metadata.json",
        "config.json",
        "run_status.json",
        "readings.csv",
        "analysis.txt",
        "summary.csv",
        "raw_io.jsonl",
        "events.jsonl",
    ],
)
def test_new_settings_cannot_create_or_replace_reserved_result_files(tmp_path, name):
    selected = settings(tmp_path)
    destination = selected.sources[1].parent / name
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match="측정 원본"):
        save_session(selected, destination)
    assert snapshot(tmp_path) == before


def test_failed_flush_removes_only_the_new_incomplete_settings(tmp_path, monkeypatch):
    selected = settings(tmp_path)
    before = snapshot(tmp_path)
    path = tmp_path / "settings.json"

    def failed_sync(*args):
        raise OSError("disk synchronization failed")

    monkeypatch.setattr(session_module.os, "fsync", failed_sync)
    with pytest.raises(OSError, match="disk synchronization failed"):
        save_session(selected, path)
    assert not path.exists() and snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "changes",
    [
        {"start_s": float("nan")},
        {"end_s": float("inf")},
        {"start_s": True},
        {"start_s": "1"},
        {"end_s": 1e13},
        {"start_s": 30},
        {"active_index": True},
        {"active_index": -1},
        {"active_index": 2},
        {"quantity": "voltage"},
        {"sources": ()},
        {"sources": tuple([Path("missing")] * 65)},
    ],
)
def test_invalid_selections_fail_without_creating_output(tmp_path, changes):
    selected = replace(settings(tmp_path), **changes)
    path = tmp_path / "settings.json"
    before = snapshot(tmp_path)
    with pytest.raises(ValueError):
        save_session(selected, path)
    assert snapshot(tmp_path) == before


def test_duplicate_aliases_are_rejected_before_output(tmp_path):
    selected = settings(tmp_path)
    source = selected.sources[0]
    selected = replace(selected, sources=(source, source.parent / "." / source.name))
    with pytest.raises(ValueError, match="중복"):
        save_session(selected, tmp_path / "settings.json")
    assert not (tmp_path / "settings.json").exists()


@pytest.mark.parametrize(
    "payload",
    [
        "{bad",
        "[]",
        '{"bad": NaN}',
        '{"kind":1,"kind":2}',
        '{"kind":"6517A-analysis-session","schema_version":2}',
    ],
)
def test_malformed_or_unsupported_json_is_rejected_without_writes(tmp_path, payload):
    path = tmp_path / "settings.json"
    path.write_text(payload, encoding="utf-8")
    before = snapshot(tmp_path)
    with pytest.raises(ValueError):
        load_session(path)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "modify",
    [
        lambda value: value.update(schema_version=True),
        lambda value: value.update(schema_version=2),
        lambda value: value.update(quantity="unknown"),
        lambda value: value.update(active_index=False),
        lambda value: value.update(start_s="0"),
        lambda value: value.update(end_s=-100),
        lambda value: value.update(unrecognized_field={"voltage": 1000}),
        lambda value: value["sources"][0].update(sha256="invalid"),
        lambda value: value["sources"][0].update(path=""),
        lambda value: value["sources"][0].update(sidecars=[]),
        lambda value: value["sources"].append(value["sources"][0]),
    ],
)
def test_valid_json_requires_explicit_supported_schema(tmp_path, modify):
    path = tmp_path / "settings.json"
    save_session(settings(tmp_path), path)
    value = json.loads(path.read_text())
    modify(value)
    path.write_text(json.dumps(value), encoding="utf-8")
    before = snapshot(tmp_path)
    with pytest.raises(ValueError):
        load_session(path)
    assert snapshot(tmp_path) == before


def test_import_and_roundtrip_do_not_construct_instrument_objects(tmp_path, monkeypatch):
    def no_hardware(*args, **kwargs):
        pytest.fail("Analysis settings must not construct an instrument session")

    monkeypatch.setattr("keithley6517a.measurement.runner.MeasurementRunner.__init__", no_hardware)
    monkeypatch.setattr("keithley6517a.transport.visa.VisaTransport.__init__", no_hardware)
    selected = settings(tmp_path)
    path = tmp_path / "settings.json"
    save_session(selected, path)
    assert load_session(path) == selected
