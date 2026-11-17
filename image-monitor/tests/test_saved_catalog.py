"""Verify offline original-byte previews without touching collection or saved data."""

import copy
import hashlib
import json
import re
import socket
import threading
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_monitor_finish_runtime import (
    assert_preserved,
    finish,
    preserve,
)
from test_monitor_finish_runtime import (
    completed_monitor as completed_monitor,
)

from image_monitor import saved_catalog as catalog
from image_monitor.candidate_save_selection import (
    MANIFEST_NAME,
    MONITOR_MANIFEST_NAME,
    write_selection_control,
)
from image_monitor.native_ui import NativeUIError
from image_monitor.queue import QueueStore
from image_monitor.watch_lock import watch_run_lock
from image_monitor.watch_runtime import DEFAULT_SCOPE


@pytest.fixture
def local_catalog(completed_monitor, monkeypatch):
    monkeypatch.setattr(catalog, "NativeSaveLock", nullcontext)
    monkeypatch.setattr(catalog, "session_id", lambda: 1)
    monkeypatch.setattr(catalog, "shared_state_path", lambda: completed_monitor.marker)
    return completed_monitor


@pytest.fixture
def saved(local_catalog):
    assert finish(local_catalog)["status"] == "candidate_finish_completed"
    assert not local_catalog.marker.exists()
    return local_catalog


def load(value, **options):
    return catalog.load_saved_catalog(value.watch_root, value.work_root, **options)


def assert_unpublished(snapshot, status):
    assert snapshot.summary["status"] == status, snapshot.summary
    assert snapshot.summary["files_verified"] == snapshot.summary["preview_count"] == 0
    assert snapshot.summary["files"] == []
    assert snapshot.images == {}


def test_completed_monitor_image_is_verified_and_cached_without_changing_any_data(saved):
    before = preserve(saved)
    original = Path(saved.artifact["final_path"]).read_bytes()
    snapshot = load(saved)
    assert snapshot.summary["status"] == "ready", snapshot.summary
    assert snapshot.summary["reason"] is snapshot.summary["error_type"] is None
    assert snapshot.summary["files_verified"] == snapshot.summary["preview_count"] == 1
    item = snapshot.summary["files"][0]
    assert item == {
        "saved_filename": "001.png",
        "detected_format": "PNG",
        "file_size": len(original),
        "width": 4,
        "height": 3,
        "frames": 1,
        "preview_id": item["preview_id"],
        "preview_available": True,
    }
    assert re.fullmatch(r"[0-9a-f]{32}", item["preview_id"])
    assert snapshot.images == {item["preview_id"]: ("image/png", original)}
    assert_preserved(saved, before)
    assert not saved.marker.exists()
    public = json.dumps(snapshot.summary)
    for private in (str(saved.root), saved.permit.post_url, saved.permit.fingerprint):
        assert private not in public


def test_cached_original_bytes_remain_stable_if_the_local_file_is_later_changed(saved):
    snapshot = load(saved)
    original = next(iter(snapshot.images.values()))[1]
    Path(saved.artifact["final_path"]).write_bytes(b"Different later local file contents")
    assert next(iter(snapshot.images.values())) == ("image/png", original)
    assert isinstance(original, bytes)
    assert_unpublished(load(saved), "needs_review")


def test_each_refresh_uses_new_opaque_preview_identifiers(saved):
    first, second = load(saved), load(saved)
    assert set(first.images).isdisjoint(second.images)
    assert list(first.images.values()) == list(second.images.values())
    assert first.summary["files"][0]["saved_filename"] == "001.png"


def test_missing_roots_never_create_data_or_acquire_native_ownership(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, "NativeSaveLock", lambda: pytest.fail("Native lock requested"))
    snapshot = catalog.load_saved_catalog(tmp_path / "watch", tmp_path / "native")
    assert_unpublished(snapshot, "empty")
    assert snapshot.summary["reason"] == "existing_saved_candidate_required"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("missing", ["manifest", "native_database"])
def test_missing_saved_records_do_not_fall_back_or_recreate_them(saved, missing):
    path = (
        saved.watch_root / MONITOR_MANIFEST_NAME
        if missing == "manifest"
        else saved.base / "queue.sqlite"
    )
    old = path.read_bytes()
    path.unlink()
    legacy = (saved.watch_root / MANIFEST_NAME).read_bytes()
    snapshot = load(saved)
    assert_unpublished(snapshot, "empty")
    assert not path.exists()
    assert (saved.watch_root / MANIFEST_NAME).read_bytes() == legacy
    assert old


def test_unresolved_native_save_stays_busy_without_verification_or_marker_changes(
    local_catalog, monkeypatch
):
    pending = local_catalog.marker.read_bytes()
    before = preserve(local_catalog)
    monkeypatch.setattr(
        catalog,
        "verify_completed_candidate_files",
        lambda *_args, **_kwargs: pytest.fail("An unresolved save was inspected"),
    )
    snapshot = load(local_catalog)
    assert_unpublished(snapshot, "busy")
    assert snapshot.summary["reason"] == "pending_save_requires_review"
    assert local_catalog.marker.read_bytes() == pending
    assert_preserved(local_catalog, before)


def test_common_watch_lease_contention_is_reported_without_native_work(saved):
    before = preserve(saved)
    with watch_run_lock(saved.watch_root / "watch.sqlite", DEFAULT_SCOPE):
        snapshot = load(saved)
    assert_unpublished(snapshot, "busy")
    assert snapshot.summary["reason"] == "another_scan_owns_this_scope"
    assert_preserved(saved, before)


def test_native_ownership_contention_is_safe_and_does_not_expose_exception_text(saved, monkeypatch):
    class Busy:
        def __enter__(self):
            raise NativeUIError("Private title, user path, token and browser identity")

        def __exit__(self, *_args):
            pytest.fail("Unacquired native ownership was released")

    monkeypatch.setattr(catalog, "NativeSaveLock", Busy)
    snapshot = load(saved)
    assert_unpublished(snapshot, "busy")
    assert snapshot.summary["reason"] == "native_save_in_progress"
    assert "Private" not in json.dumps(snapshot.summary)


def test_service_access_blocks_and_cooldowns_do_not_prevent_local_viewing(saved):
    write_selection_control(saved.watch_root / MONITOR_MANIFEST_NAME, {"blocked": True})
    write_selection_control(saved.watch_root / MANIFEST_NAME, {"blocked": True})
    before = preserve(saved)
    snapshot = load(saved)
    assert snapshot.summary["status"] == "ready", snapshot.summary
    assert snapshot.summary["files_verified"] == 1
    assert_preserved(saved, before)


@pytest.mark.parametrize("kind", ["final_path", "metadata_path"])
def test_changed_image_or_metadata_is_preserved_and_no_preview_is_published(saved, kind):
    Path(saved.artifact[kind]).write_bytes(b"Keep this changed file for review")
    before = preserve(saved)
    snapshot = load(saved)
    assert_unpublished(snapshot, "needs_review")
    assert snapshot.summary["reason"] == "saved_catalog_requires_review"
    assert snapshot.summary["error_type"]
    assert_preserved(saved, before)


def test_corrupt_monitor_selection_is_preserved_without_using_the_legacy_selection(saved):
    selection = saved.watch_root / MONITOR_MANIFEST_NAME
    selection.write_bytes(b"Not valid JSON; preserve for review")
    legacy = (saved.watch_root / MANIFEST_NAME).read_bytes()
    before = selection.read_bytes()
    snapshot = load(saved)
    assert_unpublished(snapshot, "needs_review")
    assert selection.read_bytes() == before
    assert (saved.watch_root / MANIFEST_NAME).read_bytes() == legacy


def test_selection_removed_after_precheck_is_never_recreated_by_readonly_loading(
    saved, monkeypatch
):
    selection = saved.watch_root / MONITOR_MANIFEST_NAME
    legacy = (saved.watch_root / MANIFEST_NAME).read_bytes()
    real_select = catalog.select_candidate_save

    def removed(queue, scope, path):
        assert queue.read_only is True and path == selection
        path.unlink()
        return real_select(queue, scope, path)

    monkeypatch.setattr(catalog, "select_candidate_save", removed)
    snapshot = load(saved)
    assert_unpublished(snapshot, "needs_review")
    assert not selection.exists()
    assert (saved.watch_root / MANIFEST_NAME).read_bytes() == legacy


def test_unfinished_native_job_cannot_be_previewed_or_repaired(saved):
    with QueueStore(saved.base / "queue.sqlite") as queue:
        queue.connection.execute("UPDATE jobs SET status='verifying'")
    before = preserve(saved)
    snapshot = load(saved)
    assert_unpublished(snapshot, "needs_review")
    assert_preserved(saved, before)


def test_original_file_change_after_verification_is_rejected_before_publication(saved, monkeypatch):
    real_verify = catalog.verify_completed_candidate_files

    def changed(*args, **kwargs):
        result = real_verify(*args, **kwargs)
        Path(saved.artifact["final_path"]).write_bytes(b"Changed after complete validation")
        return result

    monkeypatch.setattr(catalog, "verify_completed_candidate_files", changed)
    snapshot = load(saved)
    assert_unpublished(snapshot, "needs_review")
    assert snapshot.summary["error_type"] == "ValueError"


def test_preview_buffer_limit_keeps_verified_metadata_without_loading_oversized_bytes(
    saved, monkeypatch
):
    size = Path(saved.artifact["final_path"]).stat().st_size
    monkeypatch.setattr(catalog, "MAX_PREVIEW_BYTES", size - 1)
    monkeypatch.setattr(
        catalog, "_read_preview", lambda *_args: pytest.fail("Oversized preview was read")
    )
    snapshot = load(saved)
    assert snapshot.summary["status"] == "ready"
    assert snapshot.summary["reason"] == "preview_limit"
    assert snapshot.summary["files_verified"] == 1 and snapshot.summary["preview_count"] == 0
    assert snapshot.summary["files"][0]["preview_available"] is False
    assert snapshot.summary["files"][0]["preview_id"] is None
    assert snapshot.images == {}


def test_unsupported_inline_format_retains_only_verified_metadata(saved, monkeypatch):
    real_verify = catalog.verify_completed_candidate_files

    def verified_tiff(*args, **kwargs):
        summary, proofs = real_verify(*args, **kwargs)
        # The common verifier contract permits verified TIFF files. Simulate
        # that format at the browser-cache boundary without changing artifacts.
        proofs[0]["detected_format"] = "TIFF"
        return summary, proofs

    monkeypatch.setattr(catalog, "verify_completed_candidate_files", verified_tiff)
    monkeypatch.setattr(
        catalog, "_read_preview", lambda *_args: pytest.fail("Unsupported inline image was read")
    )
    snapshot = load(saved)
    assert snapshot.summary["status"] == "ready"
    assert snapshot.summary["files"][0]["detected_format"] == "TIFF"
    assert snapshot.summary["files"][0]["preview_id"] is None and snapshot.images == {}


def test_cancellation_before_local_work_does_not_create_data(tmp_path):
    snapshot = catalog.load_saved_catalog(
        tmp_path / "watch", tmp_path / "native", should_stop=lambda: True
    )
    assert_unpublished(snapshot, "cancelled")
    assert snapshot.summary["reason"] == "requested_stop"
    assert list(tmp_path.iterdir()) == []


def test_cancellation_after_verification_never_publishes_a_partial_catalog(saved, monkeypatch):
    stopped = threading.Event()
    real_verify = catalog.verify_completed_candidate_files

    def verified(*args, **kwargs):
        result = real_verify(*args, **kwargs)
        stopped.set()
        return result

    monkeypatch.setattr(catalog, "verify_completed_candidate_files", verified)
    snapshot = load(saved, should_stop=stopped.is_set)
    assert_unpublished(snapshot, "cancelled")


def test_cancellation_after_buffer_loading_discards_original_bytes(saved, monkeypatch):
    stopped = threading.Event()
    real_read = catalog._read_preview

    def read(proof):
        data = real_read(proof)
        stopped.set()
        return data

    monkeypatch.setattr(catalog, "_read_preview", read)
    snapshot = load(saved, should_stop=stopped.is_set)
    assert_unpublished(snapshot, "cancelled")


def test_foreign_proof_path_is_rejected_before_reading_it(saved, tmp_path, monkeypatch):
    real_verify = catalog.verify_completed_candidate_files
    foreign = tmp_path / "001.png"
    foreign.write_bytes(b"Do not expose this unrelated local file")

    def foreign_proof(*args, **kwargs):
        summary, proofs = real_verify(*args, **kwargs)
        proofs[0]["path"] = foreign
        return summary, proofs

    monkeypatch.setattr(catalog, "verify_completed_candidate_files", foreign_proof)
    monkeypatch.setattr(
        catalog, "_read_preview", lambda *_args: pytest.fail("Foreign file was read")
    )
    snapshot = load(saved)
    assert_unpublished(snapshot, "needs_review")


def test_later_preview_failure_discards_an_already_loaded_first_buffer(saved, monkeypatch):
    real_verify = catalog.verify_completed_candidate_files
    original_permit = saved.permit
    real_select = catalog.select_candidate_save

    def two_permit(*args, **kwargs):
        assert real_select(*args, **kwargs).fingerprint == original_permit.fingerprint
        return SimpleNamespace(image_count=2)

    def two_proofs(store, _permit, **kwargs):
        summary, proofs = real_verify(store, original_permit, **kwargs)
        second = copy.deepcopy(proofs[0])
        second.update(path=second["path"].with_name("002.png"), saved_filename="002.png")
        summary["saved_files"] = summary["saved_files"] * 2
        return summary, [proofs[0], second]

    reads = []
    original = Path(saved.artifact["final_path"]).read_bytes()

    def read(proof):
        reads.append(proof["saved_filename"])
        if len(reads) == 2:
            raise ValueError("Second saved image changed")
        return original

    monkeypatch.setattr(catalog, "select_candidate_save", two_permit)
    monkeypatch.setattr(catalog, "verify_completed_candidate_files", two_proofs)
    monkeypatch.setattr(catalog, "_read_preview", read)
    snapshot = load(saved)
    assert reads == ["001.png", "002.png"]
    assert_unpublished(snapshot, "needs_review")


def test_local_catalog_does_not_open_network_connections(saved, monkeypatch):
    def unexpected_network(*_args, **_kwargs):
        pytest.fail("Saved-file verification must remain offline")

    monkeypatch.setattr(socket, "socket", unexpected_network)
    snapshot = load(saved)
    assert snapshot.summary["status"] == "ready"


def test_preview_reader_rejects_same_size_bytes_with_the_wrong_hash(tmp_path):
    image = tmp_path / "001.png"
    data = b"Bounded fake data for a byte-cache integrity test"
    image.write_bytes(data)
    with pytest.raises(ValueError, match="verified artifact"):
        catalog._read_preview(
            {"path": image, "file_size": len(data), "sha256": hashlib.sha256(b"other").hexdigest()}
        )


@pytest.mark.parametrize("stop", [False, lambda: None])
def test_invalid_stop_contract_returns_only_a_safe_error(tmp_path, stop):
    snapshot = catalog.load_saved_catalog(tmp_path / "watch", tmp_path / "native", should_stop=stop)
    assert_unpublished(snapshot, "needs_review")
    assert snapshot.summary["error_type"] == "ValueError"
    assert str(tmp_path) not in json.dumps(snapshot.summary)


@pytest.mark.parametrize("kind", ["same", "nested"])
def test_shared_or_nested_roots_are_rejected_without_data_creation(tmp_path, kind):
    watch = tmp_path / "watch"
    output = watch if kind == "same" else watch / "native"
    snapshot = catalog.load_saved_catalog(watch, output)
    assert_unpublished(snapshot, "needs_review")
    assert list(tmp_path.iterdir()) == []
