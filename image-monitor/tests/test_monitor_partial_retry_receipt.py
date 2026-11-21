"""Match the original pre-claim report to the completed on-disk image before retrying."""

import json

import pytest
from test_monitor_auto_session_integration import session_data as session_data
from test_monitor_batch_runtime import ledger
from test_monitor_ten_images_integration import monitor as monitor
from test_monitor_ten_images_integration import post_base, saved_post, scan
from test_post_worker import pilot as pilot

from image_monitor import monitor_setup_retry as retry
from image_monitor import post_worker
from image_monitor.monitor_batch_runtime import reconstruct_permit
from image_monitor.native_ui import NativeFocusError
from image_monitor.queue import QueueError, QueueStore


@pytest.fixture
def between_images(monitor, monkeypatch):
    wait = post_worker._wait_for_next_image

    def lose_focus(*args, **options):
        _, _, ui, _, _, report, _ = args
        if report["job_counts"]["completed"] == 1:

            def away():
                raise NativeFocusError("The probe page itself is not in the foreground")

            ui.assert_target_ready = away
            ui.stage = "save_dialog"
            ui.focus_snapshot = lambda: {
                "target_hwnd": 123,
                "target_exists": True,
                "foreground_hwnd": None,
                "foreground_pid": None,
                "foreground_class": None,
                "belongs_to_target": False,
                "target_foreground": False,
            }
        return wait(*args, **options)

    monkeypatch.setattr(post_worker, "_wait_for_next_image", lose_focus)
    scan(monitor, 201, 200)
    stopped = monitor.collect()
    assert stopped["status"] == "monitor_collect_review" and stopped["worker_images_completed"] == 1
    base = post_base(monitor.data, "201")
    [path] = (base / "runs").glob("*/report.json")
    with ledger(monitor.data, readonly=False) as store:
        task = store.get_for_post("201")
        with QueueStore(monitor.data.watch / "watch.sqlite", read_only=True) as watch:
            permit = reconstruct_permit(watch, task)
        yield store, task, permit, base, path, monitor.clock


def test_partial_retry_preserves_previous_receipt_and_cannot_be_consumed_twice(between_images):
    store, task, permit, base, path, clock = between_images
    before = path.read_bytes(), saved_post(base)
    run, reason, preserved = retry.verify_setup_retry(store, task, permit)
    assert run == path.parent.name and reason == retry.PARTIAL_RETRY_REASON and preserved == 1
    store.start_setup_retry(task, prior_run=run, now=clock.now())
    failed = store.finish(
        task["task_id"], status="needs_review", result=task["result"], now=clock.now()
    )
    with pytest.raises(QueueError):
        retry.verify_setup_retry(store, failed, permit)
    with pytest.raises(QueueError):
        store.start_setup_retry(task, prior_run=run, now=clock.now())
    assert before == (path.read_bytes(), saved_post(base))


@pytest.mark.parametrize(
    "change",
    ["reason", "native_stage", "counts", "saved_hash", "saved_job", "focus", "active", "released"],
)
def test_partial_retry_rejects_ambiguous_or_mismatched_worker_receipt(between_images, change):
    store, task, permit, base, path, _ = between_images
    original = saved_post(base)
    report = json.loads(path.read_bytes())
    if change == "reason":
        report["reason"] = "other"
    elif change == "native_stage":
        report["native_stage"] = "right_click"
    elif change == "counts":
        report["job_counts"]["completed"] = True
    elif change == "saved_hash":
        report["saved_files"][0]["sha256"] = "0" * 64
    elif change == "saved_job":
        report["saved_files"][0]["job_id"] = "1" * 32
    elif change == "focus":
        report["focus_at_pause"]["target_hwnd"] += 1
    elif change == "active":
        report["active_attempt"] = {"phase": "input_armed"}
    else:
        report["last_preinput_attempt"] = {"phase": "released_no_input"}
    path.write_text(json.dumps(report), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(QueueError):
        retry.verify_setup_retry(store, task, permit)
    assert store.get_task(task["task_id"]) == task
    assert path.read_bytes() == before and saved_post(base) == original
