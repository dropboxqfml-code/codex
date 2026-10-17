"""Exercise the shipped dependencies and GUI using disposable generated images only."""

import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
import time
import traceback
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, features
from PySide6.QtCore import QBuffer, QIODevice, QTimer, qVersion
from PySide6.QtWidgets import QApplication, QMessageBox

from image_duplicate_finder.folder_dialog import LocalFolderDialog
from image_duplicate_finder.gui import MainWindow
from image_duplicate_finder.models import Decision
from image_duplicate_finder.privacy import local_path, runtime_blocks, runtime_guard_enabled
from image_duplicate_finder.recycling import _windows_backend
from image_duplicate_finder.scanner import scan
from image_duplicate_finder.storage import ReviewStore


def verify_windows_recycle_bin(original: Path, expected: str) -> None:
    """Check actual recycled bytes, not just disappearance from the original folder."""
    import pythoncom
    from win32com.client import dynamic

    pythoncom.CoInitialize()
    try:
        shell = dynamic.Dispatch("Shell.Application")
        for item in shell.NameSpace(10).Items():
            if (
                str(item.ExtendedProperty("System.Recycle.DeletedFrom")).casefold()
                != str(original.parent).casefold()
            ):
                continue
            if item.Name not in {original.name, original.stem}:
                continue
            recycled = Path(item.Path)
            if recycled.is_file() and hashlib.sha256(recycled.read_bytes()).hexdigest() == expected:
                return
        raise AssertionError("Generated test copy was not found in the Windows Recycle Bin")
    finally:
        pythoncom.CoUninitialize()


def run(report_path: Path, *, native_windows: bool = True) -> int:
    report_path = local_path(report_path)
    if report_path.suffix.lower() != ".json":
        raise ValueError("Diagnostic report must be a new .json file")
    if report_path.exists() or report_path.with_suffix(".png").exists():
        raise FileExistsError("Diagnostic mode never overwrites existing output files")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "status": "failed",
        "platform": sys.platform,
        "frozen": bool(getattr(sys, "frozen", False)),
    }
    report["native_versions"] = {
        "Qt": qVersion(),
        "SQLite": sqlite3.sqlite_version,
        "libjpeg": features.version("jpg"),
        "libtiff": features.version("libtiff"),
        "libwebp": features.version("webp"),
        "zlib": features.version("zlib"),
    }
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    report["qt_platform"] = app.platformName()
    workspace = tempfile.TemporaryDirectory(prefix="idf-build-smoke-", dir=report_path.parent)
    # Windows TEMP may use an 8.3 name; scanner paths are canonicalized with resolve().
    root = Path(workspace.name).resolve()
    pictures = root / "한글 이미지 폴더"
    pictures.mkdir()
    original = pictures / "original.png"
    target = pictures / f"duplicate-{uuid.uuid4().hex}.bin"
    image = Image.new("RGB", (96, 72), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((5, 8, 53, 55), fill="navy")
    draw.ellipse((35, 20, 88, 65), fill="orange")
    image.save(original)
    shutil.copyfile(original, target)
    image.save(pictures / "same-pixels.bmp")
    image.save(pictures / "similar.jpg", quality=75)
    (pictures / "nested").mkdir()
    shutil.copyfile(original, pictures / "nested" / "copy.png")
    checksum = hashlib.sha256(target.read_bytes()).hexdigest()
    window = MainWindow(root / "state" / "reviews.sqlite3")
    picker = LocalFolderDialog(window, str(pictures))
    assert picker.folders.count() == 1
    picker.accept_folder()
    assert picker.selected_path == str(pictures)
    picker.close()
    window.folder.setText(str(pictures))
    window.threshold.setValue(8)
    window.show()
    timer = QTimer()
    timer.setInterval(30)
    deadline = time.monotonic() + 60
    stage = "scan"

    def finish(error=None):
        timer.stop()
        if error is not None:
            report["error"] = error
        else:
            report["status"] = "passed"
        report["python_guard_enabled"] = runtime_guard_enabled()
        report["python_blocked_attempts"] = runtime_blocks()
        with report_path.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(report, ensure_ascii=False, indent=2))
        if window.worker is not None:
            window.worker.cancel.set()
            window.worker.wait(5000)
            app.processEvents()
        window.close()
        app.exit(1 if error else 0)

    def click_confirmation(answer):
        dialogs = [w for w in app.topLevelWidgets() if isinstance(w, QMessageBox) and w.isVisible()]
        if len(dialogs) != 1:
            raise AssertionError("Expected exactly one explicit confirmation dialog")
        box = dialogs[0]
        assert box.defaultButton() == box.button(QMessageBox.StandardButton.No)
        assert str(target) in box.detailedText()
        box.button(answer).click()

    def confirm(answer):
        errors = []

        def click():
            try:
                click_confirmation(answer)
            except Exception:
                errors.append(traceback.format_exc())
                for widget in app.topLevelWidgets():
                    if isinstance(widget, QMessageBox) and widget.isVisible():
                        widget.reject()

        QTimer.singleShot(0, click)
        window.confirm_trash()
        if errors:
            raise AssertionError(errors[0])

    def tick():
        nonlocal stage
        try:
            if time.monotonic() > deadline:
                raise TimeoutError(f"Frozen smoke timed out during {stage}")
            if window.worker is not None:
                return
            if stage == "scan":
                if sys.platform == "win32" and native_windows:
                    assert app.platformName() == "windows", "Native qwindows plugin must load"
                    assert _windows_backend().__module__ == "send2trash.win.modern"
                assert not window.result.errors, window.result.errors
                assert window.result.scanned == 5
                assert window.group_list.count() == 1
                assert window.images.topLevelItemCount() == 5
                assert not window.images.topLevelItem(0).icon(0).isNull()
                group = window.result.groups[0]
                records = {r.path.name: r for r in group.images}
                assert group.kinds == {"file", "pixel", "similar"}
                assert records[original.name].sha256 == records[target.name].sha256
                assert records[original.name].pixel_hash == records["same-pixels.bmp"].pixel_hash
                assert records[original.name].sha256 != records["same-pixels.bmp"].sha256
                assert (
                    records[original.name].phash ^ records["similar.jpg"].phash
                ).bit_count() <= 8
                assert scan(pictures, recursive=False).scanned == 4
                assert all(r.decision == Decision.HOLD for r in group.images)
                for i, record in enumerate(group.images):
                    decision = (
                        Decision.KEEP
                        if record.path == original
                        else (Decision.DELETE if record.path == target else Decision.HOLD)
                    )
                    combo = window.images.itemWidget(window.images.topLevelItem(i), 4)
                    combo.setCurrentIndex(combo.findData(decision.value))
                with ReviewStore(window.database) as store:
                    assert store.get(records[original.name]) == Decision.KEEP
                buffer = QBuffer()
                buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                assert window.grab().save(buffer, "PNG")
                with report_path.with_suffix(".png").open("xb") as stream:
                    stream.write(bytes(buffer.data()))
                report["scan_gui_sqlite"] = "passed"
                # The automated confirmation only applies to our generated temporary copy.
                timer.stop()
                confirm(QMessageBox.StandardButton.No)
                assert target.exists() and window.worker is None
                report["confirmation_no_preserves_file"] = "passed"
                stage = "recycle"
                confirm(QMessageBox.StandardButton.Yes)
                timer.start()
            elif stage == "recycle":
                assert not window.result.errors, window.result.errors
                assert not target.exists()
                assert original.exists()
                assert len(list(pictures.rglob("*.*"))) == 4
                if sys.platform == "win32" and native_windows:
                    verify_windows_recycle_bin(target, checksum)
                    report["native_windows_recycle_bin_bytes"] = "passed"
                else:
                    report["native_windows_recycle_bin_bytes"] = (
                        "not run (source test or non-Windows)"
                    )
                report["confirmation_yes_recycles_generated_copy"] = "passed"
                assert not any(runtime_blocks().values()), "Forbidden Python operation attempted"
                finish()
        except Exception:
            finish(traceback.format_exc())

    timer.timeout.connect(tick)
    window.start_scan()
    timer.start()
    exit_code = app.exec()
    workspace.cleanup()
    return exit_code
