"""Serve only verified in-memory image buffers behind the local capability."""

import io
import json
import threading
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from PIL import Image
from test_monitor_app import FakeController, action, app_factories, request

from image_monitor import monitor_app

IMAGE_ID = "0123456789abcdef" * 2


class SavedController(FakeController):
    def __init__(self):
        super().__init__()
        buffer = io.BytesIO()
        Image.new("RGB", (4, 3), "#315781").save(buffer, format="PNG")
        self.image_data = buffer.getvalue()
        self.cache = {IMAGE_ID: ("image/png", self.image_data)}
        self.image_requests = []
        self.snapshot.update(
            saved_status="ready",
            saved_reason=None,
            saved_error_type=None,
            saved_files_verified=1,
            saved_preview_count=1,
            saved_files=[
                {
                    "saved_filename": "001.png",
                    "detected_format": "PNG",
                    "file_size": len(self.image_data),
                    "width": 4,
                    "height": 3,
                    "frames": 1,
                    "preview_id": IMAGE_ID,
                    "preview_available": True,
                    "path": "C:/Invented/private/image.png",
                    "sha256": "private-file-hash",
                    "data": "private-image-bytes",
                    "post_url": "https://private.example/post",
                }
            ],
        )

    def saved_image(self, image_id):
        self.image_requests.append(image_id)
        return self.cache.get(image_id)

    def refresh_saved(self):
        self.calls.append(("refresh_saved", threading.current_thread().name))
        self.cache.clear()
        self.snapshot.update(saved_status="empty", saved_preview_count=0, saved_files=[])
        return self.status()


@pytest.fixture
def portal():
    controller = SavedController()
    server = monitor_app.MonitorServer(controller)
    thread = threading.Thread(target=server.serve, daemon=True)
    thread.start()
    value = SimpleNamespace(
        controller=controller,
        server=server,
        thread=thread,
        path=urlsplit(server.url).path,
        authority=urlsplit(server.origin).netloc,
    )
    try:
        yield value
    finally:
        controller.stop()
        server.closing.set()
        thread.join(5)
        server.server_close()
        assert not thread.is_alive()


def test_image_get_returns_exact_cached_bytes_with_fixed_raster_type_and_security_headers(portal):
    code, headers, body = request(portal, endpoint=f"images/{IMAGE_ID}")
    assert code == 200 and body == portal.controller.image_data
    assert headers["Content-Type"] == "image/png"
    assert int(headers["Content-Length"]) == len(body)
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert "Access-Control-Allow-Origin" not in headers
    assert portal.controller.image_requests == [IMAGE_ID]
    assert portal.controller.calls == []


def test_preview_ids_are_local_http_only_and_private_proofs_never_enter_status_or_shared_txt(
    portal,
):
    code, _, body = request(portal)
    assert code == 200
    local = json.loads(body)["status"]
    assert local["saved_files"][0]["preview_id"] == IMAGE_ID
    shared = monitor_app.share_monitor_report({"monitor_status": portal.controller.status()})
    serialized = json.dumps(shared)
    assert IMAGE_ID not in serialized and "preview_id" not in serialized
    assert shared["monitor_status"]["saved_files"][0]["saved_filename"] == "001.png"
    for content in (body.decode(), serialized):
        assert "private" not in content and "post_url" not in content and "sha256" not in content
    assert portal.controller.image_requests == []


@pytest.mark.parametrize(
    "suffix",
    [
        "../secret",
        "%2e%2e/secret",
        IMAGE_ID + "?path=C:/foreign",
        IMAGE_ID + "/extra",
        IMAGE_ID.upper(),
        "001.png",
        "file:///C:/foreign",
        "a" * 33,
    ],
)
def test_image_route_cannot_choose_paths_urls_filenames_queries_or_ambiguous_ids(portal, suffix):
    code, _, _ = request(portal, endpoint="images/" + suffix)
    assert code == 404 and portal.controller.image_requests == []


@pytest.mark.parametrize(
    "header", [{"Host": "foreign.example"}, {"Origin": "https://foreign.example"}]
)
def test_image_reads_keep_exact_local_host_and_origin_guards(portal, header):
    code, _, _ = request(portal, endpoint=f"images/{IMAGE_ID}", headers=header)
    assert code == 403 and portal.controller.image_requests == []


def test_unknown_or_revoked_id_does_not_reopen_a_file(portal):
    assert request(portal, endpoint="images/" + "b" * 32)[0] == 404
    assert action(portal, "refresh_saved")[0] == 200
    assert request(portal, endpoint=f"images/{IMAGE_ID}")[0] == 404
    assert [call[0] for call in portal.controller.calls] == ["refresh_saved"]


def test_range_requests_are_refused_before_reading_the_cache(portal):
    code, _, _ = request(portal, endpoint=f"images/{IMAGE_ID}", headers={"Range": "bytes=0-3"})
    assert code == 416 and portal.controller.image_requests == []


@pytest.mark.parametrize(
    "cached",
    [("text/html", b"<script>alert(1)</script>"), ("image/svg+xml", b"<svg/>"), ("image/png", b"")],
)
def test_non_raster_or_empty_cache_results_are_never_returned_as_images(portal, cached):
    portal.controller.cache[IMAGE_ID] = cached
    code, headers, body = request(portal, endpoint=f"images/{IMAGE_ID}")
    assert code == 500
    assert headers["Content-Type"].startswith("application/json")
    assert b"<script>" not in body and b"<svg" not in body


@pytest.mark.parametrize(
    "extra", [{"path": "C:/foreign"}, {"save_root": "C:/foreign"}, {"limit": 99}]
)
def test_refresh_action_has_no_user_selected_files_or_roots(portal, extra):
    assert action(portal, "refresh_saved", **extra)[0] == 400
    assert portal.controller.calls == []


def test_application_automatically_checks_configured_results_once_without_starting_monitoring(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(monitor_app, "require_windows", lambda: None)
    controller = SavedController()
    events = []
    _, _, server_factory = app_factories(events, controller=controller)
    calls = []
    save_root = tmp_path / "saved-not-created"

    def factory(root, *, save_root):
        calls.append((root, save_root))
        return controller

    report = monitor_app.run_monitor_app(
        tmp_path / "watch",
        save_root=save_root,
        controller_factory=factory,
        server_factory=server_factory,
        opener=lambda _: True,
    )
    assert report["status"] == "monitor_closed", report
    assert calls == [(tmp_path / "watch", save_root)]
    assert [call[0] for call in controller.calls].count("refresh_saved") == 1
    assert not any(call[0] == "start" for call in controller.calls)
    assert not save_root.exists()
    assert IMAGE_ID not in json.dumps(monitor_app.share_monitor_report(report))


@pytest.mark.parametrize("relation", ["same", "child", "parent"])
def test_viewer_roots_must_be_separate_before_any_directory_is_created(
    tmp_path, monkeypatch, relation
):
    monkeypatch.setattr(monitor_app, "require_windows", lambda: None)
    root = tmp_path / "watch"
    save_root = {"same": root, "child": root / "saved", "parent": tmp_path}[relation]
    with pytest.raises(monitor_app.NativeUIError):
        monitor_app.run_monitor_app(root, save_root=save_root)
    assert list(tmp_path.iterdir()) == []


def test_existing_discovery_review_still_opens_ui_without_automatic_catalog_work(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(monitor_app, "require_windows", lambda: None)
    controller = SavedController()
    controller.snapshot["phase"] = "needs_review"
    events = []

    class Server:
        url = "http://127.0.0.1:39999/invented-capability/"

        def __init__(self, supplied):
            assert supplied is controller

        def serve(self):
            events.append("served")
            assert controller.status()["phase"] == "needs_review"
            assert controller.calls == []

        def server_close(self):
            pass

    report = monitor_app.run_monitor_app(
        tmp_path / "watch",
        save_root=tmp_path / "saved",
        controller_factory=lambda *_args, **_kwargs: controller,
        server_factory=Server,
        opener=lambda _: True,
    )
    assert report["ui_opened"] is True and events == ["served"]
    assert not any(call[0] == "refresh_saved" for call in controller.calls)
