"""Qt desktop client. Exactly one worker owns instrument I/O.

STOP only sets the runner's cooperative cancellation event. It never opens a
second session or issues instrument commands from the Qt GUI thread.
"""

from __future__ import annotations

import json
import math
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QObject, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from keithley6517a.config import RunConfig
from keithley6517a.measurement.runner import MeasurementRunner


def _text_state(value: Any) -> str:
    return str(getattr(value, "value", value))


class InstrumentWorker(QObject):
    """All connect/ARM/acquire/OFF/disconnect calls run on this QObject's thread."""

    status = Signal(dict)
    sample = Signal(dict)
    event = Signal(dict)
    error = Signal(str)
    resources_found = Signal(list)
    diagnostic_ready = Signal(dict)
    closed = Signal()

    def __init__(self, runner_factory: Callable[..., Any]):
        super().__init__()
        self.runner_factory = runner_factory
        self.runner: Any = None

    def snapshot(self) -> None:
        if self.runner is None:
            self.status.emit(
                {
                    "state": "DISCONNECTED",
                    "output_state": "UNKNOWN",
                    "can_arm": False,
                    "can_start": False,
                }
            )
            return
        instrument = getattr(self.runner, "instrument", None)
        safety = getattr(instrument, "last_safety", None) or {}
        commissioning = getattr(self.runner, "commissioning", {}) or {}
        commissioned = bool(commissioning.get("ready", False))
        self.status.emit(
            {
                "state": _text_state(self.runner.state),
                "output_state": _text_state(self.runner.output_state),
                "residual_voltage_state": _text_state(
                    getattr(self.runner, "residual_voltage_state", "UNVERIFIED")
                ),
                "identity": getattr(self.runner, "identity", {}),
                "run_directory": str(getattr(self.runner, "run_directory", "") or ""),
                "can_arm": bool(getattr(self.runner, "can_arm", False)),
                "can_start": bool(getattr(self.runner, "can_start", False)),
                "interlock_query": safety.get("interlock", "UNKNOWN"),
                "commissioning": commissioning,
                "fixture_commissioning": (
                    "SIMULATED · 실장비 인증 아님"
                    if self.runner.config.simulation
                    else (
                        "현재 연결의 OFF 상태 0→1 확인 · 하드웨어 인증 아님"
                        if commissioned
                        else "현재 연결의 OFF 상태 lid open=0 / closed=1 확인 필요"
                    )
                ),
            }
        )

    def handle_event(self, event: dict) -> None:
        self.event.emit(event)
        self.snapshot()

    @Slot(object)
    def dispatch(self, command: tuple) -> None:
        action, config = command
        try:
            if action in {"discover", "diagnose"}:
                if self.runner is not None:
                    raise RuntimeError("Disconnect before opening a diagnostic VISA session")
                if action == "discover":
                    from ..transport.visa import VisaTransport

                    self.resources_found.emit(list(VisaTransport.list_resources(config or None)))
                else:
                    from ..diagnostics import run_diagnostics

                    self.diagnostic_ready.emit(run_diagnostics(**config))
            elif action == "connect":
                if self.runner is not None:
                    raise RuntimeError("Disconnect before replacing the configuration")
                self.runner = self.runner_factory(
                    config, on_sample=self.sample.emit, on_event=self.handle_event
                )
                self.runner.connect()
            elif action == "arm":
                if self.runner is None:
                    raise RuntimeError("Connect first")
                self.runner.arm()
            elif action in {"commission_open", "commission_closed"}:
                if self.runner is None:
                    raise RuntimeError("Connect first")
                self.runner.commission_interlock(0 if action == "commission_open" else 1)
            elif action == "start":
                if self.runner is None:
                    raise RuntimeError("Connect and ARM first")
                self.runner.start()
            elif action in {"disconnect", "shutdown"}:
                if self.runner is not None:
                    self.runner.shutdown()
                    self.runner = None
                if action == "shutdown":
                    self.closed.emit()
            else:
                raise ValueError(f"Unknown worker action: {action}")
        except Exception as exc:
            self.error.emit(f"{type(exc).__name__}: {exc}")
            if action == "shutdown":
                # A shutdown failure must not be labelled OFF or normal completion.
                self.status.emit({"state": "HV_STATE_UNKNOWN", "output_state": "UNKNOWN"})
                self.closed.emit()
        finally:
            if action != "shutdown":
                self.snapshot()

    def request_stop(self, reason: str) -> None:
        """Called from GUI thread: runner.request_stop only sets a threading Event."""
        runner = self.runner
        if runner is not None:
            runner.request_stop(reason)


class TracePanel(QWidget):
    """Signed data stay visible in linear and symmetric-log displays."""

    def __init__(self, title: str, x_key: str, y_key: str, x_label: str, y_label: str):
        super().__init__()
        self.x_key, self.y_key = x_key, y_key
        self.y_label = y_label
        self.rows: list[dict] = []
        layout = QVBoxLayout(self)
        heading = QHBoxLayout()
        heading.addWidget(QLabel(title))
        self.scale = QComboBox()
        self.scale.addItems(["Linear (signed)", "Signed log (symlog)"])
        heading.addWidget(self.scale)
        layout.addLayout(heading)
        self.plot = pg.PlotWidget()
        self.plot.setBackground("#111c2d")
        self.plot.showGrid(x=True, y=True, alpha=0.2)
        self.plot.setLabel("bottom", x_label)
        self.plot.setLabel("left", y_label)
        self.curve = self.plot.plot(pen=pg.mkPen("#60c9de", width=2), symbol="o", symbolSize=3)
        layout.addWidget(self.plot)
        self.scale.currentIndexChanged.connect(self.redraw)

    def redraw(self) -> None:
        pairs = [
            (row.get(self.x_key), row.get(self.y_key))
            for row in self.rows
            if row.get(self.x_key) is not None and row.get(self.y_key) is not None
        ]
        pairs = [(x, y) for x, y in pairs if math.isfinite(x) and math.isfinite(y)]
        if not pairs:
            self.curve.setData([], [])
            return
        x, y = np.array(pairs, dtype=float).T
        if self.scale.currentIndex():
            nonzero = np.abs(y[y != 0])
            linthresh = float(np.min(nonzero)) if len(nonzero) else 1.0
            y = np.sign(y) * np.log10(1 + np.abs(y) / linthresh)
            self.plot.setLabel("left", f"signed log(1+|{self.y_label}|/{linthresh:.2g})")
        else:
            self.plot.setLabel("left", self.y_label)
        self.curve.setData(x, y)


class MainWindow(QMainWindow):
    command = Signal(object)

    def __init__(self, runner_factory: Callable[..., Any] = MeasurementRunner):
        super().__init__()
        self.setWindowTitle("6517A · 고저항 측정")
        self.resize(1360, 900)
        self._state = "DISCONNECTED"
        self._busy = False
        self._connected = False
        self._closing = False
        self._closed = False
        self._last_sample_time: float | None = None
        self._last_elapsed: float | None = None
        self._fixture_status = "미확인"
        self._can_arm = False
        self._can_start = False
        self._commissioning = {}
        self._last_run_directory = None
        self._last_diagnostic_directory = None
        self.rows: list[dict] = []
        self._base_config = RunConfig().to_dict()
        self._build_ui()
        self._load_controls(self._base_config)
        self.worker_thread = QThread(self)
        self.worker = InstrumentWorker(runner_factory)
        self.worker.moveToThread(self.worker_thread)
        self.command.connect(self.worker.dispatch)
        self.worker.status.connect(self._on_status)
        self.worker.sample.connect(self._on_sample)
        self.worker.event.connect(self._on_event)
        self.worker.error.connect(self._on_error)
        self.worker.resources_found.connect(self._on_resources)
        self.worker.diagnostic_ready.connect(self._on_diagnostic)
        self.worker.closed.connect(self._worker_closed)
        self.worker_thread.finished.connect(self.worker.deleteLater)
        self.worker_thread.start()
        self.stale_timer = QTimer(self)
        self.stale_timer.timeout.connect(self._mark_stale)
        self.stale_timer.start(500)
        self._update_buttons()

    @staticmethod
    def _spin(minimum: float, maximum: float, value: float, decimals: int = 3):
        widget = QDoubleSpinBox()
        widget.setDecimals(decimals)
        widget.setRange(minimum, maximum)
        widget.setValue(value)
        return widget

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        self.mode_badge = QLabel("SIMULATION MODE · 실제 장비 출력 없음")
        self.mode_badge.setStyleSheet("font-size:20px;font-weight:700;color:#168ba5;padding:8px")
        root.addWidget(self.mode_badge)
        self.identity_label = QLabel("연결 안 됨 · model / serial / firmware 미확인")
        root.addWidget(self.identity_label)
        status = QHBoxLayout()
        self.state_label = QLabel("DISCONNECTED")
        self.output_label = QLabel("OUTPUT UNKNOWN")
        self.output_label.setStyleSheet("font-weight:bold;color:#b74d21")
        self.interlock_label = QLabel("Interlock query: UNKNOWN · fixture commissioning: 미확인")
        for widget in (self.state_label, self.output_label, self.interlock_label):
            status.addWidget(widget)
        root.addLayout(status)
        warning = QLabel(
            "잔류 전압 UNVERIFIED · 출력 OFF는 방전 완료가 아닙니다. 외부 확인 전 접촉 금지.\n"
            "software STOP은 하드웨어 비상정지가 아닙니다. "
            "진행 중인 VISA I/O는 timeout까지 지연될 수 있습니다."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("background:#fff1d6;color:#774600;padding:8px")
        root.addWidget(warning)
        splitter = QSplitter()
        root.addWidget(splitter, 1)
        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        self.settings = QWidget()
        settings_scroll.setWidget(self.settings)
        left = QVBoxLayout(self.settings)
        form = QFormLayout()
        self.transport = QComboBox()
        self.transport.addItem("SIMULATION", "simulation")
        self.transport.addItem("VISA USB–GPIB · 명시적 실장비 선택", "visa")
        form.addRow("연결", self.transport)
        self.resource = QLineEdit()
        self.resource.setPlaceholderText("사용자가 선택한 GPIB resource")
        form.addRow("Resource", self.resource)
        self.backend = QLineEdit()
        self.backend.setPlaceholderText("기본 VISA / @ivi / VISA library 경로")
        form.addRow("VISA backend", self.backend)
        resources_row = QHBoxLayout()
        self.resource_choices = QComboBox()
        self.resource_choices.addItem("GPIB 목록을 조회한 뒤 선택")
        self.discover_button = QPushButton("VISA 목록 조회")
        resources_row.addWidget(self.resource_choices, 1)
        resources_row.addWidget(self.discover_button)
        form.addRow(resources_row)
        diagnostics_row = QHBoxLayout()
        self.diagnose_button = QPushButton("연결 진단 · IDN만 조회")
        self.off_check_button = QPushButton("선택 장비 출력 OFF 시험")
        diagnostics_row.addWidget(self.diagnose_button)
        diagnostics_row.addWidget(self.off_check_button)
        form.addRow(diagnostics_row)
        self.setup_button = QPushButton("실장비 시험 설정 안내 · 양식 입력")
        form.addRow(self.setup_button)
        self.mode = QComboBox()
        self.mode.addItems(["FVMI_CURRENT", "NATIVE_RESISTANCE"])
        form.addRow("모드", self.mode)
        self.sample_id = QLineEdit("sample")
        form.addRow("Sample ID", self.sample_id)
        self.profile = QComboBox()
        self.profile.addItems(["전압 리스트 / 정전압", "선형 staircase", "Fixed-time 요약 window"])
        form.addRow("시간 / 전압 프로토콜", self.profile)
        self.voltages = QLineEdit("0")
        form.addRow("V-list (V, comma)", self.voltages)
        stair = QHBoxLayout()
        self.stair_start = self._spin(-1000, 1000, 0)
        self.stair_stop = self._spin(-1000, 1000, 10)
        self.stair_step = self._spin(-1000, 1000, 1)
        for widget in (self.stair_start, self.stair_stop, self.stair_step):
            stair.addWidget(widget)
        form.addRow("Stair start / stop / step V", stair)
        self.ceiling = self._spin(0, 1000, 10)
        form.addRow("Software ceiling (V)", self.ceiling)
        self.trip = QLineEdit()
        self.trip.setPlaceholderText("필수: A 단위 (예: 1e-8)")
        form.addRow("Software current trip (A)", self.trip)
        self.protection_label = QLabel(
            "Software trip: 판독·통신 지연 후 소프트웨어 중지\n"
            "V-Source 하드웨어 limit: 100 V 범위 10 mA / 1000 V 범위 1 mA\n"
            "외부 하드웨어 보호는 별도 검증 필요. programmable compliance가 아닙니다."
        )
        self.protection_label.setWordWrap(True)
        form.addRow(self.protection_label)
        self.source_range = QComboBox()
        self.source_range.addItems(["100", "1000"])
        form.addRow("Source range (V)", self.source_range)
        self.autorange = QCheckBox("Current autorange (Auto V-Source와 별개)")
        self.autorange.setChecked(True)
        form.addRow(self.autorange)
        self.current_range = QLineEdit("2e-9")
        form.addRow("고정 current range (A)", self.current_range)
        self.nplc = self._spin(0.01, 10, 10)
        form.addRow("NPLC", self.nplc)
        self.interval = self._spin(0.001, 86400, 1)
        form.addRow("요청 sample interval (s)", self.interval)
        self.dwell = self._spin(0.001, 86400, 300)
        form.addRow("Step dwell / duration (s)", self.dwell)
        self.exclude = self._spin(0, 86400, 1)
        form.addRow("초기 제외 구간 (s)", self.exclude)
        self.window = self._spin(0.001, 86400, 30)
        form.addRow("마지막 summary window (s)", self.window)
        self.output_dir = QLineEdit("runs")
        form.addRow("자동 저장 폴더", self.output_dir)
        self.ack = QCheckBox("잔류 전압 미확인 및 software stop의 한계를 확인했습니다")
        form.addRow(self.ack)
        left.addLayout(form)
        load_row = QHBoxLayout()
        self.load_button = QPushButton("설정 불러오기")
        self.save_button = QPushButton("설정 내보내기")
        load_row.addWidget(self.load_button)
        load_row.addWidget(self.save_button)
        left.addLayout(load_row)
        self.advanced = QPlainTextEdit()
        self.advanced.setPlaceholderText("정격 / commissioning / 환경 / 시료 metadata JSON")
        self.advanced.setMinimumHeight(160)
        self.advanced_apply = QPushButton("고급 JSON을 입력란에 적용 (출력 변경 없음)")
        left.addWidget(QLabel("전체 설정 JSON · ARM은 설정 snapshot을 검증합니다"))
        left.addWidget(self.advanced)
        left.addWidget(self.advanced_apply)
        left.addStretch()
        splitter.addWidget(settings_scroll)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.live_label = QLabel("STALE · 아직 취득한 판독값 없음")
        self.live_label.setWordWrap(True)
        right_layout.addWidget(self.live_label)
        tabs = QTabWidget()
        self.traces = [
            TracePanel("I(t) · current raw", "elapsed_s", "current_raw_A", "time (s)", "I (A)"),
            TracePanel("R(t) · V/I 또는 native", "elapsed_s", "_display_r", "time (s)", "R (Ω)"),
            TracePanel(
                "I–V · 각 판독",
                "voltage_programmed_readback_V",
                "current_raw_A",
                "setpoint (V)",
                "I (A)",
            ),
            TracePanel(
                "R–V · 각 판독",
                "voltage_programmed_readback_V",
                "_display_r",
                "setpoint (V)",
                "R (Ω)",
            ),
        ]
        for name, trace in zip(("I(t)", "R(t)", "I–V", "R–V"), self.traces, strict=True):
            tabs.addTab(trace, name)
        right_layout.addWidget(tabs, 1)
        right_layout.addWidget(
            QLabel("표시 전용 signed-log: 부호·0 보존 · smoothing OFF · raw 저장값 유지")
        )
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1000)
        self.log.setMaximumHeight(150)
        right_layout.addWidget(self.log)
        self.path_label = QLabel("Run 폴더: 아직 없음")
        self.path_label.setWordWrap(True)
        right_layout.addWidget(self.path_label)
        self.diagnostic_label = QLabel("연결 진단 보고서: 아직 없음")
        self.diagnostic_label.setWordWrap(True)
        right_layout.addWidget(self.diagnostic_label)
        files_row = QHBoxLayout()
        self.open_run_button = QPushButton("결과 폴더 열기")
        self.open_diagnostic_button = QPushButton("연결 진단 폴더 열기")
        files_row.addWidget(self.open_run_button)
        files_row.addWidget(self.open_diagnostic_button)
        right_layout.addLayout(files_row)
        splitter.addWidget(right)
        splitter.setSizes([420, 900])
        commission_actions = QHBoxLayout()
        self.commission_open_button = QPushButton("인터록 열림 확인 (출력 OFF)")
        self.commission_closed_button = QPushButton("인터록 닫힘 확인 (출력 OFF)")
        commission_actions.addWidget(
            QLabel("실장비: 승인된 fixture에서 lid를 직접 조작한 뒤 순서대로 확인")
        )
        commission_actions.addWidget(self.commission_open_button)
        commission_actions.addWidget(self.commission_closed_button)
        root.addLayout(commission_actions)
        actions = QHBoxLayout()
        self.connect_button = QPushButton("연결 (출력 ON 없음)")
        self.arm_button = QPushButton("검토 / ARM")
        self.start_button = QPushButton("START · 출력 인가")
        self.stop_button = QPushButton("STOP")
        self.fast_stop_button = QPushButton("즉시 출력 중지 (software)")
        self.fast_stop_button.setStyleSheet(
            "background:#a32e28;color:white;font-weight:bold;padding:8px"
        )
        self.disconnect_button = QPushButton("연결 종료 / 설정 편집")
        for button in (
            self.connect_button,
            self.arm_button,
            self.start_button,
            self.stop_button,
            self.fast_stop_button,
            self.disconnect_button,
        ):
            actions.addWidget(button)
        root.addLayout(actions)
        self.connect_button.clicked.connect(self._connect)
        self.commission_open_button.clicked.connect(lambda: self._send("commission_open"))
        self.commission_closed_button.clicked.connect(lambda: self._send("commission_closed"))
        self.arm_button.clicked.connect(lambda: self._send("arm"))
        self.start_button.clicked.connect(self._start)
        self.stop_button.clicked.connect(lambda: self._stop("user STOP"))
        self.fast_stop_button.clicked.connect(lambda: self._stop("software immediate output stop"))
        self.disconnect_button.clicked.connect(lambda: self._send("disconnect"))
        self.load_button.clicked.connect(self._choose_load)
        self.save_button.clicked.connect(self._choose_save)
        self.advanced_apply.clicked.connect(self._apply_json)
        self.transport.currentIndexChanged.connect(self._mode_changed)
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.discover_button.clicked.connect(self._discover)
        self.resource_choices.activated.connect(self._select_resource)
        self.diagnose_button.clicked.connect(lambda: self._diagnose(False))
        self.off_check_button.clicked.connect(lambda: self._diagnose(True))
        self.setup_button.clicked.connect(self._setup_test)
        self.open_run_button.clicked.connect(lambda: self._open_folder(self._last_run_directory))
        self.open_diagnostic_button.clicked.connect(
            lambda: self._open_folder(self._last_diagnostic_directory)
        )

    def _mode_changed(self) -> None:
        real = self.transport.currentData() == "visa"
        self.mode_badge.setText(
            (
                "REAL VISA · NATIVE_RESISTANCE 비활성: 측정 전류 보호 미검증"
                if self.mode.currentText() == "NATIVE_RESISTANCE"
                else "REAL VISA · 승인된 FVMI만 지원 · 실제 장비 동작 미검증"
            )
            if real
            else "SIMULATION MODE · 실제 장비 출력 없음"
        )
        self._update_buttons()

    def _load_controls(self, data: dict) -> None:
        self._base_config = dict(data)
        self.advanced.setPlainText(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False))
        self.transport.setCurrentIndex(1 if data.get("transport") == "visa" else 0)
        self.resource.setText(str(data.get("resource") or ""))
        self.backend.setText(str(data.get("visa_backend") or ""))
        self.mode.setCurrentText(data.get("mode", "FVMI_CURRENT"))
        self.profile.setCurrentIndex(2 if data.get("protocol") == "fixed_time" else 0)
        self.sample_id.setText(str(data.get("sample_id", "sample")))
        self.voltages.setText(", ".join(str(v) for v in data.get("voltages", [0])))
        self.ceiling.setValue(data.get("voltage_ceiling_V", 10))
        self.trip.setText("" if data.get("current_trip_A") is None else str(data["current_trip_A"]))
        self.source_range.setCurrentText(str(int(data.get("source_range_V", 100))))
        self.autorange.setChecked(data.get("current_autorange", True))
        self.current_range.setText(str(data.get("current_range_A") or 2e-9))
        self.nplc.setValue(data.get("nplc", 10))
        self.interval.setValue(data.get("sample_interval_s", 1))
        self.dwell.setValue(data.get("dwell_s", 300))
        self.exclude.setValue(data.get("exclude_initial_s", 1))
        self.window.setValue(data.get("summary_window_s", 30))
        self.output_dir.setText(str(data.get("output_directory", "runs")))
        self.ack.setChecked(data.get("residual_warning_ack", False))
        self._mode_changed()

    def config_from_controls(self) -> RunConfig:
        data = dict(self._base_config)
        if self.profile.currentIndex() == 1:
            from keithley6517a.measurement.protocols import linear_staircase

            points = linear_staircase(
                self.stair_start.value(), self.stair_stop.value(), self.stair_step.value()
            )
        else:
            points = [float(token.strip()) for token in self.voltages.text().split(",")]
        data.update(
            transport=self.transport.currentData(),
            simulation=self.transport.currentData() == "simulation",
            resource=self.resource.text().strip(),
            visa_backend=self.backend.text().strip() or None,
            mode=self.mode.currentText(),
            sample_id=self.sample_id.text().strip(),
            voltages=list(points),
            voltage_ceiling_V=self.ceiling.value(),
            current_trip_A=float(self.trip.text()) if self.trip.text().strip() else None,
            source_range_V=float(self.source_range.currentText()),
            current_autorange=self.autorange.isChecked(),
            current_range_A=float(self.current_range.text()),
            nplc=self.nplc.value(),
            sample_interval_s=self.interval.value(),
            dwell_s=self.dwell.value(),
            exclude_initial_s=self.exclude.value(),
            summary_window_s=self.window.value(),
            output_directory=self.output_dir.text().strip(),
            residual_warning_ack=self.ack.isChecked(),
        )
        data["protocol"] = (
            "staircase"
            if self.profile.currentIndex() == 1
            else (
                "fixed_time"
                if self.profile.currentIndex() == 2
                else ("list" if len(points) > 1 else "constant")
            )
        )
        # RunConfig owns validation; GUI enablement cannot replace it.
        return RunConfig.from_dict(data)

    def load_config(self, path: str | Path) -> None:
        if self._connected or self._busy:
            raise RuntimeError("Disconnect before loading another configuration")
        config = RunConfig.load(path)
        self._load_controls(config.to_dict())
        self.log.appendPlainText(f"설정 불러옴: {path} · 연결/출력 변경 없음")

    def _setup_test(self) -> None:
        if self._connected or self._busy or self._closing:
            return
        from .test_setup import TestSetupDialog

        try:
            current = self.config_from_controls()
            resources = tuple(
                self.resource_choices.itemText(i) for i in range(1, self.resource_choices.count())
            )
            dialog = TestSetupDialog(current, self, resources=resources)
            if dialog.exec() and dialog.result_config is not None:
                self._load_controls(dialog.result_config.to_dict())
                self.log.appendPlainText(
                    "시험 설정을 입력했습니다. 연결·ARM·START는 각각 별도입니다."
                )
        except Exception as exc:
            self._on_error(str(exc))

    def _discover(self) -> None:
        if self._connected or self._busy or self._closing:
            return
        self._busy = True
        self.settings.setEnabled(False)
        self._update_buttons()
        self.command.emit(("discover", self.backend.text().strip()))

    @Slot(list)
    def _on_resources(self, resources: list) -> None:
        self.resource_choices.clear()
        self.resource_choices.addItem("GPIB resource를 직접 선택하세요")
        self.resource_choices.addItems(resources)
        self.log.appendPlainText(
            f"VISA GPIB 목록 {len(resources)}개 · 선택 장비에만 명령을 보냅니다."
        )

    def _select_resource(self, index: int) -> None:
        if index > 0:
            self.resource.setText(self.resource_choices.itemText(index))

    def _diagnose(self, confirm_off: bool) -> None:
        if self._connected or self._busy or self._closing:
            return
        resource = self.resource.text().strip()
        if not resource:
            self._on_error("진단할 GPIB resource를 먼저 선택하세요.")
            return
        if confirm_off and self.transport.currentData() != "visa":
            self._on_error("실장비 출력 OFF 시험은 REAL VISA를 명시적으로 선택한 뒤 실행하세요.")
            return
        settings = self._base_config
        options = dict(
            resource=resource,
            backend=self.backend.text().strip() or None,
            timeout_ms=settings.get("timeout_ms", 2000),
            read_termination=settings.get("read_termination", "\n"),
            write_termination=settings.get("write_termination", "\n"),
            send_end=settings.get("send_end", True),
            confirm_off=confirm_off,
            output_directory=str(Path(self.output_dir.text() or "runs") / "connection_checks"),
        )
        self._busy = True
        self.settings.setEnabled(False)
        self._update_buttons()
        self.command.emit(("diagnose", options))

    @Slot(dict)
    def _on_diagnostic(self, report: dict) -> None:
        report_path = report.get("report_path")
        if report_path:
            self._last_diagnostic_directory = str(Path(report_path).parent)
        self.diagnostic_label.setText(
            f"진단 {'통과' if report.get('ok') else '확인 필요'} · {report.get('mode')} · "
            f"관찰된 출력 {report.get('output_state', 'UNKNOWN')} · 잔류 전압 UNVERIFIED\n"
            f"보고서: {report_path or '저장 실패'}"
        )
        self.log.appendPlainText(json.dumps(report, ensure_ascii=False, default=str))
        self._update_buttons()

    @staticmethod
    def _open_folder(directory) -> None:
        if directory and Path(directory).is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(directory).resolve())))

    def _choose_load(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "설정 불러오기", "", "JSON (*.json)")
        if path:
            try:
                self.load_config(path)
            except Exception as exc:
                self._on_error(str(exc))

    def _choose_save(self) -> None:
        try:
            config = self.config_from_controls()
            path, _ = QFileDialog.getSaveFileName(
                self, "설정 내보내기", "config.json", "JSON (*.json)"
            )
            if path:
                Path(path).write_text(
                    json.dumps(config.to_dict(), ensure_ascii=False, indent=2, allow_nan=False),
                    encoding="utf-8",
                )
        except Exception as exc:
            self._on_error(str(exc))

    def _apply_json(self) -> None:
        try:
            config = RunConfig.from_dict(json.loads(self.advanced.toPlainText()))
            self._load_controls(config.to_dict())
        except Exception as exc:
            self._on_error(str(exc))

    def _connect(self) -> None:
        try:
            config = self.config_from_controls()
            self._busy = True
            self.settings.setEnabled(False)
            self._update_buttons()
            self.command.emit(("connect", config))
        except Exception as exc:
            self._on_error(str(exc))

    def _send(self, action: str) -> None:
        self._busy = True
        self._update_buttons()
        self.command.emit((action, None))

    def _start(self) -> None:
        self.rows.clear()
        self._last_elapsed = None
        for trace in self.traces:
            trace.rows = self.rows
            trace.redraw()
        self._send("start")

    def _stop(self, reason: str) -> None:
        self.worker.request_stop(reason)
        self.log.appendPlainText(f"{reason} 요청 · I/O timeout에 따라 지연될 수 있음")

    @Slot(dict)
    def _on_status(self, status: dict) -> None:
        self._state = status.get("state", self._state)
        self._can_arm = status.get("can_arm", False)
        self._can_start = status.get("can_start", False)
        self._commissioning = status.get("commissioning", {}) or {}
        self._connected = self._state != "DISCONNECTED"
        self._busy = self._state in {"CONFIGURING", "RAMPING", "SETTLING", "ACQUIRING", "STOPPING"}
        self.state_label.setText(self._state)
        self.output_label.setText("OUTPUT " + status.get("output_state", "UNKNOWN"))
        identity = status.get("identity")
        if identity:
            self.identity_label.setText(
                f"Model {identity.get('model', '?')} · Serial {identity.get('serial', '?')} · "
                f"Firmware {identity.get('firmware', '?')} · "
                f"resource {self.resource.text() or 'SIMULATION'}"
            )
        self._fixture_status = status.get("fixture_commissioning", self._fixture_status)
        self.interlock_label.setText(
            f"Interlock query (last): {status.get('interlock_query', 'UNKNOWN')} · "
            f"fixture commissioning: {self._fixture_status}"
        )
        if status.get("run_directory"):
            self.path_label.setText("Run 폴더: " + status["run_directory"])
            self._last_run_directory = status["run_directory"]
        self.settings.setEnabled(not self._connected and not self._closing)
        self._update_buttons()
        self._mark_stale()

    @Slot(dict)
    def _on_sample(self, row: dict) -> None:
        self._last_sample_time = time.monotonic()
        elapsed = row.get("elapsed_s")
        interval = (
            None if self._last_elapsed is None or elapsed is None else elapsed - self._last_elapsed
        )
        self._last_elapsed = elapsed
        display = dict(row)
        display["_display_r"] = row.get("native_r_ohm")
        if display["_display_r"] is None:
            display["_display_r"] = row.get("resistance_apparent_ohm")
        self.rows.append(display)
        for trace in self.traces:
            trace.rows = self.rows
            trace.redraw()
        self.interlock_label.setText(
            f"Interlock query: {row.get('interlock_query', 'UNKNOWN')} · "
            f"fixture commissioning: {self._fixture_status}"
        )
        label = "native R" if row.get("native_r_ohm") is not None else "계산 R = V/I"
        self.live_label.setText(
            f"{row.get('wall_time_iso8601', '')} · {row.get('phase', '')}\n"
            f"Source programmed/readback: {row.get('voltage_programmed_readback_V')} V · "
            f"I measured: {row.get('current_raw_A')} A · "
            f"I inferred (V/native R): {row.get('current_inferred_A')} A\n"
            f"{label}: {display['_display_r']} Ω · "
            f"step age {row.get('time_since_voltage_command_s')} s · "
            f"range {row.get('current_range_A')} A · actual interval {interval} s\n"
            "Source hardware current-limit 상태: "
            f"{row.get('source_current_limit_state', 'UNKNOWN')}\n"
            f"Quality: {row.get('quality_flags', [])}"
        )
        self.live_label.setProperty("stale", False)

    @Slot(dict)
    def _on_event(self, event: dict) -> None:
        self.log.appendPlainText(json.dumps(event, ensure_ascii=False, default=str))

    @Slot(str)
    def _on_error(self, message: str) -> None:
        self._busy = False
        self.log.appendPlainText("ERROR · " + message)
        self._update_buttons()

    def _update_buttons(self) -> None:
        closing = self._closing
        self.connect_button.setEnabled(not self._connected and not self._busy and not closing)
        self.arm_button.setEnabled(self._can_arm and not self._busy and not closing)
        self.start_button.setEnabled(self._can_start and not self._busy and not closing)
        self.stop_button.setEnabled(self._connected and not closing)
        self.fast_stop_button.setEnabled(self._connected and not closing)
        self.disconnect_button.setEnabled(self._connected and not self._busy and not closing)
        preparation = not self._connected and not self._busy and not closing
        for button in (
            self.discover_button,
            self.diagnose_button,
            self.off_check_button,
            self.setup_button,
        ):
            button.setEnabled(preparation)
        self.off_check_button.setEnabled(preparation and self.transport.currentData() == "visa")
        self.open_run_button.setEnabled(bool(self._last_run_directory) and not closing)
        self.open_diagnostic_button.setEnabled(
            bool(self._last_diagnostic_directory) and not closing
        )
        can_commission = (
            self._connected
            and self._state == "OUTPUT_OFF_CONFIRMED"
            and self.output_label.text() == "OUTPUT OFF"
            and self.transport.currentData() == "visa"
            and not self._busy
            and not closing
        )
        self.commission_open_button.setEnabled(can_commission)
        self.commission_closed_button.setEnabled(can_commission)

    def _mark_stale(self) -> None:
        stale = (
            self._last_sample_time is None
            or self._state not in {"RAMPING", "SETTLING", "ACQUIRING"}
            or time.monotonic() - self._last_sample_time > max(3 * self.interval.value(), 2)
        )
        if stale and not self.live_label.property("stale"):
            self.live_label.setText("STALE · 현재 새 판독값 아님\n" + self.live_label.text())
            self.live_label.setProperty("stale", True)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._closed:
            event.accept()
            return
        event.ignore()
        if not self._closing:
            self._closing = True
            self.stale_timer.stop()
            self._stop("GUI close")
            self._update_buttons()
            self.command.emit(("shutdown", None))

    @Slot()
    def _worker_closed(self) -> None:
        self.worker_thread.quit()
        self.worker_thread.wait()
        self._closed = True
        self.close()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("6517A High Resistance Measurement")
    window = MainWindow()
    window.show()
    return app.exec()
