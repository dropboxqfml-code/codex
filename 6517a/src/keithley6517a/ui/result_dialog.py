"""Read-only saved-result comparison and analysis settings, without instrument sessions."""

from __future__ import annotations

import math
from html import escape
from pathlib import Path

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
)

from ..analysis.saved_run import export_selection, load_saved_run, select_rows, summarize_rows
from ..analysis.session import (
    AnalysisSession,
    load_session,
    save_session,
    source_fingerprints,
)

MAX_COMPARE_FILES = 64
QUANTITIES = ("current", "resistance", "resistivity")
COLORS = ("#60c9de", "#ffbc66", "#b7a2ff", "#8bd9a5", "#ff91b5", "#fff08a", "#a8c7ff", "#f28c73")


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
    """Overlay saved runs; statistics and TXT always use the selected source alone."""

    def __init__(self, path=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("6517A · 저장 결과 분석")
        self.resize(1100, 760)
        self.saved_runs = []
        self.active_index = -1
        self.saved_run = None
        self.selected_rows = []
        self.statistics = {}
        self.selected_rows_by_run = []
        self.comparison_statistics = []
        self._source_fingerprints = []
        self._applied_range = None
        self._pending_range = False
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
        self.add_button = QPushButton("비교 추가")
        self.add_button.clicked.connect(self._choose_comparisons)
        files.addWidget(self.add_button)
        self.remove_button = QPushButton("선택 파일 제거")
        self.remove_button.clicked.connect(self._remove_selected_source)
        files.addWidget(self.remove_button)
        files.addStretch()
        self.open_session_button = QPushButton("분석 설정 열기")
        self.open_session_button.clicked.connect(self._choose_session)
        files.addWidget(self.open_session_button)
        self.save_session_button = QPushButton("분석 설정 저장")
        self.save_session_button.clicked.connect(self._choose_session_save)
        files.addWidget(self.save_session_button)
        root.addLayout(files)
        selection = QHBoxLayout()
        selection.addWidget(QLabel("통계·TXT 파일"))
        self.source_selector = QComboBox()
        self.source_selector.setMinimumContentsLength(24)
        self.source_selector.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.source_selector.currentIndexChanged.connect(self.select_source)
        self.source_selector.setToolTip(
            "그래프는 모든 파일을 겹쳐 표시합니다. 통계·TXT는 선택 파일입니다."
        )
        selection.addWidget(self.source_selector, 1)
        self.source_label = QLabel("장비 연결 없이 이전 결과를 확인합니다.")
        self.source_label.setTextFormat(Qt.TextFormat.PlainText)
        selection.addWidget(self.source_label)
        root.addLayout(selection)
        self.path_label = QLabel("readings.csv를 선택하세요.")
        self.path_label.setTextFormat(Qt.TextFormat.PlainText)
        self.path_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        root.addWidget(self.path_label)

        interval = QGroupBox("분석 시간 구간 · 각 실행의 측정 시작 기준")
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
        self.statistics_table = QTableWidget(3, 4)
        self.statistics_table.setHorizontalHeaderLabels(["물리량", "평균", "표준편차", "유효값 수"])
        self.statistics_table.verticalHeader().hide()
        self.statistics_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.statistics_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.statistics_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.statistics_table.setMaximumHeight(144)
        self.statistics_table.setToolTip(
            "선택 파일의 통계 · 표준편차 n−1 · 저항 native 우선, 없으면 V/I · "
            "전류 원시값 · 비저항 저장값"
        )
        root.addWidget(self.statistics_table)
        self.graph_tabs = QTabWidget()
        self.plots = {}
        for key, title, axis in (
            ("current", "전류 I(t)", "I (A)"),
            ("resistance", "저항 R(t)", "R (Ohm)"),
            ("resistivity", "비저항 ρ(t)", "ρ (Ω·m)"),
        ):
            plot = pg.PlotWidget()
            plot.setBackground("#111c2d")
            plot.showGrid(x=True, y=True, alpha=0.2)
            plot.setLabel("bottom", "Time", units="s")
            plot.setLabel("left", axis)
            plot.addLegend(offset=(10, 10))
            self.plots[key] = plot
            self.graph_tabs.addTab(plot, title)
        self.comparison_curves = []
        self.curves = {}
        self._rebuild_curves()
        self.graph_tabs.currentChanged.connect(self._refresh_file_selector)
        root.addWidget(self.graph_tabs, 1)
        self.status_label = QLabel("첫 행은 항목·단위, 이후에는 측정 수치를 저장합니다.")
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        buttons = QHBoxLayout()
        self.export_button = QPushButton("선택 구간 TXT 저장")
        self.export_button.setToolTip("통계·TXT 파일에서 선택한 한 파일의 구간만 저장합니다.")
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
        for widget in (self.start_time, self.end_time, self.apply_button, self.full_range_button):
            widget.setEnabled(loaded)
        self.source_selector.setEnabled(bool(self.saved_runs))
        self.remove_button.setEnabled(bool(self.saved_runs))
        applied = loaded and self._applied_range is not None and not self._pending_range
        self.export_button.setEnabled(applied and bool(self.selected_rows))
        self.save_session_button.setEnabled(applied)

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

    def _choose_comparisons(self):
        initial = str(self.saved_run.directory) if self.saved_run is not None else ""
        paths, _ = QFileDialog.getOpenFileNames(
            self, "비교 파일 추가", initial, "6517A 결과 (readings.csv);;CSV (*.csv)"
        )
        if paths:
            self.add_paths(paths)

    @staticmethod
    def _read_source(path):
        source = Path(path).expanduser().resolve(strict=True)
        if source.is_dir():
            source = (source / "readings.csv").resolve(strict=True)
        before = source_fingerprints(source)
        saved = load_saved_run(source)
        if source_fingerprints(source) != before:
            raise ValueError(f"읽는 중 결과 파일이 변경됐습니다: {source}")
        times = [row["elapsed_s"] for row in saved.rows if row.get("elapsed_s") is not None]
        if times and max(abs(value) for value in times) > 1e12:
            raise ValueError("시간 값이 지원 범위를 벗어났습니다.")
        return saved, before

    @staticmethod
    def _bounds(runs):
        times = [
            row["elapsed_s"]
            for saved in runs
            for row in saved.rows
            if row.get("elapsed_s") is not None
        ]
        if not times:
            return None
        return math.floor(min(times) * 1e6) / 1e6, math.ceil(max(times) * 1e6) / 1e6

    def _reset(self):
        self.saved_runs = []
        self.active_index = -1
        self.saved_run = None
        self.selected_rows = []
        self.statistics = {}
        self.selected_rows_by_run = []
        self.comparison_statistics = []
        self._source_fingerprints = []
        self._applied_range = None
        self._pending_range = False
        self._refresh_file_selector()
        self._rebuild_curves()
        self._display_statistics({})
        self._set_loaded(False)
        self.selection_label.setText("선택된 데이터 없음")

    def _install_runs(self, runs, fingerprints, active_index=0):
        self.saved_runs = list(runs)
        self._source_fingerprints = list(fingerprints)
        self.active_index = active_index
        self.saved_run = self.saved_runs[active_index]
        self.selected_rows_by_run = [[] for _ in runs]
        self.comparison_statistics = [{} for _ in runs]
        self.selected_rows = []
        self.statistics = {}
        self._applied_range = None
        self._pending_range = False
        self._refresh_file_selector()
        self._rebuild_curves()
        self._show_source()
        self._set_loaded(self._bounds(self.saved_runs) is not None)

    def load_path(self, path):
        """Open a single source, retaining the original single-file public API."""
        try:
            saved, fingerprints = self._read_source(path)
        except (OSError, ValueError, TypeError) as exc:
            self._reset()
            self.source_label.setText("결과를 불러오지 못했습니다.")
            self.path_label.setText(str(path))
            self._error(f"파일 확인 필요: {exc}")
            return False
        self._install_runs([saved], [fingerprints])
        if self._bounds(self.saved_runs) is None:
            self._display_statistics({})
            self.selection_label.setText("판독 데이터 없음")
            self._error("분석할 시간 데이터가 없습니다.")
            return True
        self._full_range()
        return True

    def add_paths(self, paths):
        """Append sources atomically; a bad file leaves the existing comparison intact."""
        if isinstance(paths, (str, Path)):
            paths = [paths]
        runs, fingerprints = list(self.saved_runs), list(self._source_fingerprints)
        known = {saved.source_path for saved in runs}
        duplicates = 0
        try:
            for path in paths:
                saved, snapshot = self._read_source(path)
                if saved.source_path in known:
                    duplicates += 1
                    continue
                if len(runs) >= MAX_COMPARE_FILES:
                    raise ValueError(f"비교 파일은 최대 {MAX_COMPARE_FILES}개입니다.")
                known.add(saved.source_path)
                runs.append(saved)
                fingerprints.append(snapshot)
        except (OSError, ValueError, TypeError) as exc:
            self._error(f"비교 추가 실패 · 기존 분석 유지: {exc}")
            return False
        if len(runs) == len(self.saved_runs):
            self.status_label.setText(
                "이미 추가한 파일입니다." if duplicates else "추가할 파일이 없습니다."
            )
            return True
        self._install_runs(runs, fingerprints, max(0, self.active_index))
        if self._bounds(runs) is not None:
            self._full_range()
        else:
            self._display_statistics({})
            self._error("분석할 시간 데이터가 없습니다.")
        if duplicates:
            self.status_label.setText(f"비교 파일 {len(runs)}개 · 중복 {duplicates}개 제외")
        return True

    def select_source(self, index):
        """Choose statistics/TXT source while retaining every overlaid curve."""
        if type(index) is not int or not 0 <= index < len(self.saved_runs):
            return False
        self.active_index = index
        self.saved_run = self.saved_runs[index]
        self.curves = self.comparison_curves[index]
        self.source_selector.blockSignals(True)
        self.source_selector.setCurrentIndex(index)
        self.source_selector.blockSignals(False)
        self._show_source()
        if self._applied_range is not None:
            self._render_selection()
        self._set_loaded(self._bounds(self.saved_runs) is not None)
        return True

    def remove_source(self, index=None):
        index = self.active_index if index is None else index
        if type(index) is not int or not 0 <= index < len(self.saved_runs):
            return False
        runs, fingerprints = list(self.saved_runs), list(self._source_fingerprints)
        runs.pop(index)
        fingerprints.pop(index)
        if not runs:
            self._reset()
            self.path_label.setText("readings.csv를 선택하세요.")
            self.source_label.setText("장비 연결 없이 이전 결과를 확인합니다.")
            self.status_label.setText("비교 파일을 모두 제거했습니다.")
            return True
        active = self.active_index - (index < self.active_index)
        self._install_runs(runs, fingerprints, min(active, len(runs) - 1))
        if self._bounds(runs) is not None:
            self._full_range()
        else:
            self._display_statistics({})
            self._error("분석할 시간 데이터가 없습니다.")
        return True

    def _remove_selected_source(self):
        self.remove_source()

    def _show_source(self):
        saved = self.saved_run
        if saved is None:
            return
        self.path_label.setText(str(saved.source_path))
        self.path_label.setToolTip(str(saved.source_path))
        simulation = saved.metadata.get("simulation")
        mode = (
            "SIMULATION"
            if simulation is True
            else ("VISA 기록" if simulation is False else "모드 미기록")
        )
        count = f" · 비교 {len(self.saved_runs)}개" if len(self.saved_runs) > 1 else ""
        self.source_label.setText(
            f"{mode} · {_saved_status(saved.status)} · 전체 {len(saved.rows):,}개{count}"
        )
        self.source_label.setToolTip(escape(str(saved.status.get("reason") or "")))

    @staticmethod
    def _source_name(saved, index):
        sample = str(saved.settings.get("sample_id") or saved.directory.name)
        sample = sample if len(sample) <= 35 else sample[:32] + "…"
        simulation = saved.metadata.get("simulation")
        mode = "SIM" if simulation is True else ("VISA" if simulation is False else "모드?")
        return f"{index + 1}. {sample} [{mode}]"

    def _refresh_file_selector(self, _index=None):
        self.source_selector.blockSignals(True)
        self.source_selector.clear()
        quantity = (
            QUANTITIES[self.graph_tabs.currentIndex()] if hasattr(self, "graph_tabs") else "current"
        )
        key, unit, label = {
            "current": ("current_mean_A", "A", "I"),
            "resistance": ("resistance_mean_ohm", "Ω", "R"),
            "resistivity": ("resistivity_mean_ohm_m", "Ω·m", "ρ"),
        }[quantity]
        for index, saved in enumerate(self.saved_runs):
            title = self._source_name(saved, index)
            if index < len(self.comparison_statistics):
                stats = self.comparison_statistics[index]
                count = stats.get(quantity + "_count", 0)
                title += f" · {label} 평균 {_quantity(stats.get(key), unit)} · n={count}"
            self.source_selector.addItem(title)
            self.source_selector.setItemData(
                index, QColor(COLORS[index % len(COLORS)]), Qt.ItemDataRole.DecorationRole
            )
            self.source_selector.setItemData(
                index, str(saved.source_path), Qt.ItemDataRole.ToolTipRole
            )
        self.source_selector.setCurrentIndex(self.active_index)
        self.source_selector.blockSignals(False)

    def _rebuild_curves(self):
        self.comparison_curves = []
        for plot in self.plots.values():
            plot.clear()
            plot.getPlotItem().legend.clear()
        for index in range(max(1, len(self.saved_runs))):
            curves = {}
            name = (
                escape(self._source_name(self.saved_runs[index], index))
                if self.saved_runs
                else None
            )
            for key, plot in self.plots.items():
                curves[key] = plot.plot(
                    pen=pg.mkPen(COLORS[index % len(COLORS)], width=2),
                    symbol="o",
                    symbolSize=4,
                    name=name,
                )
            self.comparison_curves.append(curves)
        self.curves = self.comparison_curves[max(0, self.active_index)]

    def _range_edited(self):
        if self._setting_range or self.saved_run is None:
            return
        self._pending_range = True
        self._set_loaded(True)
        self.selection_label.setText("구간 변경 · 구간 적용을 누르세요.")

    def _set_interval(self, bounds, start, end):
        self._setting_range = True
        try:
            for box in (self.start_time, self.end_time):
                box.setRange(*bounds)
            self.start_time.setValue(start)
            self.end_time.setValue(end)
        finally:
            self._setting_range = False

    def _full_range(self):
        bounds = self._bounds(self.saved_runs)
        if bounds is None:
            return
        self._set_interval(bounds, *bounds)
        self.apply_range()

    def apply_range(self):
        """Apply one inclusive interval to all files without combining their statistics."""
        if self.saved_run is None:
            return False
        start, end = self.start_time.value(), self.end_time.value()
        try:
            rows = [select_rows(saved, start, end) for saved in self.saved_runs]
            statistics = [summarize_rows(selected) for selected in rows]
        except (ValueError, TypeError) as exc:
            self._pending_range = True
            self._set_loaded(True)
            self._error(f"구간 확인 필요: {exc}")
            return False
        self.selected_rows_by_run = rows
        self.comparison_statistics = statistics
        self._applied_range = start, end
        self._pending_range = False
        self._render_selection()
        return True

    def _render_selection(self):
        self.selected_rows = self.selected_rows_by_run[self.active_index]
        self.statistics = self.comparison_statistics[self.active_index]
        self._display_statistics(self.statistics)
        self._draw(self.selected_rows)
        self._refresh_file_selector()
        invalid = self.statistics.get("invalid_count", 0)
        start, end = self._applied_range
        self.selection_label.setText(
            f"{start:g}–{end:g} s · 선택 파일 {self.active_index + 1} · "
            f"선택 {len(self.selected_rows):,}개"
            + (f" · 통계 제외 {invalid:,}개" if invalid else "")
        )
        message = "표준편차는 n−1 기준입니다. 유효값이 한 개이면 —로 표시합니다."
        if self.selected_rows and not any(
            row.get("resistivity_ohm_m") is not None for row in self.selected_rows
        ):
            message += " 선택 구간에 저장된 비저항이 없습니다."
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color:#687582")
        if self._pending_range:
            self.selection_label.setText("구간 변경 · 구간 적용을 누르세요.")
        self._set_loaded(True)

    def _display_statistics(self, values):
        for index, (key, suffix, label, unit) in enumerate(
            (
                ("current", "A", "전류", "A"),
                ("resistance", "ohm", "저항", "Ω"),
                ("resistivity", "ohm_m", "비저항", "Ω·m"),
            )
        ):
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

    @staticmethod
    def _plot_rows(curves, rows):
        pairs = {key: [] for key in QUANTITIES}
        for row in rows:
            elapsed = row.get("elapsed_s")
            if elapsed is None:
                continue
            ohms = row.get("native_r_ohm")
            if ohms is None:
                ohms = row.get("resistance_apparent_ohm")
            for key, value in (
                ("current", row.get("current_raw_A")),
                ("resistance", ohms),
                ("resistivity", row.get("resistivity_ohm_m")),
            ):
                if value is not None and math.isfinite(value):
                    pairs[key].append((elapsed, value))
        for key, values in pairs.items():
            curves[key].setData([value[0] for value in values], [value[1] for value in values])

    def _draw(self, rows):
        self._plot_rows(self.curves, rows)
        for index, selected in enumerate(self.selected_rows_by_run):
            if index != self.active_index:
                self._plot_rows(self.comparison_curves[index], selected)

    def _choose_export(self):
        if self.saved_run is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "선택 파일 · 선택 구간 TXT 저장",
            str(self.saved_run.directory / "analysis-selection.txt"),
            "Text (*.txt)",
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if path:
            self.export_to(path)

    def export_to(self, path):
        """Export one selected file, never a mixture of overlaid measurement rows."""
        if self._pending_range:
            self._error("구간 적용 후 저장하세요.")
            return None
        if not self.apply_range():
            return None
        if not self.selected_rows:
            self._error("저장할 구간 데이터를 선택하세요.")
            return None
        try:
            result = export_selection(self.saved_run, Path(path), *self._applied_range)
        except FileExistsError:
            self._error("같은 이름의 파일이 있습니다. 다른 이름으로 저장하세요.")
            return None
        except (OSError, ValueError, TypeError) as exc:
            self._error(f"TXT 저장 실패: {exc}")
            return None
        columns = 5 if self.saved_run.include_resistivity else 4
        self.status_label.setText(
            f"TXT 저장 완료 · 선택 파일 {self.active_index + 1} · "
            f"{len(self.selected_rows):,}개 · {columns}열 · {path}"
        )
        self.status_label.setStyleSheet("color:#16667a")
        return result

    def _choose_session_save(self):
        initial = (
            str(self.saved_run.directory / "analysis-session.json")
            if self.saved_run
            else "analysis-session.json"
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "분석 설정 저장",
            initial,
            "Analysis JSON (*.json)",
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if path:
            self.save_session_to(path)

    def _choose_session(self):
        path, _ = QFileDialog.getOpenFileName(self, "분석 설정 열기", "", "Analysis JSON (*.json)")
        if path:
            self.load_session_path(path)

    def save_session_to(self, path):
        if self._pending_range or self._applied_range is None or not self.saved_runs:
            self._error("분석 구간을 적용한 뒤 설정을 저장하세요.")
            return False
        try:
            session = AnalysisSession(
                tuple(saved.source_path for saved in self.saved_runs),
                *self._applied_range,
                active_index=self.active_index,
                quantity=QUANTITIES[self.graph_tabs.currentIndex()],
            )
            save_session(session, path, expected_fingerprints=tuple(self._source_fingerprints))
        except FileExistsError:
            self._error("같은 이름의 파일이 있습니다. 다른 이름으로 저장하세요.")
            return False
        except (OSError, ValueError, TypeError) as exc:
            self._error(f"분석 설정 저장 실패: {exc}")
            return False
        self.status_label.setText(f"분석 설정 저장 완료 · {len(self.saved_runs)}개 파일 · {path}")
        self.status_label.setStyleSheet("color:#16667a")
        return True

    def load_session_path(self, path):
        """Restore all validated sources together, retaining current analysis on failure."""
        try:
            session = load_session(path)
            if len(session.sources) > MAX_COMPARE_FILES:
                raise ValueError(f"비교 파일은 최대 {MAX_COMPARE_FILES}개입니다.")
            loaded = [self._read_source(source) for source in session.sources]
            runs, snapshots = zip(*loaded, strict=True)
            if load_session(path) != session:
                raise ValueError("읽는 중 분석 설정이 변경됐습니다.")
            bounds = self._bounds(runs)
            if bounds is None:
                raise ValueError("분석할 시간 데이터가 없습니다.")
            if session.start_s < bounds[0] or session.end_s > bounds[1]:
                raise ValueError("분석 설정의 시간 구간이 결과 범위를 벗어났습니다.")
            if any(round(value, 6) != value for value in (session.start_s, session.end_s)):
                raise ValueError("분석 설정의 시간은 소수 6자리까지 지원합니다.")
        except (OSError, ValueError, TypeError) as exc:
            self._error(f"분석 설정 열기 실패 · 기존 분석 유지: {exc}")
            return False
        self._install_runs(runs, snapshots, session.active_index)
        self._set_interval(bounds, session.start_s, session.end_s)
        self.graph_tabs.setCurrentIndex(QUANTITIES.index(session.quantity))
        self.apply_range()
        self.status_label.setText(f"분석 설정 열기 완료 · {len(runs)}개 파일 · {path}")
        self.status_label.setStyleSheet("color:#16667a")
        return True
