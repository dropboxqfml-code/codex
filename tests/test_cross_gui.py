import shutil
from threading import Event

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QMessageBox

from image_duplicate_finder import cross_gui, gui
from image_duplicate_finder.cross_models import CrossDecision, CrossResult
from image_duplicate_finder.cross_storage import CrossStore
from image_duplicate_finder.trash import TrashResult


@pytest.fixture
def cross_window(qtbot, tmp_path):
    window = gui.MainWindow(tmp_path / "state/reviews.sqlite3")
    qtbot.addWidget(window)
    window.mode.setCurrentIndex(1)
    window.show()
    yield window
    if window.cross_page.worker:
        window.cross_page.closing = True
        window.cross_page.cancel_task()
        qtbot.waitUntil(lambda: window.cross_page.worker is None, timeout=10000)


@pytest.fixture
def cross_images(tmp_path, image_factory):
    source = image_factory("A/original.png")
    b = tmp_path / "B"
    b.mkdir()
    shutil.copyfile(source, b / "target.png")
    return source.parent, b


def scan_panel(qtbot, panel, roots):
    panel.folder_a.setText(str(roots[0]))
    panel.folder_b.setText(str(roots[1]))
    panel.start_scan()
    qtbot.waitUntil(lambda: panel.worker is None, timeout=10000)
    assert panel.result is not None


def test_new_mode_real_worker_side_by_side_metadata_and_state(qtbot, cross_window, cross_images):
    p = cross_window.cross_page
    assert not p.recursive_a.isChecked() and not p.recursive_b.isChecked()
    assert p.threshold.maximum() == 12 and p.threshold.value() == 6
    scan_panel(qtbot, p, cross_images)
    assert cross_window.pages.currentWidget() is p
    assert p.model.rowCount() == 1
    assert len(p.preview_data) == 2
    assert p.preview_a.height() == p.preview_b.height()
    assert not p.preview_a.pixmap().isNull() and not p.preview_b.pixmap().isNull()
    assert str(cross_images[0] / "original.png") in p.info_a.text()
    assert str(cross_images[1] / "target.png") in p.info_b.text()
    assert "96 × 72" in p.info_b.text() and "bytes" in p.info_b.text()
    assert p.decision.currentData() == "undecided"
    assert p.current_candidate.decision == CrossDecision.UNDECIDED
    p.decision.setCurrentIndex(p.decision.findData("hold"))
    assert p.current_candidate.decision == CrossDecision.HOLD
    with CrossStore(p.database) as store:
        assert store.get_cross(p.result, p.current_candidate) == CrossDecision.HOLD
    assert p.preview_a.textFormat() != Qt.TextFormat.RichText
    assert p.info_a.textFormat() == Qt.TextFormat.PlainText
    assert p.info_b.textFormat() == Qt.TextFormat.PlainText
    cross_window.mode.setCurrentIndex(0)
    assert cross_window.pages.currentWidget() is cross_window.single_page


def test_multiple_a_matches_share_one_b_decision_and_filters(qtbot, cross_window, cross_images):
    a, b = cross_images
    shutil.copyfile(a / "original.png", a / "second.png")
    p = cross_window.cross_page
    scan_panel(qtbot, p, cross_images)
    assert p.match_choice.count() == 2 and p.model.rowCount() == 1
    p.match_choice.setCurrentIndex(1)
    qtbot.waitUntil(lambda: p.worker is None)
    p.decision.setCurrentIndex(p.decision.findData("delete"))
    assert p.trash_button.text() == "휴지통 이동 예정 1개…"
    assert p.current_candidate.decision == CrossDecision.DELETE
    p.state_filter.setCurrentIndex(p.state_filter.findData("keep"))
    assert p.model.rowCount() == 0
    p.state_filter.setCurrentIndex(0)
    p.search.setText("missing")
    qtbot.waitUntil(lambda: p.model.rowCount() == 0)
    p.search.setText("second")
    qtbot.waitUntil(lambda: p.model.rowCount() == 1)
    p.tabs.setCurrentIndex(2)
    assert p.model.rowCount() == 0
    p.tabs.setCurrentIndex(1)
    assert p.model.rowCount() == 1


@pytest.mark.parametrize(
    "answers,kind,moves",
    [
        (["no"], "file", 0),
        (["yes"], "file", 1),
        (["yes", "no"], "similar", 0),
        (["yes", "yes"], "similar", 1),
    ],
)
def test_default_no_and_additional_similar_confirmation(
    qtbot, cross_window, cross_images, monkeypatch, answers, kind, moves
):
    p = cross_window.cross_page
    scan_panel(qtbot, p, cross_images)
    c = p.result.candidates[0]
    c.matches[0].kind = kind
    p.decision.setCurrentIndex(p.decision.findData("delete"))
    questions, called = [], []
    choices = iter(answers)

    def confirm(box):
        assert box.defaultButton() == box.button(QMessageBox.StandardButton.No)
        assert box.textFormat() == Qt.TextFormat.PlainText
        if not questions:
            assert str(c.target.path) in box.detailedText()
        questions.append(box.text())
        return (
            QMessageBox.StandardButton.Yes
            if next(choices) == "yes"
            else QMessageBox.StandardButton.No
        )

    def move(result, cancel, progress, *, confirmed, similar_confirmed):
        assert confirmed is True
        assert similar_confirmed == (kind == "similar")
        called.append(result)
        return TrashResult(moved=[c.target.path])

    monkeypatch.setattr(QMessageBox, "exec", confirm)
    monkeypatch.setattr(cross_gui, "move_cross_to_trash", move)
    p.confirm_trash()
    qtbot.waitUntil(lambda: p.worker is None)
    assert len(called) == moves
    assert len(questions) == len(answers)
    assert p.model.rowCount() == 1 - moves
    assert all(path.exists() for path in [c.target.path, c.representative.reference.path])


def test_cross_scan_responsive_cancellable_and_controls_disabled(
    qtbot, cross_window, cross_images, monkeypatch
):
    p = cross_window.cross_page
    entered = Event()

    def slow(a, b, ra, rb, threshold, similar, cancel, progress, database):
        entered.set()
        cancel.wait(10)
        return CrossResult(a, b, cancelled=cancel.is_set())

    monkeypatch.setattr(cross_gui, "scan_cross", slow)
    p.folder_a.setText(str(cross_images[0]))
    p.folder_b.setText(str(cross_images[1]))
    p.start_scan()
    qtbot.waitUntil(entered.is_set)
    heartbeat = []
    QTimer.singleShot(0, lambda: heartbeat.append(1))
    qtbot.waitUntil(lambda: bool(heartbeat))
    assert not p.swap_button.isEnabled() and not cross_window.mode.isEnabled()
    assert not p.decision.isEnabled()
    p.cancel_task()
    qtbot.waitUntil(lambda: p.worker is None)
    assert p.result.cancelled and p.model.rowCount() == 0
    assert p.swap_button.isEnabled() and cross_window.mode.isEnabled()


def test_close_cancels_cross_worker_and_waits(qtbot, cross_window):
    p, entered = cross_window.cross_page, Event()

    def task(cancel, progress):
        entered.set()
        cancel.wait(10)
        return None

    p.start_task(task, lambda _: None)
    qtbot.waitUntil(entered.is_set)
    cross_window.close()
    qtbot.waitUntil(lambda: p.worker is None)
    qtbot.waitUntil(lambda: not cross_window.isVisible())


def test_invalid_root_shows_error_recovers_and_never_moves(qtbot, cross_window, cross_images):
    p = cross_window.cross_page
    p.folder_a.setText(str(cross_images[0]))
    p.folder_b.setText(str(cross_images[0]))
    p.start_scan()
    qtbot.waitUntil(lambda: p.worker is None)
    assert p.result is None and p.model.rowCount() == 0
    assert "상위·하위" in p.status.text()
    assert p.scan_button.isEnabled() and not p.trash_button.isEnabled()


@pytest.mark.parametrize("answer", [QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes])
def test_swap_requires_confirmation_and_swaps_roles_and_scopes(
    qtbot, cross_window, cross_images, monkeypatch, answer
):
    p = cross_window.cross_page
    a, b = cross_images
    p.folder_a.setText(str(a))
    p.folder_b.setText(str(b))
    p.recursive_a.setChecked(True)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: answer)
    p.swap_folders()
    swapped = answer == QMessageBox.StandardButton.Yes
    assert p.folder_a.text() == str(b if swapped else a)
    assert p.folder_b.text() == str(a if swapped else b)
    assert p.recursive_a.isChecked() is not swapped
    assert p.recursive_b.isChecked() is swapped


def test_failed_cross_review_write_reverts_without_queuing_delete(
    qtbot, cross_window, cross_images, monkeypatch
):
    p = cross_window.cross_page
    scan_panel(qtbot, p, cross_images)
    messages = []

    def denied(*_):
        raise OSError("read-only test DB")

    monkeypatch.setattr(cross_gui, "CrossStore", denied)
    monkeypatch.setattr(cross_gui, "warning", lambda *args: messages.append(args))
    p.decision.setCurrentIndex(p.decision.findData("delete"))
    assert p.current_candidate.decision == CrossDecision.UNDECIDED
    assert p.decision.currentData() == "undecided"
    assert not p.trash_button.isEnabled()
    assert len(messages) == 1


def test_clear_cache_requires_confirmation_preserves_images(
    qtbot, cross_window, cross_images, monkeypatch
):
    p = cross_window.cross_page
    scan_panel(qtbot, p, cross_images)
    c = p.current_candidate
    p.decision.setCurrentIndex(p.decision.findData("keep"))
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.No)
    p.clear_records()
    assert c.decision == CrossDecision.KEEP
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Yes)
    p.clear_records()
    assert c.decision == CrossDecision.UNDECIDED
    with CrossStore(p.database) as store:
        assert store.connection.execute("SELECT count(*) FROM cross_cache").fetchone()[0] == 0
        assert store.connection.execute("SELECT count(*) FROM cross_reviews").fetchone()[0] == 0
    assert c.target.path.exists() and c.representative.reference.path.exists()
