"""Two-folder review UI. One list entry and one explicit decision per B file."""

import sqlite3
from collections import Counter, OrderedDict
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QAbstractListModel, Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from .cross_models import CrossDecision
from .cross_preview import preview_pair
from .cross_scanner import scan_cross
from .cross_storage import CrossStore
from .cross_trash import cross_deletion_plan, move_cross_to_trash
from .folder_dialog import LocalFolderDialog
from .ui_utils import TaskThread, format_size, warning

DECISIONS = {
    CrossDecision.UNDECIDED: "미결정",
    CrossDecision.KEEP: "보관",
    CrossDecision.HOLD: "보류",
    CrossDecision.DELETE: "휴지통 이동 예정",
}
KINDS = {"file": "완전 동일", "pixel": "픽셀 동일", "similar": "유사 후보"}


def plain(text=""):
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


class PreviewLabel(QLabel):
    def __init__(self):
        super().__init__()
        self.source_pixmap = QPixmap()
        self.setMinimumSize(160, 140)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def show_payload(self, payload):
        self.source_pixmap.loadFromData(payload, "PNG")
        self.rescale()

    def rescale(self):
        if not self.source_pixmap.isNull():
            self.setPixmap(
                self.source_pixmap.scaled(
                    self.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

    def clear(self):
        self.source_pixmap = QPixmap()
        super().clear()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.rescale()


class CandidateModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []

    def replace(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self.rows)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.rows):
            return None
        row = self.rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            if isinstance(row, str):
                return row
            return (
                f"{row.target.path.name}\n{KINDS[row.representative.kind]} · "
                f"A 매칭 {len(row.matches)}개 · {DECISIONS[row.decision]}"
            )
        if role == Qt.ItemDataRole.ToolTipRole and not isinstance(row, str):
            return str(row.target.path)
        return None


class CrossPanel(QWidget):
    busy_changed = Signal(bool)
    idle = Signal()

    def __init__(self, database, parent=None):
        super().__init__(parent)
        self.database = database
        self.result = None
        self.worker = None
        self.pending_preview = None
        self.preview_cache = OrderedDict()
        self.preview_data = None
        self.current_candidate = None
        self.closing = False
        self.folder_a, self.folder_b = QLineEdit(), QLineEdit()
        self.recursive_a, self.recursive_b = (
            QCheckBox("하위 폴더 포함"),
            QCheckBox("하위 폴더 포함"),
        )
        self.browse_a, self.browse_b = QPushButton("A 선택"), QPushButton("B 선택")
        self.swap_button = QPushButton("A/B 폴더 바꾸기…")
        self.swap_button.clicked.connect(self.swap_folders)
        self.browse_a.clicked.connect(lambda: self.choose_folder(self.folder_a))
        self.browse_b.clicked.connect(lambda: self.choose_folder(self.folder_b))
        self.similar = QCheckBox("유사 이미지 찾기")
        self.similar.setChecked(True)
        self.threshold = QSpinBox()
        self.threshold.setRange(0, 12)
        self.threshold.setValue(6)
        self.similar.toggled.connect(self.threshold.setEnabled)
        self.scan_button, self.cancel_button = QPushButton("검색 시작"), QPushButton("검색 취소")
        self.scan_button.clicked.connect(self.start_scan)
        self.cancel_button.clicked.connect(self.cancel_task)
        self.cancel_button.setEnabled(False)
        self.summary = plain(
            "A는 보호된 기준 원본, B는 정리 대상입니다. 각 하위 폴더 옵션은 기본 꺼짐입니다."
        )
        self.status = plain("B의 모든 새 후보는 미결정입니다. 자동 선택·자동 삭제는 없습니다.")
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.tabs = QTabBar()
        for text in ("전체", "완전 동일", "픽셀 동일", "유사 후보", "제외/오류"):
            self.tabs.addTab(text)
        self.tabs.currentChanged.connect(self.refresh_list)
        self.state_filter = QComboBox()
        self.state_filter.addItem("모든 상태", "")
        for decision, label in DECISIONS.items():
            self.state_filter.addItem(label, decision.value)
        self.state_filter.currentIndexChanged.connect(self.refresh_list)
        self.search = QLineEdit()
        self.search.setPlaceholderText("B 또는 매칭 A 파일명 검색")
        self.filter_timer = QTimer(self)
        self.filter_timer.setSingleShot(True)
        self.filter_timer.setInterval(150)
        self.filter_timer.timeout.connect(self.refresh_list)
        self.search.textChanged.connect(lambda: self.filter_timer.start())
        self.model = CandidateModel(self)
        self.candidates = QListView()
        self.candidates.setModel(self.model)
        self.candidates.setUniformItemSizes(True)
        self.candidates.selectionModel().currentChanged.connect(self.show_candidate)
        self.match_choice = QComboBox()
        self.match_choice.currentIndexChanged.connect(self.show_match)
        self.reason = plain()
        self.info_a, self.info_b = plain(), plain()
        self.preview_a, self.preview_b = PreviewLabel(), PreviewLabel()
        self.decision = QComboBox()
        for value, label in DECISIONS.items():
            self.decision.addItem(label, value.value)
        self.decision.currentIndexChanged.connect(self.save_decision)
        self.large_preview = QPushButton("큰 미리보기…")
        self.large_preview.clicked.connect(self.show_large_preview)
        self.trash_button = QPushButton("휴지통 이동 예정 0개…")
        self.trash_button.clicked.connect(self.confirm_trash)
        self.clear_button = QPushButton("두 폴더 캐시·검토 기록 지우기…")
        self.clear_button.clicked.connect(self.clear_records)
        self.details = QWidget()
        details = QVBoxLayout(self.details)
        details.addWidget(self.match_choice)
        details.addWidget(self.reason)
        sides = QGridLayout()
        for column, (title, preview, info, control) in enumerate(
            (
                ("A — 보호된 기준 원본 (읽기 전용)", self.preview_a, self.info_a, None),
                ("B — 정리 대상", self.preview_b, self.info_b, self.decision),
            )
        ):
            sides.addWidget(plain(title), 0, column)
            sides.addWidget(preview, 1, column)
            sides.addWidget(info, 2, column)
            if control is not None:
                sides.addWidget(control, 3, column)
            sides.setColumnStretch(column, 1)
        sides.setRowStretch(1, 1)
        details.addLayout(sides, 1)
        details.addWidget(self.large_preview)
        self.details.setEnabled(False)
        split = QSplitter()
        split.addWidget(self.candidates)
        split.addWidget(self.details)
        split.setStretchFactor(1, 1)
        layout = QVBoxLayout(self)
        for title, field, browse, recursive in (
            ("폴더 A — 기준 원본 (보호됨)", self.folder_a, self.browse_a, self.recursive_a),
            ("폴더 B — 정리 대상", self.folder_b, self.browse_b, self.recursive_b),
        ):
            row = QHBoxLayout()
            row.addWidget(plain(title))
            row.addWidget(field, 1)
            row.addWidget(browse)
            row.addWidget(recursive)
            layout.addLayout(row)
        options = QHBoxLayout()
        for widget in (
            self.swap_button,
            self.similar,
            plain("pHash 거리"),
            self.threshold,
            self.scan_button,
            self.cancel_button,
        ):
            options.addWidget(widget)
        layout.addLayout(options)
        layout.addWidget(self.summary)
        layout.addWidget(self.tabs)
        filters = QHBoxLayout()
        filters.addWidget(self.state_filter)
        filters.addWidget(self.search, 1)
        layout.addLayout(filters)
        layout.addWidget(split, 1)
        layout.addWidget(self.status)
        layout.addWidget(self.progress)
        actions = QHBoxLayout()
        actions.addWidget(self.clear_button)
        actions.addStretch()
        actions.addWidget(self.trash_button)
        layout.addLayout(actions)

    def choose_folder(self, field):
        dialog = LocalFolderDialog(self, field.text())
        if dialog.exec():
            field.setText(dialog.selected_path)

    def swap_folders(self):
        if self.worker:
            return
        answer = QMessageBox.question(
            self,
            "A/B 역할 변경",
            "바꾸면 현재 B가 보호된 A가 되고, 현재 A가 정리 대상 B가 됩니다. 바꿀까요?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        a, b = self.folder_a.text(), self.folder_b.text()
        ra, rb = self.recursive_a.isChecked(), self.recursive_b.isChecked()
        self.folder_a.setText(b)
        self.folder_b.setText(a)
        self.recursive_a.setChecked(rb)
        self.recursive_b.setChecked(ra)
        self.reset_results()

    def set_busy(self, busy):
        for widget in (
            self.folder_a,
            self.folder_b,
            self.browse_a,
            self.browse_b,
            self.recursive_a,
            self.recursive_b,
            self.swap_button,
            self.similar,
            self.threshold,
            self.scan_button,
            self.tabs,
            self.state_filter,
            self.search,
            self.candidates,
            self.details,
            self.clear_button,
        ):
            widget.setEnabled(not busy)
        self.threshold.setEnabled(not busy and self.similar.isChecked())
        self.details.setEnabled(not busy and self.current_candidate is not None)
        self.cancel_button.setEnabled(busy)
        self.trash_button.setEnabled(not busy and self.result is not None)
        self.busy_changed.emit(busy)

    def start_task(self, operation, handler):
        if self.worker:
            return
        self.set_busy(True)
        worker = TaskThread(operation, self)
        self.worker = worker
        worker.progress.connect(self.on_progress)
        worker.completed.connect(handler)
        worker.failed.connect(self.failure)
        worker.finished.connect(self.finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def finished(self):
        self.worker = None
        self.set_busy(False)
        self.update_queue()
        if self.closing:
            self.pending_preview = None
            self.idle.emit()
        elif self.pending_preview is not None:
            match, self.pending_preview = self.pending_preview, None
            self.request_preview(match)

    def on_progress(self, phase, current, total):
        self.progress.setRange(0, 100 if total else 0)
        if total:
            self.progress.setValue(current * 100 // total)
        self.status.setText(f"{phase}: {current:,} / {total:,}")

    def cancel_task(self):
        self.pending_preview = None
        if self.worker:
            self.worker.cancel.set()
            self.cancel_button.setEnabled(False)
            self.status.setText("취소 요청됨. 현재 파일 작업이 끝나면 중단합니다…")

    def reset_results(self):
        self.result = None
        self.current_candidate = None
        self.model.replace([])
        self.preview_cache.clear()
        self.preview_data = None
        self.preview_a.clear()
        self.preview_b.clear()
        self.info_a.clear()
        self.info_b.clear()
        self.match_choice.clear()
        self.details.setEnabled(False)
        self.update_queue()

    def start_scan(self):
        if self.worker:
            return
        if not self.folder_a.text().strip() or not self.folder_b.text().strip():
            warning(self, "폴더 확인", "로컬 폴더 A와 B를 모두 선택하세요")
            return
        # Validation/enumeration remains on the worker, including filesystem queries.
        a, b = Path(self.folder_a.text().strip()), Path(self.folder_b.text().strip())
        ra, rb = self.recursive_a.isChecked(), self.recursive_b.isChecked()
        threshold, similar = self.threshold.value(), self.similar.isChecked()
        self.reset_results()
        self.progress.setRange(0, 0)
        self.status.setText("A/B 경로 검증 및 검색 준비 중…")
        self.start_task(
            lambda cancel, progress: scan_cross(
                a,
                b,
                ra,
                rb,
                threshold,
                similar,
                cancel,
                progress,
                self.database,
            ),
            self.scan_completed,
        )

    def scan_completed(self, result):
        self.result = result
        self.progress.setRange(0, 100)
        self.progress.setValue(0 if result.cancelled else 100)
        self.update_summary()
        self.refresh_list()
        self.status.setText(
            "취소했습니다. 불완전한 후보는 표시하지 않습니다."
            if result.cancelled
            else "검색 완료. A는 보호됩니다. B를 직접 검토하세요. "
            "휴지통 예정 상태는 자동 복원하지 않습니다."
        )

    def update_summary(self):
        if self.result is None:
            return
        kinds = Counter(m.kind for c in self.result.candidates for m in c.matches)
        self.summary.setText(
            f"A {self.result.scanned_a:,}장 · B {self.result.scanned_b:,}장 · "
            f"B 후보 {len(self.result.candidates):,}개 · 매칭 쌍 {sum(kinds.values()):,}개 · "
            f"완전 동일 {kinds['file']:,} / 픽셀 동일 {kinds['pixel']:,} / "
            f"유사 후보 {kinds['similar']:,} · "
            f"오류/제외 {len(self.result.errors):,} · 캐시 사용 {self.result.cache_hits:,}"
        )
        self.update_queue()

    def refresh_list(self, *_):
        previous = self.current_candidate
        self.current_candidate = None
        if self.result is None:
            self.model.replace([])
            return
        if self.tabs.currentIndex() == 4:
            self.model.replace(self.result.errors)
            self.details.setEnabled(False)
            return
        kind = {1: "file", 2: "pixel", 3: "similar"}.get(self.tabs.currentIndex())
        state = self.state_filter.currentData()
        text = self.search.text().casefold().strip()
        rows = [
            c
            for c in self.result.candidates
            if (not kind or any(m.kind == kind for m in c.matches))
            and (not state or c.decision.value == state)
            and (
                not text
                or text in c.target.path.name.casefold()
                or any(text in m.reference.path.name.casefold() for m in c.matches)
            )
        ]
        self.model.replace(rows)
        if rows:
            index = next((i for i, c in enumerate(rows) if c is previous), 0)
            self.candidates.setCurrentIndex(self.model.index(index))
        else:
            self.details.setEnabled(False)
            self.preview_a.clear()
            self.preview_b.clear()
        self.update_queue()

    def show_candidate(self, index, *_):
        if not index.isValid() or not 0 <= index.row() < len(self.model.rows):
            return
        candidate = self.model.rows[index.row()]
        if isinstance(candidate, str):
            return
        self.current_candidate = candidate
        self.decision.blockSignals(True)
        self.decision.setCurrentIndex(self.decision.findData(candidate.decision.value))
        self.decision.blockSignals(False)
        self.match_choice.blockSignals(True)
        self.match_choice.clear()
        for match in candidate.matches:
            self.match_choice.addItem(
                f"{KINDS[match.kind]} · pHash 거리 {match.distance} · {match.reference.path.name}"
            )
        self.match_choice.blockSignals(False)
        self.details.setEnabled(self.worker is None)
        self.show_match(0)

    def show_match(self, index):
        if self.current_candidate is None or not 0 <= index < len(self.current_candidate.matches):
            return
        match = self.current_candidate.matches[index]
        self.reason.setText(
            f"{KINDS[match.kind]} · pHash 거리 {match.distance}. "
            "pHash 거리 0도 동일 이미지의 증명이 아닙니다. 유사 후보는 다른 사진일 수 있습니다."
        )
        for record, label in ((match.reference, self.info_a), (match.target, self.info_b)):
            label.setText(
                f"{record.path.name}\n{record.path}\n{record.size:,} bytes "
                f"({format_size(record.size)}) · {record.width} × {record.height} · "
                f"확장자 {record.path.suffix or '(없음)'}\n수정 "
                f"{datetime.fromtimestamp(record.mtime_ns / 1e9):%Y-%m-%d %H:%M:%S}"
            )
        self.request_preview(match)

    def request_preview(self, match):
        if self.closing:
            return
        if self.worker:
            self.pending_preview = match
            return
        key = (
            str(match.reference.path),
            match.reference.signature,
            match.reference.sha256,
            str(match.target.path),
            match.target.signature,
            match.target.sha256,
        )
        if key in self.preview_cache:
            self.preview_cache.move_to_end(key)
            self.display_preview(self.preview_cache[key])
            return
        self.preview_data = None
        self.preview_a.clear()
        self.preview_b.clear()
        self.start_task(
            lambda cancel, _: preview_pair(match, cancel),
            lambda data: self.preview_completed(key, data),
        )

    def preview_completed(self, key, data):
        self.preview_cache[key] = data
        while len(self.preview_cache) > 12:
            self.preview_cache.popitem(last=False)
        self.display_preview(data)

    def display_preview(self, data):
        self.preview_data = data
        for label, payload in zip((self.preview_a, self.preview_b), data, strict=True):
            label.show_payload(payload)

    def show_large_preview(self):
        if not self.preview_data or self.worker:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("A (보호됨) ↔ B · 원본 기반 미리보기 (최대 1200×900)")
        dialog.resize(1200, 800)
        layout = QHBoxLayout(dialog)
        for title, payload in zip(("A — 보호됨", "B — 정리 대상"), self.preview_data, strict=True):
            container = QWidget()
            column = QVBoxLayout(container)
            column.addWidget(plain(title))
            label = QLabel()
            pixmap = QPixmap()
            pixmap.loadFromData(payload, "PNG")
            label.setPixmap(pixmap)
            column.addWidget(label)
            scroll = QScrollArea()
            scroll.setWidget(container)
            layout.addWidget(scroll)
        dialog.exec()

    def save_decision(self, *_):
        candidate = self.current_candidate
        if candidate is None or self.worker:
            return
        decision = CrossDecision(self.decision.currentData())
        try:
            with CrossStore(self.database) as store:
                store.set_cross(self.result, candidate, decision)
            candidate.decision = decision
            self.update_queue()
            # All matches share this candidate; state filters update immediately.
            self.refresh_list()
        except (OSError, ValueError, sqlite3.Error) as error:
            self.decision.blockSignals(True)
            self.decision.setCurrentIndex(self.decision.findData(candidate.decision.value))
            self.decision.blockSignals(False)
            warning(self, "선택 저장 실패", str(error))

    def update_queue(self):
        count = (
            sum(c.decision == CrossDecision.DELETE for c in self.result.candidates)
            if self.result
            else 0
        )
        self.trash_button.setText(f"휴지통 이동 예정 {count}개…")
        self.trash_button.setEnabled(not self.worker and count > 0)

    def confirm_trash(self):
        if self.worker or self.result is None:
            return
        try:
            targets = cross_deletion_plan(self.result)
        except (OSError, ValueError) as error:
            warning(self, "이동 차단", str(error))
            return
        if not targets:
            return
        question = QMessageBox(self)
        question.setTextFormat(Qt.TextFormat.PlainText)
        question.setWindowTitle("B 파일 휴지통 이동 확인")
        question.setIcon(QMessageBox.Icon.Warning)
        question.setText(f"선택한 B 파일 {len(targets)}개만 휴지통으로 이동할까요?")
        question.setInformativeText(
            "A는 이동하지 않습니다. 자세히 보기에서 전체 경로와 유형을 확인하세요."
        )
        question.setDetailedText(
            "\n".join(f"{c.target.path} — {KINDS[c.representative.kind]}" for c in targets)
        )
        question.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        question.setDefaultButton(QMessageBox.StandardButton.No)
        if question.exec() != QMessageBox.StandardButton.Yes:
            return
        similar = any(c.similar_only for c in targets)
        if similar:
            extra = QMessageBox(self)
            extra.setTextFormat(Qt.TextFormat.PlainText)
            extra.setWindowTitle("유사 후보 추가 확인")
            extra.setIcon(QMessageBox.Icon.Warning)
            extra.setText(
                "시각적으로 비슷하지만 동일 사진이 아닐 수 있습니다. "
                "그래도 선택한 B 파일을 이동할까요?"
            )
            extra.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            extra.setDefaultButton(QMessageBox.StandardButton.No)
            if extra.exec() != QMessageBox.StandardButton.Yes:
                return
        result = self.result
        self.start_task(
            lambda cancel, progress: move_cross_to_trash(
                result,
                cancel,
                progress,
                confirmed=True,
                similar_confirmed=similar,
            ),
            self.trash_completed,
        )

    def trash_completed(self, outcome):
        moved = set(outcome.moved)
        self.result.candidates[:] = [
            c for c in self.result.candidates if c.target.path not in moved
        ]
        self.result.errors.extend(outcome.errors)
        self.preview_cache.clear()
        self.update_summary()
        self.refresh_list()
        self.progress.setRange(0, 100)
        self.progress.setValue(0 if outcome.cancelled else 100)
        self.status.setText(
            f"{'중단' if outcome.cancelled else '처리 완료'} · B 이동 {len(moved)}개 · "
            f"실패 {len(outcome.errors)}개 · 후속 건너뜀 {len(outcome.skipped)}개. "
            "A는 보호됩니다. 오류/제외 탭에서 사유를 확인하세요."
        )

    def clear_records(self):
        if self.worker:
            return
        answer = QMessageBox.question(
            self,
            "두 폴더 기록 지우기",
            "두 폴더 분석 캐시와 검토 기록을 지울까요? 이미지 파일은 유지됩니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            with CrossStore(self.database) as store:
                store.clear_cross()
            if self.result:
                for candidate in self.result.candidates:
                    candidate.decision = CrossDecision.UNDECIDED
                self.refresh_list()
            self.status.setText("두 폴더 캐시·검토 기록을 지웠습니다. 이미지 파일은 유지됩니다.")
        except (OSError, ValueError, sqlite3.Error) as error:
            warning(self, "기록 지우기 실패", str(error))

    def failure(self, message):
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.pending_preview = None
        if self.result:
            self.result.errors.append(message)
            self.update_summary()
        self.status.setText(f"작업 실패: {message}")
