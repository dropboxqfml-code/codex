"""Finish only the monitor's already completed, independently frozen native save."""

import hashlib
import sys
import tempfile
import uuid
from contextlib import nullcontext
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from test_candidate_finish_runtime import database_dump, json_write
from test_candidate_save_runtime import NOW
from test_monitor_save_runtime import seed_monitor, source_evidence

from image_monitor import candidate_finish as finish_core
from image_monitor import candidate_finish_runtime as runtime
from image_monitor.artifact_files import finalize_saved_image
from image_monitor.candidate_save_selection import (
    MANIFEST_NAME,
    MONITOR_MANIFEST_NAME,
    select_candidate_save,
    write_selection_control,
)
from image_monitor.monitor_controller import MONITOR_SCOPE
from image_monitor.native_state import PendingSave
from image_monitor.native_ui import NativeUIError
from image_monitor.post_pipeline import enqueue_candidate_snapshot
from image_monitor.queue import QueueError, QueueStore
from image_monitor.validation import verify_image
from image_monitor.watch_lock import watch_run_lock
from image_monitor.watch_runtime import DEFAULT_SCOPE
from image_monitor.watch_store import WatchScope


@pytest.fixture
def completed_monitor(monkeypatch):
    # Production Windows path limits remain enabled; use a deliberately short root.
    with tempfile.TemporaryDirectory(prefix="ims-") as directory:
        root = Path(directory).resolve()
        watch_root, work_root = root / "watch", root / "native"
        observations = seed_monitor(watch_root)
        with QueueStore(watch_root / "watch.sqlite") as queue:
            permit = select_candidate_save(queue, MONITOR_SCOPE, watch_root / MONITOR_MANIFEST_NAME)
        assert permit is not None and permit.image_count == 1
        base = work_root / "session-1"
        run_directory = base / "runs" / uuid.uuid4().hex
        (run_directory / "browser-profile").mkdir(parents=True)
        save_root = base / "images"
        save_root.mkdir()
        observed = deepcopy(observations[permit.post_url])
        observed["observed_at"] = (NOW + timedelta(seconds=5)).isoformat()
        with QueueStore(base / "queue.sqlite") as queue:
            queued = enqueue_candidate_snapshot(queue, observed, permit=permit)
            job_ids = [job["job_id"] for job in queued["jobs"]]
            job = queue.claim_next("local-fixture", NOW + timedelta(seconds=10), job_ids=job_ids)
            assert job is not None
            source = job["source"]
            image = source["image"]
            staging = save_root / "_staging" / job["job_id"] / uuid.uuid4().hex / "native-image.png"
            staging.parent.mkdir(parents=True)
            Image.new("RGB", (image["natural_width"], image["natural_height"]), "#315781").save(
                staging, format="PNG"
            )
            verified = verify_image(staging, writer_finished=True).to_dict()
            queue.transition(job["job_id"], job["lease_token"], "saving")
            queue.transition(job["job_id"], job["lease_token"], "verifying")
            artifact = finalize_saved_image(
                queue,
                job["job_id"],
                job["lease_token"],
                observation_id=source["observation_id"],
                save_root=save_root,
                staging_file=staging,
                verification=verified,
                completion_evidence={
                    "state": "COMPLETE",
                    "destination_confirmed": True,
                    "source_confirmed": True,
                    "destination": str(staging),
                    "source_url": image["display_url"],
                    "exclusive_sha256": verified["sha256"],
                },
                browser_suggested_filename="browser-name.png",
                saved_at=NOW + timedelta(seconds=15),
            )
        marker = root / "shared-pending.json"
        state = PendingSave(marker)
        pending = state.begin(run_directory)
        state.update_browser(pending, 424242, 12345.5)
        report_path = run_directory / "report.json"
        previous = {
            "schema_version": 2,
            "mode": "reviewed_candidate_native_context_menu",
            "status": "manual_review",
            "browser": "chrome",
            "last_stage": "browser_shutdown",
            "error_type": "NativeUIError",
            "reason": "Dedicated browser did not close; inspect it manually",
            "browser_closed": False,
            "shared_pending_retained": True,
            "job_counts": {"observed": 1, "completed": 1, "unresolved": 0},
            "saved_files": [
                {"saved_filename": Path(artifact["final_path"]).name, **artifact["verification"]}
            ],
            "output_directory": str(save_root),
            "report_path": str(report_path),
        }
        json_write(report_path, previous)
        old_output = root / "earlier-native"
        old_output.mkdir()
        old_image = old_output / "001.png"
        old_image.write_bytes(b"Preserve the unrelated earlier saved image")
        monkeypatch.setattr(runtime, "require_windows", lambda: None)
        monkeypatch.setattr(runtime, "NativeSaveLock", nullcontext)
        monkeypatch.setattr(runtime, "session_id", lambda: 1)
        monkeypatch.setattr(runtime, "shared_state_path", lambda: marker)
        if sys.platform != "win32":
            monkeypatch.setattr(
                finish_core,
                "exclusive_digest",
                lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            )
        yield SimpleNamespace(
            root=root,
            watch_root=watch_root,
            work_root=work_root,
            base=base,
            permit=permit,
            marker=marker,
            state=state,
            pending=pending,
            artifact=artifact,
            report_path=report_path,
            old_image=old_image,
        )


def preserve(value):
    paths = [
        Path(value.artifact["final_path"]),
        Path(value.artifact["metadata_path"]),
        value.report_path,
        value.old_image,
        value.watch_root / MANIFEST_NAME,
        value.watch_root / MONITOR_MANIFEST_NAME,
    ]
    return {
        "files": {path: path.read_bytes() for path in paths},
        "source": source_evidence(value.watch_root),
        "native": database_dump(value.base / "queue.sqlite"),
    }


def assert_preserved(value, before):
    assert all(path.read_bytes() == data for path, data in before["files"].items())
    assert source_evidence(value.watch_root) == before["source"]
    assert database_dump(value.base / "queue.sqlite") == before["native"]


def never_close(_pending):
    pytest.fail("No new browser connection should be needed")


def finish(value, **options):
    options.setdefault("scope", MONITOR_SCOPE)
    options.setdefault("is_running", lambda _pending: False)
    options.setdefault("close_owned", never_close)
    return runtime.run_candidate_finish_trial(value.watch_root, value.work_root, **options)


def test_monitor_finish_reverifies_one_image_and_clears_only_its_completed_marker(
    completed_monitor,
):
    before = preserve(completed_monitor)
    report = finish(completed_monitor)
    assert report["status"] == "candidate_finish_completed", report
    assert report["browser_closed"] is True
    assert report["shared_pending_retained"] is False
    assert report["files_verified"] == 1
    assert report["job_counts"] == {"observed": 1, "completed": 1, "unresolved": 0}
    assert not completed_monitor.marker.exists()
    assert_preserved(completed_monitor, before)


def test_default_finish_does_not_apply_legacy_selection_to_monitor_completed_save(
    completed_monitor,
):
    before = preserve(completed_monitor)
    pending = completed_monitor.marker.read_bytes()
    report = finish(completed_monitor, scope=DEFAULT_SCOPE)
    assert report["status"] == "candidate_finish_manual_review", report
    assert report["shared_pending_retained"] is True
    assert completed_monitor.marker.read_bytes() == pending
    assert_preserved(completed_monitor, before)


def test_monitor_finish_requires_its_own_selection_without_falling_back(completed_monitor):
    path = completed_monitor.watch_root / MONITOR_MANIFEST_NAME
    path.unlink()
    marker = completed_monitor.marker.read_bytes()
    legacy = (completed_monitor.watch_root / MANIFEST_NAME).read_bytes()
    report = finish(completed_monitor)
    assert report["status"] == "candidate_finish_manual_review"
    assert not path.exists()
    assert (completed_monitor.watch_root / MANIFEST_NAME).read_bytes() == legacy
    assert completed_monitor.marker.read_bytes() == marker


def test_monitor_finish_waits_for_independent_absence_after_owned_close(completed_monitor):
    before = preserve(completed_monitor)
    active = True
    events = []

    def is_running(pending):
        assert pending == completed_monitor.pending
        events.append(("running", active))
        return active

    def close_owned(pending):
        nonlocal active
        assert pending == completed_monitor.pending
        assert completed_monitor.marker.exists()
        events.append(("close", True))
        active = False

    report = finish(completed_monitor, is_running=is_running, close_owned=close_owned)
    assert report["status"] == "candidate_finish_completed", report
    assert events == [("running", True), ("close", True), ("running", False)]
    assert not completed_monitor.marker.exists()
    assert_preserved(completed_monitor, before)


def test_monitor_access_block_does_not_prevent_offline_completed_file_checks(completed_monitor):
    write_selection_control(completed_monitor.watch_root / MONITOR_MANIFEST_NAME, {"blocked": True})
    before = preserve(completed_monitor)
    assert finish(completed_monitor)["status"] == "candidate_finish_completed"
    assert_preserved(completed_monitor, before)


@pytest.mark.parametrize("kind", ["final_path", "metadata_path"])
def test_changed_monitor_file_is_not_rewritten_or_used_to_clear_pending(completed_monitor, kind):
    Path(completed_monitor.artifact[kind]).write_bytes(b"Preserve changed fixture for review")
    before = preserve(completed_monitor)
    pending = completed_monitor.marker.read_bytes()
    report = finish(completed_monitor)
    assert report["status"] == "candidate_finish_manual_review"
    assert report["files_verified"] == 0
    assert completed_monitor.marker.read_bytes() == pending
    assert_preserved(completed_monitor, before)


def test_monitor_finish_uses_the_common_scan_lease(completed_monitor):
    pending = completed_monitor.marker.read_bytes()
    with watch_run_lock(completed_monitor.watch_root / "watch.sqlite", DEFAULT_SCOPE):
        report = finish(completed_monitor)
    assert report["status"] == "candidate_finish_busy"
    assert completed_monitor.marker.read_bytes() == pending


def test_monitor_finish_does_not_create_missing_native_database(completed_monitor):
    path = completed_monitor.base / "queue.sqlite"
    path.unlink()
    marker = completed_monitor.marker.read_bytes()
    report = finish(completed_monitor)
    assert report["status"] == "candidate_finish_manual_review"
    assert not path.exists()
    assert completed_monitor.marker.read_bytes() == marker


def test_monitor_finish_with_no_marker_is_idempotent_and_does_not_probe_browser(completed_monitor):
    assert finish(completed_monitor)["status"] == "candidate_finish_completed"
    before = preserve(completed_monitor)

    def never_probe(_pending):
        pytest.fail("No pending marker must not start process or browser checks")

    report = finish(completed_monitor, is_running=never_probe)
    assert report["status"] == "candidate_finish_no_pending"
    assert_preserved(completed_monitor, before)


@pytest.mark.parametrize(
    "scope",
    [None, "monitor", WatchScope("other", "normal", "comic_new6", "ai", "search_subject_memo")],
)
def test_unreviewed_finish_scope_is_rejected_before_creating_any_files(
    tmp_path, monkeypatch, scope
):
    monkeypatch.setattr(runtime, "require_windows", lambda: None)
    with pytest.raises(QueueError):
        runtime.run_candidate_finish_trial(tmp_path / "watch", tmp_path / "native", scope=scope)
    assert list(tmp_path.iterdir()) == []


def test_monitor_finish_platform_guard_still_precedes_every_file_change(tmp_path, monkeypatch):
    def unsupported():
        raise NativeUIError("Windows required")

    monkeypatch.setattr(runtime, "require_windows", unsupported)
    with pytest.raises(NativeUIError, match="Windows"):
        runtime.run_candidate_finish_trial(
            tmp_path / "watch", tmp_path / "native", scope=MONITOR_SCOPE
        )
    assert list(tmp_path.iterdir()) == []
