"""Exercise the local monitor control surface without a gallery or saver."""

import copy
import http.client
import importlib
import json
import shutil
import socket
import sys
import threading
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest


class FakeController:
    def __init__(self, *_args, **_kwargs):
        self.lock = threading.RLock()
        self.calls = []
        self.failure = None
        self.alive = False
        self.snapshot = {
            "phase": "stopped",
            "browser": "chrome",
            "scope_label": "만화 · ai · 제목+내용",
            "interval_seconds": 60,
            "completed_cycles": 0,
            "candidate_count": 6,
            "new_candidates": 0,
            "current_cycle_new": 0,
            "baseline_initialized": False,
            "last_scan_at": None,
            "next_eligible_at": None,
            "remaining_seconds": 0,
            "last_scan_status": None,
            "gap_reason": None,
            "reason": None,
            "error_type": None,
            "browser_closed": True,
            "settings_editable": True,
            "title": "Invented private title",
            "source_url": "https://private.example/image?token=private-token",
        }

    def status(self):
        with self.lock:
            return copy.deepcopy(self.snapshot)

    def _action(self, action, phase, *, alive):
        with self.lock:
            self.calls.append((action, threading.current_thread().name))
            if self.failure is not None:
                raise self.failure
            self.alive = alive
            self.snapshot.update(phase=phase, settings_editable=phase == "stopped")
            return self.status()

    def start(self):
        return self._action("start", "waiting", alive=True)

    def pause(self):
        return self._action("pause", "paused", alive=True)

    def stop(self):
        return self._action("stop", "stopped", alive=False)

    def configure(self, interval_seconds):
        with self.lock:
            self.calls.append(("configure", interval_seconds))
            if self.snapshot["phase"] != "stopped":
                raise ValueError("Settings require stopped monitoring")
            self.snapshot["interval_seconds"] = interval_seconds
            return self.status()

    def is_alive(self):
        with self.lock:
            return self.alive

    def wait_stopped(self, timeout=None):
        with self.lock:
            self.calls.append(("wait_stopped", threading.current_thread().name))
            return not self.alive


@pytest.fixture
def app_module():
    return importlib.import_module("image_monitor.monitor_app")


@pytest.fixture
def portal(app_module):
    controller = FakeController()
    server = app_module.MonitorServer(controller)
    thread = threading.Thread(target=server.serve, name="monitor-http-test", daemon=True)
    thread.start()
    value = SimpleNamespace(
        server=server,
        controller=controller,
        thread=thread,
        path=urlsplit(server.url).path,
        authority=urlsplit(server.origin).netloc,
    )
    try:
        yield value
    finally:
        controller.failure = None
        controller.stop()
        server.closing.set()
        thread.join(timeout=5)
        server.server_close()
        assert not thread.is_alive(), "The owned local test server did not stop"


def request(portal, method="GET", endpoint="api/status", *, payload=None, body=None, headers=None):
    values = {"Host": portal.authority}
    if method == "POST":
        values |= {
            "Origin": portal.server.origin,
            "X-Image-Monitor-Token": portal.server.token,
            "Content-Type": "application/json",
        }
    if headers:
        values.update(headers)
    if payload is not None:
        body = json.dumps(payload).encode()
    connection = http.client.HTTPConnection(*portal.server.server_address, timeout=3)
    try:
        connection.request(method, portal.path + endpoint, body=body, headers=values)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def raw_request(portal, *, method="POST", endpoint="api/action", fields=(), body=b"{}"):
    with socket.create_connection(portal.server.server_address, timeout=3) as connection:
        lines = [f"{method} {portal.path}{endpoint} HTTP/1.1", *fields, "Connection: close", "", ""]
        connection.sendall("\r\n".join(lines).encode("ascii") + body)
        response = http.client.HTTPResponse(connection)
        response.begin()
        return response.status, dict(response.getheaders()), response.read()


def authorized_fields(portal, body):
    return [
        f"Host: {portal.authority}",
        f"Origin: {portal.server.origin}",
        f"X-Image-Monitor-Token: {portal.server.token}",
        "Content-Type: application/json",
        f"Content-Length: {len(body)}",
    ]


def action(portal, name, **options):
    status, headers, body = request(
        portal, "POST", "api/action", payload={"action": name, **options}
    )
    return status, headers, json.loads(body)


def test_local_page_and_status_do_not_start_work_or_expose_private_controller_fields(portal):
    assert portal.server.server_address[0] == "127.0.0.1"
    status, headers, body = request(portal, endpoint="")
    assert status == 200
    assert "Image Monitor" in body.decode()
    assert "no-store" in headers.get("Cache-Control", "")
    assert headers.get("Referrer-Policy") == "no-referrer"
    assert "frame-ancestors 'none'" in headers.get("Content-Security-Policy", "")
    assert "Access-Control-Allow-Origin" not in headers
    status, _, body = request(portal)
    assert status == 200
    result = json.loads(body)
    assert result["status"]["phase"] == "stopped"
    assert result["status"]["candidate_count"] == 6
    assert result["closing"] is False
    assert "private" not in body.decode()
    assert portal.controller.calls == []


def test_valid_control_lifecycle_and_exit_never_wait_in_the_http_handler(portal):
    assert action(portal, "configure", interval_seconds=120)[2]["status"]["interval_seconds"] == 120
    for name, phase in (
        ("start", "waiting"),
        ("pause", "paused"),
        ("start", "waiting"),
        ("stop", "stopped"),
    ):
        status, _, result = action(portal, name)
        assert status == 200
        assert result["status"]["phase"] == phase
    status, _, result = action(portal, "exit")
    assert status == 200 and result["closing"] is True
    portal.thread.join(timeout=3)
    assert not portal.thread.is_alive()
    assert [call[0] for call in portal.controller.calls] == [
        "configure",
        "start",
        "pause",
        "start",
        "stop",
        "stop",
    ]
    assert not any(call[0] == "wait_stopped" for call in portal.controller.calls)


@pytest.mark.parametrize("header", ["Origin", "X-Image-Monitor-Token"])
@pytest.mark.parametrize("variation", ["missing", "wrong", "duplicate"])
def test_mutations_require_exact_single_origin_and_capability(portal, header, variation):
    body = b'{"action":"start"}'
    fields = authorized_fields(portal, body)
    if variation == "missing":
        fields = [line for line in fields if not line.startswith(header + ":")]
    elif variation == "wrong":
        fields = [
            f"{header}: https://foreign.example" if line.startswith(header + ":") else line
            for line in fields
        ]
    else:
        fields.append(f"{header}: foreign")
    status, _, _ = raw_request(portal, fields=fields, body=body)
    assert status == 403
    assert portal.controller.calls == []


@pytest.mark.parametrize("variation", ["missing", "foreign", "localhost", "duplicate"])
def test_exact_host_prevents_localhost_aliases_and_dns_rebinding(portal, variation):
    body = b'{"action":"start"}'
    fields = [line for line in authorized_fields(portal, body) if not line.startswith("Host:")]
    if variation == "foreign":
        fields.append("Host: foreign.example")
    elif variation == "localhost":
        fields.append(f"Host: localhost:{portal.server.server_port}")
    elif variation == "duplicate":
        fields += [f"Host: {portal.authority}", "Host: foreign.example"]
    status, _, _ = raw_request(portal, fields=fields, body=body)
    assert status == 403
    assert portal.controller.calls == []


def test_non_ascii_capability_is_rejected_without_a_handler_failure(portal):
    status, _, _ = request(
        portal,
        "POST",
        "api/action",
        payload={"action": "start"},
        headers={"X-Image-Monitor-Token": "\u00e9"},
    )
    assert status == 403
    assert portal.controller.calls == []


def test_extreme_decimal_length_is_rejected_before_integer_conversion_or_body_read(portal):
    body = b'{"action":"start"}'
    fields = [
        "Content-Length: " + "9" * 5000 if line.startswith("Content-Length:") else line
        for line in authorized_fields(portal, body)
    ]
    status, _, _ = raw_request(portal, fields=fields, body=body)
    assert status in {400, 413}
    assert portal.controller.calls == []


@pytest.mark.parametrize(
    "endpoint",
    ["../api/status", "api/status?token=foreign", "%2e%2e/api/status", "api/unknown"],
)
def test_only_fixed_exact_routes_are_available(portal, endpoint):
    status, _, _ = request(portal, endpoint=endpoint)
    assert status == 404
    assert portal.controller.calls == []


def test_unknown_secret_path_cannot_read_status(portal):
    connection = http.client.HTTPConnection(*portal.server.server_address, timeout=3)
    try:
        connection.request("GET", "/unknown/api/status", headers={"Host": portal.authority})
        response = connection.getresponse()
        assert response.status == 404
        response.read()
    finally:
        connection.close()
    assert portal.controller.calls == []


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "unknown"},
        {"action": []},
        {"action": "start", "path": "C:/foreign"},
        {"action": "start", "interval_seconds": 60},
        {"action": "configure"},
        {"action": "configure", "interval_seconds": True},
        {"action": "configure", "interval_seconds": 60.0},
        {"action": "configure", "interval_seconds": "60"},
        {"action": "configure", "interval_seconds": 59},
        {"action": "configure", "interval_seconds": 301},
        ["start"],
    ],
)
def test_untrusted_json_cannot_choose_paths_or_invalid_actions_and_intervals(portal, payload):
    status, _, _ = request(portal, "POST", "api/action", payload=payload)
    assert status == 400
    assert portal.controller.calls == []


@pytest.mark.parametrize("body", [b'{"action":', b'{"action":"start","action":"stop"}', b"null"])
def test_malformed_or_duplicate_json_never_dispatches(portal, body):
    status, _, _ = request(portal, "POST", "api/action", body=body)
    assert status == 400
    assert portal.controller.calls == []


@pytest.mark.parametrize("problem", ["large", "chunked", "duplicate_length", "wrong_type"])
def test_bounded_nonstreaming_json_is_required_before_dispatch(portal, problem):
    body = b'{"action":"start"}'
    fields = authorized_fields(portal, body)
    if problem == "large":
        body = b"x" * 2049
        fields = authorized_fields(portal, body)
    elif problem == "chunked":
        fields.append("Transfer-Encoding: chunked")
    elif problem == "duplicate_length":
        fields.append(f"Content-Length: {len(body)}")
    else:
        fields = [
            "Content-Type: text/plain" if line.startswith("Content-Type:") else line
            for line in fields
        ]
    status, _, _ = raw_request(portal, fields=fields, body=body)
    assert status in {400, 413, 415}
    assert portal.controller.calls == []


def test_controller_failures_return_safe_errors_without_logging_the_capability(portal, capsys):
    portal.controller.failure = OSError("Invented private title and https://private.example")
    status, headers, body = request(portal, "POST", "api/action", payload={"action": "start"})
    assert status == 500
    assert "no-store" in headers.get("Cache-Control", "")
    assert "Access-Control-Allow-Origin" not in headers
    assert not any(
        secret in body.decode() for secret in ("private", "https://", portal.server.token)
    )
    portal.controller.failure = None
    captured = capsys.readouterr()
    assert portal.server.token not in captured.out + captured.err


def test_settings_conflict_does_not_change_an_active_interval(portal):
    action(portal, "start")
    status, _, result = action(portal, "configure", interval_seconds=300)
    assert status in {400, 409}
    assert portal.controller.snapshot["interval_seconds"] == 60
    assert "private" not in json.dumps(result)


def test_platform_guard_precedes_files_and_ui_open(app_module, tmp_path, monkeypatch):
    from image_monitor.native_ui import NativeUIError

    def unsupported():
        raise NativeUIError("Windows is required")

    monkeypatch.setattr(app_module, "require_windows", unsupported)
    root = tmp_path / "not-created"
    with pytest.raises(NativeUIError, match="Windows"):
        app_module.run_monitor_app(root, opener=lambda *_: pytest.fail("UI opened"))
    assert not root.exists()


def app_factories(events, *, on_serve=None, controller=None):
    controller = controller or FakeController()

    def controller_factory(root):
        events.append(("controller", root))
        assert not (root / "watch.sqlite").exists()
        return controller

    class Server:
        url = "http://127.0.0.1:39999/invented-private-capability/"

        def __init__(self, supplied):
            assert supplied is controller
            self.closing = threading.Event()
            events.append(("server",))

        def serve(self):
            events.append(("serve",))
            assert controller.status()["phase"] == "stopped"
            if on_serve is not None:
                on_serve(controller)
            self.closing.set()

        def server_close(self):
            events.append(("server_close",))

    return controller, controller_factory, Server


def test_application_opens_one_local_ui_without_starting_work_and_shares_no_capability(
    app_module, tmp_path, monkeypatch
):
    from image_monitor.watch_lock import WatchRunBusy, watch_run_lock

    monkeypatch.setattr(app_module, "require_windows", lambda: None)
    root = tmp_path / "watch"
    events = []
    controller, controller_factory, server_factory = app_factories(events)
    opened = []

    def opener(url):
        opened.append(url)
        with pytest.raises(WatchRunBusy):
            with watch_run_lock(root / "watch.sqlite", app_module.MONITOR_SCOPE, purpose="monitor"):
                pytest.fail("The UI lifetime monitor lease was released before serving")
        assert controller.calls == []
        return True

    report = app_module.run_monitor_app(
        root,
        controller_factory=controller_factory,
        server_factory=server_factory,
        opener=opener,
    )
    assert report["status"] == "monitor_closed", report
    assert report["ui_opened"] is True and report["worker_stopped"] is True
    assert report["browser_closed"] is True
    assert opened == [server_factory.url]
    assert not any(call[0] == "start" for call in controller.calls)
    assert any(item[0] == "server_close" for item in events)
    assert not (root / "watch.sqlite").exists()
    shared = json.dumps(app_module.share_monitor_report(report), ensure_ascii=False)
    for secret in ("invented-private-capability", "private", str(root), "report_path", "http://"):
        assert secret not in shared
    with watch_run_lock(root / "watch.sqlite", app_module.MONITOR_SCOPE, purpose="monitor"):
        pass


def test_second_monitor_cannot_open_another_ui_or_controller(app_module, tmp_path, monkeypatch):
    from image_monitor.watch_lock import watch_run_lock

    monkeypatch.setattr(app_module, "require_windows", lambda: None)
    with watch_run_lock(tmp_path / "watch.sqlite", app_module.MONITOR_SCOPE, purpose="monitor"):
        report = app_module.run_monitor_app(
            tmp_path,
            controller_factory=lambda *_: pytest.fail("A second controller was created"),
            server_factory=lambda *_: pytest.fail("A second server was created"),
            opener=lambda *_: pytest.fail("A second status window was opened"),
        )
    assert report["status"] == "monitor_busy"
    assert report["ui_opened"] is False
    assert not (tmp_path / "watch.sqlite").exists()


def test_failure_to_open_the_ui_closes_the_server_without_starting_monitoring(
    app_module, tmp_path, monkeypatch
):
    monkeypatch.setattr(app_module, "require_windows", lambda: None)
    events = []
    controller, controller_factory, server_factory = app_factories(events)
    report = app_module.run_monitor_app(
        tmp_path,
        controller_factory=controller_factory,
        server_factory=server_factory,
        opener=lambda *_: False,
    )
    assert report["status"] == "monitor_failed"
    assert report["ui_opened"] is False
    assert not any(call[0] == "start" for call in controller.calls)
    assert any(item[0] == "server_close" for item in events)
    assert not any(item[0] == "serve" for item in events)


@pytest.mark.parametrize("failure", [KeyboardInterrupt, OSError])
def test_application_failure_stops_the_worker_before_releasing_monitor_ownership(
    app_module, tmp_path, monkeypatch, failure
):
    from image_monitor.watch_lock import WatchRunBusy, watch_run_lock

    monkeypatch.setattr(app_module, "require_windows", lambda: None)
    events = []

    def interrupted(controller):
        controller.start()
        raise failure("Invented private source https://private.example")

    controller, controller_factory, server_factory = app_factories(events, on_serve=interrupted)
    original_wait = controller.wait_stopped

    def verify_cleanup_lease(timeout=None):
        with pytest.raises(WatchRunBusy):
            with watch_run_lock(
                tmp_path / "watch.sqlite", app_module.MONITOR_SCOPE, purpose="monitor"
            ):
                pytest.fail("A monitor could start before the old worker stopped")
        return original_wait(timeout)

    controller.wait_stopped = verify_cleanup_lease
    report = app_module.run_monitor_app(
        tmp_path,
        controller_factory=controller_factory,
        server_factory=server_factory,
        opener=lambda *_: True,
    )
    assert report["status"] == (
        "monitor_cancelled" if failure is KeyboardInterrupt else "monitor_failed"
    )
    assert report["worker_stopped"] is True and not controller.is_alive()
    assert any(call[0] == "stop" for call in controller.calls)
    assert any(call[0] == "wait_stopped" for call in controller.calls)
    assert not any("private" in str(value) for value in report.values())


def test_unknown_browser_cleanup_cannot_be_reported_as_clean_application_exit(
    app_module, tmp_path, monkeypatch
):
    monkeypatch.setattr(app_module, "require_windows", lambda: None)
    events = []
    controller = FakeController()
    controller.snapshot["browser_closed"] = False
    controller, controller_factory, server_factory = app_factories(events, controller=controller)
    report = app_module.run_monitor_app(
        tmp_path,
        controller_factory=controller_factory,
        server_factory=server_factory,
        opener=lambda *_: True,
    )
    assert report["status"] == "monitor_failed"
    assert report["worker_stopped"] is True
    assert report["browser_closed"] is False
    assert report["reason"] == "monitor_cleanup_requires_review"


def test_real_browser_controls_stay_local_and_never_execute_status_text(portal):
    playwright = pytest.importorskip("playwright.sync_api")
    if sys.platform == "win32":
        from image_monitor.native_probe import browser_executable

        executable = str(browser_executable("chrome"))
    else:
        executable = shutil.which("chromium") or shutil.which("google-chrome")
    if not executable:
        pytest.skip("Installed browser unavailable")
    with playwright.sync_playwright() as driver:
        browser = driver.chromium.launch(
            executable_path=executable,
            headless=True,
            args=["--disable-background-networking"],
        )
        try:
            context = browser.new_context(accept_downloads=False)
            page = context.new_page()
            requests = []
            page.on("request", lambda item: requests.append(item.url))
            page.goto(portal.server.url, wait_until="domcontentloaded")
            interval = page.locator('input[type="number"]')
            interval.fill("120")
            page.get_by_role("button", name="간격 적용", exact=True).click()
            playwright.expect(interval).to_have_value("120")
            page.get_by_role("button", name="감시 시작", exact=True).click()
            playwright.expect(interval).to_be_disabled()
            page.get_by_role("button", name="일시정지", exact=True).click()
            page.get_by_role("button", name="계속 감시", exact=True).click()
            page.get_by_role("button", name="중지", exact=True).click()
            playwright.expect(interval).to_be_enabled()
            with portal.controller.lock:
                portal.controller.snapshot["reason"] = (
                    '<img src="https://foreign.example/x" onerror="window.untrustedExecuted=1">'
                )
            page.wait_for_timeout(1100)
            assert page.evaluate("window.untrustedExecuted") is None
            assert page.locator("img").count() == 0
            assert all(urlsplit(value).netloc == portal.authority for value in requests)
            page.get_by_role("button", name="프로그램 종료", exact=True).click()
            portal.thread.join(timeout=3)
            assert not portal.thread.is_alive()
            assert portal.server.closing.is_set()
        finally:
            browser.close()


def test_batch_catalog_root_is_forwarded_once_without_creating_output_directories(
    app_module, tmp_path, monkeypatch
):
    monkeypatch.setattr(app_module, "require_windows", lambda: None)
    controller = FakeController()
    events = []
    _, _, server_factory = app_factories(events, controller=controller)
    save_root = tmp_path / "saved-not-created"
    batch_root = tmp_path / "batch-not-created"
    calls = []

    def refresh_saved():
        controller.calls.append(("refresh_saved", threading.current_thread().name))
        return controller.status()

    controller.refresh_saved = refresh_saved

    def factory(root, *, save_root, batch_root):
        calls.append((root, save_root, batch_root))
        return controller

    report = app_module.run_monitor_app(
        tmp_path / "watch",
        save_root=save_root,
        batch_root=batch_root,
        controller_factory=factory,
        server_factory=server_factory,
        opener=lambda _: True,
    )
    assert report["status"] == "monitor_closed", report
    assert calls == [(tmp_path / "watch", save_root, batch_root)]
    assert [call[0] for call in controller.calls].count("refresh_saved") == 1
    assert not any(call[0] == "start" for call in controller.calls)
    assert not save_root.exists() and not batch_root.exists()


def test_batch_catalog_root_requires_saved_results_before_creating_any_directory(
    app_module, tmp_path, monkeypatch
):
    monkeypatch.setattr(app_module, "require_windows", lambda: None)
    with pytest.raises(app_module.NativeUIError):
        app_module.run_monitor_app(
            tmp_path / "watch",
            batch_root=tmp_path / "batch",
            controller_factory=lambda *_args, **_kwargs: pytest.fail("Controller created"),
            opener=lambda _: pytest.fail("UI opened"),
        )
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("other_root", ["work", "saved"])
@pytest.mark.parametrize("relation", ["same", "child", "parent"])
def test_batch_catalog_root_must_be_separate_from_work_and_saved_roots(
    app_module, tmp_path, monkeypatch, other_root, relation
):
    monkeypatch.setattr(app_module, "require_windows", lambda: None)
    work_root = tmp_path / "work" / "leaf"
    save_root = tmp_path / "saved" / "leaf"
    compared = work_root if other_root == "work" else save_root
    batch_root = {
        "same": compared,
        "child": compared / "batch",
        "parent": compared.parent,
    }[relation]
    with pytest.raises(app_module.NativeUIError):
        app_module.run_monitor_app(
            work_root,
            save_root=save_root,
            batch_root=batch_root,
            controller_factory=lambda *_args, **_kwargs: pytest.fail("Controller created"),
            opener=lambda _: pytest.fail("UI opened"),
        )
    assert list(tmp_path.iterdir()) == []


def test_batch_saved_projection_preserves_duplicate_filenames_and_bounded_anonymous_groups(
    app_module,
):
    rows = [
        {
            "saved_filename": "001.jpg",
            "detected_format": "JPEG",
            "file_size": 123,
            "width": 4,
            "height": 3,
            "frames": 1,
            "preview_available": index != 1,
            "preview_id": f"{100 + index:032x}",
            "group_id": f"{index + 1:032x}",
            "source_post_id": "private-post-id",
            "post_url": "https://private.example/post",
            "path": "C:/private/image.jpg",
            "sha256": "private-file-hash",
        }
        for index in range(22)
    ]
    status = {
        "saved_status": "ready",
        "saved_files_verified": 2000,
        "saved_groups_verified": 50,
        "saved_files_omitted": 1980,
        "saved_preview_count": 19,
        "saved_files": rows,
    }
    local = app_module._public_status(status, include_preview_ids=True)
    assert local["saved_files_verified"] == 2000
    assert local["saved_groups_verified"] == 50
    assert local["saved_files_omitted"] == 1980
    assert len(local["saved_files"]) == 20
    assert [row["saved_filename"] for row in local["saved_files"][:2]] == ["001.jpg"] * 2
    assert [row["group_id"] for row in local["saved_files"]] == [
        row["group_id"] for row in rows[:20]
    ]
    assert local["saved_files"][0]["preview_id"] == rows[0]["preview_id"]
    assert "preview_id" not in local["saved_files"][1]

    shared = app_module.share_monitor_report({"monitor_status": status})
    assert len(shared["monitor_status"]["saved_files"]) == 20
    serialized = json.dumps(shared)
    for secret in ("group_id", "preview_id", "source_post_id", "post_url", "path", "sha256"):
        assert secret not in serialized
    for row in rows:
        assert row["group_id"] not in serialized
        assert row["preview_id"] not in serialized
    for content in (json.dumps(local), serialized):
        assert "private" not in content


@pytest.mark.parametrize(
    "group_id",
    [None, False, 17, "a" * 31, "a" * 33, "A" * 32, "../private", "https://private.example"],
)
def test_saved_projection_rejects_invalid_group_ids_and_accepts_legacy_rows(app_module, group_id):
    rows = [
        {"saved_filename": "001.jpg", "group_id": group_id, "preview_available": False},
        {"saved_filename": "002.jpg", "preview_available": False},
    ]
    local = app_module._public_status({"saved_files": rows}, include_preview_ids=True)
    assert len(local["saved_files"]) == 2
    assert all("group_id" not in row for row in local["saved_files"])
