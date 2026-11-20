"""Use real local image journals to exercise bounded, repeat-safe batch saving."""

import hashlib
import json
import sys
import tempfile
import uuid
from contextlib import nullcontext
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from test_candidate_finish_runtime import database_dump
from test_candidate_save_runtime import NOW
from test_monitor_save_runtime import seed_monitor, source_evidence

from image_monitor import candidate_finish
from image_monitor import monitor_batch_runtime as runtime
from image_monitor.artifact_files import finalize_saved_image
from image_monitor.candidate_save_selection import (
    MONITOR_MANIFEST_NAME,
    select_candidate_save,
)
from image_monitor.monitor_save_ledger import LedgerStore
from image_monitor.native_state import PendingSave
from image_monitor.native_ui import NativeUIError
from image_monitor.post_pipeline import enqueue_candidate_snapshot
from image_monitor.queue import QueueStore
from image_monitor.validation import verify_image
from image_monitor.watch_lock import watch_run_lock
from image_monitor.watch_runtime import DEFAULT_SCOPE, SERVICE_SCOPE


class Clock:
    def __init__(self):
        self.current = NOW
        self.waits = []

    def now(self):
        return self.current

    def wait(self, seconds):
        self.waits.append(seconds)
        self.current += timedelta(seconds=seconds)


@pytest.fixture
def data(monkeypatch, request):
    with tempfile.TemporaryDirectory(prefix="ib-") as folder:
        root = Path(folder).resolve()
        watch, legacy, batch = root / "w", root / "l", root / "b"
        observations = seed_monitor(watch, image_count=getattr(request, "param", 1))
        # Short fixture authors keep the unchanged production Windows budget
        # meaningful even under the runner's long temporary-directory prefix.
        with QueueStore(watch / "watch.sqlite") as queue:
            rows = queue.connection.execute(
                "SELECT attempt_id,result_json FROM candidate_details WHERE watch_name=?",
                (runtime.MONITOR_SCOPE.watch_name,),
            ).fetchall()
            for row in rows:
                result = json.loads(row["result_json"])
                snapshot = result["private_observation"]["snapshot"]
                snapshot["nickname"] = "fixture"
                observations[snapshot["post_url"]] = deepcopy(snapshot)
                queue.connection.execute(
                    "UPDATE candidate_details SET result_json=? WHERE attempt_id=?",
                    (json.dumps(result), row["attempt_id"]),
                )
        marker = root / "pending.json"
        monkeypatch.setattr(runtime, "require_windows", lambda: None)
        monkeypatch.setattr(runtime, "NativeSaveLock", nullcontext)
        monkeypatch.setattr(runtime, "shared_state_path", lambda: marker)
        monkeypatch.setattr(runtime, "session_id", lambda: 1)
        if sys.platform != "win32":
            monkeypatch.setattr(
                candidate_finish,
                "exclusive_digest",
                lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            )
        yield SimpleNamespace(
            root=root,
            watch=watch,
            legacy=legacy,
            batch=batch,
            marker=marker,
            observations=observations,
            clock=Clock(),
        )


def ledger(data, *, readonly=True):
    return LedgerStore(
        data.watch / runtime.LEDGER_NAME,
        watch_root=data.watch,
        legacy_root=data.legacy,
        batch_root=data.batch,
        read_only=readonly,
    )


def finalize(root, permit, snapshot, now, *, native_filename="native-image.png"):
    base = root / "session-1"
    base.mkdir(parents=True, exist_ok=True)
    snapshot = deepcopy(snapshot)
    snapshot["observed_at"] = now.isoformat()
    artifacts = []
    with QueueStore(base / "queue.sqlite") as queue:
        queued = enqueue_candidate_snapshot(queue, snapshot, permit=permit)
        for entry in queued["jobs"]:
            job = queue.claim_next("batch-fixture", now, job_ids=[entry["job_id"]])
            source = job["source"]
            image = source["image"]
            staging = (
                base / "images" / "_staging" / job["job_id"] / uuid.uuid4().hex / native_filename
            )
            staging.parent.mkdir(parents=True)
            Image.new("RGB", (image["natural_width"], image["natural_height"]), "#315781").save(
                staging
            )
            verified = verify_image(staging, writer_finished=True).to_dict()
            queue.transition(job["job_id"], job["lease_token"], "saving")
            queue.transition(job["job_id"], job["lease_token"], "verifying")
            artifact = finalize_saved_image(
                queue,
                job["job_id"],
                job["lease_token"],
                observation_id=source["observation_id"],
                save_root=base / "images",
                staging_file=staging,
                verification=verified,
                completion_evidence={
                    "state": "COMPLETE",
                    "destination_confirmed": True,
                    "source_confirmed": True,
                    "source_url": image["display_url"],
                    "destination": str(staging),
                    "exclusive_sha256": verified["sha256"],
                },
                browser_suggested_filename="invented" + staging.suffix,
                saved_at=now,
            )
            artifacts.append(artifact)
    return artifacts


class Runner:
    def __init__(self, data, *, statuses=(), fail=False):
        self.data, self.statuses, self.fail = data, list(statuses), fail
        self.calls = []

    def __call__(self, root, browser, url, *, candidate_permit, navigation_observer):
        assert browser == "chrome"
        self.calls.append((root, url, candidate_permit))
        with ledger(self.data) as store:
            task = store.get_for_post(candidate_permit.reference_snapshot["post_id"])
            assert task["status"] == "started" and task["native_session"] == 1
        if self.fail:
            raise NativeUIError("Invented private title https://private.example")
        navigation_observer.before()
        self.data.clock.current += timedelta(seconds=15)
        status = self.statuses.pop(0) if self.statuses else 200
        navigation_observer.after(
            SimpleNamespace(status=status, header_value=lambda _name: "300"), None
        )
        if status >= 400:
            return {
                "status": "manual_review",
                "browser_closed": True,
                "shared_pending_retained": False,
                "error_type": "NativeUIError",
            }
        finalize(root, candidate_permit, self.data.observations[url], self.data.clock.now())
        return {
            "status": "post_completed",
            "browser_closed": True,
            "shared_pending_retained": False,
            "job_counts": {
                "observed": candidate_permit.image_count,
                "completed": candidate_permit.image_count,
                "unresolved": 0,
            },
        }


def run(data, runner=None, **options):
    return runtime.run_monitor_batch(
        data.watch,
        data.legacy,
        data.batch,
        clock=data.clock,
        save_runner=runner or Runner(data),
        **options,
    )


def test_two_isolated_candidates_complete_and_repeat_never_launches_a_worker(data):
    before = source_evidence(data.watch)
    runner = Runner(data)
    result = run(data, runner)
    assert result["status"] == "monitor_batch_completed", result
    assert result["tasks_started"] == result["tasks_completed"] == 2
    assert len(runner.calls) == 2 and runner.calls[0][0] != runner.calls[1][0]
    assert data.clock.waits == [60]
    assert source_evidence(data.watch) == before
    with ledger(data) as store:
        assert {task["status"] for task in store.list_tasks()} == {"completed"}
    repeated = run(data, Runner(data, fail=True))
    assert repeated["status"] == "monitor_batch_no_candidates", repeated
    assert repeated["already_completed_count"] == 2
    assert repeated["tasks_started"] == 0


def test_max_one_commits_other_candidate_and_continues_without_resaving(data):
    first = Runner(data)
    assert run(data, first, max_tasks=1)["tasks_completed"] == 1
    result = run(data, Runner(data, fail=True), max_tasks=1)
    assert result["status"] == "monitor_batch_waiting"
    data.clock.current += timedelta(seconds=60)
    second = Runner(data)
    result = run(data, second, max_tasks=1)
    assert result["tasks_completed"] == 1 and result["already_completed_count"] == 1
    assert first.calls[0][1] != second.calls[0][1]


def test_old_fixed_save_is_verified_adopted_and_preserved_without_runner(data):
    with QueueStore(data.watch / "watch.sqlite") as queue:
        permit = select_candidate_save(
            queue, runtime.MONITOR_SCOPE, data.watch / MONITOR_MANIFEST_NAME
        )
    finalize(data.legacy, permit, data.observations[permit.post_url], data.clock.now())
    manifest = (data.watch / MONITOR_MANIFEST_NAME).read_bytes()
    old_files = {p: p.read_bytes() for p in data.legacy.rglob("*") if p.is_file()}
    source = source_evidence(data.watch)
    runner = Runner(data)
    result = run(data, runner)
    assert result["status"] == "monitor_batch_completed", result
    assert result["adopted_count"] == result["already_completed_count"] == 1
    assert result["tasks_started"] == result["tasks_completed"] == 1
    assert runner.calls[0][1] != permit.post_url
    assert (data.watch / MONITOR_MANIFEST_NAME).read_bytes() == manifest
    assert {p: p.read_bytes() for p in old_files} == old_files
    assert source_evidence(data.watch) == source
    with ledger(data) as store:
        assert {t["output_kind"] for t in store.list_tasks()} == {"legacy", "managed"}


@pytest.mark.parametrize("status", [401, 403, 404, 410, 429, 503])
def test_failed_response_is_durable_and_stops_before_the_next_candidate(data, status):
    runner = Runner(data, statuses=[status])
    report = run(data, runner)
    assert report["status"] == "monitor_batch_manual_review", report
    assert len(runner.calls) == 1
    with ledger(data) as store:
        tasks = store.list_tasks()
        attempted = next(t for t in tasks if t["status"] == "needs_review")
        assert attempted["control"]["http_status"] == status
        assert attempted["control"]["in_flight"] is False
    if status in {429, 503}:
        assert datetime.fromisoformat(report["next_eligible_at_local"]) == (
            data.clock.now() + timedelta(seconds=300)
        )
    data.clock.current += timedelta(days=1)
    repeated = Runner(data, fail=True)
    report = run(data, repeated)
    assert report["reason"] == "unfinished_batch_requires_reconcile"
    assert repeated.calls == []


def test_second_task_failure_cannot_hide_behind_first_success(data):
    result = run(data, Runner(data, statuses=[200, 403]))
    assert result["status"] == "monitor_batch_manual_review"
    assert result["tasks_completed"] == 1 and result["tasks_started"] == 2


def test_worker_exception_keeps_unknown_browser_state_and_blocks_retry(data):
    result = run(data, Runner(data, fail=True))
    assert result["status"] == "monitor_batch_manual_review"
    assert result["browser_closed"] is result["shared_pending_retained"] is None
    with ledger(data) as store:
        assert sum(t["status"] == "needs_review" for t in store.list_tasks()) == 1
    again = Runner(data)
    assert run(data, again)["reason"] == "unfinished_batch_requires_reconcile"
    assert again.calls == []


def test_persisted_wait_does_not_start_a_task(data):
    with QueueStore(data.watch / "watch.sqlite") as queue:
        queue.defer_service(SERVICE_SCOPE, data.clock.now() + timedelta(hours=1))
    result = run(data, Runner(data, fail=True))
    assert result["status"] == "monitor_batch_waiting"
    assert result["tasks_started"] == 0
    assert data.clock.waits == []


def test_shared_scan_lease_prevents_batch_planning(data):
    with watch_run_lock(data.watch / "watch.sqlite", DEFAULT_SCOPE):
        result = run(data, Runner(data, fail=True))
    assert result["status"] == "monitor_batch_busy"
    assert not (data.watch / runtime.LEDGER_NAME).exists()


def test_current_pending_save_is_preserved_and_no_ledger_is_created(data):
    data.marker.write_text(
        json.dumps({"run_id": "old", "run_directory": "old", "browser_profile": "old"})
    )
    before = data.marker.read_bytes()
    result = run(data, Runner(data, fail=True))
    assert result["status"] == "monitor_batch_manual_review"
    assert data.marker.read_bytes() == before
    assert not (data.watch / runtime.LEDGER_NAME).exists()


def test_corrupt_completed_file_is_never_requeued(data):
    assert run(data, max_tasks=1)["tasks_completed"] == 1
    with ledger(data) as store:
        task = next(t for t in store.list_tasks() if t["status"] == "completed")
    image = next((data.batch / task["relative_root"] / "session-1" / "images").rglob("001.png"))
    image.write_bytes(b"corrupt")
    data.clock.current += timedelta(days=1)
    runner = Runner(data, fail=True)
    result = run(data, runner)
    assert result["status"] == "monitor_batch_manual_review"
    assert runner.calls == [] and image.read_bytes() == b"corrupt"


def test_missing_watch_does_not_create_a_discovery_database(data):
    missing = data.root / "missing"
    result = runtime.run_monitor_batch(missing, data.legacy, data.batch, clock=data.clock)
    assert result["status"] == "monitor_batch_no_candidates"
    assert not missing.exists()


def test_long_output_path_fails_before_any_started_task(data):
    long_root = data.root / ("x" * 100)
    runner = Runner(data, fail=True)
    result = runtime.run_monitor_batch(
        data.watch, data.legacy, long_root, clock=data.clock, save_runner=runner
    )
    assert result["status"] == "monitor_batch_manual_review"
    assert runner.calls == []
    with LedgerStore(
        data.watch / runtime.LEDGER_NAME,
        watch_root=data.watch,
        legacy_root=data.legacy,
        batch_root=long_root,
        read_only=True,
    ) as store:
        assert all(task["status"] == "planned" for task in store.list_tasks())


def test_source_change_after_completed_task_stops_before_another_native_attempt(data):
    assert run(data, max_tasks=1)["tasks_completed"] == 1
    before = source_evidence(data.watch)
    with QueueStore(data.watch / "watch.sqlite") as queue:
        task = next(t for t in ledger_tasks(data) if t["status"] == "completed")
        row = queue.connection.execute(
            "SELECT result_json FROM candidate_details WHERE attempt_id=?",
            (task["detail_attempt_id"],),
        ).fetchone()
        result = json.loads(row[0])
        result["private_observation"]["snapshot"]["title"] = "Invented changed header"
        queue.connection.execute(
            "UPDATE candidate_details SET result_json=? WHERE attempt_id=?",
            (json.dumps(result), task["detail_attempt_id"]),
        )
    runner = Runner(data, fail=True)
    assert run(data, runner)["status"] == "monitor_batch_manual_review"
    assert runner.calls == [] and before != source_evidence(data.watch)


def ledger_tasks(data):
    with ledger(data) as store:
        return store.list_tasks()


def test_shared_report_excludes_roots_source_identities_and_private_evidence(data):
    report = run(data, max_tasks=1)
    report.update(task_id="private-id", post_url="private-url", control={"private": "identity"})
    public = runtime.share_batch_report(report)
    serialized = json.dumps(public)
    assert "private" not in serialized and str(data.root) not in serialized
    assert "report_path" not in serialized and "task_id" not in serialized
    assert public["saved_files"][0]["saved_filename"] == "001.png"
    assert "post_url" not in serialized


@pytest.mark.parametrize("limit", [0, 3, True, 1.5])
def test_invalid_batch_limit_fails_before_output_creation(data, limit):
    with pytest.raises(NativeUIError):
        run(data, max_tasks=limit)
    assert not data.batch.exists()


def test_reported_completed_task_without_real_files_stays_review(data):
    def false_report(root, browser, url, *, candidate_permit, navigation_observer):
        navigation_observer.before()
        navigation_observer.after(SimpleNamespace(status=200), None)
        return {
            "status": "post_completed",
            "browser_closed": True,
            "shared_pending_retained": False,
            "job_counts": {"observed": 1, "completed": 1, "unresolved": 0},
        }

    result = run(data, false_report)
    assert result["status"] == "monitor_batch_manual_review"
    assert any(task["status"] == "needs_review" for task in ledger_tasks(data))


def test_batch_does_not_write_the_discovery_database_except_service_waits(data):
    before = source_evidence(data.watch)
    watch_dump = database_dump(data.watch / "watch.sqlite")
    report = run(data, max_tasks=1)
    assert report["tasks_completed"] == 1
    assert source_evidence(data.watch) == before
    assert database_dump(data.watch / "watch.sqlite") != watch_dump  # Common service deadline only.


@pytest.mark.parametrize("http_status", [404, 410])
def test_proven_missing_post_leaves_no_image_work_and_allows_the_next_candidate(data, http_status):
    normal = Runner(data)
    calls = []

    def runner(root, browser, url, *, candidate_permit, navigation_observer):
        calls.append(url)
        if len(calls) > 1:
            return normal(
                root,
                browser,
                url,
                candidate_permit=candidate_permit,
                navigation_observer=navigation_observer,
            )
        base = root / "session-1"
        base.mkdir(parents=True)
        with QueueStore(base / "queue.sqlite"):
            pass
        navigation_observer.before()
        data.clock.current += timedelta(seconds=15)
        navigation_observer.after(SimpleNamespace(status=http_status), None)
        return {
            "status": "manual_review",
            "last_stage": "post_inspection",
            "error_type": "NativeUIError",
            "browser_closed": True,
            "shared_pending_retained": False,
            "saved_files": [],
        }

    result = run(data, runner)
    assert result["status"] == "monitor_batch_completed", result
    assert result["unavailable_count"] == 1
    assert result["tasks_started"] == 2 and result["tasks_completed"] == 1
    assert len(calls) == 2 and calls[0] != calls[1]
    assert data.clock.waits == [60]
    assert {t["status"] for t in ledger_tasks(data)} == {"completed", "unavailable"}
    assert run(data, Runner(data, fail=True))["tasks_started"] == 0


@pytest.mark.parametrize("change", ["closed", "pending", "active", "work"])
def test_missing_post_with_uncertain_cleanup_or_native_work_cannot_skip_to_next(data, change):
    calls = []

    def runner(root, browser, url, *, candidate_permit, navigation_observer):
        calls.append(url)
        base = root / "session-1"
        base.mkdir(parents=True)
        with QueueStore(base / "queue.sqlite") as queue:
            if change == "work":
                snapshot = deepcopy(data.observations[url])
                snapshot["observed_at"] = data.clock.now().isoformat()
                enqueue_candidate_snapshot(queue, snapshot, permit=candidate_permit)
        navigation_observer.before()
        navigation_observer.after(SimpleNamespace(status=404), None)
        result = {
            "status": "manual_review",
            "last_stage": "post_inspection",
            "error_type": "NativeUIError",
            "browser_closed": True,
            "shared_pending_retained": False,
            "saved_files": [],
        }
        if change == "closed":
            result["browser_closed"] = False
        elif change == "pending":
            result["shared_pending_retained"] = True
        elif change == "active":
            result["active_attempt"] = {"native_input": True}
        return result

    result = run(data, runner)
    assert result["status"] == "monitor_batch_manual_review"
    assert result["unavailable_count"] == 0 and len(calls) == 1
    assert any(t["status"] == "needs_review" for t in ledger_tasks(data))


def test_observer_records_real_owned_pending_identity_and_preserves_it_after_navigation(data):
    normal = Runner(data)
    identities = []

    def runner(root, browser, url, *, candidate_permit, navigation_observer):
        base = root / "session-1"
        run_directory = base / "runs" / uuid.uuid4().hex
        (run_directory / "browser-profile").mkdir(parents=True)
        (base / "images").mkdir()
        state = PendingSave(data.marker)
        pending = state.begin(run_directory)
        state.update_browser(pending, 424242, 12345.5)
        identities.append(state.read())
        result = normal(
            root,
            browser,
            url,
            candidate_permit=candidate_permit,
            navigation_observer=navigation_observer,
        )
        state.finish(pending)
        return result

    result = run(data, runner, max_tasks=1)
    assert result["tasks_completed"] == 1
    task = next(t for t in ledger_tasks(data) if t["status"] == "completed")
    assert task["control"]["browser_identity"] == identities[0]
    assert task["control"]["in_flight"] is False


def test_production_observer_requires_an_owned_pending_browser_before_navigation(data):
    run(data, Runner(data, fail=True))
    with QueueStore(data.watch / "watch.sqlite") as queue, ledger(data, readonly=False) as store:
        planned = next(t for t in store.list_tasks() if t["status"] == "planned")
        # Finish the intentionally failed earlier task as a controlled fixture
        # so the second task can be started without sending native input.
        failed = next(t for t in store.list_tasks() if t["status"] == "needs_review")
        store.reconcile_completed(failed["task_id"], result={"fixture": True}, now=data.clock.now())
        task = store.start(planned["task_id"], data.clock.now(), native_session=1)
        observer = runtime._NavigationObserver(queue, store, task, data.clock)
        with pytest.raises(NativeUIError, match="identity"):
            observer.before()
        assert store.get_task(task["task_id"])["control"] == {"blocked": False}


def prepare_legacy(data):
    with QueueStore(data.watch / "watch.sqlite") as queue:
        permit = select_candidate_save(
            queue, runtime.MONITOR_SCOPE, data.watch / MONITOR_MANIFEST_NAME
        )
    finalize(data.legacy, permit, data.observations[permit.post_url], data.clock.now())
    return permit


def test_existing_planned_legacy_binding_can_never_be_sent_to_the_native_worker(data):
    permit = prepare_legacy(data)
    with QueueStore(data.watch / "watch.sqlite") as queue, ledger(data, readonly=False) as store:
        candidate = runtime._candidate(queue, permit.reference_snapshot["post_id"])
        detail = runtime.CandidateDetailStore(queue).get(permit.detail_attempt_id)
        store.plan(candidate, detail, permit, output_kind="legacy", now=data.clock.now())
    runner = Runner(data, fail=True)
    result = run(data, runner)
    assert result["status"] == "monitor_batch_manual_review"
    assert result["reason"] == "unfinished_legacy_requires_review"
    assert runner.calls == []


def test_missing_old_selection_with_existing_native_output_does_not_plan_a_duplicate(data):
    prepare_legacy(data)
    before = {p: p.read_bytes() for p in data.legacy.rglob("*") if p.is_file()}
    manifest = data.watch / MONITOR_MANIFEST_NAME
    manifest.unlink()
    runner = Runner(data, fail=True)
    result = run(data, runner)
    assert result["status"] == "monitor_batch_manual_review"
    assert not manifest.exists() and runner.calls == []
    assert ledger_tasks(data) == []
    assert {p: p.read_bytes() for p in before} == before


def test_adoption_failure_cannot_leave_an_old_save_eligible_for_native_retry(data, monkeypatch):
    permit = prepare_legacy(data)
    original = LedgerStore.adopt_completed

    def interrupted(*_args, **_kwargs):
        raise OSError("Controlled adoption write failure")

    monkeypatch.setattr(LedgerStore, "adopt_completed", interrupted)
    runner = Runner(data, fail=True)
    assert run(data, runner)["status"] == "monitor_batch_manual_review"
    assert runner.calls == [] and ledger_tasks(data) == []
    monkeypatch.setattr(LedgerStore, "adopt_completed", original)
    runner = Runner(data)
    result = run(data, runner)
    assert result["adopted_count"] == 1 and result["tasks_completed"] == 1
    assert runner.calls[0][1] != permit.post_url


def test_missing_ledger_with_existing_batch_images_cannot_recreate_and_resave(data):
    assert run(data, max_tasks=1)["tasks_completed"] == 1
    ledger_path = data.watch / runtime.LEDGER_NAME
    images = {p: p.read_bytes() for p in (data.batch / "tasks").rglob("*") if p.is_file()}
    ledger_path.unlink()
    runner = Runner(data, fail=True)
    result = run(data, runner)
    assert result["status"] == "monitor_batch_manual_review"
    assert not ledger_path.exists() and runner.calls == []
    assert {p: p.read_bytes() for p in images} == images


def test_unreferenced_native_output_is_not_adopted_or_ignored(data):
    assert run(data, max_tasks=1)["tasks_completed"] == 1
    foreign = data.batch / "tasks" / uuid.uuid4().hex
    foreign.mkdir()
    proof = foreign / "foreign.txt"
    proof.write_bytes(b"Preserve foreign task data")
    runner = Runner(data, fail=True)
    result = run(data, runner)
    assert result["status"] == "monitor_batch_manual_review"
    assert runner.calls == [] and proof.read_bytes() == b"Preserve foreign task data"


def test_planned_task_with_existing_native_output_never_starts(data):
    with QueueStore(data.watch / "watch.sqlite") as queue:
        queue.defer_service(SERVICE_SCOPE, data.clock.now() + timedelta(seconds=60))
    assert run(data)["status"] == "monitor_batch_waiting"
    with ledger(data) as store:
        task = store.list_tasks()[0]
    root = data.batch / task["relative_root"]
    root.mkdir(parents=True)
    proof = root / "unowned.txt"
    proof.write_bytes(b"Unowned native work remains")
    data.clock.current += timedelta(seconds=60)
    runner = Runner(data, fail=True)
    result = run(data, runner)
    assert result["status"] == "monitor_batch_manual_review"
    assert runner.calls == [] and proof.read_bytes() == b"Unowned native work remains"


def test_dashboard_stop_before_native_commit_keeps_planned_tasks_reusable(data, monkeypatch):
    import threading

    stopped = threading.Event()
    original = runtime._preflight

    def preflight(*args):
        original(*args)
        stopped.set()

    monkeypatch.setattr(runtime, "_preflight", preflight)
    runner = Runner(data)
    outcome = run(data, runner, max_tasks=1, should_stop=stopped.is_set)
    assert outcome["status"] == "monitor_batch_cancelled"
    assert outcome["reason"] == "requested_stop"
    assert outcome["tasks_started"] == 0 and runner.calls == []
    with ledger(data) as state:
        assert [task["status"] for task in state.list_tasks()] == ["planned", "planned"]
    result = run(data, runner, max_tasks=1)
    assert result["tasks_completed"] == 1 and len(runner.calls) == 1


def test_dashboard_stop_during_started_native_work_preserves_its_verified_result(data):
    import threading

    stopped = threading.Event()
    runner = Runner(data)

    def finish(*args, **kwargs):
        stopped.set()
        return runner(*args, **kwargs)

    outcome = run(data, finish, max_tasks=1, should_stop=stopped.is_set)
    assert outcome["status"] == "monitor_batch_completed"
    assert outcome["tasks_completed"] == 1 and len(runner.calls) == 1
    assert outcome["tasks_remaining"] == 1


@pytest.mark.parametrize("data", [10], indirect=True)
def test_two_monitor_posts_verify_twenty_files_and_reopen_without_more_saves(data):
    report = run(data)
    assert report["status"] == "monitor_batch_completed" and report["tasks_completed"] == 2, report
    shared = runtime.share_batch_report(report)
    names = [f"{slot:03d}.png" for slot in range(1, 11)]
    assert shared["saved_file_count"] == 20
    assert [item["saved_filename"] for item in shared["saved_files"]] == names + names
    for path in data.batch.glob("tasks/*/session-1/images/**/metadata.json"):
        entries = json.loads(path.read_bytes())["images"]
        assert [entry["artifact"]["saved_filename"] for entry in entries] == names
    assert len(list(data.batch.glob("tasks/*/session-1/images/**/010.png"))) == 2
    again = run(data, Runner(data, fail=True))
    assert again["tasks_started"] == 0 and again["already_completed_count"] == 2
