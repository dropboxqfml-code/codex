"""Save a controlled PNG through real owned Edge UI in opted-in Windows CI.

First intercept identified menu execution to inspect the unchanged guards. Then
restore Invoke and use the actual native Save As dialog for this disposable fixture.
Never use a personal profile, unidentified menu entry, direct download or screenshot.
"""

import json
import os
import platform
import subprocess
import sys
import time

import pytest

from image_monitor.native_probe import (
    browser_executable,
    close_probe_browser,
    connect_owned_browser,
    create_fixture,
    wait_for_debug_port,
    wait_for_fixture,
)
from image_monitor.native_ui import NativeUIError, WindowsUI, normalize_label

pytestmark = pytest.mark.skipif(
    sys.platform != "win32"
    or os.environ.get("GITHUB_ACTIONS") != "true"
    or os.environ.get("IMAGE_MONITOR_ALLOW_PATH_TESTS") != "1",
    reason="Real headed menu checks require an explicitly enabled Windows CI session",
)


def safe_owned_menu_snapshot(ui):
    """Read only owned browser menu labels; never collect window titles or edit values."""
    result = {"focus": ui.focus_snapshot(), "windows": []}
    try:
        pids = ui.process_ids()
        remaining = 72
        for window in ui.desktop.windows():
            hwnd = window.handle
            native_pid = ui._window_pid(hwnd) if isinstance(hwnd, int) and hwnd else 0
            if window.process_id() not in pids and native_pid not in pids:
                continue
            if len(result["windows"]) >= 8:
                result["truncated"] = True
                break
            entry = {
                "hwnd": hwnd if isinstance(hwnd, int) else None,
                "pid": window.process_id(),
                "native_pid": native_pid,
                "class": window.class_name(),
                "role": window.element_info.control_type,
                "belongs_to_target": bool(hwnd and ui.belongs_to_target(hwnd)),
                "menu_nodes": [],
            }
            # descendants() omits the root, which can itself be a native menu.
            if entry["role"] in {"Menu", "MenuItem"}:
                entry["root_name"] = window.window_text()[:160]
            result["windows"].append(entry)
            for role in ("Menu", "MenuItem", "ListItem"):
                nodes = window.descendants(control_type=role)
                entry[f"{role}_count"] = len(nodes)
                for node in nodes:
                    if remaining <= 0:
                        result["truncated"] = True
                        break
                    if node.process_id() not in pids:
                        continue
                    info = node.element_info
                    # ListItem names can be page data, so record only their role/count.
                    name = node.window_text()[:160] if role in {"Menu", "MenuItem"} else None
                    parent = node.parent()
                    node_data = {
                        "role": role,
                        "name": name,
                        "visible": node.is_visible(),
                        "enabled": node.is_enabled(),
                        "pid": node.process_id(),
                        "native_handle": node.handle,
                        "automation_id": str(info.automation_id)[:120],
                        "parent_role": parent.element_info.control_type if parent else None,
                        "parent_handle": parent.handle if parent else None,
                    }
                    entry["menu_nodes"].append(node_data)
                    remaining -= 1
    except Exception as error:
        result["diagnostic_error_type"] = type(error).__name__
    return result


def public_snapshot(capsys, locale, snapshot):
    # pytest normally captures passing-test output. This intentionally produces a
    # bounded notice for this opt-in CI check, later relayed by the workflow.
    message = json.dumps({"requested_locale": locale, **snapshot}, ensure_ascii=False)
    escaped = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    with capsys.disabled():
        print(f"\n::notice title=Owned Edge menu snapshot::{escaped}", flush=True)


def safe_control_guard_trace(ui, control, window):
    """Read native parent identities only, with no names or UI actions."""
    trace = {"window": {}, "control_parent_chain": []}
    try:
        window_handle = window.handle
        trace["window"] = {
            "hwnd": window_handle,
            "pid": window.process_id(),
            "root_hwnd": ui._root_window(window_handle),
        }
        pids = ui.process_ids()
        current = control
        for _index in range(32):
            if current is None:
                trace["end"] = "parent_none"
                break
            pid = current.process_id()
            hwnd = current.handle
            trace["control_parent_chain"].append(
                {
                    "pid": pid,
                    "role": current.element_info.control_type,
                    "hwnd": hwnd,
                    "root_hwnd": ui._root_window(hwnd) if isinstance(hwnd, int) and hwnd else None,
                }
            )
            if pid not in pids:
                trace["end"] = "outside_owned_processes"
                break
            current = current.parent()
        else:
            trace["end"] = "bounded_at_32"
    except Exception as error:
        trace["diagnostic_error_type"] = type(error).__name__
    return trace


def bind_owned_window(process, title, timeout=15):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            return WindowsUI(process.pid, title)
        except NativeUIError as error:
            last_error = type(error).__name__
            time.sleep(0.1)
    pytest.fail(f"Owned CI browser title binding did not become ready: {last_error}")


def foreground_owned_window(page, ui, timeout=10):
    """One normal activation request, then passive checks; never attach input threads."""
    from ctypes import wintypes

    page.bring_to_front()
    ui.user32.ShowWindow.argtypes = [wintypes.HWND, ui.ctypes.c_int]
    ui.user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    ui.user32.ShowWindow(ui.target_hwnd, 9)  # SW_RESTORE of this test's own window.
    ui.user32.SetForegroundWindow(ui.target_hwnd)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            ui.assert_target_ready()
            return
        except NativeUIError:
            time.sleep(0.1)
    pytest.fail("CI foreground handoff failed: " + json.dumps(ui.focus_snapshot()))


@pytest.mark.parametrize("locale", ["en-US", "ko-KR"])
def test_owned_headed_edge_context_menu_saves_the_synthetic_fixture(
    tmp_path, monkeypatch, capsys, locale
):
    import psutil
    from playwright.sync_api import sync_playwright
    from pywinauto.controls.uia_controls import MenuItemWrapper
    from pywinauto.controls.uiawrapper import UIAWrapper

    html, expected_hash = create_fixture(tmp_path / "fixture")
    staging = tmp_path / "_staging"
    staging.mkdir()
    target = staging / "native-image.png"
    profile = tmp_path / "browser-profile"
    profile.mkdir()
    process = subprocess.Popen(
        [
            str(browser_executable("edge")),
            f"--user-data-dir={profile}",
            "--remote-debugging-port=0",
            "--remote-debugging-address=127.0.0.1",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--force-renderer-accessibility",
            f"--lang={locale}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    owned_process = psutil.Process(process.pid)
    created_at = owned_process.create_time()
    driver = browser = ui = cleanup_session = None
    selected = []
    try:
        port = wait_for_debug_port(profile, process, timeout=30)
        driver = sync_playwright().start()
        browser = connect_owned_browser(driver, port)
        # Create this before native menus/dialogs can enter a modal message loop.
        cleanup_session = browser.new_browser_cdp_session()
        metadata = {"browser_version": browser.version, "windows_version": platform.version()}
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(html.as_uri(), wait_until="load", timeout=30_000)
        ui = bind_owned_window(process, page.title())
        foreground_owned_window(page, ui)
        image = page.locator("#probe-image")
        image.scroll_into_view_if_needed(timeout=15_000)
        image.evaluate("async image => { await image.decode(); }")
        ui.assert_target_ready()
        image.click(button="right", timeout=15_000)
        time.sleep(0.5)
        before = safe_owned_menu_snapshot(ui) | metadata
        public_snapshot(capsys, locale, before)

        def identified_invoke(control):
            # Guard identification, but do not actually invoke any UIA action.
            assert control.process_id() in ui.process_ids()
            assert normalize_label(control.window_text()) in {
                "Save image as",
                "이미지를 다른 이름으로 저장",
                "다른 이름으로 사진 저장",
            }
            selected.append(control.window_text())
            return control

        original_guard = ui.assert_control_ready
        control_guard_traces = []

        def traced_control_guard(control, window):
            trace = safe_control_guard_trace(ui, control, window)
            control_guard_traces.append(trace)
            try:
                result = original_guard(control, window)
            except Exception as error:
                trace["guard_error_type"] = type(error).__name__
                trace["guard_error"] = str(error)[:800]
                raise
            else:
                trace["guard_passed"] = True
                return result

        monkeypatch.setattr(ui, "assert_control_ready", traced_control_guard)
        native_save_stage = "context_menu_identification"
        try:
            with monkeypatch.context() as invoke_interception:
                invoke_interception.setattr(UIAWrapper, "invoke", identified_invoke)
                invoke_interception.setattr(MenuItemWrapper, "invoke", identified_invoke)
                ui.click_save_image_menu()
            assert len(selected) == 1
            # Invoke is now real again. The identified menu is still open because
            # the interception above performed no UI action.
            native_save_stage = "context_menu_invoke"
            ui.click_save_image_menu()
            native_save_stage = "save_dialog"
            ui.save_dialog(str(target))
            native_save_stage = "file_verification"
            verified = wait_for_fixture(target, expected_hash, ui, timeout=30)
            assert verified["detected_format"] == "PNG"
            assert verified["sha256"] == expected_hash
            assert target.read_bytes() == (html.parent / "fixture-original.png").read_bytes()
            public_snapshot(
                capsys,
                locale,
                {
                    "native_save_verified": True,
                    "menu_name": selected[0],
                    **metadata,
                    "detected_format": verified["detected_format"],
                    "sha256": verified["sha256"],
                    "file_size": verified["file_size"],
                },
            )
        except Exception as error:
            # Put the reason/trace first: GitHub truncates large public notices.
            after = {
                "native_save_stage": native_save_stage,
                "native_save_error_type": type(error).__name__,
                "native_save_error": str(error)[:800],
                "selection_error_type": type(error).__name__,
                "selection_error": str(error)[:800],
                "control_guard_trace": control_guard_traces,
                **metadata,
                **safe_owned_menu_snapshot(ui),
            }
            public_snapshot(capsys, locale, after)
            pytest.fail(
                "Owned native image save did not complete safely: "
                + json.dumps(
                    {
                        "error_type": type(error).__name__,
                        "error": str(error),
                        "before": before,
                        "after": after,
                    },
                    ensure_ascii=False,
                )
            )
    finally:
        already_failed = sys.exc_info()[0] is not None
        cleanup_errors = []
        try:
            if ui is not None and ui.user32.IsWindow(ui.target_hwnd):
                # End this owned window's menu loop before asking CDP to close.
                # Never send a global Escape key or act on another application.
                try:
                    from ctypes import wintypes

                    if ui._window_pid(ui.target_hwnd) in ui.process_ids():
                        result = ui.ctypes.c_size_t()
                        ui.user32.SendMessageTimeoutW.argtypes = [
                            wintypes.HWND,
                            wintypes.UINT,
                            wintypes.WPARAM,
                            wintypes.LPARAM,
                            wintypes.UINT,
                            wintypes.UINT,
                            ui.ctypes.POINTER(ui.ctypes.c_size_t),
                        ]
                        ui.user32.SendMessageTimeoutW.restype = ui.ctypes.c_ssize_t
                        ui.user32.SendMessageTimeoutW(
                            ui.target_hwnd, 0x001F, 0, 0, 0x0002, 2_000, ui.ctypes.byref(result)
                        )
                except Exception as error:
                    cleanup_errors.append(type(error).__name__)
            if browser is not None:
                try:
                    if cleanup_session is not None:
                        try:
                            cleanup_session.send("Browser.close", timeout=5_000)
                        except Exception:
                            # Normal browser exit can disconnect before its reply.
                            pass
                        process.wait(timeout=10)
                    else:
                        close_probe_browser(browser, process)
                except Exception as error:
                    cleanup_errors.append(type(error).__name__)
            if process.poll() is None:
                # Only this disposable synthetic fixture can be in flight. A failed
                # normal close may terminate this exact CI process, never a user's
                # browser. Production retains uncertain saves for manual inspection.
                if owned_process.is_running() and owned_process.create_time() == created_at:
                    owned_process.terminate()
                    process.wait(timeout=10)
                else:
                    cleanup_errors.append("OwnedProcessIdentityUnavailable")
        except Exception as error:
            cleanup_errors.append(type(error).__name__)
        finally:
            if driver is not None:
                try:
                    driver.stop()
                except Exception as error:
                    cleanup_errors.append(type(error).__name__)
        if process.poll() is None:
            cleanup_errors.append("DedicatedBrowserStillRunning")
        if cleanup_errors:
            message = "Owned CI browser cleanup: " + ",".join(cleanup_errors)
            if already_failed:
                # Preserve the original diagnostic failure rather than masking it.
                with capsys.disabled():
                    print(f"\n::warning::{message}", flush=True)
            else:
                pytest.fail(message)
