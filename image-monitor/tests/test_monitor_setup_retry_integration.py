"""Reopen a pre-input alpha.1 task and save its original image on a second invocation."""

import hashlib
import json
import logging
import os
import shutil
import sys
import tempfile
from contextlib import ExitStack, nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
import test_windows_monitor_batch as fixtures
from test_monitor_batch_runtime import ledger, run
from test_monitor_collect_integration import saved_content
from test_post_worker import pilot as pilot
from test_windows_candidate_save import CandidatePageView
from test_windows_post_pipeline import (
    close_ci_browser,
    fixture_assets,
    foreground_ci_window,
    serve_fixtures,
)

from image_monitor import (
    candidate_finish,
    monitor_auto_selection,
    monitor_batch_runtime,
    monitor_collect,
    monitor_operations,
    monitor_setup_retry,
    post_worker,
)
from image_monitor.browser_completion import BrowserCompletionError
from image_monitor.candidate_store import CandidateDetailStore
from image_monitor.queue import QueueStore
from image_monitor.watch_store import MONITOR_SCOPE


def use_windows_browser(monkeypatch, cleanup, origin, post_url, visits):
    import psutil
    import pywinauto  # noqa: F401

    for handler in logging.getLogger("pywinauto").handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(
            handler, logging.FileHandler
        ):
            monkeypatch.setattr(handler, "stream", sys.__stderr__)

    class LocalPost(CandidatePageView):
        def goto(self, url, **options):
            assert url == post_url
            visits.append(url)
            return self._page.goto(origin + "/post-" + url.split("no=")[-1], **options)

    class Runtime(post_worker.NativeRuntime):
        def launch(self, profile, kind):
            process = super().launch(profile, kind)
            owned = psutil.Process(process.pid)
            cleanup.callback(close_ci_browser, process, owned, owned.create_time(), None, None)
            return process

        def attach(self, profile, process):
            return LocalPost(super().attach(profile, process), post_url=post_url)

        def bind(self, process, title):
            ui = super().bind(process, title)
            foreground_ci_window(self.page, ui)
            return ui

    monkeypatch.setattr(post_worker, "NativeRuntime", Runtime)


def failed_enter(self):
    raise BrowserCompletionError("The bound source page lost its identity or foreground")


def test_saved_alpha1_preinput_task_retries_its_original_post_once(monkeypatch, request):
    pytest.importorskip("playwright.sync_api")
    windows = sys.platform == "win32"
    if windows and (
        os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("IMAGE_MONITOR_ALLOW_PATH_TESTS") != "1"
    ):
        pytest.skip("Requires the explicitly enabled owned Windows CI desktop")
    if not windows:
        chrome = shutil.which("chromium") or shutil.which("google-chrome")
        if not chrome:
            pytest.skip("Headless Chromium unavailable")
        monkeypatch.setattr(fixtures, "browser_executable", lambda _: Path(chrome))

    published = datetime.now(ZoneInfo("Asia/Seoul")) - timedelta(minutes=3)
    posts = (*fixtures.POSTS, "900000103")
    monkeypatch.setattr(fixtures, "POSTS", posts)
    title = "Synthetic controller fixture"
    header = {
        "title": title,
        "nickname": "fx",
        "published_at_raw": published.strftime("%Y.%m.%d %H:%M:%S"),
    }
    assets = {
        "/post-" + p: ("text/html; charset=utf-8", fixtures._html(title, header)) for p in posts
    }
    png = fixture_assets(title)["/render-first.png"]
    assets["/render-first.png"] = png
    with (
        tempfile.TemporaryDirectory(prefix="rs-", dir=os.environ.get("RUNNER_TEMP")) as short,
        serve_fixtures(assets) as (origin, _requests),
        ExitStack() as cleanup,
    ):
        root = Path(short).resolve()
        data = SimpleNamespace(
            watch=root / "w", legacy=root / "l", batch=root / "b", clock=fixtures._Clock()
        )
        data.watch.mkdir()
        fixtures._observe_and_seed(data.watch, origin, published)
        database = data.watch / "watch.sqlite"
        with QueueStore(database, read_only=True) as source:
            before = fixtures._source_records(source)
            data.observations = {
                row["result"]["private_observation"]["url"]: row["result"]["private_observation"][
                    "snapshot"
                ]
                for row in CandidateDetailStore(source).list_details(MONITOR_SCOPE)
            }
        marker = root / "pending.json"
        if not windows:
            desktop = request.getfixturevalue("pilot")
            monkeypatch.setattr(monitor_batch_runtime, "require_windows", lambda: None)
            monkeypatch.setattr(
                candidate_finish,
                "exclusive_digest",
                lambda p: hashlib.sha256(p.read_bytes()).hexdigest(),
            )
            for module in (monitor_batch_runtime, monitor_operations):
                monkeypatch.setattr(module, "NativeSaveLock", nullcontext)
                monkeypatch.setattr(module, "session_id", lambda: 1)
        for module in (post_worker, monitor_batch_runtime, monitor_operations):
            monkeypatch.setattr(module, "shared_state_path", lambda: marker)
        data.clock.current = datetime.now(UTC) + timedelta(seconds=62)
        with monkeypatch.context() as previous:
            previous.setattr(monitor_batch_runtime, "session_id", lambda: 1)
            seeded = run(data)
        assert seeded["tasks_completed"] == 2, json.dumps(seeded, indent=2)
        previous_files = saved_content(data)
        assert len(previous_files) == 4
        with ledger(data) as records:
            [planned] = [t for t in records.list_tasks() if t["status"] == "planned"]
        post_id = planned["post_id"]
        target = fixtures._post_url(post_id)
        data.clock.next_ready()
        visits = []
        if windows:
            use_windows_browser(monkeypatch, cleanup, origin, target, visits)

        def native(root, browser, url, **options):
            assert options["automatic_start"] and url == target
            if not windows:
                desktop.root = root
                desktop.expected_url = url
                reference = options["candidate_permit"].reference_snapshot
                desktop.snapshots = [reference, reference]
                visits.append(url)
            return post_worker.run_post_save(root, browser, url, **options)

        def collect():
            return monitor_collect.run_monitor_collect(
                data.watch,
                data.legacy,
                data.batch,
                clock=data.clock,
                save_runner=native,
                detail_runner=lambda *a, **kw: pytest.fail("Checked a different candidate"),
            )

        with monkeypatch.context() as fault:
            fault.setattr(post_worker.BrowserCompletion, "__enter__", failed_enter)
            first = collect()
        assert first["status"] == "monitor_collect_review", first
        assert first["save"]["error_type"] == "BrowserCompletionError", json.dumps(first, indent=2)
        assert first["save"]["worker_last_stage"] == "completion_setup"
        assert first["worker_images_completed"] == first["files_verified"] == 0
        assert first["browser_closed"] and not marker.exists()
        with ledger(data) as records:
            failed = records.get_for_post(post_id)
        assert failed["status"] == "needs_review"
        base = data.batch / "tasks" / failed["task_id"] / f"session-{failed['native_session']}"
        with QueueStore(base / "queue.sqlite", read_only=True) as queue:
            [untouched] = queue.list_jobs()
            assert untouched["status"] == "queued" and not queue.history(untouched["job_id"])
            assert queue.list_artifacts() == []
        [old_report] = (base / "runs").glob("*/report.json")
        old = json.loads(old_report.read_bytes())
        # The first alpha had only its private exception reason. Verify a real
        # pre-input stop can reopen without depending on diagnostic fields added later.
        assert old.pop("completion_setup_reason") == "source_identity_or_foreground_changed"
        old_report.write_text(json.dumps(old), encoding="utf-8")
        retained = old_report.read_bytes()
        monkeypatch.setattr(monitor_setup_retry, "shared_state_path", lambda: marker)
        if not windows:
            monkeypatch.setattr(monitor_auto_selection, "NativeSaveLock", nullcontext)
            monkeypatch.setattr(monitor_setup_retry, "session_id", lambda: 1)
            monkeypatch.setattr(monitor_setup_retry, "browser_still_running", lambda _: False)
        data.clock.next_ready()
        recovered = collect()
        assert recovered["status"] == "monitor_collect_saved", json.dumps(recovered, indent=2)
        assert recovered["setup_retry_started"] and recovered["new_details_checked"] == 0
        assert (
            recovered["search"]["previous_completion_setup_reason"]
            == "source_identity_or_foreground_changed"
        )
        assert recovered["native_save_tasks_started"] == recovered["files_verified"] == 1
        assert recovered["browser_closed"] and not marker.exists()
        assert old_report.read_bytes() == retained
        data.clock.next_ready()
        repeated = collect()
        assert repeated["status"] == "monitor_collect_no_candidates", repeated
        assert repeated["native_save_tasks_started"] == 0 and visits == [target, target]
        assert len(list((base / "runs").glob("*/report.json"))) == 2
        with QueueStore(database, read_only=True) as source:
            assert fixtures._source_records(source) == before
        with ledger(data) as records:
            assert len(records.list_tasks()) == 3
            assert all(task["status"] == "completed" for task in records.list_tasks())
            assert records.get_for_post(post_id)["task_id"] == failed["task_id"]
        with QueueStore(base / "queue.sqlite", read_only=True) as queue:
            [done] = queue.list_jobs()
            assert done["status"] == "completed" and done["job_id"] == untouched["job_id"]
        files = saved_content(data)
        assert len(files) == 6 and all(files[p] == v for p, v in previous_files.items())
        [image] = [p for p in files.keys() - previous_files.keys() if p.name == "001.png"]
        assert image.parent.name == post_id
        if windows:
            assert image.read_bytes() == png[1]
