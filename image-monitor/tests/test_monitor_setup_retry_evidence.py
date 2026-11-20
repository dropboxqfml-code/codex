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
def evidence(data, monkeypatch):
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
            result={"error_type": "BrowserCompletionError", "worker_status": "manual_review"},
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
        path.write_text(json.dumps(report), encoding="utf-8")
        yield store, task, permit, base, path, report, data


def test_proven_setup_retry_is_durable_even_if_it_fails_before_the_worker_makes_a_new_run(evidence):
    store, task, permit, base, path, _, fixture = evidence
    run, reason = retry.verify_setup_retry(store, task, permit)
    assert run == path.parent.name and reason == "source_identity_or_foreground_changed"
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
