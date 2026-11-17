"""A local, capability-protected control window for background list monitoring."""

import json
import re
import secrets
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from image_monitor.artifact_files import _plain_path
from image_monitor.monitor_controller import MONITOR_SCOPE, MonitorController
from image_monitor.monitor_page import render_monitor_page
from image_monitor.native_probe import write_report
from image_monitor.native_ui import NativeUIError, require_windows
from image_monitor.watch_lock import WatchRunBusy, watch_run_lock

MAX_BODY_BYTES = 2048
_STATUS_FIELDS = (
    "scope_label",
    "phase",
    "browser",
    "interval_seconds",
    "completed_cycles",
    "candidate_count",
    "new_candidates",
    "current_cycle_new",
    "baseline_initialized",
    "last_scan_at",
    "next_eligible_at",
    "remaining_seconds",
    "last_scan_status",
    "gap_reason",
    "reason",
    "error_type",
    "browser_closed",
    "settings_editable",
    "task_kind",
    "detail_count",
    "detail_pending_count",
    "detail_completed_count",
    "detail_failed_count",
    "saved_status",
    "saved_reason",
    "saved_error_type",
    "saved_files_verified",
    "saved_preview_count",
)

_DETAIL_FIELDS = ("order", "status", "time_status", "reason", "image_count", "pending_images")
_SAVED_FIELDS = (
    "saved_filename",
    "detected_format",
    "file_size",
    "width",
    "height",
    "frames",
    "preview_available",
)
_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/bmp"}
_PREVIEW_LIMIT = 16 * 1024 * 1024


def _public_status(status, *, include_preview_ids=False):
    if not isinstance(status, dict):
        raise ValueError("A monitor status object is required")
    result = {key: status[key] for key in _STATUS_FIELDS if key in status}
    # Detail rows are anonymous structure summaries, never private observations.
    # Bound and project these separately so a future controller field cannot
    # accidentally expose a post URL, title, filename, or local path.
    if isinstance(status.get("details"), list):
        result["details"] = [
            {key: row[key] for key in _DETAIL_FIELDS if key in row}
            for row in status["details"][:10]
            if isinstance(row, dict)
        ]
    if isinstance(status.get("saved_files"), list):
        result["saved_files"] = []
        for row in status["saved_files"][:2]:
            if not isinstance(row, dict):
                continue
            item = {key: row[key] for key in _SAVED_FIELDS if key in row}
            preview_id = row.get("preview_id")
            if (
                include_preview_ids
                and row.get("preview_available") is True
                and isinstance(preview_id, str)
                and re.fullmatch(r"[0-9a-f]{32}", preview_id)
            ):
                item["preview_id"] = preview_id
            result["saved_files"].append(item)
    return result


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate action field")
        result[key] = value
    return result


class MonitorServer(ThreadingHTTPServer):
    """Expose no files or arbitrary commands, and never log the control capability."""

    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, controller):
        self.controller = controller
        self.token = secrets.token_urlsafe(32)
        self.script_nonce = secrets.token_urlsafe(24)
        self.closing = threading.Event()
        self._exit_reply_pending = threading.Event()
        super().__init__(("127.0.0.1", 0), _MonitorHandler)
        self.timeout = 0.25
        self.origin = f"http://127.0.0.1:{self.server_port}"
        self.base_path = f"/{self.token}/"
        self.url = self.origin + self.base_path

    def snapshot(self):
        return {
            "status": _public_status(self.controller.status(), include_preview_ids=True),
            "closing": self.closing.is_set(),
        }

    def serve(self):
        while (
            not self.closing.is_set()
            or self.controller.is_alive()
            or self._exit_reply_pending.is_set()
        ):
            self.handle_request()

    def handle_error(self, request, client_address):
        # Request paths contain a local control capability; no request logging.
        pass


class _MonitorHandler(BaseHTTPRequestHandler):
    server_version = "ImageMonitor"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(3)

    def log_message(self, *_args):
        pass

    def _respond(self, status, payload, *, html=False, image_type=None):
        if image_type is not None:
            if (
                image_type not in _IMAGE_TYPES
                or not isinstance(payload, bytes)
                or not 0 < len(payload) <= _PREVIEW_LIMIT
            ):
                raise ValueError("A bounded verified image buffer is required")
            data = payload
            content_type = image_type
        else:
            data = (
                payload.encode("utf-8")
                if html
                else json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
            )
            content_type = "text/html; charset=utf-8" if html else "application/json; charset=utf-8"
        self.close_connection = True
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Pragma", "no-cache")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; "
            f"script-src 'nonce-{self.server.script_nonce}'; "
            "style-src 'unsafe-inline'; connect-src 'self'; "
            "img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
        )
        self.end_headers()
        self.wfile.write(data)

    def _one_header(self, name):
        values = self.headers.get_all(name, [])
        return values[0] if len(values) == 1 else None

    def _valid_host(self):
        return self._one_header("Host") == f"127.0.0.1:{self.server.server_port}"

    def do_GET(self):
        if not self._valid_host():
            self._respond(403, {"error": "forbidden"})
            return
        origins = self.headers.get_all("Origin", [])
        if origins and (len(origins) != 1 or origins[0] != self.server.origin):
            self._respond(403, {"error": "forbidden"})
            return
        try:
            if self.path == self.server.base_path:
                self._respond(
                    200, render_monitor_page(script_nonce=self.server.script_nonce), html=True
                )
            elif self.path == self.server.base_path + "api/status":
                self._respond(200, self.server.snapshot())
            elif self.path.startswith(self.server.base_path + "images/"):
                if self.headers.get_all("Range"):
                    self._respond(416, {"error": "range_not_supported"})
                    return
                image_id = self.path.removeprefix(self.server.base_path + "images/")
                getter = getattr(self.server.controller, "saved_image", None)
                cached = (
                    getter(image_id)
                    if re.fullmatch(r"[0-9a-f]{32}", image_id) and callable(getter)
                    else None
                )
                if cached is None:
                    self._respond(404, {"error": "not_found"})
                else:
                    content_type, data = cached
                    self._respond(200, data, image_type=content_type)
            else:
                self._respond(404, {"error": "not_found"})
        except Exception:
            self._respond(500, {"error": "monitor_status_unavailable"})

    def do_POST(self):
        token = self._one_header("X-Image-Monitor-Token")
        if (
            not self._valid_host()
            or self._one_header("Origin") != self.server.origin
            or not isinstance(token, str)
            or not token.isascii()
            or len(token) > 128
            or not secrets.compare_digest(token, self.server.token)
        ):
            self._respond(403, {"error": "forbidden"})
            return
        if self.path != self.server.base_path + "api/action":
            self._respond(404, {"error": "not_found"})
            return
        if self.headers.get_all("Transfer-Encoding"):
            self._respond(400, {"error": "invalid_request_body"})
            return
        length = self._one_header("Content-Length")
        if (
            not isinstance(length, str)
            or not 1 <= len(length) <= 10
            or not length.isascii()
            or not length.isdigit()
        ):
            self._respond(400, {"error": "invalid_request_body"})
            return
        length = int(length)
        if not 1 <= length <= MAX_BODY_BYTES:
            self._respond(413, {"error": "request_body_too_large"})
            return
        if self._one_header("Content-Type") != "application/json":
            self._respond(415, {"error": "json_required"})
            return
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError("Incomplete action")
            action = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
            if not isinstance(action, dict) or not isinstance(action.get("action"), str):
                raise ValueError("Invalid action")
            name = action["action"]
            if name == "configure":
                interval = action.get("interval_seconds")
                if (
                    set(action) != {"action", "interval_seconds"}
                    or type(interval) is not int
                    or not 60 <= interval <= 300
                ):
                    raise ValueError("Invalid interval")
            elif name not in {
                "start",
                "pause",
                "stop",
                "exit",
                "inspect_candidates",
                "refresh_saved",
            } or set(action) != {"action"}:
                raise ValueError("Invalid action")
        except (ValueError, UnicodeError, RecursionError, OSError):
            self._respond(400, {"error": "invalid_action"})
            return
        if self.server.closing.is_set() and name != "exit":
            self._respond(409, {"error": "monitor_is_closing"})
            return
        try:
            controller = self.server.controller
            if name == "start":
                controller.start()
            elif name == "pause":
                controller.pause()
            elif name == "stop":
                controller.stop()
            elif name == "configure":
                controller.configure(action["interval_seconds"])
            elif name == "inspect_candidates":
                controller.inspect_candidates()
            elif name == "refresh_saved":
                controller.refresh_saved()
            else:
                controller.stop()
                self.server._exit_reply_pending.set()
                self.server.closing.set()
            try:
                self._respond(200, self.server.snapshot())
            finally:
                if name == "exit":
                    self.server._exit_reply_pending.clear()
        except (ValueError, RuntimeError):
            self._respond(409, {"error": "monitor_action_not_available"})
        except Exception:
            self._respond(500, {"error": "monitor_action_failed"})

    def do_OPTIONS(self):
        self._respond(405, {"error": "method_not_allowed"})

    do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS


def share_monitor_report(report):
    fields = (
        "schema_version",
        "mode",
        "status",
        "last_stage",
        "error_type",
        "reason",
        "ui_opened",
        "worker_stopped",
        "browser_closed",
    )
    public = {key: report[key] for key in fields if key in report}
    if isinstance(report.get("monitor_status"), dict):
        public["monitor_status"] = _public_status(report["monitor_status"])
    return public


def run_monitor_app(
    work_root: Path,
    *,
    save_root: Path | None = None,
    controller_factory=MonitorController,
    server_factory=MonitorServer,
    opener=None,
):
    require_windows()
    base = _plain_path(Path(work_root).absolute()).resolve()
    if str(base).startswith("\\\\"):
        raise NativeUIError("A local monitoring work root is required")
    saved_base = None
    if save_root is not None:
        saved_base = _plain_path(Path(save_root).absolute()).resolve()
        if (
            str(saved_base).startswith("\\\\")
            or saved_base == base
            or saved_base.is_relative_to(base)
            or base.is_relative_to(saved_base)
        ):
            raise NativeUIError("Saved results require a separate local output root")
    base.mkdir(parents=True, exist_ok=True)
    run_directory = base / "monitor-runs" / uuid.uuid4().hex
    run_directory.mkdir(parents=True)
    report_path = run_directory / "report.json"
    report = {
        "schema_version": 1,
        "mode": "local_discovery_monitor",
        "status": "monitor_failed",
        "last_stage": "monitor_ownership",
        "error_type": None,
        "ui_opened": False,
        "worker_stopped": True,
        "browser_closed": True,
    }
    controller = server = None
    cancelled = False
    try:
        with watch_run_lock(base / "watch.sqlite", MONITOR_SCOPE, purpose="monitor"):
            controller = (
                controller_factory(base)
                if saved_base is None
                else controller_factory(base, save_root=saved_base)
            )
            try:
                server = server_factory(controller)
                if opener is None:
                    import webbrowser

                    opener = webbrowser.open
                report["last_stage"] = "opening_status_window"
                if opener(server.url) is False:
                    raise NativeUIError("The local monitoring status window could not be opened")
                report["ui_opened"] = True
                if saved_base is not None and controller.status().get("phase") == "stopped":
                    controller.refresh_saved()
                report["last_stage"] = "status_window"
                server.serve()
            except KeyboardInterrupt:
                cancelled = True
            finally:
                controller.stop()
                # Only the application thread waits for Playwright cleanup.
                # HTTP handlers merely request the stop and return immediately.
                while not controller.wait_stopped(0.5):
                    pass
                if server is not None:
                    server.server_close()
            report["monitor_status"] = _public_status(controller.status())
            report["worker_stopped"] = not controller.is_alive()
            report["browser_closed"] = report["monitor_status"].get("browser_closed")
            if report["worker_stopped"] and report["browser_closed"] is True:
                report.update(
                    status="monitor_cancelled" if cancelled else "monitor_closed",
                    last_stage="complete",
                )
            else:
                report.update(reason="monitor_cleanup_requires_review", last_stage="cleanup")
    except WatchRunBusy:
        report.update(status="monitor_busy", reason="another_monitor_is_open")
    except KeyboardInterrupt:
        report.update(
            status="monitor_cancelled", error_type="KeyboardInterrupt", reason="cancelled"
        )
    except Exception as error:
        report.update(error_type=type(error).__name__, reason="monitor_application_stopped")
    finally:
        if controller is not None and controller.is_alive():
            controller.stop()
            while not controller.wait_stopped(0.5):
                pass
        if server is not None:
            server.server_close()
        if controller is not None:
            report["monitor_status"] = _public_status(controller.status())
            report["worker_stopped"] = not controller.is_alive()
            report["browser_closed"] = report["monitor_status"].get("browser_closed")
        report["report_path"] = str(report_path)
        write_report(report_path, report)
    return report
