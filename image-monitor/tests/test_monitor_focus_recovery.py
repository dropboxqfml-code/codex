"""Resume the original unattempted focus-failure task among a 40-post backlog."""

from collections import deque
from datetime import UTC, datetime, timedelta

import pytest
from test_monitor_auto_session_integration import auto_session, listing, local_workers
from test_monitor_auto_session_integration import session_data as session_data
from test_monitor_batch_runtime import ledger
from test_monitor_collect_integration import saved_content
from test_monitor_gap_continuation import run_scan
from test_monitor_resume_once_integration import partial_pages
from test_post_worker import pilot as pilot
from test_watch_runtime import FakeClock, link, observed, snapshot

from image_monitor import monitor_collect, post_worker
from image_monitor.browser_completion import BrowserCompletionError
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.queue import QueueStore
from image_monitor.watch_store import MONITOR_SCOPE


def source_unfocused(_self):
    raise BrowserCompletionError("The source document did not have focus")


@pytest.mark.parametrize("entry_point", ["one_shot", "automatic"])
def test_reopen_partial_scan_with_focus_failure_saves_original_job_once(
    monkeypatch, pilot, session_data, entry_point
):
    data = session_data
    clock = FakeClock(datetime.now(UTC) + timedelta(seconds=62))
    events, browsers = [], []
    detail, save = local_workers(monkeypatch, pilot, clock, events, browsers)
    partial = partial_pages(245)
    pages = deque([listing(201, 200), partial])
    roots = data.watch, data.legacy, data.batch
    session = auto_session(roots, clock, pages, events, browsers, detail, save)

    baseline = observed(lambda stamp: snapshot([200], stamp, links=[link()]))
    assert run_scan(data.watch, clock, baseline)["status"] == "watch_test_completed"
    assert session(max_cycles=1)["files_verified"] == 1
    prior_files = saved_content(data)
    assert len(prior_files) == 2
    with monkeypatch.context() as fault:
        fault.setattr(post_worker.BrowserCompletion, "__enter__", source_unfocused)
        failed = session(max_cycles=1)
    assert failed["status"] == "auto_monitor_review", failed
    assert failed["cycles_completed"] == failed["files_verified"] == failed["posts_saved"] == 0
    assert failed["partial_list_checks"] == failed["new_details_checked"] == 1
    assert failed["new_candidates"] == 40 and failed["browser_closed"]
    assert failed["last_collection"]["completion_setup_reason"] == "source_document_unfocused"
    assert failed["last_collection"]["worker_last_stage"] == "completion_setup"
    with ledger(data) as store:
        [task] = [t for t in store.list_tasks() if t["status"] == "needs_review"]
        previous = store.get_for_post("201")
    base = data.batch / "tasks" / task["task_id"] / "session-1"
    [report] = (base / "runs").glob("*/report.json")
    original_report = report.read_bytes()
    with QueueStore(base / "queue.sqlite", read_only=True) as queue:
        [job] = queue.list_jobs()
        assert job["status"] == "queued" and not queue.history(job["job_id"])
        assert not queue.list_artifacts()
    with QueueStore(data.watch / "watch.sqlite", read_only=True) as queue:
        details = CandidateDetailStore(queue)
        prior_details = details.list_details(MONITOR_SCOPE)
        pending = details.list_pending(MONITOR_SCOPE, limit=100)
    assert len(pending) == 39 and len(prior_details) == 2
    assert not data.marker.exists() and not pages
    events.clear()

    if entry_point == "one_shot":
        recovered = monitor_collect.run_monitor_collect(
            *roots, clock=clock, detail_runner=detail, save_runner=save
        )
        assert recovered["status"] == "monitor_collect_saved", recovered
        assert recovered["setup_retry_started"]
        assert (
            recovered["search"]["previous_completion_setup_reason"] == "source_document_unfocused"
        )
        assert [(kind, post) for kind, post, _ in events] == [("save", task["post_id"])]
    else:
        pages.append(partial)
        recovered = session(max_cycles=1)
        assert recovered["status"] == "auto_monitor_completed", recovered
        assert recovered["last_collection"]["setup_retry_started"]
        assert recovered["posts_saved"] == recovered["cycles_completed"] == 1
        assert recovered["new_candidates"] == 0
        assert [(kind, post) for kind, post, _ in events] == [
            ("list", "245"),
            ("save", task["post_id"]),
        ]
    assert recovered["new_details_checked"] == 0 and recovered["browser_closed"]
    assert recovered["files_verified"] == recovered["native_save_tasks_started"] == 1
    assert not pages and all(browser.browser_closed for browser in browsers)
    assert not data.marker.exists() and report.read_bytes() == original_report
    assert len(list((base / "runs").glob("*/report.json"))) == 2
    assert len(pilot.saves) == 2
    with ledger(data) as store:
        assert store.get_for_post("201") == previous
        recovered_task = store.get_task(task["task_id"])
        assert recovered_task["status"] == "completed"
        assert recovered_task["control"]["setup_retry"]["prior_run"] == report.parent.name
    with QueueStore(base / "queue.sqlite", read_only=True) as queue:
        [finished] = queue.list_jobs()
        assert finished["status"] == "completed" and finished["job_id"] == job["job_id"]
        [artifact] = queue.list_artifacts()
        assert artifact["job_id"] == finished["job_id"]
    with QueueStore(data.watch / "watch.sqlite", read_only=True) as queue:
        details = CandidateDetailStore(queue)
        assert details.list_details(MONITOR_SCOPE) == prior_details
        pending_after = details.list_pending(MONITOR_SCOPE, limit=100)
        assert [p["post_id"] for p in pending_after] == [p["post_id"] for p in pending]
    output = saved_content(data)
    assert len(output) == 4 and all(output[p] == v for p, v in prior_files.items())
    assert {p.parent.name for p in output.keys() - prior_files.keys()} == {task["post_id"]}
