"""Resolve completed batch records using only existing local, owned evidence."""

import hashlib
import json
import sqlite3
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
from image_monitor import monitor_batch_finish as runtime
from image_monitor.artifact_files import finalize_saved_image
from image_monitor.candidate_save_policy import make_candidate_save_permit
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.monitor_controller import MONITOR_SCOPE
from image_monitor.monitor_save_ledger import (
    LEDGER_NAME,
    LedgerStore,
    batch_service_blocked,
    task_native_base,
)
from image_monitor.native_state import PendingSave
from image_monitor.native_ui import NativeUIError
from image_monitor.post_pipeline import enqueue_candidate_snapshot
from image_monitor.queue import QueueStore
from image_monitor.validation import verify_image
from image_monitor.watch_lock import watch_run_lock
from image_monitor.watch_runtime import DEFAULT_SCOPE
from image_monitor.watch_store import WatchStore


def ledger(value, **options):
    return LedgerStore(
        value.ledger_path,
        watch_root=value.watch_root,
        legacy_root=value.legacy_root,
        batch_root=value.batch_root,
        **options,
    )


@pytest.fixture
def completed_batch(monkeypatch):
    # Preserve the production Windows path budget with a short fixture root.
    with tempfile.TemporaryDirectory(prefix="imbf-") as directory:
        root = Path(directory).resolve()
        watch_root, legacy_root, batch_root = root / "watch", root / "legacy", root / "batch"
        seed_monitor(watch_root)
        with QueueStore(watch_root / "watch.sqlite", read_only=True) as watch:
            candidate = WatchStore(watch).list_candidates(MONITOR_SCOPE)[0]
            baseline = WatchStore(watch).get_state(MONITOR_SCOPE)["baseline"]
            detail = next(
                item
                for item in CandidateDetailStore(watch).list_details(MONITOR_SCOPE)
                if item["post_id"] == candidate["post_id"]
            )
            permit = make_candidate_save_permit(candidate, baseline, detail)
        value = SimpleNamespace(
            root=root,
            watch_root=watch_root,
            legacy_root=legacy_root,
            batch_root=batch_root,
            ledger_path=watch_root / LEDGER_NAME,
            permit=permit,
        )
        with ledger(value) as store:
            task = store.plan(candidate, detail, permit, now=NOW)
            task = store.start(task["task_id"], NOW + timedelta(seconds=1), native_session=1)
        base = task_native_base(task, batch_root, legacy_root)
        run_directory = base / "runs" / uuid.uuid4().hex
        (run_directory / "browser-profile").mkdir(parents=True)
        snapshot = deepcopy(permit.reference_snapshot)
        snapshot["observed_at"] = (NOW + timedelta(seconds=5)).isoformat()
        with QueueStore(base / "queue.sqlite") as native:
            queued = enqueue_candidate_snapshot(native, snapshot, permit=permit)
            claim = native.claim_next(
                "batch-local-fixture",
                NOW + timedelta(seconds=10),
                job_ids=[item["job_id"] for item in queued["jobs"]],
            )
            assert claim is not None
            image = claim["source"]["image"]
            staging = (
                base
                / "images"
                / "_staging"
                / claim["job_id"]
                / uuid.uuid4().hex
                / "native-image.png"
            )
            staging.parent.mkdir(parents=True)
            Image.new("RGB", (image["natural_width"], image["natural_height"]), "#315781").save(
                staging, format="PNG"
            )
            verified = verify_image(staging, writer_finished=True).to_dict()
            native.transition(claim["job_id"], claim["lease_token"], "saving")
            native.transition(claim["job_id"], claim["lease_token"], "verifying")
            artifact = finalize_saved_image(
                native,
                claim["job_id"],
                claim["lease_token"],
                observation_id=claim["source"]["observation_id"],
                save_root=base / "images",
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
                browser_suggested_filename="owned-fixture-name.png",
                saved_at=NOW + timedelta(seconds=15),
            )
        marker = root / "shared-pending.json"
        state = PendingSave(marker)
        pending = state.begin(run_directory)
        state.update_browser(pending, 424242, 12345.5)
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
            "output_directory": str(base / "images"),
            "report_path": str(run_directory / "report.json"),
        }
        json_write(run_directory / "report.json", previous)
        with ledger(value) as store:
            store.update_control(
                task["task_id"],
                {"blocked": False, "in_flight": False, "browser_identity": pending},
            )
            store.finish(
                task["task_id"],
                status="needs_review",
                result={"browser_closed": False, "shared_pending_retained": True},
                now=NOW + timedelta(seconds=30),
            )
        old_output = legacy_root / "earlier-file.png"
        old_output.parent.mkdir()
        old_output.write_bytes(b"Preserve the earlier frozen save verbatim")
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
        value.__dict__.update(
            base=base,
            task_id=task["task_id"],
            artifact=artifact,
            marker=marker,
            state=state,
            pending=pending,
            previous=previous,
            report_path=run_directory / "report.json",
            old_output=old_output,
        )
        yield value


def preserve(value):
    files = [
        Path(value.artifact["final_path"]),
        Path(value.artifact["metadata_path"]),
        value.report_path,
        value.old_output,
        value.watch_root / "candidate-save-selection.json",
    ]
    return {
        "files": {path: path.read_bytes() for path in files},
        "watch": source_evidence(value.watch_root),
        "native": database_dump(value.base / "queue.sqlite"),
    }


def assert_preserved(value, before):
    assert all(path.read_bytes() == data for path, data in before["files"].items())
    assert source_evidence(value.watch_root) == before["watch"]
    assert database_dump(value.base / "queue.sqlite") == before["native"]


def task_record(value):
    with ledger(value, read_only=True) as store:
        return store.get_task(value.task_id)


def finish(value, **options):
    options.setdefault("is_running", lambda _identity: False)
    options.setdefault("close_owned", lambda _: pytest.fail("No owned close was expected"))
    return runtime.run_monitor_batch_finish(
        value.watch_root, value.legacy_root, value.batch_root, **options
    )


def test_completed_batch_rechecks_files_and_clears_only_matching_pending(completed_batch):
    before = preserve(completed_batch)
    original_control = task_record(completed_batch)["control"]
    report = finish(completed_batch)
    assert report["status"] == "batch_finish_completed", report
    assert report["files_verified"] == report["tasks_completed"] == 1
    assert report["browser_closed"] is True and report["shared_pending_retained"] is False
    assert report["job_counts"] == {"observed": 1, "completed": 1, "unresolved": 0}
    assert not completed_batch.marker.exists()
    assert task_record(completed_batch)["status"] == "completed"
    assert task_record(completed_batch)["control"] == original_control
    assert_preserved(completed_batch, before)


def test_owned_close_requires_independent_absence_and_final_recheck(completed_batch):
    before = preserve(completed_batch)
    active = True
    events = []

    def running(identity):
        assert identity == completed_batch.pending
        events.append(("probe", active))
        return active

    def close(identity):
        nonlocal active
        assert identity == completed_batch.pending and completed_batch.marker.exists()
        events.append(("close", True))
        active = False

    report = finish(completed_batch, is_running=running, close_owned=close)
    assert report["status"] == "batch_finish_completed", report
    assert report["close_attempted"] is True
    assert events == [("probe", True), ("close", True), ("probe", False), ("probe", False)]
    assert_preserved(completed_batch, before)


def test_still_active_browser_preserves_marker_and_uncertain_task(completed_batch):
    before = preserve(completed_batch)
    pending = completed_batch.marker.read_bytes()
    report = finish(completed_batch, is_running=lambda _: True, close_owned=lambda _: None)
    assert report["status"] == "batch_finish_manual_review"
    assert report["browser_closed"] is False and report["shared_pending_retained"] is True
    assert completed_batch.marker.read_bytes() == pending
    assert task_record(completed_batch)["status"] == "needs_review"
    assert_preserved(completed_batch, before)


@pytest.mark.parametrize("kind", ["final_path", "metadata_path"])
def test_corrupt_file_is_preserved_and_never_repaired_or_cleared(completed_batch, kind):
    Path(completed_batch.artifact[kind]).write_bytes(b"Preserve changed data for manual review")
    before = preserve(completed_batch)
    pending = completed_batch.marker.read_bytes()
    report = finish(completed_batch)
    assert report["status"] == "batch_finish_manual_review" and report["files_verified"] == 0
    assert completed_batch.marker.read_bytes() == pending
    assert task_record(completed_batch)["status"] == "needs_review"
    assert_preserved(completed_batch, before)


def test_foreign_pending_is_never_probed_closed_or_cleared(completed_batch):
    foreign = dict(completed_batch.pending, run_directory=str(completed_batch.root / "foreign"))
    json_write(completed_batch.marker, foreign)
    marker = completed_batch.marker.read_bytes()
    before = preserve(completed_batch)
    report = finish(
        completed_batch,
        is_running=lambda _: pytest.fail("Foreign browser must not be probed"),
    )
    assert report["status"] == "batch_finish_manual_review"
    assert completed_batch.marker.read_bytes() == marker
    assert task_record(completed_batch)["status"] == "needs_review"
    assert_preserved(completed_batch, before)


def test_pending_requires_its_actual_shutdown_failure_report(completed_batch):
    changed = dict(completed_batch.previous, status="post_completed", browser_closed=True)
    json_write(completed_batch.report_path, changed)
    before = preserve(completed_batch)
    marker = completed_batch.marker.read_bytes()
    report = finish(completed_batch, is_running=lambda _: pytest.fail("Report was not proven"))
    assert report["status"] == "batch_finish_manual_review"
    assert completed_batch.marker.read_bytes() == marker
    assert_preserved(completed_batch, before)


@pytest.mark.parametrize("changed", ["image", "metadata", "report", "marker"])
def test_shutdown_changes_are_rechecked_before_clearing(completed_batch, changed):
    active = True

    def close(_identity):
        nonlocal active
        active = False
        if changed == "image":
            Path(completed_batch.artifact["final_path"]).write_bytes(b"changed image")
        elif changed == "metadata":
            Path(completed_batch.artifact["metadata_path"]).write_bytes(b"changed metadata")
        elif changed == "report":
            json_write(completed_batch.report_path, dict(completed_batch.previous, extra="changed"))
        else:
            json_write(
                completed_batch.marker, dict(completed_batch.pending, run_id=uuid.uuid4().hex)
            )

    report = finish(completed_batch, is_running=lambda _: active, close_owned=close)
    assert report["status"] == "batch_finish_manual_review"
    assert completed_batch.marker.exists()
    assert task_record(completed_batch)["status"] == "needs_review"


def test_no_pending_requires_recorded_absent_browser_and_completed_files(completed_batch):
    completed_batch.state.finish(completed_batch.pending)
    before = preserve(completed_batch)
    probes = []

    def absent(identity):
        probes.append(identity)
        return False

    report = finish(completed_batch, is_running=absent)
    assert report["status"] == "batch_finish_completed", report
    assert report["close_attempted"] is False and report["shared_pending_retained"] is False
    assert probes == [completed_batch.pending, completed_batch.pending]
    assert task_record(completed_batch)["status"] == "completed"
    assert_preserved(completed_batch, before)


def test_missing_marker_alone_does_not_prove_an_attempt_finished(completed_batch):
    completed_batch.state.finish(completed_batch.pending)
    with ledger(completed_batch) as store:
        store.update_control(completed_batch.task_id, {"blocked": False, "in_flight": False})
    report = finish(completed_batch, is_running=lambda _: pytest.fail("No recorded identity"))
    assert report["status"] == "batch_finish_manual_review"
    assert task_record(completed_batch)["status"] == "needs_review"
    assert not completed_batch.marker.exists()


@pytest.mark.parametrize("running", [True, None])
def test_missing_marker_does_not_allow_live_or_unknown_recorded_browser(completed_batch, running):
    completed_batch.state.finish(completed_batch.pending)
    before = preserve(completed_batch)
    report = finish(completed_batch, is_running=lambda _: running)
    assert report["status"] == "batch_finish_manual_review"
    assert task_record(completed_batch)["status"] == "needs_review"
    assert_preserved(completed_batch, before)


def test_recorded_browser_identity_must_match_frozen_output_root(completed_batch):
    completed_batch.state.finish(completed_batch.pending)
    with ledger(completed_batch) as store:
        store.update_control(
            completed_batch.task_id,
            {
                "blocked": False,
                "browser_identity": dict(
                    completed_batch.pending, browser_profile=str(completed_batch.root / "foreign")
                ),
            },
        )
    report = finish(completed_batch, is_running=lambda _: pytest.fail("Foreign identity"))
    assert report["status"] == "batch_finish_manual_review"
    assert task_record(completed_batch)["status"] == "needs_review"


def test_no_pending_recheck_preserves_a_new_marker_and_reports_it_truthfully(completed_batch):
    completed_batch.state.finish(completed_batch.pending)
    probes = 0

    def absent(_identity):
        nonlocal probes
        probes += 1
        if probes == 2:
            json_write(completed_batch.marker, completed_batch.pending)
        return False

    report = finish(completed_batch, is_running=absent)
    assert report["status"] == "batch_finish_manual_review"
    assert report["shared_pending_retained"] is True
    assert completed_batch.state.read() == completed_batch.pending
    assert task_record(completed_batch)["status"] == "needs_review"


def test_profile_becoming_active_after_verification_is_reported_and_not_cleared(completed_batch):
    probes = iter((False, True))
    marker = completed_batch.marker.read_bytes()
    report = finish(completed_batch, is_running=lambda _: next(probes))
    assert report["status"] == "batch_finish_manual_review"
    assert report["browser_closed"] is False
    assert completed_batch.marker.read_bytes() == marker
    assert task_record(completed_batch)["status"] == "needs_review"


def test_completed_reconciliation_does_not_clear_network_block_or_uncertain_inflight(
    completed_batch,
):
    with ledger(completed_batch) as store:
        control = store.get_task(completed_batch.task_id)["control"]
        control.update(blocked=True, in_flight=True)
        store.update_control(completed_batch.task_id, control)
    assert finish(completed_batch)["status"] == "batch_finish_completed"
    assert task_record(completed_batch)["control"] == control
    assert batch_service_blocked(completed_batch.watch_root / "watch.sqlite") is True


def test_common_watch_lease_prevents_overlapping_batch_finish(completed_batch):
    marker = completed_batch.marker.read_bytes()
    with watch_run_lock(completed_batch.watch_root / "watch.sqlite", DEFAULT_SCOPE):
        report = finish(completed_batch)
    assert report["status"] == "batch_finish_busy"
    assert completed_batch.marker.read_bytes() == marker
    assert task_record(completed_batch)["status"] == "needs_review"


@pytest.mark.parametrize("marker_present", [True, False])
def test_other_session_is_refused_before_any_marker_or_browser_probe(
    completed_batch, monkeypatch, marker_present
):
    if not marker_present:
        completed_batch.state.finish(completed_batch.pending)
    old_marker = completed_batch.marker.read_bytes() if marker_present else None
    current_marker = completed_batch.root / "different-session-marker.json"
    current_marker.write_bytes(b"Preserve this session's independent marker")
    before = preserve(completed_batch)
    monkeypatch.setattr(runtime, "session_id", lambda: 2)
    monkeypatch.setattr(runtime, "shared_state_path", lambda: current_marker)
    monkeypatch.setattr(runtime, "PendingSave", lambda _: pytest.fail("Cross-session marker probe"))
    report = finish(
        completed_batch,
        is_running=lambda _: pytest.fail("Cross-session browser probe"),
        close_owned=lambda _: pytest.fail("Cross-session browser close"),
    )
    assert report["status"] == "batch_finish_manual_review"
    assert report["shared_pending_retained"] is None
    assert current_marker.read_bytes() == b"Preserve this session's independent marker"
    if marker_present:
        assert completed_batch.marker.read_bytes() == old_marker
    else:
        assert not completed_batch.marker.exists()
    assert task_record(completed_batch)["status"] == "needs_review"
    assert_preserved(completed_batch, before)


def test_missing_native_database_is_not_recreated(completed_batch):
    path = completed_batch.base / "queue.sqlite"
    path.unlink()
    marker = completed_batch.marker.read_bytes()
    report = finish(completed_batch)
    assert report["status"] == "batch_finish_manual_review" and not path.exists()
    assert completed_batch.marker.read_bytes() == marker


def test_discovery_database_with_image_work_is_not_treated_as_separate_source(completed_batch):
    snapshot = deepcopy(completed_batch.permit.reference_snapshot)
    snapshot["observed_at"] = (NOW + timedelta(seconds=5)).isoformat()
    with QueueStore(completed_batch.watch_root / "watch.sqlite") as watch:
        enqueue_candidate_snapshot(watch, snapshot, permit=completed_batch.permit)
    marker = completed_batch.marker.read_bytes()
    before = database_dump(completed_batch.watch_root / "watch.sqlite")
    report = finish(completed_batch)
    assert report["status"] == "batch_finish_manual_review"
    assert completed_batch.marker.read_bytes() == marker
    assert database_dump(completed_batch.watch_root / "watch.sqlite") == before
    assert task_record(completed_batch)["status"] == "needs_review"


def test_finished_task_is_an_inert_second_finish_without_browser_probe(completed_batch):
    assert finish(completed_batch)["status"] == "batch_finish_completed"
    before = preserve(completed_batch)
    with sqlite3.connect(completed_batch.ledger_path) as connection:
        ledger_before = tuple(connection.iterdump())
    report = finish(completed_batch, is_running=lambda _: pytest.fail("No unfinished attempt"))
    assert report["status"] == "batch_finish_no_pending"
    with sqlite3.connect(completed_batch.ledger_path) as connection:
        assert tuple(connection.iterdump()) == ledger_before
    assert_preserved(completed_batch, before)


def test_missing_ledger_does_not_create_registry_or_native_queue(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "require_windows", lambda: None)
    monkeypatch.setattr(runtime, "NativeSaveLock", nullcontext)
    monkeypatch.setattr(runtime, "shared_state_path", lambda: tmp_path / "absent-marker.json")
    report = runtime.run_monitor_batch_finish(
        tmp_path / "watch", tmp_path / "legacy", tmp_path / "batch"
    )
    assert report["status"] == "batch_finish_no_pending"
    assert not (tmp_path / "watch").exists()
    assert not list(tmp_path.rglob("queue.sqlite"))
    assert not list(tmp_path.rglob(LEDGER_NAME))


def test_ledger_removed_before_open_is_not_recreated(completed_batch, monkeypatch):
    original = runtime.LedgerStore

    def removed(*args, **kwargs):
        completed_batch.ledger_path.unlink()
        return original(*args, **kwargs)

    monkeypatch.setattr(runtime, "LedgerStore", removed)
    marker = completed_batch.marker.read_bytes()
    report = finish(completed_batch)
    assert report["status"] == "batch_finish_manual_review"
    assert not completed_batch.ledger_path.exists()
    assert completed_batch.marker.read_bytes() == marker


def test_shared_report_omits_private_paths_identities_hashes_and_unbounded_files(completed_batch):
    report = finish(completed_batch)
    report.update(
        task_id=completed_batch.task_id,
        private_identity=completed_batch.pending,
        permit_fingerprint=completed_batch.permit.fingerprint,
    )
    report["saved_files"] *= 4
    report["saved_files"][0]["path"] = str(completed_batch.base)
    report["saved_files"][0]["sha256"] = "private-hash"
    public = runtime.share_batch_finish_report(report)
    text = json.dumps(public)
    assert len(public["saved_files"]) == 2
    for private in (
        str(completed_batch.root),
        completed_batch.task_id,
        completed_batch.permit.fingerprint,
        "browser_profile",
        "private-hash",
        "report_path",
    ):
        assert private not in text


def test_platform_guard_precedes_all_new_finish_files(tmp_path, monkeypatch):
    def unsupported():
        raise NativeUIError("Windows required")

    monkeypatch.setattr(runtime, "require_windows", unsupported)
    with pytest.raises(NativeUIError, match="Windows"):
        runtime.run_monitor_batch_finish(
            tmp_path / "watch", tmp_path / "legacy", tmp_path / "batch"
        )
    assert list(tmp_path.iterdir()) == []
