"""The dashboard save button drives one batch task and reloads its verified image."""

import json
import sys
import threading
from contextlib import nullcontext
from datetime import timedelta

import pytest
from test_monitor_batch_runtime import Runner
from test_monitor_batch_runtime import data as data
from test_saved_catalog_integration import browser as browser
from test_saved_catalog_integration import local_only_context

from image_monitor import monitor_operations, saved_catalog
from image_monitor.monitor_app import MonitorServer
from image_monitor.monitor_batch_runtime import run_monitor_batch
from image_monitor.monitor_controller import MonitorController
from image_monitor.monitor_save_action import _single_result, run_dashboard_save


@pytest.mark.skipif(sys.platform != "win32", reason="The actual dashboard child runs on Windows")
def test_real_child_returns_anonymous_no_work_result_for_empty_watch(tmp_path):
    watch, legacy, batch = (tmp_path / name for name in ("watch", "legacy", "batch"))
    result = run_dashboard_save(watch, legacy, batch)
    assert result == {
        "status": "monitor_batch_no_candidates",
        "reason": "existing_watch_required",
        "tasks_started": 0,
        "tasks_completed": 0,
        "files_verified": 0,
        "browser_closed": True,
    }
    [report] = (batch / "batch-runs").glob("*/report.json")
    assert json.loads(report.read_text(encoding="utf-8"))["max_tasks"] == 1
    assert not watch.exists() and not legacy.exists()


def test_one_click_processes_one_task_and_refreshes_its_preview(data, browser, monkeypatch):
    from playwright.sync_api import expect

    for module in (monitor_operations, saved_catalog):
        monkeypatch.setattr(module, "NativeSaveLock", nullcontext)
        monkeypatch.setattr(module, "shared_state_path", lambda: data.marker)
        monkeypatch.setattr(module, "session_id", lambda: 1)
    data.clock.current += timedelta(minutes=5)
    worker = Runner(data)

    def save_one(watch, legacy, batch, *, should_stop):
        assert not should_stop()
        return _single_result(
            run_monitor_batch(
                watch, legacy, batch, max_tasks=1, clock=data.clock, save_runner=worker
            )
        )

    controller = MonitorController(
        data.watch,
        save_root=data.legacy,
        batch_root=data.batch,
        clock=data.clock,
        save_runner=save_one,
    )
    server = MonitorServer(controller)
    serving = threading.Thread(target=server.serve, daemon=True)
    serving.start()
    context, page, _, external, downloads = local_only_context(browser, server)
    try:
        controller.refresh_overview()
        assert controller.wait_stopped(10)
        page.goto(server.url, wait_until="domcontentloaded")
        button = page.get_by_role("button", name="후보 1건 저장", exact=True)
        expect(page.locator("#operation-save-ready")).to_have_text("2")
        for completed in (1, 2):
            with page.expect_response(
                lambda response: (
                    response.url == server.url + "api/action" and response.request.method == "POST"
                )
            ) as action:
                button.click()
            assert action.value.ok
            # Wait for the disk-backed save and preview refresh before checking the next UI poll.
            assert controller.wait_stopped(30)
            state = controller.status()
            assert len(worker.calls) == completed
            assert state["phase"] == "stopped" and state["completed_cycles"] == 0
            assert state["operations_save_status"] == "monitor_batch_completed"
            assert state["operations_save_tasks_completed"] == 1
            assert state["operations_save_files_verified"] == worker.calls[-1][2].image_count
            expect(page.locator("#operation-save-completed")).to_have_text(str(completed))
            expected_files = sum(permit.image_count for _, _, permit in worker.calls)
            expect(page.locator("#saved-files img")).to_have_count(expected_files)
            page.wait_for_function(
                """() => [...document.querySelectorAll('#saved-files img')]
                    .every(img => img.complete && img.naturalWidth > 0)"""
            )
            expect(button).to_be_disabled()
            data.clock.current += timedelta(minutes=2)
        assert not external and not downloads
    finally:
        context.close()
        controller.stop()
        server.closing.set()
        serving.join(5)
        server.server_close()
        assert controller.wait_stopped(10) and not serving.is_alive()
