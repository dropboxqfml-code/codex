"""Windows-only, single synthetic PNG native-save acceptance probe.

This is deliberately not a production downloader. The known fixture hash provides
an independent completion/correspondence signal unavailable for arbitrary images.
"""

import hashlib
import json
import os
import platform
import subprocess
import time
import uuid
from pathlib import Path

from PIL import Image, ImageDraw

from image_monitor.native_state import PendingSave, browser_still_running, shared_state_path
from image_monitor.native_ui import NativeSaveLock, NativeUIError, WindowsUI, require_windows
from image_monitor.validation import verify_image


def browser_executable(browser: str) -> Path:
    if browser not in {"edge", "chrome"}:
        raise ValueError("Choose edge or chrome")
    suffix = (
        "Microsoft/Edge/Application/msedge.exe"
        if browser == "edge"
        else "Google/Chrome/Application/chrome.exe"
    )
    for variable in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(variable)
        if base:
            executable = Path(base) / suffix
            if executable.is_file():
                return executable.resolve()
    raise NativeUIError(f"Installed {browser} executable not found in standard locations")


def create_fixture(directory: Path) -> tuple[Path, str]:
    directory.mkdir()
    image_path = directory / "fixture-original.png"
    image = Image.new("RGB", (96, 64), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((7, 9, 40, 50), fill="navy")
    draw.ellipse((42, 11, 87, 54), fill="orange")
    image.save(image_path)
    page = directory / "probe.html"
    title = f"Image Monitor probe {uuid.uuid4().hex}"
    page.write_text(
        '<!doctype html><html lang="ko"><meta charset="utf-8">'
        f"<title>{title}</title><body>"
        "<h1>이미지 저장 시험</h1>"
        "<p>준비되면 아래 버튼을 한 번 누르고, 시험이 끝날 때까지 이 창을 그대로 두세요.</p>"
        '<button id="start-test" style="font-size:24px;padding:16px" '
        'onclick="window.imageMonitorStartRequested=true;this.disabled=true;'
        "document.getElementById('probe-status').textContent="
        "'시험 준비 중입니다. 이 창을 그대로 두세요.';"
        '">시험 시작</button>'
        '<p id="probe-status">버튼을 누르기 전에는 마우스 자동 조작을 시작하지 않습니다.</p>'
        '<img id="probe-image" src="fixture-original.png" alt="Synthetic test image">'
        "</body></html>",
        encoding="utf-8",
    )
    return page, hashlib.sha256(image_path.read_bytes()).hexdigest()


def wait_for_user_start(page, ui, timeout: float = 300) -> None:
    """Passively wait for an explicit local-page click and foreground ownership.

    No native input or focus activation is attempted here. Once native automation
    starts, the existing immediate-stop guards still apply to any focus loss.
    """
    ui.stage = "waiting_for_user_start"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        requested = page.evaluate("window.imageMonitorStartRequested === true")
        if requested:
            try:
                ui.assert_target_ready()
            except NativeUIError:
                pass
            else:
                page.evaluate(
                    "document.getElementById('probe-status').textContent = "
                    "'시험 진행 중입니다. 마우스와 다른 창을 조작하지 말고 기다려 주세요.'"
                )
                return
        time.sleep(0.1)
    raise NativeUIError(
        "Start was not confirmed in the foreground probe window within the waiting period"
    )


def save_one_image(page, ui, target: Path) -> str | None:
    """Only the fixture's exact body image is eligible; no whole-page fallback."""
    body = page.locator("body")
    image = body.locator("img#probe-image")
    if body.count() != 1 or image.count() != 1:
        raise NativeUIError("Synthetic body image is missing or ambiguous")
    ui.stage = "image_load"
    ui.assert_target_ready()
    image.scroll_into_view_if_needed(timeout=15_000)
    image.evaluate(
        """async image => {
        await image.decode();
        if (!image.complete || image.naturalWidth !== 96 || image.naturalHeight !== 64)
            throw new Error('Synthetic image is not completely loaded');
    }""",
        timeout=15_000,
    )
    ui.assert_target_ready()
    ui.stage = "right_click"
    image.click(button="right", timeout=15_000)
    ui.click_save_image_menu()
    return ui.save_dialog(str(target))


def exclusive_digest(path: Path) -> str | None:
    """Return a digest only when Windows grants exclusive read access to the file."""
    require_windows()
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.CreateFileW(str(path), 0x80000000, 0, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        return None
    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        kernel32.CloseHandle(handle)
        raise
    with os.fdopen(descriptor, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def wait_for_fixture(target: Path, expected_sha256: str, ui, timeout: float = 60) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ui.assert_ready()
        if target.is_symlink():
            raise NativeUIError("Unexpected staging symlink")
        if target.is_file() and exclusive_digest(target) == expected_sha256:
            verified = verify_image(target, writer_finished=True)
            if verified.sha256 != expected_sha256:
                raise NativeUIError("Saved file changed after exclusive inspection")
            return verified.to_dict()
        time.sleep(0.1)
    raise NativeUIError("Save completion/correspondence is uncertain; inspect staging manually")


def wait_for_debug_port(profile: Path, process, timeout: float = 30) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise NativeUIError("Dedicated browser exited before becoming ready")
        try:
            port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
            if 1 <= port <= 65535:
                return port
        except (FileNotFoundError, ValueError, IndexError):
            pass
        time.sleep(0.1)
    raise NativeUIError("Dedicated browser did not expose its local debugging endpoint")


def write_report(path: Path, report: dict) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def connect_owned_browser(driver, port: int):
    # Without no_defaults, a CDP attachment can itself change download behavior.
    return driver.chromium.connect_over_cdp(
        f"http://127.0.0.1:{port}",
        no_defaults=True,
        timeout=15_000,
    )


def close_probe_browser(browser, process) -> None:
    # Browser.close() on a CDP attachment only disconnects. Explicitly close the
    # disposable browser and independently confirm that the process actually exited.
    try:
        session = browser.new_browser_cdp_session()
        session.send("Browser.close", timeout=5_000)
    except Exception:
        # Closing the browser may disconnect before the CDP response arrives.
        # Process exit below is the required success signal, not this exception.
        pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired as error:
        raise NativeUIError("Dedicated browser did not close; inspect it manually") from error


def run_probe(work_root: Path, browser: str) -> dict:
    require_windows()  # Fail before creating files or importing Windows-only dependencies.
    try:
        import psutil
        import pywinauto  # noqa: F401
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise NativeUIError("Run uv sync --locked --extra windows first") from error
    executable = browser_executable(browser)
    root = work_root.resolve()
    if str(root).startswith("\\\\"):
        raise NativeUIError("Probe work root must be on a local disk")
    root.mkdir(parents=True, exist_ok=True)
    with NativeSaveLock():
        state = PendingSave(shared_state_path())
        state.assert_clear()
        if (root / "native-probe.pending").exists():
            raise NativeUIError(
                "Legacy native-probe.pending exists; inspect the previous browser and files first"
            )
        run_directory = root / uuid.uuid4().hex
        run_directory.mkdir()
        pending = state.begin(run_directory)
        report_path = run_directory / "report.json"
        report = {
            "schema_version": 1,
            "status": "manual_review",
            "browser": browser,
            "windows_version": platform.version(),
            "synthetic_fixture_only": True,
            "save_method": "native_context_menu_save_image_as",
            "original_attachment_filename": None,
            "browser_suggested_filename": None,
            "saved_filename": None,
            "http_status": None,
            "last_stage": "fixture_preparation",
            "shared_pending_state": str(state.path),
        }
        driver = None
        owned_browser = None
        ui = None
        try:
            target = run_directory / "_staging" / "native-image.png"
            if len(str(target).encode("utf-16-le")) // 2 > 240:
                raise NativeUIError("Work root too long; select a shorter local path")
            target.parent.mkdir()
            html, expected_hash = create_fixture(run_directory / "fixture")
            profile = run_directory / "browser-profile"
            profile.mkdir()
            # Launch independently: Playwright must not configure download interception
            # or a download directory. Attach only to this disposable browser via CDP.
            report["last_stage"] = "browser_launch"
            process = subprocess.Popen(
                [
                    str(executable),
                    f"--user-data-dir={profile}",
                    "--remote-debugging-port=0",
                    "--remote-debugging-address=127.0.0.1",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-background-networking",
                    "--force-renderer-accessibility",
                    "about:blank",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            report["browser_pid"] = process.pid
            state.update_browser(pending, process.pid, psutil.Process(process.pid).create_time())
            port = wait_for_debug_port(profile, process)
            report["last_stage"] = "browser_connection"
            driver = sync_playwright().start()
            owned_browser = connect_owned_browser(driver, port)
            report["browser_version"] = owned_browser.version
            context = owned_browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()
            report["last_stage"] = "local_page_load"
            page.goto(html.as_uri(), wait_until="load", timeout=30_000)
            report["last_stage"] = "window_binding"
            ui = WindowsUI(process.pid, page.title())
            report["target_hwnd"] = ui.target_hwnd
            report["environment"] = environment_info(ui)
            print("Click the Start test button in the dedicated browser when ready.", flush=True)
            wait_for_user_start(page, ui)
            report["browser_suggested_filename"] = save_one_image(page, ui, target)
            ui.stage = "file_verification"
            report["last_stage"] = ui.stage
            report["verification"] = wait_for_fixture(target, expected_hash, ui)
            report["saved_filename"] = target.name
            report["saved_relative_path"] = str(target.relative_to(run_directory))
            ui.stage = "browser_shutdown"
            report["last_stage"] = ui.stage
            close_probe_browser(owned_browser, process)
            if browser_still_running(pending):
                raise NativeUIError("Dedicated profile is still active; shared save state retained")
            report["browser_closed"] = True
            report["status"] = "probe_passed"
            report["last_stage"] = "complete"
            owned_browser = None
        except BaseException as error:
            # Do not print exception text: UI/driver exceptions can include page content.
            report["status"] = "manual_review"
            if ui is not None:
                report["last_stage"] = ui.stage
                report["focus_at_failure"] = ui.focus_snapshot()
                if ui.stage == "context_menu":
                    try:
                        report["menu_at_failure"] = ui.menu_snapshot()
                    except Exception as diagnostic_error:
                        report["menu_at_failure"] = {
                            "diagnostic_error_type": type(diagnostic_error).__name__
                        }
            report["error_type"] = type(error).__name__
            report["reason"] = "Probe stopped; inspect its browser and staging before retrying"
            if isinstance(error, KeyboardInterrupt):
                report["status"] = "cancelled_manual_review"
            raise
        finally:
            if ui is not None:
                report["browser_suggested_filename"] = ui.browser_suggested_filename
            # Disconnect on failure, leaving this dedicated browser for manual inspection.
            # Never close another browser or automatically retry an uncertain native save.
            try:
                if driver is not None:
                    driver.stop()
            except Exception as error:
                report["status"] = "manual_review"
                report["disconnect_error_type"] = type(error).__name__
                raise
            finally:
                write_report(report_path, report)
                print(f"Probe report: {report_path}", flush=True)
                print(
                    "Probe summary: "
                    + json.dumps(
                        {
                            "status": report["status"],
                            "last_stage": report["last_stage"],
                            "error_type": report.get("error_type"),
                            "browser": report["browser"],
                            "browser_version": report.get("browser_version"),
                            "windows_version": report["windows_version"],
                            "environment": report.get("environment"),
                            "focus_at_failure": report.get("focus_at_failure"),
                            "menu_at_failure": report.get("menu_at_failure"),
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
                if report["status"] == "probe_passed":
                    state.finish(pending)
        return report


def environment_info(ui: WindowsUI) -> dict:
    regional_locale = ui.ctypes.create_unicode_buffer(85)
    windows_ui_language = ui.ctypes.create_unicode_buffer(85)
    kernel_locale = ui.ctypes.WinDLL("kernel32", use_last_error=True)
    kernel_locale.GetUserDefaultLocaleName.argtypes = [ui.wintypes.LPWSTR, ui.ctypes.c_int]
    kernel_locale.GetUserDefaultLocaleName.restype = ui.ctypes.c_int
    kernel_locale.GetUserDefaultUILanguage.argtypes = []
    kernel_locale.GetUserDefaultUILanguage.restype = ui.wintypes.WORD
    kernel_locale.LCIDToLocaleName.argtypes = [
        ui.wintypes.DWORD,
        ui.wintypes.LPWSTR,
        ui.ctypes.c_int,
        ui.wintypes.DWORD,
    ]
    kernel_locale.LCIDToLocaleName.restype = ui.ctypes.c_int
    locale_ok = kernel_locale.GetUserDefaultLocaleName(regional_locale, len(regional_locale))
    language_id = kernel_locale.GetUserDefaultUILanguage()
    # A LANGID with SORT_DEFAULT (zero) is its LCID representation. This records
    # the user's preferred Windows UI language, not the regional formatting locale
    # or the separately configurable browser interface language.
    language_ok = language_id and kernel_locale.LCIDToLocaleName(
        language_id, windows_ui_language, len(windows_ui_language), 0
    )
    return {
        "regional_locale": regional_locale.value if locale_ok else None,
        "windows_ui_language": windows_ui_language.value if language_ok else None,
        "windows_ui_language_source": "GetUserDefaultUILanguage",
        "browser_ui_language": None,
        "system_dpi": ui.user32.GetDpiForSystem(),
        "monitor_count": ui.user32.GetSystemMetrics(80),  # SM_CMONITORS
        "remote_session": bool(ui.user32.GetSystemMetrics(0x1000)),
    }
