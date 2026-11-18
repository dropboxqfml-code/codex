"""Real frozen saves reach the operations screen without collection or repair."""

import json
import sys
import threading
from contextlib import nullcontext
from datetime import timedelta
from types import SimpleNamespace

import pytest
from test_candidate_finish_runtime import database_dump
from test_monitor_batch_runtime import data as data
from test_monitor_batch_runtime import ledger
from test_saved_catalog_batch import complete_with_legacy, disk_bytes
from test_saved_catalog_integration import browser as browser
from test_saved_catalog_integration import local_only_context

from image_monitor import monitor_operations, saved_catalog
from image_monitor.monitor_app import MonitorServer, share_monitor_report
from image_monitor.monitor_controller import MonitorController
from image_monitor.queue import QueueStore
from image_monitor.watch_store import WatchStore


@pytest.mark.parametrize("blocked", [False, True])
def test_real_overview_shows_two_completed_saves_and_one_uninspected_candidate(
    data, monkeypatch, browser, blocked
):
    from playwright.sync_api import expect

    complete_with_legacy(data)
    with QueueStore(data.watch / "watch.sqlite") as queue:
        watch = WatchStore(queue)
        state = watch.get_state(monitor_operations.MONITOR_SCOPE)
        now = data.clock.now()
        watch.persist_scan(
            monitor_operations.MONITOR_SCOPE,
            observed_at=now,
            expected_generation=state["generation"],
            scan_result={
                "mode": "invented_operations_fixture",
                "control": {
                    "finished_at": now.isoformat(),
                    "blocked": False,
                    "interval_seconds": 60,
                    "next_eligible_at": (now + timedelta(seconds=60)).isoformat(),
                },
            },
            candidates=[
                {
                    "post_id": "203",
                    "post_url": "https://gall.dcinside.com/board/view/?id=comic_new6&no=203",
                    "title": "Invented uninspected fixture",
                    "shown_metadata": {"baseline_observed_at": state["baseline"]["observed_at"]},
                }
            ],
            checkpoint=state["baseline"] | {"anchor_ids": ["203", "202", "201", "200"]},
            complete=True,
        )
    if blocked:
        with ledger(data, readonly=False) as store:
            task = store.list_tasks()[0]
            store.update_control(task["task_id"], {"blocked": True})
    for module in (monitor_operations, saved_catalog):
        monkeypatch.setattr(module, "NativeSaveLock", nullcontext)
        monkeypatch.setattr(module, "shared_state_path", lambda: data.marker)
        monkeypatch.setattr(module, "session_id", lambda: 1)
    before = disk_bytes(data)
    databases = {
        path: database_dump(path)
        for path in data.root.rglob("*.sqlite")
        if path.name in {"watch.sqlite", "queue.sqlite"}
    }

    def forbidden(*_args, **_kwargs):
        pytest.fail("Reviewing existing work started collection or reconciliation")

    controller = MonitorController(
        data.watch,
        save_root=data.legacy,
        batch_root=data.batch,
        clock=SimpleNamespace(now=lambda: data.clock.now() + timedelta(days=1)),
        run_cycle=forbidden,
        run_details=forbidden,
        finish_runner=forbidden,
    )
    server = MonitorServer(controller)
    serving = threading.Thread(target=server.serve, daemon=True)
    serving.start()
    context, page, _requests, external, downloads = local_only_context(browser, server)
    try:
        controller.refresh_overview()
        assert controller.wait_stopped(10)
        assert controller.status()["operations_counts"]["candidate_uninspected"] == 1, json.dumps(
            controller.status()
        )
        page.goto(server.url, wait_until="domcontentloaded")
        expect(page.locator("#operation-candidate-uninspected")).to_have_text("1")
        expect(page.locator("#operation-save-completed")).to_have_text("2")
        expect(page.get_by_role("button", name="완료 상태 다시 확인", exact=True)).to_be_disabled()
        expect(page.locator("#saved-files img")).to_have_count(2)
        page.wait_for_function(
            """() => [...document.querySelectorAll('#saved-files img')]
                .every(image => image.complete && image.naturalWidth > 0)"""
        )
        if blocked:
            expect(page.locator("#operations-help")).to_contain_text("접근 제한")
        page.get_by_role("button", name="작업 현황 새로 확인", exact=True).click()
        expect(page.get_by_role("button", name="작업 현황 새로 확인", exact=True)).to_be_enabled()
        assert controller.wait_stopped(10)
        state = controller.status()
        assert state["operations_counts"]["save_completed"] == 2
        assert state["operations_counts"]["candidate_uninspected"] == 1
        assert not state["operations_can_finish"]
        assert state["completed_cycles"] == state["new_candidates"] == 0
        public = share_monitor_report({"status": "monitor_closed", "monitor_status": state})
        encoded = json.dumps(public)
        assert str(data.root) not in encoded and "preview_id" not in encoded
        assert not external and not downloads
        if sys.platform != "win32" and not blocked:
            page.screenshot(path="/tmp/im-v23-real-overview.png", full_page=True)
        page.get_by_role("button", name="프로그램 종료", exact=True).click()
        serving.join(5)
        assert not serving.is_alive()
    finally:
        context.close()
        controller.stop()
        assert controller.wait_stopped(10)
        server.closing.set()
        serving.join(5)
        server.server_close()
    assert disk_bytes(data) == before
    assert {path: database_dump(path) for path in databases} == databases
