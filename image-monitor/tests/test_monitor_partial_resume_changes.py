"""Changes after choosing a partial post must never send an unproved image save."""

import pytest
from PIL import Image
from test_monitor_auto_session_integration import session_data as session_data
from test_monitor_batch_runtime import ledger
from test_monitor_ten_images_integration import (
    lose_foreground_between_files,
    post_base,
    saved_post,
    scan,
)
from test_monitor_ten_images_integration import monitor as monitor
from test_post_worker import pilot as pilot

from image_monitor import monitor_collect, post_worker
from image_monitor.queue import QueueStore


def queue_state(base):
    with QueueStore(base / "queue.sqlite", read_only=True) as queue:
        jobs = sorted(queue.list_jobs(), key=lambda row: row["file_slot"])
        histories = [queue.history(job["job_id"]) for job in jobs]
        return jobs, histories, queue.list_artifacts()


@pytest.fixture
def interrupted(monitor, pilot, monkeypatch):
    scan(monitor, 202, 200)
    with monkeypatch.context() as focus:
        lose_foreground_between_files(focus, pilot, completed=6)
        failure = monitor.collect()
    assert failure["status"] == "monitor_collect_review", failure
    assert failure["save"]["worker_last_stage"] == "pre_input_check"
    assert failure["worker_images_completed"] == len(pilot.saves) == 6
    assert failure["browser_closed"] and not monitor.data.marker.exists()
    pilot.focus_ready = True
    base = post_base(monitor.data, "202")
    with ledger(monitor.data) as db:
        [task] = db.list_tasks()
    assert task["status"] == "needs_review" and "setup_retry" not in task["control"]
    return base, task


def test_changed_final_image_after_selection_blocks_retry_before_it_is_spent(
    monitor, pilot, interrupted, monkeypatch
):
    base, original_task = interrupted
    before = queue_state(base)
    [original_report] = (base / "runs").glob("*/report.json")
    report_bytes = original_report.read_bytes()
    [first] = (base / "images").rglob("001.png")
    files = saved_post(base)
    batch = monitor_collect.run_monitor_batch

    def change_file(*args, **kwargs):
        handoff = kwargs["monitor_handoff"]
        assert handoff["retry_task_id"] == original_task["task_id"]
        assert handoff["prior_run"] == original_report.parent.name
        # Keep path, format and dimensions valid; only the recorded bytes differ.
        Image.new("RGB", (4, 3), "teal").save(first)
        assert first.read_bytes() != files[first.name][0]
        return batch(*args, **kwargs)

    with monkeypatch.context() as mutation:
        mutation.setattr(monitor_collect, "run_monitor_batch", change_file)
        rejected = monitor.collect()
    assert rejected["search"]["status"] == "ready", rejected
    assert rejected["status"] == "monitor_collect_review", rejected
    assert rejected["native_save_tasks_started"] == 0 and not rejected["partial_retry_started"]
    assert len(pilot.saves) == 6 and len(pilot.runtimes) == 1
    assert not monitor.data.marker.exists()
    assert list((base / "runs").glob("*/report.json")) == [original_report]
    assert original_report.read_bytes() == report_bytes
    with ledger(monitor.data) as db:
        assert db.list_tasks() == [original_task]
    assert queue_state(base) == before
    after = saved_post(base)
    assert set(after) == set(files) and after.pop(first.name)[0] != files.pop(first.name)[0]
    assert after == files


def test_changed_live_post_after_retry_is_spent_keeps_pending_images_untouched(
    monitor, pilot, interrupted, monkeypatch
):
    base, original_task = interrupted
    before = queue_state(base)
    files = saved_post(base)
    [first_report] = (base / "runs").glob("*/report.json")
    original_report = first_report.read_bytes()
    inspect = post_worker.NativeRuntime.inspect

    def changed_post(runtime, page, url, **options):
        with ledger(monitor.data) as db:
            current = db.get_for_post("202")
            assert current["status"] == "started"
            assert current["control"]["setup_retry"]["prior_run"] == first_report.parent.name
        live = inspect(runtime, page, url, **options)
        return live | {"title": "Different live post title"}

    with monkeypatch.context() as changed:
        changed.setattr(post_worker.NativeRuntime, "inspect", changed_post)
        rejected = monitor.collect()
    assert rejected["status"] == "monitor_collect_review", rejected
    assert rejected["native_save_tasks_started"] == 1 and rejected["partial_retry_started"]
    assert rejected["save"]["worker_last_stage"] == "post_inspection"
    assert rejected["save"]["error_type"] == "CandidateSavePolicyError", rejected
    assert rejected["files_verified"] == 0 and rejected["browser_closed"]
    assert not monitor.data.marker.exists()
    with ledger(monitor.data) as db:
        [task] = db.list_tasks()
    assert task["status"] == "needs_review" and task["task_id"] == original_task["task_id"]
    assert task["control"]["setup_retry"]["prior_run"] == first_report.parent.name

    again = monitor.collect()
    assert again["status"] == "monitor_collect_review", again
    assert again["native_save_tasks_started"] == 0 and not again["partial_retry_started"]
    assert len(pilot.saves) == 6 and len(pilot.runtimes) == 2
    assert first_report.read_bytes() == original_report
    assert len(list((base / "runs").glob("*/report.json"))) == 2
    assert saved_post(base) == files and queue_state(base) == before
    with ledger(monitor.data) as db:
        assert db.list_tasks() == [task]
