"""Existing real journals drive anonymous operations and completed-only preflight."""

import json
import socket
from contextlib import nullcontext
from datetime import timedelta
from types import SimpleNamespace

import pytest
from test_monitor_batch_finish import completed_batch as completed_batch
from test_monitor_batch_runtime import Runner, ledger, run
from test_monitor_batch_runtime import data as data
from test_saved_catalog_batch import complete_with_legacy, disk_bytes

from image_monitor import monitor_operations as operations
from image_monitor.monitor_save_ledger import LEDGER_NAME, LedgerStore, task_native_base
from image_monitor.native_ui import NativeUIError
from image_monitor.queue import QueueStore
from image_monitor.watch_lock import watch_run_lock
from image_monitor.watch_runtime import DEFAULT_SCOPE, SERVICE_SCOPE


@pytest.fixture
def local_data(data, monkeypatch):
    monkeypatch.setattr(operations, "NativeSaveLock", nullcontext)
    monkeypatch.setattr(operations, "shared_state_path", lambda: data.marker)
    monkeypatch.setattr(operations, "session_id", lambda: 1)
    return data


@pytest.fixture
def local_finish(completed_batch, monkeypatch):
    monkeypatch.setattr(operations, "NativeSaveLock", nullcontext)
    monkeypatch.setattr(operations, "shared_state_path", lambda: completed_batch.marker)
    monkeypatch.setattr(operations, "session_id", lambda: 1)
    return completed_batch


def load(data, **options):
    options.setdefault("now", data.clock.now() + timedelta(days=1))
    return operations.load_monitor_operations(data.watch, data.legacy, data.batch, **options)


def finish_load(value, **options):
    return operations.load_monitor_operations(
        value.watch_root, value.legacy_root, value.batch_root, **options
    )


def assert_private(result, data):
    encoded = json.dumps(result)
    assert str(data.root) not in encoded
    assert "https:" not in encoded
    assert set(result) == {
        "status",
        "reason",
        "error_type",
        "candidate_uninspected",
        "save_ready",
        "save_planned",
        "save_active",
        "save_completed",
        "save_unavailable",
        "save_needs_review",
        "wait_until",
        "can_finish",
        "rows",
        "rows_omitted",
    }
    assert result["reason"] in operations.OPERATIONS_REASONS
    assert len(result["rows"]) <= 20
    for row in result["rows"]:
        assert set(row) == {"order", "status", "reason", "image_count"}
        assert row["status"] in operations.OPERATIONS_ROW_STATUSES
        assert row["reason"] in operations.ROW_REASONS
    if (data.watch / LEDGER_NAME).exists():
        with ledger(data) as store:
            for task in store.list_tasks():
                for field in ("task_id", "post_url", "permit_fingerprint", "detail_attempt_id"):
                    assert task[field] not in encoded


def assert_unpublished(result, status="needs_review"):
    assert result["status"] == status, result
    assert result["can_finish"] is False
    assert result["rows"] == [] and result["rows_omitted"] == 0
    assert all(result[key] == 0 for key in operations._COUNTS)


def test_missing_data_is_empty_and_creates_no_directories(tmp_path):
    roots = [tmp_path / name for name in ("watch", "legacy", "batch")]
    result = operations.load_monitor_operations(*roots)
    assert result["status"] == "empty", result
    assert result["reason"] == "no_existing_work"
    assert not any(root.exists() for root in roots)


def test_existing_details_are_ready_without_a_new_ledger_or_output(local_data, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Operations must remain a local read-only operation")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    before = disk_bytes(local_data)
    result = load(local_data)
    assert result["status"] == "ready", result
    assert result["reason"] == "save_ready"
    assert result["save_ready"] == 2
    assert result["candidate_uninspected"] == result["save_active"] == 0
    assert result["can_finish"] is False
    assert not local_data.legacy.exists() and not local_data.batch.exists()
    assert disk_bytes(local_data) == before
    assert_private(result, local_data)


def test_uninspected_is_separate_from_native_pending_and_attempted_details(local_data):
    with QueueStore(local_data.watch / "watch.sqlite") as queue:
        queue.connection.execute(
            "DELETE FROM candidate_details WHERE attempt_id=(SELECT attempt_id "
            "FROM candidate_details WHERE watch_name=? ORDER BY attempt_id LIMIT 1)",
            (operations.MONITOR_SCOPE.watch_name,),
        )
        queue.connection.execute("UPDATE candidate_details SET status='failed'")
    result = load(local_data)
    assert result["candidate_uninspected"] == 1, result
    assert result["save_active"] == result["save_needs_review"] == 0
    assert result["reason"] == "candidate_detail_requires_review"
    assert {row["status"] for row in result["rows"]} == {
        "candidate_uninspected",
        "candidate_detail_needs_review",
    }
    local_data.marker.write_text(
        json.dumps(
            {
                "run_id": "unrelated",
                "run_directory": "/private/run",
                "browser_profile": "/private/profile",
            }
        )
    )
    result = load(local_data)
    assert result["status"] == "busy" and result["reason"] == "pending_save_requires_review"
    assert result["candidate_uninspected"] == 1 and result["can_finish"] is False
    assert_private(result, local_data)


def test_completed_tasks_are_verified_and_ledger_sources_are_counted_once(local_data):
    complete_with_legacy(local_data)
    before = disk_bytes(local_data)
    result = load(local_data)
    assert result["save_completed"] == 2, result
    assert result["save_ready"] == result["save_planned"] == 0
    assert len(result["rows"]) == 2
    assert disk_bytes(local_data) == before
    assert_private(result, local_data)


@pytest.mark.parametrize("kind", ["image", "metadata", "queue"])
def test_bad_second_completed_task_discards_all_partial_counts(local_data, kind):
    assert run(local_data)["tasks_completed"] == 2
    with ledger(local_data) as store:
        second = store.list_tasks()[1]
    base = task_native_base(second, local_data.batch, local_data.legacy)
    path = (
        next(base.rglob("001.png"))
        if kind == "image"
        else next(base.rglob("metadata.json"))
        if kind == "metadata"
        else base / "queue.sqlite"
    )
    path.write_bytes(b"Keep these private corrupt bytes for manual review")
    before = disk_bytes(local_data)
    result = load(local_data)
    assert_unpublished(result)
    assert result["reason"] == "operations_require_review"
    assert disk_bytes(local_data) == before


def test_missing_ledger_with_existing_tasks_fails_closed(local_data):
    assert run(local_data)["tasks_completed"] == 2
    (local_data.watch / LEDGER_NAME).unlink()
    before = disk_bytes(local_data)
    assert_unpublished(load(local_data))
    assert disk_bytes(local_data) == before


@pytest.mark.parametrize("binding", ["root", "scope", "extra_session", "symlink"])
def test_foreign_or_unbound_outputs_are_rejected(local_data, binding):
    assert run(local_data)["tasks_completed"] == 2
    if binding in {"root", "scope"}:
        with ledger(local_data, readonly=False) as store:
            if binding == "root":
                store.connection.execute(
                    "UPDATE ledger_meta SET batch_root=?", (str(local_data.root),)
                )
            else:
                store.connection.execute("UPDATE ledger_meta SET scope_json='[]'")
    elif binding == "extra_session":
        with ledger(local_data) as store:
            task = store.list_tasks()[0]
        (task_native_base(task, local_data.batch, local_data.legacy).parent / "session-55").mkdir()
    else:
        local_data.legacy.symlink_to(local_data.batch, target_is_directory=True)
    assert_unpublished(load(local_data))


@pytest.mark.parametrize(
    "control,reason",
    [
        ({"blocked": True}, "service_access_blocked"),
        ({"blocked": False, "in_flight": True}, "navigation_in_progress"),
    ],
)
def test_persistent_controls_have_distinct_reasons(local_data, control, reason):
    assert run(local_data)["tasks_completed"] == 2
    with ledger(local_data, readonly=False) as store:
        store.update_control(store.list_tasks()[0]["task_id"], control)
    result = load(local_data)
    assert result["status"] == "needs_review" and result["reason"] == reason, result
    assert result["save_completed"] == 2


def test_shared_cooldown_is_utc_and_does_not_hide_ready_counts(local_data):
    due = local_data.clock.now() + timedelta(minutes=10)
    with QueueStore(local_data.watch / "watch.sqlite") as queue:
        queue.defer_service(SERVICE_SCOPE, due)
    result = load(local_data, now=local_data.clock.now())
    assert result["save_ready"] == 2
    assert result["reason"] == "service_cooldown"
    assert result["wait_until"] == due.isoformat(timespec="microseconds")


@pytest.mark.parametrize("completed_batch", [1, 10], indirect=True)
def test_pending_completed_proof_enables_only_explicit_finish_without_mutation(local_finish):
    value = local_finish
    before = {path: path.read_bytes() for path in value.root.rglob("*") if path.is_file()}
    result = finish_load(value)
    assert result["can_finish"] is True, result
    assert result["reason"] == "completed_save_can_finish"
    assert result["save_completed"] == 0 and result["save_needs_review"] == 1
    [pending] = [row for row in result["rows"] if row["status"] == "save_needs_review"]
    assert pending["image_count"] == value.permit.image_count
    assert value.marker.exists()
    assert all(path.read_bytes() == contents for path, contents in before.items())
    with LedgerStore(
        value.ledger_path,
        watch_root=value.watch_root,
        legacy_root=value.legacy_root,
        batch_root=value.batch_root,
        read_only=True,
    ) as store:
        assert store.get_task(value.task_id)["status"] == "needs_review"


@pytest.mark.parametrize(
    "control,reason",
    [
        ({"blocked": True}, "service_access_blocked"),
        ({"blocked": False, "in_flight": True}, "navigation_in_progress"),
    ],
)
def test_completed_local_finish_remains_available_and_preserves_persistent_controls(
    local_finish, control, reason
):
    value = local_finish
    with LedgerStore(
        value.ledger_path,
        watch_root=value.watch_root,
        legacy_root=value.legacy_root,
        batch_root=value.batch_root,
    ) as store:
        control["browser_identity"] = value.pending
        store.update_control(value.task_id, control)
    result = finish_load(value)
    assert result["can_finish"] is True, result
    assert result["reason"] == reason
    with LedgerStore(
        value.ledger_path,
        watch_root=value.watch_root,
        legacy_root=value.legacy_root,
        batch_root=value.batch_root,
        read_only=True,
    ) as store:
        assert store.get_task(value.task_id)["control"] == control
    assert value.marker.exists()


@pytest.mark.parametrize("change", ["report", "profile", "image", "foreign_session"])
def test_unknown_partial_or_foreign_pending_never_enables_finish(local_finish, monkeypatch, change):
    value = local_finish
    if change == "report":
        value.report_path.unlink()
    elif change == "profile":
        pending = json.loads(value.marker.read_text())
        pending["browser_profile"] += "-foreign"
        value.marker.write_text(json.dumps(pending))
    elif change == "image":
        from pathlib import Path

        Path(value.artifact["final_path"]).write_bytes(b"partial original must be preserved")
    else:
        monkeypatch.setattr(operations, "session_id", lambda: 55)
    result = finish_load(value)
    assert result["can_finish"] is False, result
    assert value.marker.exists()
    assert result["save_completed"] == 0


@pytest.mark.parametrize("identity", [None, "forged"])
def test_no_pending_requires_recorded_real_browser_identity(local_finish, identity):
    value = local_finish
    value.marker.unlink()
    assert finish_load(value)["can_finish"] is True
    with LedgerStore(
        value.ledger_path,
        watch_root=value.watch_root,
        legacy_root=value.legacy_root,
        batch_root=value.batch_root,
    ) as store:
        control = {"blocked": False}
        if identity == "forged":
            control["browser_identity"] = value.pending | {"browser_pid": None}
        store.update_control(value.task_id, control)
    result = finish_load(value)
    assert result["can_finish"] is False and result["save_completed"] == 0


def test_multiple_unfinished_tasks_do_not_enable_finish(local_finish):
    value = local_finish
    with QueueStore(value.watch_root / "watch.sqlite", read_only=True) as queue:
        detail = next(
            item
            for item in operations.CandidateDetailStore(queue).list_details(
                operations.MONITOR_SCOPE
            )
            if item["post_id"] != value.permit.reference_snapshot["post_id"]
        )
        candidate, permit = operations._eligible_permit(queue, detail)
    with LedgerStore(
        value.ledger_path,
        watch_root=value.watch_root,
        legacy_root=value.legacy_root,
        batch_root=value.batch_root,
    ) as store:
        planned = store.plan(
            candidate, detail, permit, now=value.permit.first_seen_at + timedelta(days=1)
        )
        store.connection.execute(
            "UPDATE save_tasks SET status='started',started_at=created_at,native_session=1 "
            "WHERE task_id=?",
            (planned["task_id"],),
        )
    result = finish_load(value)
    assert result["can_finish"] is False
    assert result["save_active"] == result["save_needs_review"] == 1


def test_started_task_without_completed_files_is_review_only(local_data):
    result = run(local_data, max_tasks=1)
    assert result["tasks_completed"] == 1
    with ledger(local_data, readonly=False) as store:
        planned = next(task for task in store.list_tasks() if task["status"] == "planned")
        store.start(planned["task_id"], local_data.clock.now(), native_session=1)
    result = load(local_data)
    assert result["save_completed"] == result["save_active"] == 1
    assert result["can_finish"] is False and result["reason"] == "save_requires_review"


def test_ledger_task_limit_fails_closed_before_publishing_completed_counts(local_data):
    assert run(local_data)["tasks_completed"] == 2
    with ledger(local_data, readonly=False) as store:
        task = store.connection.execute("SELECT * FROM save_tasks LIMIT 1").fetchone()
        keys = list(task.keys())
        for number in range(3, 1002):
            copied = dict(task)
            copied.update(task_id=f"{number:032x}", post_id=str(9000 + number))
            copied["post_url"] = (
                f"https://gall.dcinside.com/board/view/?id=comic_new6&no={copied['post_id']}"
            )
            copied["relative_root"] = f"tasks/{copied['task_id']}"
            store.connection.execute(
                "INSERT INTO save_tasks VALUES(" + ",".join("?" for _key in keys) + ")",
                tuple(copied[key] for key in keys),
            )
    result = load(local_data)
    assert_unpublished(result)


def test_unavailable_task_with_native_image_work_cannot_conceal_completed_files(local_data):
    assert run(local_data)["tasks_completed"] == 2
    with ledger(local_data, readonly=False) as store:
        task = store.list_tasks()[0]
        store.connection.execute(
            "UPDATE save_tasks SET status='unavailable',result_json=? WHERE task_id=?",
            (
                json.dumps(
                    {
                        "http_status": 404,
                        "no_native_work": True,
                        "browser_closed": True,
                        "shared_pending_retained": False,
                    }
                ),
                task["task_id"],
            ),
        )
    assert_unpublished(load(local_data))


def test_proven_unavailable_without_image_work_remains_distinct_from_completed(local_data):
    normal = Runner(local_data)
    called = False

    def runner(root, browser, url, *, candidate_permit, navigation_observer):
        nonlocal called
        if called:
            return normal(
                root,
                browser,
                url,
                candidate_permit=candidate_permit,
                navigation_observer=navigation_observer,
            )
        called = True
        base = root / "session-1"
        base.mkdir(parents=True)
        with QueueStore(base / "queue.sqlite"):
            pass
        navigation_observer.before()
        local_data.clock.current += timedelta(seconds=15)
        navigation_observer.after(SimpleNamespace(status=404), None)
        return {
            "status": "manual_review",
            "last_stage": "post_inspection",
            "error_type": "NativeUIError",
            "browser_closed": True,
            "shared_pending_retained": False,
            "saved_files": [],
        }

    report = run(local_data, runner)
    assert report["tasks_completed"] == report["unavailable_count"] == 1
    result = load(local_data)
    assert result["save_completed"] == result["save_unavailable"] == 1, result
    assert result["save_ready"] == result["save_needs_review"] == 0


def test_rows_are_bounded_without_losing_total_uninspected_count(local_data):
    with QueueStore(local_data.watch / "watch.sqlite") as queue:
        queue.connection.execute("DELETE FROM candidate_details")
        candidate = dict(
            queue.connection.execute(
                "SELECT * FROM watch_candidates WHERE watch_name=? LIMIT 1",
                (operations.MONITOR_SCOPE.watch_name,),
            ).fetchone()
        )
        keys = list(candidate)
        for number in range(900, 925):
            candidate["post_id"] = str(number)
            candidate["post_url"] = (
                f"https://gall.dcinside.com/board/view/?id=comic_new6&no={number}"
            )
            queue.connection.execute(
                "INSERT INTO watch_candidates VALUES(" + ",".join("?" for _ in keys) + ")",
                tuple(candidate[key] for key in keys),
            )
    result = load(local_data)
    assert result["candidate_uninspected"] == 27
    assert len(result["rows"]) == 20 and result["rows_omitted"] == 7
    assert [row["order"] for row in result["rows"]] == list(range(1, 21))


def test_cancellation_discards_an_in_progress_snapshot(local_data):
    assert run(local_data)["tasks_completed"] == 2
    calls = 0

    def stop():
        nonlocal calls
        calls += 1
        return calls == 8

    assert_unpublished(load(local_data, should_stop=stop), "cancelled")


def test_scan_and_native_owners_report_busy(local_data, monkeypatch):
    with watch_run_lock(local_data.watch / "watch.sqlite", DEFAULT_SCOPE):
        result = load(local_data)
        assert_unpublished(result, "busy")
        assert result["reason"] == "another_scan_owns_this_scope"

    class Busy:
        def __enter__(self):
            raise NativeUIError("Private ownership details")

    monkeypatch.setattr(operations, "NativeSaveLock", Busy)
    result = load(local_data)
    assert_unpublished(result, "busy")
    assert result["reason"] == "native_save_in_progress"


@pytest.mark.parametrize("options", [{"should_stop": lambda: 1}, {"now": "private-invalid-time"}])
def test_invalid_inputs_are_sanitized(local_data, options):
    result = load(local_data, **options)
    assert_unpublished(result)
    assert "private-invalid-time" not in json.dumps(result)
