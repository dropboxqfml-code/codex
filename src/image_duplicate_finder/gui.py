import sqlite3
from pathlib import Path
from threading import Event

from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtGui import QCloseEvent, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .folder_dialog import LocalFolderDialog
from .models import Decision, ImageRecord, ScanResult
from .privacy import local_path
from .scanner import scan
from .storage import ReviewStore
from .trash import TrashResult, deletion_plan, move_to_trash

LABELS = {Decision.HOLD: "보류", Decision.KEEP: "보관", Decision.DELETE: "삭제 대상"}
KINDS = {"file": "파일 동일", "pixel": "픽셀 동일", "similar": "유사"}


def warning(parent, title, text):
    box = QMessageBox(parent)
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(title)
    box.setText(text)
    box.exec()


def format_size(size: int) -> str:
    return f"{size / 1024 / 1024:.2f} MB" if size >= 1024 * 1024 else f"{size / 1024:.1f} KB"


class TaskThread(QThread):
    progress = Signal(str, int, int)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, operation, parent=None):
        super().__init__(parent)
        self.operation = operation
        self.cancel = Event()

    def run(self):
        try:
            result = self.operation(self.cancel, self.progress.emit)
            self.completed.emit(result)
        except Exception as error:
            self.failed.emit(f"{type(error).__name__}: {error}")


class MainWindow(QMainWindow):
    def __init__(self, database: Path):
        super().__init__()
        self.database = database
        self.result = ScanResult()
        self.worker: TaskThread | None = None
        self.close_requested = False
        self.setWindowTitle("Image Duplicate Finder")
        self.resize(1200, 760)

        self.folder = QLineEdit()
        self.folder.setPlaceholderText("검색할 폴더를 선택하세요")
        self.browse = QPushButton("폴더 선택")
        self.browse.clicked.connect(self.choose_folder)
        self.recursive = QCheckBox("하위 폴더 포함")
        self.recursive.setChecked(True)
        self.threshold = QSpinBox()
        self.threshold.setRange(0, 64)
        self.threshold.setValue(6)
        self.threshold.setToolTip("64비트 pHash의 최대 허용 거리입니다. 낮을수록 엄격합니다.")
        self.scan_button = QPushButton("검색 시작")
        self.scan_button.clicked.connect(self.start_scan)
        self.cancel_button = QPushButton("취소")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_task)
        self.trash_button = QPushButton("삭제 대상을 휴지통으로…")
        self.trash_button.setEnabled(False)
        self.trash_button.clicked.connect(self.confirm_trash)
        self.errors_button = QPushButton("문제 보기")
        self.errors_button.setEnabled(False)
        self.errors_button.clicked.connect(self.show_errors)
        self.forget_button = QPushButton("선택 기록 지우기…")
        self.forget_button.clicked.connect(self.forget_reviews)

        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder, 1)
        folder_row.addWidget(self.browse)
        options = QHBoxLayout()
        options.addWidget(self.recursive)
        options.addWidget(QLabel("유사도 거리"))
        options.addWidget(self.threshold)
        options.addStretch()
        options.addWidget(self.scan_button)
        options.addWidget(self.cancel_button)

        self.group_list = QListWidget()
        self.group_list.setMinimumWidth(220)
        self.group_list.currentRowChanged.connect(self.show_group)
        self.images = QTreeWidget()
        self.images.setHeaderLabels(["이미지 / 파일명", "경로", "크기", "해상도", "선택"])
        self.images.setRootIsDecorated(False)
        self.images.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.images.setIconSize(QSize(160, 120))
        self.images.setColumnWidth(0, 270)
        self.images.setColumnWidth(1, 310)
        self.images.header().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        splitter = QSplitter()
        splitter.addWidget(self.group_list)
        splitter.addWidget(self.images)
        splitter.setStretchFactor(1, 1)
        self.status = QLabel("폴더를 선택하고 검색을 시작하세요. 모든 이미지는 기본 ‘보류’입니다.")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        actions = QHBoxLayout()
        actions.addWidget(self.errors_button)
        actions.addWidget(self.forget_button)
        actions.addStretch()
        actions.addWidget(self.trash_button)
        layout = QVBoxLayout()
        layout.addLayout(folder_row)
        layout.addLayout(options)
        note = QLabel(
            "그룹은 유사도 연결 관계입니다. 그룹 안의 모든 쌍이 같은 이미지는 아닙니다. "
            "삭제할 그룹에서 최소 한 장을 ‘보관’으로 지정하세요."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addWidget(splitter, 1)
        layout.addWidget(self.status)
        layout.addWidget(self.progress)
        layout.addLayout(actions)
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def choose_folder(self):
        dialog = LocalFolderDialog(self, self.folder.text())
        if dialog.exec():
            self.folder.setText(dialog.selected_path)

    def set_busy(self, busy: bool):
        for widget in (
            self.folder,
            self.browse,
            self.recursive,
            self.threshold,
            self.scan_button,
            self.group_list,
            self.images,
            self.forget_button,
        ):
            widget.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.trash_button.setEnabled(not busy and bool(self.result.groups))

    def start_task(self, operation, handler):
        if self.worker is not None:
            return
        self.set_busy(True)
        worker = TaskThread(operation, self)
        self.worker = worker
        worker.progress.connect(self.on_progress)
        worker.completed.connect(handler)
        worker.failed.connect(self.on_failure)
        worker.finished.connect(self.task_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def task_finished(self):
        self.worker = None
        self.set_busy(False)
        if self.close_requested:
            self.close()

    def on_progress(self, phase: str, current: int, total: int):
        if total:
            self.progress.setRange(0, 100)
            self.progress.setValue(current * 100 // total)
            self.status.setText(f"{phase}: {current:,} / {total:,}")
        else:
            self.progress.setRange(0, 0)
            self.status.setText(f"{phase}: {current:,}")

    def cancel_task(self):
        if self.worker:
            self.worker.cancel.set()
            self.cancel_button.setEnabled(False)
            self.status.setText("취소 요청됨. 현재 파일 작업이 끝나면 중단합니다…")

    def start_scan(self):
        if self.worker is not None:
            return
        raw_path = self.folder.text().strip()
        try:
            if not raw_path or not local_path(Path(raw_path)).is_dir():
                raise ValueError("존재하는 로컬 검색 폴더를 선택하세요.")
        except (OSError, ValueError) as error:
            warning(self, "폴더 확인", str(error))
            return
        folder = Path(raw_path)
        recursive, threshold = self.recursive.isChecked(), self.threshold.value()
        self.result = ScanResult()
        self.group_list.clear()
        self.images.clear()
        self.errors_button.setEnabled(False)
        self.progress.setRange(0, 0)
        self.status.setText("검색 준비 중…")
        self.start_task(
            lambda cancel, progress: scan(
                folder, recursive, threshold, cancel, progress, self.database
            ),
            self.scan_completed,
        )

    def scan_completed(self, result: ScanResult):
        self.result = result
        self.progress.setRange(0, 100)
        self.progress.setValue(0 if result.cancelled else 100)
        for index, group in enumerate(result.groups, 1):
            labels = ", ".join(KINDS[k] for k in ("file", "pixel", "similar") if k in group.kinds)
            self.group_list.addItem(f"그룹 {index} · {len(group.images)}장\n{labels}")
        if result.groups:
            self.group_list.setCurrentRow(0)
        self.errors_button.setEnabled(bool(result.errors))
        if result.cancelled:
            self.status.setText("검색을 취소했습니다. 불완전한 결과는 표시하지 않습니다.")
        else:
            self.status.setText(
                f"검색 완료 · 파일 {result.discovered:,}개 · 이미지 {result.scanned:,}장 · "
                f"중복/유사 그룹 {len(result.groups):,}개 · 문제 {len(result.errors):,}건. "
                "같은 경로·내용의 이전 선택은 복원됩니다."
            )

    def show_group(self, index: int):
        self.images.clear()
        if not 0 <= index < len(self.result.groups):
            return
        for record in self.result.groups[index].images:
            item = QTreeWidgetItem(
                [
                    record.path.name,
                    str(record.path),
                    format_size(record.size),
                    f"{record.width} × {record.height}",
                    "",
                ]
            )
            item.setToolTip(1, str(record.path))
            item.setSizeHint(0, QSize(270, 128))
            pixmap = QPixmap()
            pixmap.loadFromData(record.thumbnail, "PNG")
            item.setIcon(0, QIcon(pixmap))
            self.images.addTopLevelItem(item)
            combo = QComboBox()
            for decision, label in LABELS.items():
                combo.addItem(label, decision.value)
            combo.setCurrentIndex(combo.findData(record.decision.value))
            combo.currentIndexChanged.connect(lambda _, r=record, c=combo: self.save_decision(r, c))
            self.images.setItemWidget(item, 4, combo)

    def save_decision(self, record: ImageRecord, combo: QComboBox):
        decision = Decision(combo.currentData())
        try:
            with ReviewStore(self.database) as store:
                store.set(record, decision)
            record.decision = decision
        except (OSError, ValueError, sqlite3.Error) as error:
            combo.blockSignals(True)
            combo.setCurrentIndex(combo.findData(record.decision.value))
            combo.blockSignals(False)
            warning(self, "선택 저장 실패", str(error))

    def confirm_trash(self):
        if self.worker is not None:
            return
        try:
            targets = deletion_plan(self.result.groups)
        except ValueError as error:
            warning(self, "보관 이미지 필요", str(error))
            return
        if not targets:
            QMessageBox.information(
                self, "삭제 대상 없음", "이미지의 선택을 ‘삭제 대상’으로 바꾸세요."
            )
            return
        question = QMessageBox(self)
        question.setTextFormat(Qt.TextFormat.PlainText)
        question.setIcon(QMessageBox.Icon.Warning)
        question.setWindowTitle("휴지통 이동 확인")
        question.setText(f"선택한 {len(targets)}개 파일을 휴지통으로 이동할까요?")
        question.setInformativeText(
            f"합계 {format_size(sum(r.size for r in targets))}. "
            "자세히 보기에서 전체 경로를 확인하세요. 복원은 운영체제의 휴지통에서 합니다."
        )
        question.setDetailedText("\n".join(str(r.path) for r in targets))
        question.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        question.setDefaultButton(QMessageBox.StandardButton.No)
        if question.exec() != QMessageBox.StandardButton.Yes:
            return
        groups = self.result.groups
        self.start_task(
            lambda cancel, progress: move_to_trash(groups, cancel, progress, confirmed=True),
            self.trash_completed,
        )

    def trash_completed(self, result: TrashResult):
        moved = set(result.moved)
        for group in self.result.groups:
            group.images[:] = [r for r in group.images if r.path not in moved]
        self.result.groups[:] = [g for g in self.result.groups if len(g.images) > 1]
        self.result.errors.extend(result.errors)
        self.group_list.clear()
        self.images.clear()
        # Remaining groups are only an aid; rescan to recompute connectivity after removals.
        for index, group in enumerate(self.result.groups, 1):
            self.group_list.addItem(f"그룹 {index} · {len(group.images)}장 · 잔여 결과")
        if self.result.groups:
            self.group_list.setCurrentRow(0)
        self.progress.setRange(0, 100)
        self.progress.setValue(0 if result.cancelled else 100)
        self.errors_button.setEnabled(bool(self.result.errors))
        self.status.setText(
            f"{'중단' if result.cancelled else '처리 완료'} · 휴지통 이동 {len(moved)}개 · "
            f"실패 {len(result.errors)}개. 그룹을 갱신하려면 다시 검색하세요."
        )

    def show_errors(self):
        box = QMessageBox(self)
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setWindowTitle("검색·휴지통 이동 문제")
        box.setText(f"총 {len(self.result.errors)}건. 자세히 보기에서 내용을 확인하세요.")
        box.setDetailedText("\n".join(self.result.errors))
        box.exec()

    def forget_reviews(self):
        if self.worker is not None:
            return
        answer = QMessageBox.question(
            self,
            "선택 기록 지우기",
            "저장된 선택을 모두 지우고 보류로 바꿀까요? 이미지 파일은 유지됩니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            with ReviewStore(self.database) as store:
                store.clear()
            for group in self.result.groups:
                for record in group.images:
                    record.decision = Decision.HOLD
            self.show_group(self.group_list.currentRow())
            self.status.setText("선택 기록을 지웠습니다. 이미지 파일은 그대로입니다.")
        except (OSError, ValueError, sqlite3.Error) as error:
            warning(self, "기록 지우기 실패", str(error))

    def on_failure(self, message: str):
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.result.errors.append(message)
        self.errors_button.setEnabled(True)
        self.status.setText(f"작업 실패: {message}")

    def closeEvent(self, event: QCloseEvent):
        if self.worker is not None:
            self.close_requested = True
            self.cancel_task()
            event.ignore()
        else:
            event.accept()
