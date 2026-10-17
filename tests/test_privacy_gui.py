import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from image_duplicate_finder import gui
from image_duplicate_finder.folder_dialog import LocalFolderDialog
from image_duplicate_finder.models import Decision
from image_duplicate_finder.scanner import scan
from image_duplicate_finder.storage import ReviewStore


@pytest.mark.parametrize("confirm", [False, True])
def test_forget_records_requires_confirmation_and_keeps_images(
    qtbot, tmp_path, image_factory, monkeypatch, confirm
):
    first = image_factory()
    second = image_factory("other.png")
    originals = {p: p.read_bytes() for p in [first, second]}
    window = gui.MainWindow(tmp_path / "app" / "reviews.sqlite3")
    qtbot.addWidget(window)
    result = scan(tmp_path)
    record = result.groups[0].images[0]
    record.decision = Decision.KEEP
    with ReviewStore(window.database) as store:
        store.set(record, Decision.KEEP)
    window.scan_completed(result)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *a: QMessageBox.StandardButton.Yes if confirm else QMessageBox.StandardButton.No,
    )
    window.forget_reviews()
    with ReviewStore(window.database) as store:
        assert store.get(record) == (Decision.HOLD if confirm else Decision.KEEP)
    assert all(p.read_bytes() == contents for p, contents in originals.items())


def test_dynamic_messages_are_plain_text(qtbot, tmp_path, monkeypatch):
    window = gui.MainWindow(tmp_path / "reviews.sqlite3")
    qtbot.addWidget(window)
    assert window.status.textFormat() == Qt.TextFormat.PlainText
    seen = []

    def inspect(box):
        assert box.textFormat() == Qt.TextFormat.PlainText
        seen.append(box.text())

    monkeypatch.setattr(QMessageBox, "exec", inspect)
    text = '<img src="https://example.invalid/sensitive">'
    gui.warning(window, "Error", text)
    assert seen == [text]


def test_folder_picker_rejects_unc_without_scandir(qtbot, monkeypatch):
    import image_duplicate_finder.folder_dialog as picker

    monkeypatch.setattr(picker.os, "scandir", lambda _: pytest.fail("must not inspect remote path"))
    dialog = LocalFolderDialog(initial="//server/share")
    qtbot.addWidget(dialog)
    assert not dialog.choose.isEnabled()
    assert dialog.selected_path == ""
    assert dialog.message.textFormat() == Qt.TextFormat.PlainText
