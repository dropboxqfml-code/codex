"""Reconcile a finished native pilot using only its existing local evidence."""

import hashlib
import json
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
from test_candidate_save_runtime import NOW, evidence, seed

from image_monitor import candidate_finish as finish_core
from image_monitor import candidate_finish_runtime as runtime
from image_monitor.artifact_files import finalize_saved_image
from image_monitor.candidate_save_selection import (
    select_candidate_save,
    write_selection_control,
)
from image_monitor.native_state import PendingSave
from image_monitor.native_ui import NativeUIError
from image_monitor.post_pipeline import enqueue_candidate_snapshot
from image_monitor.queue import QueueStore
from image_monitor.validation import verify_image
from image_monitor.watch_lock import watch_run_lock
from image_monitor.watch_runtime import DEFAULT_SCOPE


def json_write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def database_dump(path):
    with QueueStore(path, read_only=True) as store:
        return tuple(store.connection.iterdump())


@pytest.fixture
def completed(monkeypatch):
    # Keep the real production Windows path budget in the finalizer tests.
    with tempfile.TemporaryDirectory(prefix="imf-") as directory:
        root = Path(directory).resolve()
        watch_root, work_root = root / "watch", root / "native"
        snapshots = seed(watch_root)
        with QueueStore(watch_root / "watch.sqlite") as watch:
            permit = select_candidate_save(
                watch, DEFAULT_SCOPE, watch_root / "candidate-save-selection.json"
            )
        assert permit is not None
        base = work_root / "session-1"
        base.mkdir(parents=True)
        run_directory = base / "runs" / uuid.uuid4().hex
        run_directory.mkdir(parents=True)
        profile = run_directory / "browser-profile"
        profile.mkdir()
        save_root = base / "images"
        save_root.mkdir()
        snapshot = deepcopy(snapshots[permit.post_url])
        snapshot["observed_at"] = (NOW + timedelta(seconds=5)).isoformat()
        artifacts = []
        with QueueStore(base / "queue.sqlite") as queue:
            queued = enqueue_candidate_snapshot(queue, snapshot, permit=permit)
            job_ids = [job["job_id"] for job in queued["jobs"]]
            for index in range(2):
                job = queue.claim_next(
                    "local-fixture", NOW + timedelta(seconds=10), job_ids=job_ids
                )
                assert job is not None
                source = job["source"]
                image = source["image"]
                staging = (
                    save_root / "_staging" / job["job_id"] / uuid.uuid4().hex / "native-image.png"
                )
                staging.parent.mkdir(parents=True)
                Image.new(
                    "RGB", (image["natural_width"], image["natural_height"]), (80 + index, 20, 60)
                ).save(staging, format="PNG")
                verified = verify_image(staging, writer_finished=True).to_dict()
                queue.transition(job["job_id"], job["lease_token"], "saving")
                queue.transition(job["job_id"], job["lease_token"], "verifying")
                artifacts.append(
                    finalize_saved_image(
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
                        saved_at=NOW + timedelta(seconds=15 + index),
                    )
                )
        state_path = root / "shared-pending.json"
        state = PendingSave(state_path)
        pending = state.begin(run_directory)
        state.update_browser(pending, 424242, 12345.5)
        report_path = run_directory / "report.json"
        report = {
            "schema_version": 2,
            "mode": "reviewed_candidate_native_context_menu",
            "status": "manual_review",
            "browser": "chrome",
            "browser_version": "invented-fixture-browser",
            "last_stage": "browser_shutdown",
            "error_type": "NativeUIError",
            "reason": "Dedicated browser did not close; inspect it manually",
            "browser_closed": False,
            "shared_pending_retained": True,
            "job_counts": {"observed": 2, "completed": 2, "unresolved": 0},
            "saved_files": [
                {"saved_filename": Path(item["final_path"]).name, **item["verification"]}
                for item in artifacts
            ],
            "output_directory": str(save_root),
            "report_path": str(report_path),
        }
        json_write(report_path, report)
        monkeypatch.setattr(runtime, "require_windows", lambda: None)
        monkeypatch.setattr(runtime, "NativeSaveLock", nullcontext)
        monkeypatch.setattr(runtime, "session_id", lambda: 1)
        monkeypatch.setattr(runtime, "shared_state_path", lambda: state_path)
        if sys.platform != "win32":
            monkeypatch.setattr(
                finish_core,
                "exclusive_digest",
                lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            )
        values = SimpleNamespace(
            root=root,
            watch_root=watch_root,
            work_root=work_root,
            base=base,
            save_root=save_root,
            permit=permit,
            report=report,
            report_path=report_path,
            state_path=state_path,
            pending=pending,
            state=state,
            artifacts=artifacts,
            manifest=watch_root / "candidate-save-selection.json",
        )
        yield values


def preserve(values):
    files = {
        Path(item["final_path"]): Path(item["final_path"]).read_bytes() for item in values.artifacts
    }
    files.update(
        {
            Path(item["metadata_path"]): Path(item["metadata_path"]).read_bytes()
            for item in values.artifacts
        }
    )
    return {
        "files": files,
        "watch": evidence(values.watch_root),
        "native": database_dump(values.base / "queue.sqlite"),
        "worker_report": values.report_path.read_bytes(),
        "selection": values.manifest.read_bytes(),
    }


def assert_preserved(values, before):
    assert all(path.read_bytes() == data for path, data in before["files"].items())
    assert evidence(values.watch_root) == before["watch"]
    assert database_dump(values.base / "queue.sqlite") == before["native"]
    assert values.report_path.read_bytes() == before["worker_report"]
    assert values.manifest.read_bytes() == before["selection"]


def finish(values, **options):
    def no_close_for_dead_profile(_pending):
        pytest.fail("A proven dead profile must not start a browser connection")

    options.setdefault("close_owned", no_close_for_dead_profile)
    return runtime.run_candidate_finish_trial(
        values.watch_root, values.work_root, is_running=lambda _pending: False, **options
    )


def test_completed_local_files_are_verified_and_only_pending_marker_is_cleared(completed):
    before = preserve(completed)
    report = finish(completed)

    assert report["status"] == "candidate_finish_completed", report
    assert report["browser_closed"] is True
    assert report["shared_pending_retained"] is False
    assert report["files_preserved"] is True
    assert report["metadata_preserved"] is True
    assert report["job_counts"] == {"observed": 2, "completed": 2, "unresolved": 0}
    assert len(report["saved_files"]) == 2
    assert not completed.state_path.exists()
    assert_preserved(completed, before)
    assert json.loads(Path(report["report_path"]).read_text()) == report


def test_repeat_with_no_pending_marker_never_opens_browser_or_changes_saved_records(completed):
    assert finish(completed)["status"] == "candidate_finish_completed"
    before = preserve(completed)

    def no_process_check(_pending):
        pytest.fail("No pending marker requires no process check")

    report = runtime.run_candidate_finish_trial(
        completed.watch_root, completed.work_root, is_running=no_process_check
    )
    assert report["status"] == "candidate_finish_no_pending"
    assert_preserved(completed, before)


def test_active_previous_profile_preserves_marker_and_files(completed):
    before = preserve(completed)
    pending_bytes = completed.state_path.read_bytes()
    seen = []

    def active(pending):
        seen.append(pending)
        return True

    report = runtime.run_candidate_finish_trial(
        completed.watch_root,
        completed.work_root,
        is_running=active,
        close_owned=lambda _pending: False,
    )
    assert report["status"] == "candidate_finish_manual_review", report
    assert report["browser_closed"] is False
    assert report["shared_pending_retained"] is True
    assert seen and all(pending == completed.pending for pending in seen)
    assert completed.state_path.read_bytes() == pending_bytes
    assert_preserved(completed, before)


def test_owned_close_is_followed_by_independent_profile_absence_before_marker_cleanup(completed):
    before = preserve(completed)
    active = True
    events = []

    def is_running(pending):
        assert pending == completed.pending
        events.append(("running", active))
        return active

    def close_owned(pending):
        nonlocal active
        assert pending == completed.pending
        assert completed.state_path.exists()
        events.append(("close", True))
        active = False
        return True

    report = runtime.run_candidate_finish_trial(
        completed.watch_root,
        completed.work_root,
        is_running=is_running,
        close_owned=close_owned,
    )
    assert report["status"] == "candidate_finish_completed", report
    assert events == [("running", True), ("close", True), ("running", False)]
    assert not completed.state_path.exists()
    assert_preserved(completed, before)


def test_ownership_refusal_cannot_close_or_clear_an_active_profile(completed):
    pending = completed.state_path.read_bytes()
    before = preserve(completed)

    def refusal(_pending):
        raise NativeUIError("Invented private foreign process details")

    report = runtime.run_candidate_finish_trial(
        completed.watch_root,
        completed.work_root,
        is_running=lambda _pending: True,
        close_owned=refusal,
    )
    assert report["status"] in {"candidate_finish_manual_review", "candidate_finish_failed"}
    assert completed.state_path.read_bytes() == pending
    assert_preserved(completed, before)


@pytest.mark.parametrize("kind", ["image", "metadata"])
def test_file_changed_during_owned_close_is_reverified_before_pending_cleanup(completed, kind):
    before = preserve(completed)
    pending = completed.state_path.read_bytes()
    path = Path(completed.artifacts[0]["final_path" if kind == "image" else "metadata_path"])
    changed = b"Preserve the file changed while the previous browser was closing"
    active = True
    closes = []

    def close_owned(value):
        nonlocal active
        assert value == completed.pending
        closes.append(value)
        path.write_bytes(changed)
        active = False
        return True

    report = runtime.run_candidate_finish_trial(
        completed.watch_root,
        completed.work_root,
        is_running=lambda _pending: active,
        close_owned=close_owned,
    )
    assert closes == [completed.pending]
    assert report["status"] in {"candidate_finish_failed", "candidate_finish_manual_review"}
    assert report["files_verified"] == 0
    assert report["saved_files"] == []
    assert completed.state_path.read_bytes() == pending
    assert path.read_bytes() == changed
    for other, data in before["files"].items():
        if other != path:
            assert other.read_bytes() == data
    assert evidence(completed.watch_root) == before["watch"]
    assert database_dump(completed.base / "queue.sqlite") == before["native"]
    assert completed.report_path.read_bytes() == before["worker_report"]
    assert completed.manifest.read_bytes() == before["selection"]


def test_unreadable_previous_process_state_never_claims_browser_is_closed(completed):
    pending = completed.state_path.read_bytes()

    def unknown(_pending):
        raise NativeUIError("Invented private process details")

    report = runtime.run_candidate_finish_trial(
        completed.watch_root, completed.work_root, is_running=unknown
    )
    assert report["status"] in {"candidate_finish_failed", "candidate_finish_manual_review"}
    assert report.get("browser_closed") is not True
    assert completed.state_path.read_bytes() == pending
    assert "Invented private" not in json.dumps(runtime.share_candidate_finish_report(report))


@pytest.mark.parametrize(
    "change",
    [
        {"last_stage": "native_saving"},
        {"job_counts": {"observed": 2, "completed": 1, "unresolved": 1}},
        {"active_attempt": {"phase": "input_armed"}},
        {"mode": "single_post_native_context_menu"},
        {"reason": "Unrelated failure"},
        {"output_directory": "foreign/images"},
    ],
)
def test_report_does_not_authorize_finishing_another_or_incomplete_save(completed, change):
    json_write(completed.report_path, completed.report | change)
    before = preserve(completed)
    pending = completed.state_path.read_bytes()
    report = finish(completed)
    assert report["status"] in {"candidate_finish_failed", "candidate_finish_manual_review"}
    assert completed.state_path.read_bytes() == pending
    assert_preserved(completed, before)


@pytest.mark.parametrize("kind", ["image", "metadata"])
def test_corrupt_completed_file_or_metadata_never_clears_pending_or_rewrites_it(completed, kind):
    path = Path(completed.artifacts[0]["final_path" if kind == "image" else "metadata_path"])
    path.write_bytes(b"Preserve this deliberately changed fixture")
    before = preserve(completed)
    pending = completed.state_path.read_bytes()
    report = finish(completed)
    assert report["status"] in {"candidate_finish_failed", "candidate_finish_manual_review"}
    assert completed.state_path.read_bytes() == pending
    assert_preserved(completed, before)


def test_existing_service_block_does_not_prevent_offline_file_verification(completed):
    write_selection_control(completed.manifest, {"blocked": True})
    before = preserve(completed)
    report = finish(completed)
    assert report["status"] == "candidate_finish_completed", report
    assert_preserved(completed, before)


def test_foreign_pending_root_never_reads_or_clears_that_save(completed):
    foreign = dict(completed.pending) | {"run_directory": str(completed.root / "foreign-run")}
    json_write(completed.state_path, foreign)
    pending = completed.state_path.read_bytes()
    report = finish(completed)
    assert report["status"] in {"candidate_finish_failed", "candidate_finish_manual_review"}
    assert completed.state_path.read_bytes() == pending


def test_missing_previous_profile_is_not_used_as_proof_to_clear_pending(completed):
    (Path(completed.pending["browser_profile"])).rmdir()
    pending = completed.state_path.read_bytes()
    report = finish(completed)
    assert report["status"] in {"candidate_finish_failed", "candidate_finish_manual_review"}
    assert completed.state_path.read_bytes() == pending


def test_changed_marker_during_verification_does_not_clear_new_state(completed, monkeypatch):
    original = runtime.finish_completed_candidate
    # Same run ID defeats PendingSave's ordinary ID-only guard; the finish
    # controller must retain all fields of the evidence it actually verified.
    changed = dict(completed.pending) | {"browser_pid": completed.pending["browser_pid"] + 1}

    def change(*args, **kwargs):
        result = original(*args, **kwargs)
        json_write(completed.state_path, changed)
        return result

    monkeypatch.setattr(runtime, "finish_completed_candidate", change)
    report = finish(completed)
    assert report["status"] in {"candidate_finish_failed", "candidate_finish_manual_review"}
    assert json.loads(completed.state_path.read_text()) == changed


@pytest.mark.parametrize("database", ["watch", "native"])
def test_missing_existing_database_is_not_recreated_or_used_to_clear_pending(completed, database):
    path = (
        completed.watch_root / "watch.sqlite"
        if database == "watch"
        else completed.base / "queue.sqlite"
    )
    path.unlink()
    pending = completed.state_path.read_bytes()
    image_bytes = {
        Path(item["final_path"]): Path(item["final_path"]).read_bytes()
        for item in completed.artifacts
    }
    report = finish(completed)
    assert report["status"] in {"candidate_finish_failed", "candidate_finish_manual_review"}
    assert not path.exists()
    assert completed.state_path.read_bytes() == pending
    assert all(file.read_bytes() == contents for file, contents in image_bytes.items())


def test_corrupt_file_prevents_any_owned_browser_close_attempt(completed):
    Path(completed.artifacts[0]["final_path"]).write_bytes(b"Changed file must remain for review")
    pending = completed.state_path.read_bytes()

    def no_close(_pending):
        pytest.fail("Unverified saved files cannot authorize closing the old browser")

    report = runtime.run_candidate_finish_trial(
        completed.watch_root,
        completed.work_root,
        is_running=lambda _pending: True,
        close_owned=no_close,
    )
    assert report["status"] in {"candidate_finish_failed", "candidate_finish_manual_review"}
    assert completed.state_path.read_bytes() == pending


def test_changed_frozen_source_keeps_pending_and_all_existing_artifacts(completed):
    with QueueStore(completed.base / "queue.sqlite") as store:
        artifact = store.list_artifacts()[0]
        observation = store.get_observation(artifact["observation_id"])
        observation["snapshot"]["title"] = "Invented changed frozen title"
        store.connection.execute(
            "UPDATE post_observations SET snapshot_json=? WHERE observation_id=?",
            (json.dumps(observation["snapshot"]), artifact["observation_id"]),
        )
    before = preserve(completed)
    pending = completed.state_path.read_bytes()
    report = finish(completed)
    assert report["status"] in {"candidate_finish_failed", "candidate_finish_manual_review"}
    assert completed.state_path.read_bytes() == pending
    assert_preserved(completed, before)


def test_another_scope_lease_prevents_finish_work_before_pending_read(completed):
    pending = completed.state_path.read_bytes()
    with watch_run_lock(completed.watch_root / "watch.sqlite", DEFAULT_SCOPE):
        report = finish(completed)
    assert report["status"] == "candidate_finish_busy"
    assert completed.state_path.read_bytes() == pending


def test_shared_report_keeps_saved_location_without_private_post_or_source_data(completed):
    report = finish(completed)
    assert report["status"] == "candidate_finish_completed"
    shared = runtime.share_candidate_finish_report(
        report
        | {
            "title": "Invented private title",
            "snapshot": {"url": "https://private.example/image?token=private-token"},
            "source_hash": "Invented private source hash",
        }
    )
    encoded = json.dumps(shared)
    assert shared["output_directory"] == str(completed.save_root)
    assert len(shared["saved_files"]) == 2
    for private in (
        "Invented private",
        "private.example",
        "private-token",
        "source_hash",
        "sha256",
    ):
        assert private not in encoded


def test_platform_guard_runs_before_any_directory_or_database_creation(tmp_path, monkeypatch):
    def unsupported():
        raise NativeUIError("Windows required")

    monkeypatch.setattr(runtime, "require_windows", unsupported)
    watch_root, work_root = tmp_path / "watch", tmp_path / "native"
    with pytest.raises(NativeUIError, match="Windows"):
        runtime.run_candidate_finish_trial(watch_root, work_root)
    assert not watch_root.exists()
    assert not work_root.exists()
