"""Read-only review of saved measurement results, independent of instrument sessions."""

from __future__ import annotations

import math
from html import escape
from pathlib import Path

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
)

from ..analysis.saved_run import (
    export_selection,
    load_saved_run,
    select_rows,
    summarize_rows,
)


def _quantity(value, unit):
    if value is None or not math.isfinite(value):
        return "—"
    if value == 0:
        return f"0 {unit}"
    for scale, prefix in (
        (1e15, "P"),
        (1e12, "T"),
        (1e9, "G"),
        (1e6, "M"),
        (1e3, "k"),
        (1, ""),
        (1e-3, "m"),
        (1e-6, "µ"),
        (1e-9, "n"),
        (1e-12, "p"),
        (1e-15, "f"),
    ):
        if abs(value) >= scale:
            return f"{value / scale:.6g} {prefix}{unit}"
    return f"{value:.6g} {unit}"


def _saved_status(status):
    value = status.get("status")
    if value == "completed":
        return "정상 완료"
    if value == "stopped":
        return "사용자 중지"
    if value == "aborted" and status.get("reason") in {
        "user STOP",
        "GUI close",
        "software immediate output stop",
        "CLI interrupt",
    }:
        return "사용자 중지 · 이전 기록"
    return {
        "aborted": "오류 중단",
        "interrupted": "미완료 기록",
        "running": "기록 중 상태",
        "armed": "실행 전 기록",
    }.get(value, "종료 상태 미기록")


class SavedResultDialog(QDialog):
    """Inspect a CSV, select an elapsed-time interval, and export a new analysis TXT.

    All filesystem reads are independent of the instrument worker. Loading a run
    never applies its configuration or resumes a measurement.
    """

    def __init__(self, path=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("6517A · 저장 결과 분석")
        self.resize(1100, 760)
        self.saved_run = None
        self.selected_rows = []
        self.statistics = {}
        self._setting_range = False
        self._build_ui()
        self._set_loaded(False)
        if path is not None:
            self.load_path(path)

    def _build_ui(self):
        root = QVBoxLayout(self)
        files = QHBoxLayout()
        self.open_button = QPushButton("저장 결과 열기")
        self.open_button.clicked.connect(self._choose_source)
        files.addWidget(self.open_button)
        self.path_label = QLabel("readings.csv를 선택하세요.")
        self.path_label.setTextFormat(Qt.TextFormat.PlainText)
        self.path_label.setWordWrap(True)
        files.addWidget(self.path_label, 1)
        root.addLayout(files)
        self.source_label = QLabel("장비 연결 없이 이전 결과를 확인합니다.")
        self.source_label.setTextFormat(Qt.TextFormat.PlainText)
        root.addWidget(self.source_label)

        interval = QGroupBox("분석 시간 구간")
        controls = QHBoxLayout(interval)
        controls.addWidget(QLabel("시작 (s)"))
        self.start_time = self._time_box()
        controls.addWidget(self.start_time)
        controls.addWidget(QLabel("끝 (s)"))
        self.end_time = self._time_box()
        controls.addWidget(self.end_time)
        self.apply_button = QPushButton("구간 적용")
        self.apply_button.clicked.connect(self.apply_range)
        controls.addWidget(self.apply_button)
        self.full_range_button = QPushButton("전체 구간")
        self.full_range_button.clicked.connect(self._full_range)
        controls.addWidget(self.full_range_button)
        controls.addStretch()
        root.addWidget(interval)

        self.selection_label = QLabel("선택된 데이터 없음")
        root.addWidget(self.selection_label)
        self.statistics_table = QTableWidget(2, 4)
        self.statistics_table.setHorizontalHeaderLabels(["물리량", "평균", "표준편차", "유효값 수"])
        self.statistics_table.verticalHeader().hide()
        self.statistics_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.statistics_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.statistics_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.statistics_table.setMaximumHeight(112)
        self.statistics_table.setToolTip(
            "표준편차: 표본 기준(n−1). 저항: native 우선, 없으면 V/I. 전류: 원시 측정값."
        )
        root.addWidget(self.statistics_table)
        self.graph_tabs = QTabWidget()
        self.plots = {}
        self.curves = {}
        for key, title, axis in (
            ("current", "전류 I(t)", "I (A)"),
            ("resistance", "저항 R(t)", "R (Ohm)"),
        ):
            plot = pg.PlotWidget()
            plot.setBackground("#111c2d")
            plot.showGrid(x=True, y=True, alpha=0.2)
            plot.setLabel("bottom", "Time", units="s")
            plot.setLabel("left", axis)
            curve = plot.plot(pen=pg.mkPen("#60c9de", width=2), symbol="o", symbolSize=4)
            self.plots[key], self.curves[key] = plot, curve
            self.graph_tabs.addTab(plot, title)
        root.addWidget(self.graph_tabs, 1)
        self.status_label = QLabel("첫 행은 항목·단위, 이후에는 네 열의 수치를 저장합니다.")
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        buttons = QHBoxLayout()
        self.export_button = QPushButton("선택 구간 TXT 저장")
        self.export_button.clicked.connect(self._choose_export)
        buttons.addWidget(self.export_button)
        buttons.addStretch()
        close = QPushButton("닫기")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        root.addLayout(buttons)
        self.start_time.valueChanged.connect(self._range_edited)
        self.end_time.valueChanged.connect(self._range_edited)
        self._display_statistics({})

    @staticmethod
    def _time_box():
        box = QDoubleSpinBox()
        box.setDecimals(6)
        box.setRange(-1e12, 1e12)
        box.setMinimumWidth(145)
        box.setKeyboardTracking(False)
        return box

    def _set_loaded(self, loaded):
        for widget in (
            self.start_time,
            self.end_time,
            self.apply_button,
            self.full_range_button,
        ):
            widget.setEnabled(loaded)
        self.export_button.setEnabled(loaded and bool(self.selected_rows))

    def _error(self, message):
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color:#a32e28")

    def _choose_source(self):
        initial = str(self.saved_run.directory) if self.saved_run is not None else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "저장 결과 열기", initial, "6517A 결과 (readings.csv);;CSV (*.csv)"
        )
        if path:
            self.load_path(path)

    def load_path(self, path):
        """Load only saved data; failures leave a concise message and disable export."""
        try:
            saved = load_saved_run(path)
            finite_times = [
                row["elapsed_s"] for row in saved.rows if row.get("elapsed_s") is not None
            ]
            if finite_times and max(abs(value) for value in finite_times) > 1e12:
                raise ValueError("시간 값이 지원 범위를 벗어났습니다.")
        except (OSError, ValueError, TypeError) as exc:
            self.saved_run = None
            self.selected_rows = []
            self.statistics = {}
            self._set_loaded(False)
            self._draw([])
            self._display_statistics({})
            self.selection_label.setText("선택된 데이터 없음")
            self.source_label.setText("결과를 불러오지 못했습니다.")
            self.path_label.setText(str(path))
            self._error(f"파일 확인 필요: {exc}")
            return False
        self.saved_run = saved
        self.path_label.setText(str(saved.source_path))
        simulation = saved.metadata.get("simulation")
        mode = (
            "SIMULATION"
            if simulation is True
            else ("실장비 기록" if simulation is False else "모드 미기록")
        )
        self.source_label.setText(
            f"{mode} · {_saved_status(saved.status)} · 전체 {len(saved.rows):,}개"
        )
        self.source_label.setToolTip(escape(str(saved.status.get("reason") or "")))
        self._set_loaded(bool(finite_times))
        if not finite_times:
            self.selected_rows = []
            self.statistics = {}
            self._draw([])
            self._display_statistics({})
            self.selection_label.setText("판독 데이터 없음")
            self._error("분석할 시간 데이터가 없습니다.")
            return True
        self._full_range()
        return True

    def _range_edited(self):
        if self._setting_range or self.saved_run is None:
            return
        self.export_button.setEnabled(False)
        self.selection_label.setText("구간 변경 · 구간 적용을 누르세요.")

    def _full_range(self):
        if self.saved_run is None:
            return
        times = [
            row["elapsed_s"] for row in self.saved_run.rows if row.get("elapsed_s") is not None
        ]
        if not times:
            return
        # Outward rounding avoids losing a boundary row to spin-box display precision.
        start = math.floor(min(times) * 1e6) / 1e6
        end = math.ceil(max(times) * 1e6) / 1e6
        self._setting_range = True
        for box in (self.start_time, self.end_time):
            box.setRange(start, end)
        self.start_time.setValue(start)
        self.end_time.setValue(end)
        self._setting_range = False
        self.apply_range()

    def apply_range(self):
        """Show the selected rows and independent finite-value statistics."""
        if self.saved_run is None:
            return False
        try:
            rows = select_rows(self.saved_run, self.start_time.value(), self.end_time.value())
            statistics = summarize_rows(rows)
        except (ValueError, TypeError) as exc:
            self.export_button.setEnabled(False)
            self._error(f"구간 확인 필요: {exc}")
            return False
        self.selected_rows = rows
        self.statistics = statistics
        self._display_statistics(statistics)
        self._draw(rows)
        invalid = statistics.get("invalid_count", 0)
        self.selection_label.setText(
            f"{self.start_time.value():g}–{self.end_time.value():g} s · 선택 {len(rows):,}개"
            + (f" · 통계 제외 {invalid:,}개" if invalid else "")
        )
        self.status_label.setText("표준편차는 n−1 기준입니다. 유효값이 한 개이면 —로 표시합니다.")
        self.status_label.setStyleSheet("color:#687582")
        self.export_button.setEnabled(bool(rows))
        return True

    def _display_statistics(self, values):
        for index, (key, label, unit) in enumerate(
            (("current", "전류", "A"), ("resistance", "저항", "Ω"))
        ):
            suffix = "A" if key == "current" else "ohm"
            fields = (
                label,
                _quantity(values.get(f"{key}_mean_{suffix}"), unit),
                _quantity(values.get(f"{key}_std_{suffix}"), unit),
                str(values.get(f"{key}_count", 0)),
            )
            for column, value in enumerate(fields):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.statistics_table.setItem(index, column, item)

    def _draw(self, rows):
        current, resistance = [], []
        for row in rows:
            elapsed = row.get("elapsed_s")
            if elapsed is None:
                continue
            amps = row.get("current_raw_A")
            ohms = row.get("native_r_ohm")
            if ohms is None:
                ohms = row.get("resistance_apparent_ohm")
            if amps is not None and math.isfinite(amps):
                current.append((elapsed, amps))
            if ohms is not None and math.isfinite(ohms):
                resistance.append((elapsed, ohms))
        for name, pairs in (("current", current), ("resistance", resistance)):
            self.curves[name].setData([pair[0] for pair in pairs], [pair[1] for pair in pairs])

    def _choose_export(self):
        if self.saved_run is None:
            return
        destination = str(self.saved_run.directory / "analysis-selection.txt")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "선택 구간 TXT 저장",
            destination,
            "Text (*.txt)",
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if path:
            self.export_to(path)

    def export_to(self, path):
        """Export the visible selection to a new file, leaving the original run untouched."""
        if not self.apply_range():
            return None
        if not self.selected_rows:
            self._error("저장할 구간 데이터를 선택하세요.")
            return None
        try:
            result = export_selection(
                self.saved_run, Path(path), self.start_time.value(), self.end_time.value()
            )
        except FileExistsError:
            self._error("같은 이름의 파일이 있습니다. 다른 이름으로 저장하세요.")
            return None
        except (OSError, ValueError, TypeError) as exc:
            self._error(f"TXT 저장 실패: {exc}")
            return None
        self.status_label.setText(f"TXT 저장 완료 · {len(self.selected_rows):,}개 · {path}")
        self.status_label.setStyleSheet("color:#16667a")
        return result
