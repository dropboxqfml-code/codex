import shutil
from threading import Event

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QComboBox, QMessageBox

from image_duplicate_finder import gui
from image_duplicate_finder.models import Decision, ScanResult
from image_duplicate_finder.scanner import scan
from image_duplicate_finder.storage import ReviewStore
from image_duplicate_finder.trash import TrashResult


@pytest.fixture
def window(qtbot, tmp_path):
    widget = gui.MainWindow(tmp_path / "appdata" / "reviews.sqlite3")
    qtbot.addWidget(widget)
    widget.show()
    yield widget
    if widget.worker:
        widget.worker.cancel.set()
        qtbot.waitUntil(lambda: widget.worker is None, timeout=10000)


def test_real_gui_scan_preview_and_persisted_review(qtbot, window, image_factory, tmp_path):
    first = image_factory()
    shutil.copyfile(first, tmp_path / "copy.png")
    window.folder.setText(str(tmp_path))
    qtbot.mouseClick(window.scan_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.worker is None, timeout=10000)
    assert window.group_list.count() == 1
    assert window.images.topLevelItemCount() == 2
    item = window.images.topLevelItem(0)
    assert not item.icon(0).isNull()
    record = window.result.groups[0].images[0]
    assert item.text(1) == str(record.path)
    assert item.text(3) == "96 × 72"
    combo = window.images.itemWidget(item, 4)
    assert isinstance(combo, QComboBox)
    assert combo.currentData() == "hold"
    combo.setCurrentIndex(combo.findData("keep"))
    assert record.decision == Decision.KEEP
    with ReviewStore(window.database) as store:
        assert store.get(record) == Decision.KEEP
    qtbot.mouseClick(window.scan_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.worker is None, timeout=10000)
    assert window.result.groups[0].images[0].decision == Decision.KEEP
    assert window.progress.value() == 100


def test_gui_remains_responsive_and_cancels(qtbot, window, tmp_path, monkeypatch):
    entered = Event()

    def slow_scan(folder, recursive, threshold, cancel, progress, database):
        entered.set()
        progress("이미지 분석", 1, 20)
        cancel.wait(10)
        return ScanResult(cancelled=cancel.is_set())

    monkeypatch.setattr(gui, "scan", slow_scan)
    window.folder.setText(str(tmp_path))
    window.start_scan()
    qtbot.waitUntil(entered.is_set)
    heartbeat = []
    QTimer.singleShot(0, lambda: heartbeat.append(True))
    qtbot.waitUntil(lambda: bool(heartbeat))
    assert window.worker is not None
    assert not window.scan_button.isEnabled()
    qtbot.mouseClick(window.cancel_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.worker is None)
    assert window.result.cancelled
    assert window.group_list.count() == 0
    assert window.scan_button.isEnabled()


def test_close_requests_cancel_and_waits_for_thread(qtbot, window):
    entered = Event()

    def task(cancel, progress):
        entered.set()
        cancel.wait(10)
        return ScanResult(cancelled=cancel.is_set())

    window.start_task(task, window.scan_completed)
    qtbot.waitUntil(entered.is_set)
    window.close()
    qtbot.waitUntil(lambda: window.worker is None)
    qtbot.waitUntil(lambda: not window.isVisible())


@pytest.mark.parametrize("answer", [QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes])
def test_confirmation_controls_trash_backend(
    qtbot, window, tmp_path, image_factory, monkeypatch, answer
):
    first = image_factory()
    shutil.copyfile(first, tmp_path / "copy.png")
    window.scan_completed(scan(tmp_path))
    group = window.result.groups[0]
    group.images[0].decision = Decision.KEEP
    group.images[1].decision = Decision.DELETE
    called = []

    def confirm(box):
        assert box.defaultButton() == box.button(QMessageBox.StandardButton.No)
        assert str(group.images[1].path) in box.detailedText()
        return answer

    def fake_move(groups, cancel, progress, *, confirmed=False):
        assert confirmed is True
        called.append(groups)
        return TrashResult(moved=[group.images[1].path])

    monkeypatch.setattr(QMessageBox, "exec", confirm)
    monkeypatch.setattr(gui, "move_to_trash", fake_move)
    window.confirm_trash()
    qtbot.waitUntil(lambda: window.worker is None)
    assert len(called) == int(answer == QMessageBox.StandardButton.Yes)
    if answer == QMessageBox.StandardButton.Yes:
        assert window.group_list.count() == 0


def test_worker_error_is_reported_and_controls_recover(qtbot, window):
    def broken(cancel, progress):
        raise OSError("test failure")

    window.start_task(broken, window.scan_completed)
    qtbot.waitUntil(lambda: window.worker is None)
    assert "test failure" in window.status.text()
    assert window.scan_button.isEnabled()
    assert window.errors_button.isEnabled()


def test_failed_review_write_reverts_selection(window, tmp_path, image_factory, monkeypatch):
    first = image_factory()
    shutil.copyfile(first, tmp_path / "copy.png")
    window.scan_completed(scan(tmp_path))
    record = window.result.groups[0].images[0]
    combo = window.images.itemWidget(window.images.topLevelItem(0), 4)

    def failing(*_):
        raise OSError("read-only")

    warnings = []
    monkeypatch.setattr(gui, "ReviewStore", failing)
    monkeypatch.setattr(gui, "warning", lambda *args: warnings.append(args))
    combo.setCurrentIndex(combo.findData("delete"))
    assert record.decision == Decision.HOLD
    assert combo.currentData() == "hold"
    assert len(warnings) == 1
