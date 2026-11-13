"""Diagnostic ZIPs contain only bounded, selected local records and preserve originals."""

import hashlib
import json
import math
import os
import zipfile
from pathlib import Path

import pytest

from keithley6517a.storage import diagnostic_bundle as bundle


def read_bundle(path):
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        data = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(data["manifest.json"])
    for item in manifest["files"]:
        assert len(data[item["name"]]) == item["bytes"]
        assert hashlib.sha256(data[item["name"]]).hexdigest() == item["sha256"]
    assert sum(map(len, data.values())) <= manifest["limits"]["total_bytes"]
    return manifest, data


def write_directory(directory, names):
    directory.mkdir()
    for name in names:
        (directory / name).write_bytes((name + "\nsynthetic\n").encode())
    return directory


def symlink_or_skip(link, target, *, directory=False):
    try:
        link.symlink_to(target, target_is_directory=directory)
    except OSError as exc:
        if os.name == "nt" and getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows runner cannot create symlinks without the required privilege")
        raise


def test_actual_zip_includes_allowlisted_records_latest_reports_and_hashes_only(tmp_path):
    run = write_directory(tmp_path / "run", bundle.RUN_FILES)
    diagnostics = write_directory(tmp_path / "connection", bundle.DIAGNOSTIC_FILES)
    startup = write_directory(
        tmp_path / "startup",
        [
            "startup-check-old.json",
            "startup-check-new.json",
            "bundle-verification-one.json",
            "launcher-error-one.json",
        ],
    )
    os.utime(startup / "startup-check-old.json", ns=(1_000_000, 1_000_000))
    os.utime(startup / "startup-check-new.json", ns=(2_000_000, 2_000_000))
    for directory in (run, diagnostics, startup):
        (directory / "unrelated-private.txt").write_text("must not be included")
        nested = directory / "another-run"
        nested.mkdir()
        (nested / "raw_io.jsonl").write_text("unselected historical record")
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    path = tmp_path / "review.zip"
    result = bundle.export_diagnostic_bundle(
        path,
        run_directory=run,
        diagnostic_directory=diagnostics,
        startup_directory=startup,
        log_text="Synthetic GUI log · 시험\n",
        context={"state": "DISCONNECTED", "output": "OFF"},
    )
    manifest, data = read_bundle(path)
    expected = {"manifest.json", "gui/log.txt"}
    expected.update(f"source/run/{name}" for name in bundle.RUN_FILES)
    expected.update(f"source/diagnostic/{name}" for name in bundle.DIAGNOSTIC_FILES)
    expected.update(
        f"source/startup/{name}"
        for name in (
            "startup-check-new.json",
            "bundle-verification-one.json",
            "launcher-error-one.json",
        )
    )
    assert set(data) == expected == set(result["included"])
    assert data["gui/log.txt"].decode() == "Synthetic GUI log · 시험\n"
    assert manifest["hardware_accessed"] is manifest["automatically_uploaded"] is False
    assert manifest["context"] == {"state": "DISCONNECTED", "output": "OFF"}
    assert manifest["software"]["version"] and manifest["software"]["python"]
    assert any(
        item["reason"] == "older_reports" and item["count"] == 1 for item in manifest["omitted"]
    )
    assert all(source.read_bytes() == value for source, value in before.items())


def test_no_run_yet_still_exports_local_gui_and_environment_summary(tmp_path, monkeypatch):
    def no_hardware(*args, **kwargs):
        pytest.fail("Export must not create instrument or network sessions")

    monkeypatch.setattr("keithley6517a.transport.visa.VisaTransport.__init__", no_hardware)
    monkeypatch.setattr("socket.create_connection", no_hardware)
    path = tmp_path / "early-error.zip"
    bundle.export_diagnostic_bundle(path, log_text="Connection failed", context={"error": "test"})
    manifest, data = read_bundle(path)
    assert set(data) == {"manifest.json", "gui/log.txt"}
    assert manifest["context"]["error"] == "test"
    assert {item["source"] for item in manifest["omitted"]} == {"run", "diagnostic", "startup"}
    assert all(item["reason"] == "not_selected" for item in manifest["omitted"])


def test_missing_files_and_directories_are_explicit_without_failing_export(tmp_path):
    run = write_directory(tmp_path / "run", ["run_status.json"])
    path = tmp_path / "missing.zip"
    bundle.export_diagnostic_bundle(
        path, run_directory=run, diagnostic_directory=tmp_path / "absent", startup_directory=run
    )
    manifest, data = read_bundle(path)
    assert "source/run/run_status.json" in data
    assert sum(item["reason"] == "missing_file" for item in manifest["omitted"]) == 7
    assert any(item["reason"] == "missing_directory" for item in manifest["omitted"])
    assert sum(item["reason"] == "missing_report" for item in manifest["omitted"]) == 3


def test_existing_output_and_source_records_cannot_be_overwritten(tmp_path):
    run = write_directory(tmp_path / "run", ["readings.csv"])
    existing = tmp_path / "existing.zip"
    existing.write_bytes(b"keep this existing file")
    for path in (existing, run / "readings.csv"):
        before = path.read_bytes()
        with pytest.raises(FileExistsError):
            bundle.export_diagnostic_bundle(path, run_directory=run)
        assert path.read_bytes() == before
    # A missing measurement file must not be replaced by a differently named ZIP payload.
    with pytest.raises(ValueError, match="source record"):
        bundle.export_diagnostic_bundle(run / "analysis.txt", run_directory=run)
    assert not (run / "analysis.txt").exists()


def test_source_symlinks_and_linked_ancestors_are_omitted_without_reading_target(tmp_path):
    outside = write_directory(tmp_path / "outside", ["raw_io.jsonl"])
    secret = outside / "raw_io.jsonl"
    secret.write_bytes(b"outside target must never be copied")
    run = write_directory(tmp_path / "run", ["run_status.json"])
    symlink_or_skip(run / "raw_io.jsonl", secret)
    link = tmp_path / "linked"
    symlink_or_skip(link, outside, directory=True)
    path = tmp_path / "links.zip"
    bundle.export_diagnostic_bundle(path, run_directory=run, diagnostic_directory=link)
    manifest, data = read_bundle(path)
    assert b"outside target" not in b"".join(data.values())
    assert "source/run/raw_io.jsonl" not in data
    assert not any(name.startswith("source/diagnostic/") for name in data)
    assert any(item["reason"] == "unsafe_link" for item in manifest["omitted"])
    assert any(item["reason"] == "unsafe_or_changed_source" for item in manifest["omitted"])


def test_output_symlink_or_linked_parent_never_modifies_target(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    original = outside / "original.zip"
    original.write_bytes(b"preserved")
    link = tmp_path / "output.zip"
    symlink_or_skip(link, original)
    with pytest.raises(FileExistsError):
        bundle.export_diagnostic_bundle(link)
    directory_link = tmp_path / "linked-folder"
    symlink_or_skip(directory_link, outside, directory=True)
    with pytest.raises(ValueError, match="symbolic link"):
        bundle.export_diagnostic_bundle(directory_link / "new.zip")
    assert original.read_bytes() == b"preserved" and not (outside / "new.zip").exists()


def test_nonregular_allowlisted_path_is_reported_without_opening_it(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "raw_io.jsonl").mkdir()
    path = tmp_path / "not-regular.zip"
    bundle.export_diagnostic_bundle(path, run_directory=run)
    manifest, data = read_bundle(path)
    assert "source/run/raw_io.jsonl" not in data
    assert any(item["reason"] == "not_regular_file" for item in manifest["omitted"])


def test_oversized_file_is_omitted_and_total_archive_payload_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(bundle, "MAX_FILE_BYTES", 8_000)
    monkeypatch.setattr(bundle, "MAX_TOTAL_BYTES", 12_000)
    run = write_directory(tmp_path / "run", bundle.RUN_FILES)
    (run / "raw_io.jsonl").write_bytes(b"a" * 8_001)
    (run / "events.jsonl").write_bytes(b"b" * 7_000)
    (run / "summary.csv").write_bytes(b"c" * 7_000)
    before = {source: source.read_bytes() for source in run.iterdir()}
    path = tmp_path / "limits.zip"
    bundle.export_diagnostic_bundle(path, run_directory=run)
    manifest, data = read_bundle(path)
    assert "source/run/raw_io.jsonl" not in data
    assert any(item["reason"] == "file_size_limit" for item in manifest["omitted"])
    assert any(item["reason"] == "total_size_limit" for item in manifest["omitted"])
    assert all(source.read_bytes() == value for source, value in before.items())


def test_manifest_is_counted_in_total_size_and_removals_are_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(bundle, "MAX_TOTAL_BYTES", 6_000)
    run = write_directory(tmp_path / "run", ["analysis.txt"])
    (run / "analysis.txt").write_bytes(b"a" * 5_900)
    path = tmp_path / "manifest-budget.zip"
    bundle.export_diagnostic_bundle(path, run_directory=run)
    manifest, data = read_bundle(path)
    assert "source/run/analysis.txt" not in data
    assert any(item["reason"] == "manifest_total_size_limit" for item in manifest["omitted"])


def test_log_tail_remains_valid_utf8_and_truncation_is_explicit(tmp_path, monkeypatch):
    monkeypatch.setattr(bundle, "MAX_LOG_BYTES", 7)
    path = tmp_path / "log.zip"
    bundle.export_diagnostic_bundle(path, log_text="앞부분 생략하고 마지막끝")
    manifest, data = read_bundle(path)
    assert len(data["gui/log.txt"]) <= 7
    assert data["gui/log.txt"].decode() == "막끝"
    assert any(item["reason"] == "log_truncated" for item in manifest["omitted"])


@pytest.mark.parametrize("context", [[], {"nan": math.nan}, {"object": Path("test")}])
def test_invalid_context_does_not_create_output(tmp_path, context):
    path = tmp_path / "bad.zip"
    with pytest.raises((ValueError, TypeError)):
        bundle.export_diagnostic_bundle(path, context=context)
    assert not path.exists()


def test_context_size_limit_is_validated_before_creating_output(tmp_path, monkeypatch):
    monkeypatch.setattr(bundle, "MAX_CONTEXT_BYTES", 16)
    path = tmp_path / "large-context.zip"
    with pytest.raises(ValueError, match="context exceeds"):
        bundle.export_diagnostic_bundle(path, context={"message": "x" * 100})
    assert not path.exists()


def test_zip_write_failure_removes_only_the_new_partial_output(tmp_path, monkeypatch):
    run = write_directory(tmp_path / "run", ["readings.csv"])
    original = (run / "readings.csv").read_bytes()
    path = tmp_path / "partial.zip"
    written = []
    real_write = zipfile.ZipFile.writestr

    def failed_write(self, name, data, *args, **kwargs):
        written.append(name)
        if len(written) == 2:
            raise OSError("synthetic ZIP disk failure")
        return real_write(self, name, data, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "writestr", failed_write)
    with pytest.raises(OSError, match="synthetic ZIP disk failure"):
        bundle.export_diagnostic_bundle(path, run_directory=run)
    assert written and not path.exists()
    assert (run / "readings.csv").read_bytes() == original


def test_unreadable_or_changing_source_is_omitted_instead_of_corrupt_snapshot(
    tmp_path, monkeypatch
):
    run = write_directory(tmp_path / "run", ["raw_io.jsonl"])
    path = tmp_path / "unreadable.zip"
    real_open = bundle.os.open

    def deny(source, *args, **kwargs):
        if Path(source).name == "raw_io.jsonl":
            raise PermissionError("synthetic read denial")
        return real_open(source, *args, **kwargs)

    monkeypatch.setattr(bundle.os, "open", deny)
    bundle.export_diagnostic_bundle(path, run_directory=run)
    manifest, data = read_bundle(path)
    assert "source/run/raw_io.jsonl" not in data
    assert any(item["reason"] == "read_error" for item in manifest["omitted"])


def test_record_changed_during_snapshot_is_omitted_with_no_mixed_file(tmp_path, monkeypatch):
    run = write_directory(tmp_path / "run", ["raw_io.jsonl"])
    source = run / "raw_io.jsonl"
    original_time = source.stat().st_mtime_ns
    real_open = bundle.os.open

    def change_after_initial_stat(path, *args, **kwargs):
        descriptor = real_open(path, *args, **kwargs)
        if Path(path) == source:
            source.write_bytes(b"changed externally after snapshot began")
            os.utime(source, ns=(original_time + 1_000_000, original_time + 1_000_000))
        return descriptor

    monkeypatch.setattr(bundle.os, "open", change_after_initial_stat)
    path = tmp_path / "changed.zip"
    bundle.export_diagnostic_bundle(path, run_directory=run)
    manifest, data = read_bundle(path)
    assert "source/run/raw_io.jsonl" not in data
    assert any(item["reason"] == "source_changed" for item in manifest["omitted"])


def test_final_disk_sync_failure_removes_new_zip_without_changing_sources(tmp_path, monkeypatch):
    run = write_directory(tmp_path / "run", ["readings.csv"])
    before = (run / "readings.csv").read_bytes()

    def fail_sync(*args):
        raise OSError("synthetic diagnostic sync failure")

    monkeypatch.setattr(bundle.os, "fsync", fail_sync)
    path = tmp_path / "unsynced.zip"
    with pytest.raises(OSError, match="synthetic diagnostic sync failure"):
        bundle.export_diagnostic_bundle(path, run_directory=run)
    assert not path.exists() and (run / "readings.csv").read_bytes() == before


def test_impossible_manifest_budget_fails_before_creating_output(tmp_path, monkeypatch):
    monkeypatch.setattr(bundle, "MAX_TOTAL_BYTES", 1)
    path = tmp_path / "too-small.zip"
    with pytest.raises(ValueError, match="manifest exceeds"):
        bundle.export_diagnostic_bundle(path)
    assert not path.exists()


def test_startup_scan_limit_is_explicit_and_does_not_claim_partial_latest_selection(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(bundle, "MAX_STARTUP_ENTRIES", 1)
    startup = write_directory(
        tmp_path / "startup", ["startup-check-a.json", "startup-check-b.json"]
    )
    path = tmp_path / "limited-scan.zip"
    bundle.export_diagnostic_bundle(path, startup_directory=startup)
    manifest, data = read_bundle(path)
    assert not any(name.startswith("source/startup/") for name in data)
    assert any(item["reason"] == "startup_scan_limit" for item in manifest["omitted"])


def test_unsafe_startup_name_never_becomes_a_zip_traversal_path(tmp_path):
    if os.name == "nt":
        # Backslashes are directory separators on Windows, rather than legal basenames.
        return
    startup = write_directory(tmp_path / "startup", ["startup-check-..\\..\\escape.json"])
    path = tmp_path / "names.zip"
    bundle.export_diagnostic_bundle(path, startup_directory=startup)
    manifest, data = read_bundle(path)
    assert not any("\\" in name or name.startswith("source/startup/") for name in data)
    assert any(item["reason"] == "unsafe_report_name" for item in manifest["omitted"])
