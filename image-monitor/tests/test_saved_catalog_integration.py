"""Show finalized local images through the actual catalog, HTTP server and UI."""

import hashlib
import json
import shutil
import sys
import threading
from contextlib import contextmanager, nullcontext
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

import pytest
import test_monitor_finish_runtime as finished_fixture
from test_candidate_finish_runtime import database_dump
from test_candidate_save_runtime import NOW
from test_monitor_finish_runtime import assert_preserved, finish, preserve

from image_monitor.candidate_save_selection import MONITOR_MANIFEST_NAME, write_selection_control
from image_monitor.monitor_app import MonitorServer, share_monitor_report
from image_monitor.monitor_controller import MonitorController
from image_monitor.queue import QueueStore
from image_monitor.watch_runtime import SERVICE_SCOPE


@pytest.fixture
def completed_save(monkeypatch):
    yield from finished_fixture.completed_monitor.__wrapped__(monkeypatch)


@pytest.fixture(scope="module")
def browser():
    playwright = pytest.importorskip("playwright.sync_api")
    if sys.platform == "win32":
        from image_monitor.native_probe import browser_executable

        executable = str(browser_executable("chrome"))
    else:
        executable = shutil.which("chromium") or shutil.which("google-chrome")
    if not executable:
        pytest.skip("Installed Chromium unavailable")
    with playwright.sync_playwright() as driver:
        owned = driver.chromium.launch(
            executable_path=executable,
            headless=True,
            args=["--disable-background-networking"],
        )
        try:
            yield owned
        finally:
            owned.close()


def prepare_completed_save(value, monkeypatch, *, service_blocked=False):
    from image_monitor import saved_catalog

    assert finish(value)["status"] == "candidate_finish_completed"
    assert not value.marker.exists()
    # These are owned fixture identities, never the user's actual session state.
    monkeypatch.setattr(saved_catalog, "session_id", lambda: 1)
    monkeypatch.setattr(saved_catalog, "shared_state_path", lambda: value.marker)
    if sys.platform != "win32":
        monkeypatch.setattr(saved_catalog, "NativeSaveLock", nullcontext)
    if service_blocked:
        write_selection_control(value.watch_root / MONITOR_MANIFEST_NAME, {"blocked": True})
        with QueueStore(value.watch_root / "watch.sqlite") as queue:
            queue.defer_service(SERVICE_SCOPE, NOW + timedelta(days=3650))
    return saved_catalog.load_saved_catalog


@contextmanager
def owned_portal(value, loader):
    def never_collect(*_args, **_kwargs):
        pytest.fail("Viewing saved files must not start list, detail or native collection")

    controller = MonitorController(
        value.watch_root,
        save_root=value.work_root,
        catalog_loader=loader,
        run_cycle=never_collect,
        run_details=never_collect,
    )
    server = MonitorServer(controller)
    thread = threading.Thread(target=server.serve, name="saved-view-http", daemon=True)
    thread.start()
    try:
        yield controller, server, thread
    finally:
        controller.stop()
        assert controller.wait_stopped(10), "The local verification worker did not stop"
        server.closing.set()
        thread.join(5)
        server.server_close()
        assert not thread.is_alive(), "The owned local HTTP server did not stop"


def local_only_context(browser, server):
    context = browser.new_context(accept_downloads=False, service_workers="block")
    requests, external, downloads = [], [], []

    def local_request(route):
        if urlsplit(route.request.url).netloc != urlsplit(server.origin).netloc:
            external.append(route.request.url)
            route.abort()
        else:
            requests.append(route.request.url)
            route.continue_()

    context.route("**/*", local_request)
    page = context.new_page()
    page.on("download", lambda item: downloads.append(item))
    return context, page, requests, external, downloads


@pytest.mark.parametrize("service_blocked", [False, True])
def test_finalized_saved_image_reaches_real_http_and_browser_without_collection_or_file_changes(
    completed_save, monkeypatch, browser, service_blocked
):
    from playwright.sync_api import expect

    value = completed_save
    real_loader = prepare_completed_save(value, monkeypatch, service_blocked=service_blocked)
    before = preserve(value)
    watch_before = database_dump(value.watch_root / "watch.sqlite")
    final = Path(value.artifact["final_path"])
    original = final.read_bytes()
    worker_threads = []

    def loader(*args, **kwargs):
        worker_threads.append((threading.get_ident(), threading.current_thread().name))
        return real_loader(*args, **kwargs)

    with owned_portal(value, loader) as (controller, server, thread):
        context, page, requests, external, downloads = local_only_context(browser, server)
        try:
            page.goto(server.url, wait_until="domcontentloaded")
            expect(page.locator("#refresh-saved")).to_be_enabled()
            page.locator("#refresh-saved").click()
            image = page.locator("#saved-files img")
            expect(image).to_have_count(1)
            page.wait_for_function(
                """() => { const image = document.querySelector('#saved-files img');
                    return image && image.complete && image.naturalWidth > 0; }"""
            )
            assert controller.wait_stopped(10)
            state = controller.status()
            assert state["saved_status"] == "ready", state
            assert state["saved_files_verified"] == state["saved_preview_count"] == 1
            assert state["phase"] == "stopped" and state["browser_closed"] is True
            assert state["completed_cycles"] == state["new_candidates"] == 0
            assert state["saved_files"][0]["saved_filename"] == "001.png"
            preview_id = state["saved_files"][0]["preview_id"]
            expected_url = server.url + "images/" + preview_id
            assert image.get_attribute("src") == expected_url
            assert image.evaluate("image => [image.naturalWidth, image.naturalHeight]") == [4, 3]

            # This HTTP request reads only the already saved fixture's cached
            # bytes. It is not a collection request to any original image host.
            real_open = Path.open

            def guard_reopen(path, *args, **kwargs):
                if path == final:
                    pytest.fail("An HTTP image request reopened the saved file")
                return real_open(path, *args, **kwargs)

            with monkeypatch.context() as cache_only:
                cache_only.setattr(Path, "open", guard_reopen)
                with urlopen(expected_url, timeout=3) as response:
                    assert response.status == 200
                    assert response.headers["Content-Type"] == "image/png"
                    assert response.headers["X-Content-Type-Options"] == "nosniff"
                    assert response.headers["Cache-Control"] == "no-store"
                    served = response.read()
            assert served == original
            assert hashlib.sha256(served).hexdigest() == value.artifact["verification"]["sha256"]
            assert controller.saved_image(preview_id) == ("image/png", original)
            assert len(worker_threads) == 1
            assert worker_threads[0][0] not in {threading.get_ident(), thread.ident}
            assert worker_threads[0][1] == "image-monitor-saved-files"
            shared = json.dumps(
                share_monitor_report({"monitor_status": controller.status()}), ensure_ascii=False
            )
            assert "preview_id" not in shared and preview_id not in shared
            assert str(value.root) not in shared and "private.example" not in shared
            assert external == [] and downloads == []
            assert expected_url in requests
            assert all(urlsplit(url).netloc == urlsplit(server.origin).netloc for url in requests)
            page.get_by_role("button", name="프로그램 종료", exact=True).click()
            thread.join(5)
            assert not thread.is_alive() and server.closing.is_set()
        finally:
            context.close()
    assert_preserved(value, before)
    assert database_dump(value.watch_root / "watch.sqlite") == watch_before
    assert not value.marker.exists()


def test_real_ui_exit_returns_while_local_verification_worker_is_finishing(
    completed_save, monkeypatch, browser
):
    from playwright.sync_api import expect

    value = completed_save
    real_loader = prepare_completed_save(value, monkeypatch)
    before = preserve(value)
    entered, release = threading.Event(), threading.Event()

    def loader(*args, **kwargs):
        entered.set()
        assert release.wait(10), "The owned verification fixture was not released"
        return real_loader(*args, **kwargs)

    with owned_portal(value, loader) as (controller, server, thread):
        context, page, _, external, downloads = local_only_context(browser, server)
        try:
            page.goto(server.url, wait_until="domcontentloaded")
            page.locator("#refresh-saved").click()
            assert entered.wait(3)
            expect(page.locator("#refresh-saved")).to_be_disabled()
            assert controller.is_alive()
            with page.expect_response(
                lambda response: (
                    response.url == server.url + "api/action"
                    and response.request.method == "POST"
                    and response.request.post_data_json == {"action": "exit"}
                )
            ) as response:
                page.get_by_role("button", name="프로그램 종료", exact=True).click()
            assert response.value.status == 200
            assert response.value.json()["closing"] is True
            assert controller.is_alive() and thread.is_alive()
            release.set()
            assert controller.wait_stopped(10)
            thread.join(5)
            assert not thread.is_alive()
            state = controller.status()
            assert state["saved_status"] == "cancelled"
            assert state["saved_preview_count"] == 0 and state["saved_files"] == []
            assert state["phase"] == "stopped" and state["browser_closed"] is True
            assert external == [] and downloads == []
        finally:
            release.set()
            context.close()
    assert_preserved(value, before)
    assert not value.marker.exists()
