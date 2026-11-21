"""Only the original never-attempted image queue can consume one setup retry."""

import json
import uuid

import pytest
from test_monitor_batch_runtime import data as data
from test_monitor_batch_runtime import ledger

from image_monitor import monitor_batch_runtime as batch
from image_monitor import monitor_setup_retry as retry
from image_monitor.native_state import PendingSave
from image_monitor.native_ui import NativeUIError
from image_monitor.post_pipeline import enqueue_candidate_snapshot
from image_monitor.queue import QueueError, QueueStore


@pytest.fixture
def evidence(data, monkeypatch, request):
    foreground = getattr(request, "param", "completion") == "foreground"
    monkeypatch.setattr(retry, "shared_state_path", lambda: data.marker)
    monkeypatch.setattr(retry, "session_id", lambda: 1)
    monkeypatch.setattr(retry, "browser_still_running", lambda _: False)
    with QueueStore(data.watch / "watch.sqlite", read_only=True) as watch:
        detail = batch._details(watch)[0]
        candidate, permit = batch._eligible_permit(watch, detail)
    with ledger(data, readonly=False) as store:
        clock = data.clock
        task = store.plan(candidate, detail, permit, now=clock.now())
        task = store.start(task["task_id"], clock.now(), native_session=1)
        base = batch.task_native_base(task, data.batch, data.legacy)
        run = base / "runs" / uuid.uuid4().hex
        (run / "browser-profile").mkdir(parents=True)
        images = base / "images"
        images.mkdir()
        with QueueStore(base / "queue.sqlite") as native:
            if not foreground:
                enqueue_candidate_snapshot(native, permit.reference_snapshot, permit=permit)
        state = PendingSave(data.marker)
        identity = state.begin(run)
        state.update_browser(identity, 123, 456.0)
        store.update_control(
            task["task_id"],
            {
                "blocked": False,
                "in_flight": False,
                "http_status": 200,
                "browser_identity": identity,
            },
        )
        state.finish(identity)
        task = store.finish(
            task["task_id"],
            status="needs_review",
            now=clock.now(),
            result={
                "error_type": "NativeFocusError" if foreground else "BrowserCompletionError",
                "worker_status": "manual_review",
            },
        )
        path = run / "report.json"
        report = {
            "schema_version": 2,
            "mode": "reviewed_candidate_native_context_menu",
            "status": "manual_review",
            "last_stage": "completion_setup",
            "error_type": "BrowserCompletionError",
            "reason": "The bound source page lost its identity or foreground",
            "browser": "chrome",
            "browser_closed": True,
            "shared_pending_retained": False,
            "output_directory": str(images),
            "report_path": str(path),
            "saved_files": [],
            "job_counts": {
                "observed": permit.image_count,
                "completed": 0,
                "unresolved": permit.image_count,
            },
        }
        if foreground:
            del report["job_counts"]
            report.update(
                last_stage="automatic_foreground_check",
                native_stage="desktop_guard",
                browser_version="155.0.8059.84",
                error_type="NativeFocusError",
                reason="Foreground focus is outside the bound probe window; input stopped",
                preinput_recovery=None,
                recovery={"recovered": 0, "metadata_written": 0, "skipped": 0, "manual_review": []},
                focus_at_failure={
                    "target_hwnd": 1234,
                    "target_exists": True,
                    "foreground_hwnd": None,
                    "foreground_pid": None,
                    "foreground_class": None,
                    "belongs_to_target": False,
                    "target_foreground": False,
                },
            )
        path.write_text(json.dumps(report), encoding="utf-8")
        yield store, task, permit, base, path, report, data


@pytest.mark.parametrize(
    "evidence,expected_reason",
    [
        ("completion", "source_identity_or_foreground_changed"),
        ("foreground", "automatic_foreground_unconfirmed"),
    ],
    indirect=["evidence"],
)
def test_proven_setup_retry_is_durable_even_if_it_fails_before_the_worker_makes_a_new_run(
    evidence, expected_reason
):
    store, task, permit, base, path, _, fixture = evidence
    run, reason, preserved = retry.verify_setup_retry(store, task, permit)
    assert run == path.parent.name and reason == expected_reason and preserved == 0
    before = path.read_bytes()
    active = store.start_setup_retry(task, prior_run=run, now=fixture.clock.now())
    assert active["task_id"] == task["task_id"] and active["status"] == "started"
    assert active["control"]["setup_retry"]["prior_control"] == task["control"]
    store.update_control(task["task_id"], task["control"])
    failed = store.finish(
        task["task_id"], status="needs_review", result=task["result"], now=fixture.clock.now()
    )
    assert "setup_retry" in failed["control"]
    with pytest.raises(QueueError):
        retry.verify_setup_retry(store, failed, permit)
    with pytest.raises(QueueError):
        store.start_setup_retry(task, prior_run=run, now=fixture.clock.now())
    assert store.get_task(task["task_id"]) == failed
    assert path.read_bytes() == before and not any((base / "images").iterdir())


@pytest.mark.parametrize(
    "change",
    [
        "stage",
        "active",
        "count",
        "path",
        "marker",
        "alive",
        "session",
        "second_run",
        "file",
        "claim",
        "history",
        "source",
        "folder",
    ],
)
def test_ambiguous_source_is_preserved_without_claiming_or_rearming(evidence, monkeypatch, change):
    store, task, permit, base, path, report, fixture = evidence
    if change == "stage":
        report["last_stage"] = "native_saving"
    elif change == "active":
        report["active_attempt"] = {"phase": "input_armed"}
    elif change == "count":
        report["job_counts"]["completed"] = False
    elif change == "path":
        report["report_path"] = str(base / "other.json")
    elif change == "marker":
        PendingSave(fixture.marker).begin(path.parent)
    elif change == "alive":
        monkeypatch.setattr(retry, "browser_still_running", lambda _: True)
    elif change == "session":
        monkeypatch.setattr(retry, "session_id", lambda: 2)
    elif change == "second_run":
        (path.parent.parent / uuid.uuid4().hex).mkdir()
    elif change == "file":
        (base / "images" / "001.jpg").write_bytes(b"existing")
    else:
        with QueueStore(base / "queue.sqlite") as native:
            if change == "claim":
                native.claim_next(uuid.uuid4().hex, fixture.clock.now())
            elif change == "history":
                native.connection.execute(
                    "INSERT INTO attempts(job_id,at,kind,reason,attempt_count,"
                    "resulting_status) "
                    "SELECT job_id,?,'ui','old',1,'paused_ui' FROM jobs",
                    (fixture.clock.now().isoformat(),),
                )
            elif change == "source":
                native.connection.execute(
                    "UPDATE post_observations SET snapshot_json=json_set(snapshot_json,"
                    "'$.profile_evidence.pilot_scope.permit_fingerprint','wrong')"
                )
            else:
                native.connection.execute("UPDATE posts SET folder_plan='{}'")
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises((NativeUIError, QueueError)):
        retry.verify_setup_retry(store, task, permit)
    assert store.get_task(task["task_id"]) == task


@pytest.mark.parametrize("evidence", ["foreground"], indirect=True)
@pytest.mark.parametrize(
    "change",
    [
        "job_counts",
        "another_stage",
        "another_error",
        "report_closed",
        "nonempty_recovery",
        "focus_snapshot",
        "unexpected_field",
        "native_content",
        "isolated_attempt",
        "orphaned_journal",
        "service_state",
        "unexpected_output",
        "staging",
        "additional_run",
        "additional_session_root",
        "running",
        "unknown_browser",
        "another_session",
        "pending",
    ],
)
def test_foreground_failure_requires_the_original_untouched_private_run(
    evidence, monkeypatch, change
):
    store, task, permit, base, path, report, fixture = evidence
    if change == "job_counts":
        report["job_counts"] = {"observed": 0, "completed": 0, "unresolved": 0}
    elif change == "another_stage":
        report["native_stage"] = "right_click"
    elif change == "another_error":
        report["error_type"] = "BrowserCompletionError"
    elif change == "report_closed":
        report["browser_closed"] = False
    elif change == "nonempty_recovery":
        report["recovery"]["skipped"] = 1
    elif change == "focus_snapshot":
        report["focus_at_failure"]["target_foreground"] = True
    elif change == "unexpected_field":
        report["active_attempt"] = None
    elif change == "unexpected_output":
        (path.parent / "native-image.png").write_bytes(b"prior output")
    elif change == "staging":
        (base / "images" / "_staging").mkdir()
    elif change == "additional_run":
        (path.parent.parent / uuid.uuid4().hex).mkdir()
    elif change == "additional_session_root":
        (base.parent / "session-2").mkdir()
    elif change in ("running", "unknown_browser"):
        monkeypatch.setattr(
            retry, "browser_still_running", lambda _: True if change == "running" else None
        )
    elif change == "another_session":
        monkeypatch.setattr(retry, "session_id", lambda: 2)
    elif change == "pending":
        PendingSave(fixture.marker).begin(path.parent)
    else:
        with QueueStore(base / "queue.sqlite") as native:
            if change == "native_content":
                enqueue_candidate_snapshot(native, permit.reference_snapshot, permit=permit)
            elif change == "isolated_attempt":
                native.connection.execute("PRAGMA foreign_keys=OFF")
                native.connection.execute(
                    "INSERT INTO attempts(job_id,at,kind,reason,attempt_count,resulting_status) "
                    "VALUES('old','then','ui','prior',1,'paused_ui')"
                )
            elif change == "orphaned_journal":
                native.connection.execute("PRAGMA foreign_keys=OFF")
                native.connection.execute(
                    "INSERT INTO artifact_finalizations VALUES("
                    "'old','artifact','observation','root','staging','final','{}','{}',"
                    "'then','prepared','key')"
                )
            else:
                native.defer_service("unknown", fixture.clock.now())
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises((NativeUIError, QueueError)):
        retry.verify_setup_retry(store, task, permit)
    assert store.get_task(task["task_id"]) == task
