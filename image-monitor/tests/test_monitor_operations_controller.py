"""Run local work checks and explicit completion on one owned monitor worker."""

import json
import threading
from datetime import timedelta

import pytest
from test_monitor_controller import NOW, Clock, persist
from test_saved_catalog_controller import FIRST, SECOND
from test_saved_catalog_controller import snapshot as catalog_snapshot

from image_monitor.monitor_controller import MONITOR_SCOPE, MonitorController
from image_monitor.queue import QueueError, QueueStore
from image_monitor.watch_store import WatchStore

COUNT_KEYS = (
    "candidate_uninspected",
    "save_ready",
    "save_planned",
    "save_active",
    "save_completed",
    "save_unavailable",
    "save_needs_review",
)


def operations_snapshot(*, can_finish=False, count=1, wait_until=None):
    result = {
        "status": "ready",
        "reason": "candidate_detail_required",
        "error_type": None,
        **dict.fromkeys(COUNT_KEYS, 0),
        "candidate_uninspected": count,
        "wait_until": wait_until,
        "can_finish": can_finish,
        "rows": [
            {
                "order": 1,
                "status": "candidate_uninspected",
                "reason": "candidate_detail_required",
                "image_count": None,
            }
        ],
        "rows_omitted": 0,
    }
    if can_finish:
        result.update(
            status="needs_review",
            reason="completed_save_can_finish",
            candidate_uninspected=0,
            save_ready=1,
            save_needs_review=1,
            rows=[
                {
                    "order": 1,
                    "status": "save_needs_review",
                    "reason": "save_requires_review",
                    "image_count": 1,
                },
                {
                    "order": 2,
                    "status": "save_ready",
                    "reason": "save_ready",
                    "image_count": 1,
                },
            ],
        )
    return result


def finish_report(**changes):
    return {
        "schema_version": 1,
        "mode": "completed_monitor_batch_local_finish",
        "status": "batch_finish_completed",
        "last_stage": "complete",
        "error_type": None,
        "reason": "completed_files_reverified_and_batch_resolved",
        "files_verified": 1,
        "tasks_completed": 1,
        "saved_files": [],
        **changes,
    }


@pytest.fixture
def controllers():
    values = []
    yield values
    for value in values:
        value.stop()
        assert value.wait_stopped(3), "A local monitor operations worker leaked"


def create(controllers, root, *, operations_loader=None, finish_runner=None, **options):
    def forbidden(*_args, **_kwargs):
        pytest.fail("A local operations action started browser work")

    value = MonitorController(
        root,
        save_root=options.pop("save_root", root.parent / "legacy"),
        batch_root=options.pop("batch_root", root.parent / "batch"),
        operations_loader=operations_loader or (lambda *_args, **_kwargs: operations_snapshot()),
        finish_runner=finish_runner or forbidden,
        catalog_loader=options.pop("catalog_loader", lambda *_args, **_kwargs: catalog_snapshot()),
        run_cycle=options.pop("run_cycle", forbidden),
        run_details=forbidden,
        clock=options.pop("clock", Clock()),
        **options,
    )
    controllers.append(value)
    return value


@pytest.mark.parametrize("configured", [False, True])
def test_opening_and_disabled_actions_do_not_check_or_finish_existing_work(
    tmp_path, controllers, configured
):
    calls = []
    value = create(
        controllers,
        tmp_path / "watch",
        save_root=tmp_path / "legacy" if configured else None,
        batch_root=None,
        operations_loader=lambda *_args, **_kwargs: calls.append("operations"),
        finish_runner=lambda *_args, **_kwargs: calls.append("finish"),
    )
    before = value.status()
    assert before["operations_status"] == "disabled"
    assert before["operations_counts"] == dict.fromkeys(COUNT_KEYS, 0)
    assert before["operations_can_finish"] is False
    assert value.refresh_operations() == before
    with pytest.raises(QueueError):
        value.finish_completed()
    assert calls == [] and not value.is_alive()
    assert list(tmp_path.iterdir()) == [tmp_path / "watch"]
    assert not (tmp_path / "watch" / "watch.sqlite").exists()


def test_enabled_startup_is_inert_and_read_only_check_owns_a_background_thread(
    tmp_path, controllers
):
    root, clock = tmp_path / "watch", Clock()
    persist(root, clock, added=("101", "102"))
    with QueueStore(root / "watch.sqlite", read_only=True) as queue:
        before = WatchStore(queue).get_state(MONITOR_SCOPE)
        candidates = WatchStore(queue).list_candidates(MONITOR_SCOPE)
    entered, release = threading.Event(), threading.Event()
    calls = []

    def load(watch, legacy, batch, *, now, should_stop):
        calls.append((watch, legacy, batch, now, threading.get_ident(), should_stop))
        entered.set()
        assert release.wait(3)
        return operations_snapshot()

    value = create(controllers, root, operations_loader=load, clock=clock)
    assert calls == [] and not value.is_alive()
    assert value.status()["operations_status"] == "empty"
    initial = value.status()
    value.refresh_operations()
    try:
        assert entered.wait(3)
        active = value.status()
        assert active["task_kind"] == "operations"
        assert active["phase"] == "verifying_operations"
        assert active["operations_status"] == "checking"
        assert active["operations_can_finish"] is False
        assert active["browser_closed"] is True
        assert not (tmp_path / "legacy").exists() and not (tmp_path / "batch").exists()
    finally:
        release.set()
    assert value.wait_stopped(3)
    result = value.status()
    assert result["phase"] == "stopped" and result["operations_status"] == "ready"
    assert result["operations_counts"]["candidate_uninspected"] == 1
    assert calls[0][:4] == (root, tmp_path / "legacy", tmp_path / "batch", NOW)
    assert calls[0][4] != threading.get_ident()
    assert calls[0][5].__self__ is value
    for key in ("completed_cycles", "new_candidates", "last_scan_at", "baseline_initialized"):
        assert result[key] == initial[key]
    with QueueStore(root / "watch.sqlite", read_only=True) as queue:
        assert WatchStore(queue).get_state(MONITOR_SCOPE) == before
        assert WatchStore(queue).list_candidates(MONITOR_SCOPE) == candidates
        assert queue.summary()["posts"] == queue.summary()["jobs"] == 0


def test_snapshots_copy_counts_and_rows_and_only_expose_anonymous_metadata(tmp_path, controllers):
    loaded = operations_snapshot(wait_until=(NOW + timedelta(seconds=60)).isoformat())
    loaded["private_path"] = "Invented private path"
    loaded["rows"][0]["post_url"] = "https://private.example/post"
    clock = Clock()
    value = create(
        controllers,
        tmp_path / "watch",
        operations_loader=lambda *_args, **_kwargs: loaded,
        clock=clock,
    )
    value.refresh_operations()
    assert value.wait_stopped(3)
    result = value.status()
    assert result["operations_remaining_seconds"] == 60
    assert "private" not in json.dumps(result)
    loaded["candidate_uninspected"] = 99
    loaded["rows"][0]["image_count"] = 99
    result["operations_counts"]["candidate_uninspected"] = 88
    result["operations_rows"][0]["order"] = 88
    current = value.status()
    assert current["operations_counts"]["candidate_uninspected"] == 1
    assert current["operations_rows"][0]["image_count"] is None
    assert current["operations_rows"][0]["order"] == 1
    clock.advance(17)
    assert value.status()["operations_remaining_seconds"] == 43


@pytest.mark.parametrize("action", ["refresh_operations", "refresh_overview"])
@pytest.mark.parametrize("cancel", ["stop", "pause"])
def test_cancelled_read_only_work_discards_late_results_and_cannot_resume_discovery(
    tmp_path, controllers, action, cancel
):
    entered, release = threading.Event(), threading.Event()
    calls = []

    def load(*_args, now, should_stop):
        calls.append(threading.get_ident())
        entered.set()
        assert release.wait(3)
        assert should_stop()
        return operations_snapshot(can_finish=True)

    value = create(controllers, tmp_path / "watch", operations_loader=load)
    getattr(value, action)()
    try:
        assert entered.wait(3)
        getattr(value, cancel)()
        before = value.status()
        value.start()
        value.start()
        assert value.status()["phase"] == before["phase"]
        assert value._requested_stop()
        for other in (value.refresh_operations, value.refresh_overview, value.finish_completed):
            with pytest.raises(QueueError):
                other()
    finally:
        release.set()
    assert value.wait_stopped(3)
    status = value.status()
    assert status["phase"] == "stopped"
    assert status["operations_status"] == "cancelled"
    assert status["operations_reason"] == "requested_stop"
    assert status["operations_can_finish"] is False
    assert status["operations_rows"] == []
    assert status["operations_counts"] == dict.fromkeys(COUNT_KEYS, 0)
    assert value.saved_image(FIRST) is None
    assert len(calls) == 1


@pytest.mark.parametrize("action", ["refresh_operations", "refresh_overview"])
@pytest.mark.parametrize("browser_closed", [False, None, True])
def test_read_only_checks_can_explain_sticky_review_without_clearing_it(
    tmp_path, controllers, action, browser_closed
):
    value = create(controllers, tmp_path / "watch")
    value._set(
        phase="needs_review",
        reason="stored_monitor_data_invalid",
        error_type="QueueError",
        browser_closed=browser_closed,
    )
    getattr(value, action)()
    assert value.wait_stopped(3)
    status = value.status()
    assert status["phase"] == "needs_review"
    assert status["reason"] == "stored_monitor_data_invalid"
    assert status["error_type"] == "QueueError"
    assert status["browser_closed"] is browser_closed
    assert status["operations_status"] == "ready"
    with pytest.raises(QueueError):
        value.start()


def test_overview_revokes_old_images_and_publishes_both_checks_atomically(tmp_path, controllers):
    entered, release = threading.Event(), threading.Event()
    calls = []
    generation = 0

    def operations(*_args, **_kwargs):
        calls.append(("operations", threading.get_ident()))
        return operations_snapshot(count=generation + 1)

    def catalog(*_args, **_kwargs):
        calls.append(("catalog", threading.get_ident()))
        if generation:
            entered.set()
            assert release.wait(3)
            return catalog_snapshot(image_id=SECOND)
        return catalog_snapshot()

    value = create(
        controllers, tmp_path / "watch", operations_loader=operations, catalog_loader=catalog
    )
    value.refresh_overview()
    assert value.wait_stopped(3)
    assert value.saved_image(FIRST) is not None
    generation = 1
    value.refresh_overview()
    try:
        assert entered.wait(3)
        current = value.status()
        assert current["phase"] == "verifying_overview"
        assert current["task_kind"] == "overview"
        assert current["operations_status"] == current["saved_status"] == "checking"
        assert current["operations_rows"] == current["saved_files"] == []
        assert value.saved_image(FIRST) is value.saved_image(SECOND) is None
    finally:
        release.set()
    assert value.wait_stopped(3)
    current = value.status()
    assert current["operations_counts"]["candidate_uninspected"] == 2
    assert current["operations_status"] == current["saved_status"] == "ready"
    assert value.saved_image(FIRST) is None and value.saved_image(SECOND) is not None
    assert [kind for kind, _thread in calls] == ["operations", "catalog"] * 2
    assert calls[0][1] == calls[1][1] and calls[2][1] == calls[3][1]
    assert all(worker != threading.get_ident() for _kind, worker in calls)


def test_cancelling_overview_during_catalog_discards_both_late_snapshots(tmp_path, controllers):
    entered, release = threading.Event(), threading.Event()

    def catalog(*_args, should_stop, **_kwargs):
        entered.set()
        assert release.wait(3)
        assert should_stop()
        return catalog_snapshot()

    value = create(
        controllers,
        tmp_path / "watch",
        operations_loader=lambda *_args, **_kwargs: operations_snapshot(can_finish=True),
        catalog_loader=catalog,
    )
    value.refresh_overview()
    try:
        assert entered.wait(3)
        value.stop()
    finally:
        release.set()
    assert value.wait_stopped(3)
    status = value.status()
    assert status["operations_status"] == status["saved_status"] == "cancelled"
    assert status["operations_can_finish"] is False
    assert status["operations_rows"] == status["saved_files"] == []
    assert status["operations_counts"] == dict.fromkeys(COUNT_KEYS, 0)
    assert value.saved_image(FIRST) is None


@pytest.mark.parametrize("browser_closed", [False, None])
def test_explicit_finish_requires_confirmed_browser_closure(tmp_path, controllers, browser_closed):
    value = create(
        controllers,
        tmp_path / "watch",
        operations_loader=lambda *_args, **_kwargs: operations_snapshot(can_finish=True),
    )
    value.refresh_operations()
    assert value.wait_stopped(3)
    assert value.status()["operations_can_finish"] is True
    value._set(browser_closed=browser_closed)
    with pytest.raises(QueueError):
        value.finish_completed()
    assert not value.is_alive()


def test_finish_requires_a_cached_gate_and_rechecks_it_before_calling_runner(tmp_path, controllers):
    calls = []

    def operations(*_args, **_kwargs):
        calls.append("operations")
        return operations_snapshot(can_finish=len(calls) == 1)

    def finish(*_args, **_kwargs):
        calls.append("finish")
        return finish_report()

    value = create(
        controllers, tmp_path / "watch", operations_loader=operations, finish_runner=finish
    )
    with pytest.raises(QueueError):
        value.finish_completed()
    assert calls == []
    value.refresh_operations()
    assert value.wait_stopped(3)
    assert value.status()["operations_can_finish"] is True
    value.finish_completed()
    assert value.wait_stopped(3)
    assert calls == ["operations", "operations"]
    assert value.status()["operations_can_finish"] is False
    assert value.status()["phase"] == "stopped"


def test_stop_during_finish_preflight_never_calls_the_finish_runner(tmp_path, controllers):
    entered, release = threading.Event(), threading.Event()
    calls = []

    def operations(*_args, should_stop, **_kwargs):
        calls.append("operations")
        if len(calls) == 2:
            entered.set()
            assert release.wait(3)
            assert should_stop()
        return operations_snapshot(can_finish=True)

    value = create(controllers, tmp_path / "watch", operations_loader=operations)
    value.refresh_operations()
    assert value.wait_stopped(3)
    value.finish_completed()
    try:
        assert entered.wait(3)
        value.stop()
        value.start()
        assert value._requested_stop()
    finally:
        release.set()
    assert value.wait_stopped(3)
    status = value.status()
    assert calls == ["operations", "operations"]
    assert status["operations_finish_status"] == "batch_finish_cancelled"
    assert status["operations_finish_reason"] == "cancelled"
    assert status["operations_status"] == "cancelled"
    assert status["operations_can_finish"] is False


@pytest.mark.parametrize("review", [False, True])
@pytest.mark.parametrize("cancel", [None, "stop", "pause"])
def test_finish_is_explicit_single_worker_and_retains_a_completed_late_report(
    tmp_path, controllers, cancel, review
):
    entered, release = threading.Event(), threading.Event()
    calls = []
    root = tmp_path / "watch"

    def operations(watch, legacy, batch, *, now, should_stop):
        assert (watch, legacy, batch) == (root, tmp_path / "legacy", tmp_path / "batch")
        assert now == NOW
        calls.append(("operations", threading.get_ident()))
        return operations_snapshot(can_finish=len(calls) <= 2)

    def catalog(watch, legacy, *, batch_root, should_stop):
        assert (watch, legacy, batch_root) == (root, tmp_path / "legacy", tmp_path / "batch")
        calls.append(("catalog", threading.get_ident()))
        return catalog_snapshot(image_id=SECOND)

    def finish(watch, legacy, batch, *, should_stop):
        assert (watch, legacy, batch) == (root, tmp_path / "legacy", tmp_path / "batch")
        calls.append(("finish", threading.get_ident()))
        entered.set()
        assert release.wait(3)
        assert should_stop() is (cancel is not None)
        return finish_report(private_path="Invented private finish path")

    value = create(
        controllers,
        root,
        operations_loader=operations,
        finish_runner=finish,
        catalog_loader=catalog,
    )
    value.refresh_saved()
    assert value.wait_stopped(3)
    assert value.saved_image(SECOND) is not None
    calls.clear()
    value.refresh_operations()
    assert value.wait_stopped(3)
    assert [kind for kind, _thread in calls] == ["operations"]
    if review:
        value._set(
            phase="needs_review", reason="stored_monitor_data_invalid", error_type="QueueError"
        )
    value.finish_completed()
    try:
        assert entered.wait(3)
        status = value.status()
        assert status["phase"] == "finishing_completed" and status["task_kind"] == "finish"
        assert status["operations_can_finish"] is False
        assert value.saved_image(SECOND) is None
        assert status["saved_files"] == []
        with pytest.raises(QueueError):
            value.finish_completed()
        if cancel is not None:
            getattr(value, cancel)()
            before = value.status()
            value.start()
            assert value._requested_stop()
            assert value.status()["phase"] == before["phase"]
    finally:
        release.set()
    assert value.wait_stopped(3)
    status = value.status()
    assert status["phase"] == ("needs_review" if review else "stopped")
    if review:
        assert status["reason"] == "stored_monitor_data_invalid"
        assert status["error_type"] == "QueueError"
    assert status["operations_finish_status"] == "batch_finish_completed"
    assert status["operations_finish_reason"] == "completed_files_reverified_and_batch_resolved"
    assert status["operations_finish_files_verified"] == 1
    assert "private" not in json.dumps(status)
    expected = ["operations", "operations", "finish"]
    if cancel is None:
        expected += ["operations", "catalog"]
    assert [kind for kind, _thread in calls] == expected
    assert len({worker for _kind, worker in calls[1:]}) == 1
    assert all(worker != threading.get_ident() for _kind, worker in calls)


@pytest.mark.parametrize("invalid", ["exception", "status", "reason", "row", "count"])
def test_failed_or_untrusted_operations_never_publish_private_or_partial_state(
    tmp_path, controllers, invalid
):
    loaded = operations_snapshot()
    if invalid == "status":
        loaded["status"] = "Invented private status"
    elif invalid == "reason":
        loaded["reason"] = "https://private.example/path"
    elif invalid == "row":
        loaded["rows"][0]["reason"] = {"private_path": "C:/private"}
    elif invalid == "count":
        loaded["save_ready"] = True

    def operations(*_args, **_kwargs):
        if invalid == "exception":
            raise OSError("Invented private path and https://private.example")
        return loaded

    value = create(controllers, tmp_path / "watch", operations_loader=operations)
    value.refresh_operations()
    assert value.wait_stopped(3)
    status = value.status()
    assert status["phase"] == "stopped"
    assert status["operations_status"] == "needs_review"
    assert status["operations_reason"] == "operations_require_review"
    assert status["operations_can_finish"] is False
    assert status["operations_rows"] == []
    assert status["operations_counts"] == dict.fromkeys(COUNT_KEYS, 0)
    assert "private" not in json.dumps(status)


def test_finish_exception_is_sanitized_and_does_not_retain_the_old_finish_gate(
    tmp_path, controllers
):
    def finish(*_args, **_kwargs):
        raise OSError("Invented private path and https://private.example")

    value = create(
        controllers,
        tmp_path / "watch",
        operations_loader=lambda *_args, **_kwargs: operations_snapshot(can_finish=True),
        finish_runner=finish,
    )
    value.refresh_operations()
    assert value.wait_stopped(3)
    value.finish_completed()
    assert value.wait_stopped(3)
    status = value.status()
    assert status["operations_finish_status"] == "batch_finish_manual_review"
    assert status["operations_finish_reason"] == "completed_batch_requires_review"
    assert status["operations_finish_error_type"] == "OSError"
    assert status["operations_finish_files_verified"] == 0
    assert status["operations_can_finish"] is False
    assert "private" not in json.dumps(status)


@pytest.mark.parametrize("failure", ["operations", "catalog"])
def test_a_failed_followup_check_cannot_erase_an_actual_successful_finish(
    tmp_path, controllers, failure
):
    calls = []

    def operations(*_args, **_kwargs):
        calls.append("operations")
        if len(calls) > 2 and failure == "operations":
            raise OSError("Invented private followup path")
        return operations_snapshot(can_finish=True)

    def catalog(*_args, **_kwargs):
        calls.append("catalog")
        raise OSError("Invented private followup path")

    value = create(
        controllers,
        tmp_path / "watch",
        operations_loader=operations,
        catalog_loader=catalog,
        finish_runner=lambda *_args, **_kwargs: finish_report(),
    )
    value.refresh_operations()
    assert value.wait_stopped(3)
    value.finish_completed()
    assert value.wait_stopped(3)
    status = value.status()
    assert status["operations_finish_status"] == "batch_finish_completed"
    assert status["operations_finish_reason"] == "completed_files_reverified_and_batch_resolved"
    assert status["operations_finish_files_verified"] == 1
    assert status["operations_finish_error_type"] is None
    assert status["operations_status"] == "needs_review"
    assert status["operations_can_finish"] is False
    assert "private" not in json.dumps(status)
    assert calls == ["operations"] * 3 + (["catalog"] if failure == "catalog" else [])


def test_save_only_overview_keeps_the_existing_catalog_call_signature(tmp_path, controllers):
    calls = []

    def catalog(watch, legacy, *, should_stop):
        calls.append((watch, legacy, should_stop))
        return catalog_snapshot()

    value = create(
        controllers,
        tmp_path / "watch",
        batch_root=None,
        catalog_loader=catalog,
        operations_loader=lambda *_args, **_kwargs: pytest.fail("Disabled operations ran"),
    )
    value.refresh_overview()
    assert value.wait_stopped(3)
    assert value.status()["saved_status"] == "ready"
    assert value.status()["operations_status"] == "disabled"
    assert len(calls) == 1 and calls[0][:2] == (tmp_path / "watch", tmp_path / "legacy")
    assert calls[0][2].__self__ is value


def test_discovery_start_never_implicitly_loads_operations_or_finishes(tmp_path, controllers):
    calls = []

    def cycle(*_args, **_kwargs):
        calls.append("list")
        value.stop()
        return {
            "status": "watch_test_cancelled",
            "cycles_completed": 0,
            "new_candidates": 0,
            "browser_closed": True,
        }

    value = create(
        controllers,
        tmp_path / "watch",
        operations_loader=lambda *_args, **_kwargs: calls.append("operations"),
        finish_runner=lambda *_args, **_kwargs: calls.append("finish"),
        run_cycle=cycle,
    )
    value.start()
    assert value.wait_stopped(3)
    assert calls == ["list"]
    assert value.status()["phase"] == "stopped"
