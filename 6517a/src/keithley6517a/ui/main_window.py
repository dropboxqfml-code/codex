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
    QGroupBox,
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
from keithley6517a.ui.connection_guide import ConnectionGuide
from keithley6517a.ui.readiness import configuration_issues, humanize_issue


def _text_state(value: Any) -> str:
    return str(getattr(value, "value", value))


def _display_si(value, unit: str) -> str:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return f"— {unit}"
    if not math.isfinite(value):
        return f"— {unit}"
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
            return f"{value / scale:.5g} {prefix}{unit}"
    return f"{value:.4g} {unit}"


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
        self._active_action: str | None = None
        self._run_result: dict = {}

    def snapshot(self) -> None:
        if self.runner is None:
            self.status.emit(
                {
                    "state": "DISCONNECTED",
                    "output_state": "UNKNOWN",
                    "can_arm": False,
                    "can_start": False,
                    "worker_busy": self._active_action is not None,
                    "run_result": dict(self._run_result),
                }
            )
            return
        instrument = getattr(self.runner, "instrument", None)
        safety = getattr(instrument, "last_safety", None) or {}
        commissioning = getattr(self.runner, "commissioning", {}) or {}
        commissioned = bool(commissioning.get("ready", False))
        setup_policy = getattr(self.runner.config, "setup_policy", "verified_fixture")
        operator_setup = setup_policy == "operator_low_voltage"
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
                "configuration_issues": configuration_issues(self.runner.config),
                "run_started": bool(getattr(self.runner, "_started", False)),
                "worker_busy": self._active_action is not None,
                "run_result": dict(self._run_result),
                "interlock_query": safety.get("interlock", "UNKNOWN"),
                "setup_policy": setup_policy,
                "operator_setup_acknowledged": bool(
                    getattr(self.runner.config, "operator_setup_acknowledged", False)
                ),
                "commissioning": commissioning,
                "fixture_commissioning": (
                    "SIMULATED · 실장비 인증 아님"
                    if self.runner.config.simulation
                    else (
                        "연결·정격: 사용자 관리 · 최대 10 V · 물리 인터록 인증 미수행"
                        if operator_setup
                        else (
                            "현재 연결의 OFF 상태 0→1 확인 · 하드웨어 인증 아님"
                            if commissioned
                            else "현재 연결의 OFF 상태 lid open=0 / closed=1 확인 필요"
                        )
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
        self._active_action = action
        try:
            if action in {"discover", "diagnose"}:
                if self.runner is not None:
                    raise RuntimeError("Disconnect before opening a diagnostic VISA session")
                if action == "discover":
                    from ..diagnostics import run_diagnostics

                    report = run_diagnostics(resource=None, **config)
                    self.resources_found.emit(report.get("resources", []))
                    self.diagnostic_ready.emit(report)
                else:
                    from ..diagnostics import run_diagnostics

                    self.diagnostic_ready.emit(run_diagnostics(**config))
            elif action == "connect":
                if self.runner is not None:
                    raise RuntimeError("Disconnect before replacing the configuration")
                self._run_result = {}
                self.runner = self.runner_factory(
                    config, on_sample=self.sample.emit, on_event=self.handle_event
                )
                self.runner.connect()
            elif action == "arm":
                if self.runner is None:
                    raise RuntimeError("Connect first")
                result = self.runner.arm()
                if isinstance(result, dict):
                    self._run_result = dict(result)
            elif action in {"commission_open", "commission_closed"}:
                if self.runner is None:
                    raise RuntimeError("Connect first")
                self.runner.commission_interlock(0 if action == "commission_open" else 1)
            elif action == "start":
                if self.runner is None:
                    raise RuntimeError("Connect and ARM first")
                self._run_result = dict(self.runner.start() or {})
            elif action == "cancel_pending":
                cancel = getattr(self.runner, "cancel_pending", None)
                if callable(cancel):
                    result = cancel(config)
                    if result:
                        self._run_result = dict(result)
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
            self._active_action = None
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
        self.resize(1280, 820)
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
        self._loading_controls = False
        self._last_worker_status: dict = {}
        self._last_run_result: dict = {}
        self._edit_after_disconnect = False
        self._last_error = ""
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
        root.setSpacing(10)
        header = QHBoxLayout()
        self.mode_badge = QLabel()
        self.mode_badge.setStyleSheet("font-size:18px;font-weight:700;color:#176b88")
        self.state_label = QLabel("DISCONNECTED")
        self.output_label = QLabel("OUTPUT UNKNOWN")
        self.output_label.setStyleSheet("font-weight:bold;color:#a35325")
        header.addWidget(self.mode_badge, 1)
        header.addWidget(self.state_label)
        header.addWidget(self.output_label)
        root.addLayout(header)
        self.identity_label = QLabel("연결할 장비를 선택하세요.")
        root.addWidget(self.identity_label)
        stages = QHBoxLayout()
        self.stage_labels = []
        for name in ("1  설정", "2  연결", "3  ARM", "4  START"):
            label = QLabel(name)
            label.setStyleSheet("background:#edf1f4;padding:8px;border-radius:4px")
            stages.addWidget(label)
            self.stage_labels.append(label)
        root.addLayout(stages)

        splitter = QSplitter()
        root.addWidget(splitter, 1)
        sidebar = QWidget()
        sidebar.setMinimumWidth(340)
        sidebar.setMaximumWidth(460)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(0, 0, 0, 0)
        self.settings = QWidget()
        settings_layout = QVBoxLayout(self.settings)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        self.setting_pages = QTabWidget()
        settings_layout.addWidget(self.setting_pages)
        basic = QWidget()
        basic_layout = QVBoxLayout(basic)
        form = QFormLayout()
        self.transport = QComboBox()
        self.transport.addItem("시뮬레이션", "simulation")
        self.transport.addItem("실장비 · VISA USB–GPIB", "visa")
        form.addRow("장비", self.transport)
        self.resource = QLineEdit()
        self.resource.setPlaceholderText("GPIB0::27::INSTR")
        resource_row = QHBoxLayout()
        resource_row.addWidget(self.resource, 1)
        self.discover_button = QPushButton("주소 조회")
        resource_row.addWidget(self.discover_button)
        form.addRow("주소", resource_row)
        self.resource_choices = QComboBox()
        self.resource_choices.addItem("조회한 주소 선택")
        form.addRow("조회 결과", self.resource_choices)
        self.sample_id = QLineEdit("sample")
        form.addRow("시료 ID", self.sample_id)
        basic_layout.addLayout(form)
        self.setup_button = QPushButton("1. 시험 설정")
        self.setup_button.setMinimumHeight(38)
        basic_layout.addWidget(self.setup_button)
        self.plan_summary = QLabel()
        self.plan_summary.setWordWrap(True)
        basic_layout.addWidget(self.plan_summary)
        load_row = QHBoxLayout()
        self.load_button = QPushButton("설정 불러오기")
        self.save_button = QPushButton("설정 저장")
        load_row.addWidget(self.load_button)
        load_row.addWidget(self.save_button)
        basic_layout.addLayout(load_row)
        basic_layout.addStretch()
        self.setting_pages.addTab(basic, "기본")

        detailed_scroll = QScrollArea()
        detailed_scroll.setWidgetResizable(True)
        detailed = QWidget()
        detailed_scroll.setWidget(detailed)
        detail_layout = QVBoxLayout(detailed)
        advanced_form = QFormLayout()
        self.backend = QLineEdit()
        self.backend.setPlaceholderText("기본 @ivi / @py / 라이브러리 경로")
        advanced_form.addRow("VISA backend", self.backend)
        self.backend_profiles = QComboBox()
        self.backend_profiles.addItem("NI-VISA", "@ivi")
        self.backend_profiles.addItem("NI-488.2 전용 · 선택 확장", "@py")
        self.backend_profiles.addItem("직접 지정", "custom")
        advanced_form.addRow("통신 방식", self.backend_profiles)
        self.setup_policy = QComboBox()
        self.setup_policy.addItem("검증 fixture", "verified_fixture")
        self.setup_policy.addItem("사용자 관리 · 최대 10 V", "operator_low_voltage")
        advanced_form.addRow("운용 방식", self.setup_policy)
        self.operator_setup_ack = QCheckBox("연결·정격·외부 보호를 사용자가 관리합니다")
        advanced_form.addRow(self.operator_setup_ack)
        self.mode = QComboBox()
        self.mode.addItems(["FVMI_CURRENT", "NATIVE_RESISTANCE"])
        advanced_form.addRow("측정 모드", self.mode)
        self.profile = QComboBox()
        self.profile.addItems(["전압 리스트 / 정전압", "선형 staircase", "Fixed-time"])
        advanced_form.addRow("프로토콜", self.profile)
        self.voltages = QLineEdit("0")
        advanced_form.addRow("전압 목록 (V)", self.voltages)
        stair = QHBoxLayout()
        self.stair_start = self._spin(-1000, 1000, 0)
        self.stair_stop = self._spin(-1000, 1000, 10)
        self.stair_step = self._spin(-1000, 1000, 1)
        for control in (self.stair_start, self.stair_stop, self.stair_step):
            stair.addWidget(control)
        advanced_form.addRow("시작/끝/간격 (V)", stair)
        self.ceiling = self._spin(0, 1000, 10)
        advanced_form.addRow("전압 상한 (V)", self.ceiling)
        self.trip = QLineEdit()
        self.trip.setPlaceholderText("A 단위 · 예: 1e-8")
        advanced_form.addRow("Software trip (A)", self.trip)
        self.source_range = QComboBox()
        self.source_range.addItems(["100", "1000"])
        advanced_form.addRow("소스 범위 (V)", self.source_range)
        self.autorange = QCheckBox("전류 자동 범위")
        self.autorange.setChecked(True)
        advanced_form.addRow(self.autorange)
        self.current_range = QLineEdit("2e-9")
        advanced_form.addRow("고정 범위 (A)", self.current_range)
        self.nplc = self._spin(0.01, 10, 10)
        self.interval = self._spin(0.001, 86400, 1)
        self.dwell = self._spin(0.001, 86400, 300)
        self.exclude = self._spin(0, 86400, 1)
        self.window = self._spin(0.001, 86400, 30)
        for text, control in (
            ("NPLC", self.nplc),
            ("판독 간격 (s)", self.interval),
            ("전압별 시간 (s)", self.dwell),
            ("초기 제외 (s)", self.exclude),
            ("요약 구간 (s)", self.window),
        ):
            advanced_form.addRow(text, control)
        self.output_dir = QLineEdit("runs")
        advanced_form.addRow("저장 폴더", self.output_dir)
        self.ack = QCheckBox("잔류 전압 미확인·software stop의 한계를 확인했습니다")
        advanced_form.addRow(self.ack)
        detail_layout.addLayout(advanced_form)
        self.protection_label = QLabel(
            "Software trip: 판독·통신 지연 후 소프트웨어 중지\n"
            "V-Source 하드웨어 limit: 100 V 범위 10 mA / 1000 V 범위 1 mA\n"
            "외부 하드웨어 보호는 별도 검증 필요. programmable compliance가 아닙니다."
        )
        self.protection_label.setWordWrap(True)
        detail_layout.addWidget(self.protection_label)
        self.advanced = QPlainTextEdit()
        self.advanced.setMinimumHeight(180)
        detail_layout.addWidget(QLabel("전체 설정 JSON"))
        detail_layout.addWidget(self.advanced)
        self.advanced_apply = QPushButton("JSON을 설정에 적용")
        detail_layout.addWidget(self.advanced_apply)
        self.setting_pages.addTab(detailed_scroll, "고급")
        side.addWidget(self.settings, 1)

        readiness = QGroupBox("진행 안내")
        readiness_layout = QVBoxLayout(readiness)
        self.workflow_label = QLabel()
        self.workflow_label.setWordWrap(True)
        self.workflow_label.setStyleSheet("font-weight:600;color:#176b88")
        self.setup_status_label = QLabel()
        self.setup_status_label.setWordWrap(True)
        self.blockers_label = QLabel()
        self.blockers_label.setWordWrap(True)
        self.repair_button = QPushButton("설정 확인")
        self.repair_button.clicked.connect(self._repair_settings)
        for control in (
            self.workflow_label,
            self.setup_status_label,
            self.blockers_label,
            self.repair_button,
        ):
            readiness_layout.addWidget(control)
        side.addWidget(readiness)
        splitter.addWidget(sidebar)

        self.main_tabs = QTabWidget()
        measurement = QWidget()
        right_layout = QVBoxLayout(measurement)
        values = QHBoxLayout()
        self.value_labels = {}
        for key, title, unit in (
            ("voltage", "전압", "V"),
            ("current", "전류", "A"),
            ("resistance", "저항", "Ω"),
        ):
            box = QGroupBox(title)
            box_layout = QVBoxLayout(box)
            label = QLabel(f"— {unit}")
            label.setStyleSheet("font-size:24px;font-weight:600;color:#173f5f")
            box_layout.addWidget(label)
            values.addWidget(box)
            self.value_labels[key] = label
        right_layout.addLayout(values)
        self.reading_state_label = QLabel("판독 대기 · START 후 값이 표시됩니다")
        right_layout.addWidget(self.reading_state_label)
        self.result_status_label = QLabel()
        self.result_status_label.setWordWrap(True)
        self.result_status_label.hide()
        right_layout.addWidget(self.result_status_label)
        graph_tabs = QTabWidget()
        self.traces = [
            TracePanel("I(t)", "elapsed_s", "current_raw_A", "time (s)", "I (A)"),
            TracePanel("R(t)", "elapsed_s", "_display_r", "time (s)", "R (Ω)"),
            TracePanel("I–V", "voltage_programmed_readback_V", "current_raw_A", "V", "I (A)"),
            TracePanel("R–V", "voltage_programmed_readback_V", "_display_r", "V", "R (Ω)"),
        ]
        for title, trace in zip(("I(t)", "R(t)", "I–V", "R–V"), self.traces, strict=True):
            graph_tabs.addTab(trace, title)
        right_layout.addWidget(graph_tabs, 1)
        self.path_label = QLabel("저장 위치: 실행 후 생성됩니다")
        self.path_label.setWordWrap(True)
        right_layout.addWidget(self.path_label)
        self.open_run_button = QPushButton("결과 폴더 열기")
        self.review_results_button = QPushButton("저장 결과 분석")
        results_actions = QHBoxLayout()
        results_actions.addWidget(self.review_results_button)
        results_actions.addWidget(self.open_run_button)
        right_layout.addLayout(results_actions)
        self.main_tabs.addTab(measurement, "측정")

        tools = QWidget()
        tool_layout = QVBoxLayout(tools)
        self.connection_guide = ConnectionGuide(self)
        tool_layout.addWidget(self.connection_guide)
        diagnostic_actions = QHBoxLayout()
        self.diagnose_button = QPushButton("IDN 확인")
        self.off_check_button = QPushButton("보호 OFF 확인")
        self.open_diagnostic_button = QPushButton("진단 폴더")
        for control in (self.diagnose_button, self.off_check_button, self.open_diagnostic_button):
            diagnostic_actions.addWidget(control)
        tool_layout.addLayout(diagnostic_actions)
        self.diagnostic_label = QLabel("진단 기록 없음")
        self.diagnostic_label.setWordWrap(True)
        self.interlock_label = QLabel("Interlock query: UNKNOWN · fixture commissioning: 미확인")
        self.interlock_label.setWordWrap(True)
        tool_layout.addWidget(self.diagnostic_label)
        tool_layout.addWidget(self.interlock_label)
        self.commissioning_hint = QLabel()
        self.commissioning_hint.setWordWrap(True)
        tool_layout.addWidget(self.commissioning_hint)
        commissions = QHBoxLayout()
        self.commission_open_button = QPushButton("인터록 열림 확인")
        self.commission_closed_button = QPushButton("인터록 닫힘 확인")
        commissions.addWidget(self.commission_open_button)
        commissions.addWidget(self.commission_closed_button)
        tool_layout.addLayout(commissions)
        warning = QLabel(
            "잔류 전압 UNVERIFIED · 출력 OFF는 방전 완료가 아닙니다.\n"
            "software STOP은 하드웨어 비상정지가 아닙니다. "
            "VISA I/O는 timeout까지 지연될 수 있습니다."
        )
        warning.setWordWrap(True)
        tool_layout.addWidget(warning)
        self.live_label = QLabel("STALE · 아직 취득한 판독값 없음")
        self.live_label.setWordWrap(True)
        tool_layout.addWidget(self.live_label)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1500)
        tool_layout.addWidget(self.log, 1)
        self.fast_stop_button = QPushButton("즉시 출력 중지 (software)")
        tool_layout.addWidget(self.fast_stop_button)
        self.main_tabs.addTab(tools, "진단 · 상세 기록")
        splitter.addWidget(self.main_tabs)
        splitter.setSizes([390, 880])

        actions = QHBoxLayout()
        self.connect_button = QPushButton("2. 연결")
        self.arm_button = QPushButton("3. ARM")
        self.start_button = QPushButton("4. START")
        self.stop_button = QPushButton("STOP")
        self.stop_button.setStyleSheet(
            "background:#aa3026;color:white;font-weight:bold;padding:9px"
        )
        self.disconnect_button = QPushButton("연결 종료")
        for control in (
            self.connect_button,
            self.arm_button,
            self.start_button,
            self.stop_button,
            self.disconnect_button,
        ):
            control.setMinimumHeight(36)
            actions.addWidget(control)
        root.addLayout(actions)
        footer = QLabel("출력 OFF ≠ 방전 완료 · STOP은 소프트웨어 중지")
        footer.setStyleSheet("color:#687582;font-size:11px")
        root.addWidget(footer)

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
        self.transport.currentIndexChanged.connect(self._transport_changed)
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.setup_policy.currentIndexChanged.connect(self._setup_policy_changed)
        self.operator_setup_ack.toggled.connect(self._refresh_connection_guide)
        self.ack.toggled.connect(self._refresh_connection_guide)
        self.profile.currentIndexChanged.connect(self._refresh_connection_guide)
        self.source_range.currentIndexChanged.connect(self._refresh_connection_guide)
        self.autorange.toggled.connect(self._refresh_connection_guide)
        for control in (self.voltages, self.trip, self.current_range):
            control.textChanged.connect(self._refresh_connection_guide)
        for control in (
            self.ceiling,
            self.nplc,
            self.interval,
            self.dwell,
            self.exclude,
            self.window,
            self.stair_start,
            self.stair_stop,
            self.stair_step,
        ):
            control.valueChanged.connect(self._refresh_connection_guide)
        self.backend_profiles.currentIndexChanged.connect(self._backend_profile_changed)
        self.backend.textChanged.connect(self._backend_text_changed)
        self.resource.textChanged.connect(self._refresh_connection_guide)
        self.connection_guide.request_real_mode.connect(self._enter_real_test)
        self.connection_guide.request_discover.connect(self._discover)
        self.connection_guide.request_identify.connect(lambda: self._diagnose(False))
        self.connection_guide.request_off_check.connect(lambda: self._diagnose(True))
        self.connection_guide.request_prepare_settings.connect(self._setup_test)
        self.discover_button.clicked.connect(self._discover)
        self.resource_choices.activated.connect(self._select_resource)
        self.diagnose_button.clicked.connect(lambda: self._diagnose(False))
        self.off_check_button.clicked.connect(lambda: self._diagnose(True))
        self.setup_button.clicked.connect(self._setup_test)
        self.open_run_button.clicked.connect(lambda: self._open_folder(self._last_run_directory))
        self.review_results_button.clicked.connect(self._review_results)
        self.open_diagnostic_button.clicked.connect(
            lambda: self._open_folder(self._last_diagnostic_directory)
        )

    def _mode_changed(self) -> None:
        real = self.transport.currentData() == "visa"
        self.mode_badge.setText(
            (
                "REAL VISA · NATIVE_RESISTANCE 비활성: 측정 전류 보호 미검증"
                if self.mode.currentText() == "NATIVE_RESISTANCE"
                else (
                    "REAL VISA · 사용자 관리 저전압 시험 · 최대 10 V"
                    if self.setup_policy.currentData() == "operator_low_voltage"
                    else "REAL VISA · 검증 fixture 운용 · 실제 장비 동작 미검증"
                )
            )
            if real
            else "SIMULATION MODE · 실제 장비 출력 없음"
        )
        self._update_buttons()

    def _transport_changed(self) -> None:
        if (
            not self._loading_controls
            and self.transport.currentData() == "visa"
            and self._base_config.get("simulation", True)
        ):
            self._enter_real_test()
        else:
            self._mode_changed()

    def _enter_real_test(self) -> None:
        if self._connected or self._busy or self._closing:
            return
        if self._base_config.get("simulation", True):
            # A simulation plan is not approval for a real specimen.
            settings = RunConfig().to_dict()
            for key in ("timeout_ms", "read_termination", "write_termination", "send_end"):
                settings[key] = self._base_config.get(key, settings[key])
            settings.update(
                simulation=False,
                transport="visa",
                setup_policy="operator_low_voltage",
                operator_setup_acknowledged=False,
                resource=self.resource.text().strip(),
                visa_backend=self.backend.text().strip() or "@ivi",
                output_directory=self.output_dir.text().strip() or "runs",
            )
            self._load_controls(settings)
            self.log.appendPlainText(
                "REAL 연결 시험 준비: 시뮬레이션의 전압·trip·승인을 재사용하지 않습니다. "
                "목표 0 V에서 시작하며 먼저 NI MAX와 같은 주소의 IDN을 조회하세요."
            )
        self.resource.setFocus()
        self._refresh_connection_guide()

    def _setup_policy_changed(self) -> None:
        operator_setup = self.setup_policy.currentData() == "operator_low_voltage"
        self.commissioning_hint.setText(
            "사용자 관리 저전압 시험: 설정 검토 → 연결 → ARM → 별도 START"
            if operator_setup
            else "실장비: 승인된 fixture에서 lid를 직접 조작한 뒤 순서대로 확인"
        )
        self.ceiling.setMaximum(10 if operator_setup else 1000)
        self.source_range.setEnabled(not operator_setup)
        self.operator_setup_ack.setEnabled(operator_setup)
        if not self._loading_controls:
            self.operator_setup_ack.setChecked(False)
            if operator_setup:
                self.source_range.setCurrentText("100")
        self._mode_changed()

    def _backend_profile_changed(self) -> None:
        choice = self.backend_profiles.currentData()
        if choice != "custom":
            self.backend.setText(choice)
        self._refresh_connection_guide()

    def _backend_text_changed(self) -> None:
        text = self.backend.text().strip()
        index = 1 if text == "@py" else (0 if text in ("", "@ivi") else 2)
        self.backend_profiles.blockSignals(True)
        self.backend_profiles.setCurrentIndex(index)
        self.backend_profiles.blockSignals(False)
        self._refresh_connection_guide()

    def _refresh_connection_guide(self) -> None:
        if self._loading_controls:
            return
        issues = []
        try:
            config = self.config_from_controls()
            issues = configuration_issues(config)
            voltages = ", ".join(f"{value:g}" for value in config.voltages[:4])
            if len(config.voltages) > 4:
                voltages += f" … ({len(config.voltages)}단계)"
            self.plan_summary.setText(
                f"전압  {voltages} V\n"
                f"Trip  {_display_si(config.current_trip_A, 'A')}\n"
                f"전압별 {config.dwell_s:g} s · 간격 {config.sample_interval_s:g} s"
            )
        except (ValueError, TypeError) as exc:
            issues = [{"field": "", "code": "INVALID_SETTINGS", "message": humanize_issue(exc)}]
            self.plan_summary.setText("설정 입력을 확인하세요.")
        if self._connected and "configuration_issues" in self._last_worker_status:
            issues = self._last_worker_status["configuration_issues"]
        self._preparation_issues = issues
        idle = not self._busy and not self._closing
        self.arm_button.setEnabled(self._can_arm and idle and not issues)
        self.start_button.setEnabled(self._can_start and idle and not issues)
        arm_issue = " / ".join(issue["message"] for issue in issues)
        self.setup_status_label.setText(
            f"준비 초안 · 미완료 {len(issues)}개" if issues else "설정 준비 완료"
        )
        self.setup_status_label.setStyleSheet("color:#9b6817" if issues else "color:#16667a")
        visible = issues[:5]
        self.blockers_label.setText("\n".join("• " + issue["message"] for issue in visible))
        self.blockers_label.setVisible(bool(issues))
        self.blockers_label.setToolTip(arm_issue)
        state = self._state
        output = self.output_label.text().removeprefix("OUTPUT ")
        interlock = self._last_worker_status.get("interlock_query")
        started = self._last_worker_status.get("run_started", False)
        if self._closing:
            stage, action = 3, "종료 중 · 출력 정리 작업을 기다리세요."
        elif self._busy:
            stage = 2 if state == "CONFIGURING" else (3 if self._connected else 1)
            action = "ARM 설정 검증 중…" if state == "CONFIGURING" else "장비 작업 중…"
        elif not self._connected:
            stage = 0 if issues else 1
            action = "1. 시험 설정에서 필수 항목을 완료하세요." if issues else "2. 연결을 누르세요."
        elif interlock in (0, "0"):
            stage, action = 2, "장비 인터록 조회 0 · ARM·START 조건 미충족"
        elif state in {"FAULT", "HV_STATE_UNKNOWN"}:
            reason = humanize_issue(self._last_error) if self._last_error else state
            stage, action = 2, "장비 확인 필요: " + reason
        elif started and state == "OUTPUT_OFF_CONFIRMED":
            outcome = self._last_run_result.get("status")
            title = "사용자 중지" if outcome == "stopped" else "측정 완료"
            stage, action = (
                0,
                title + " · 저장 결과를 분석하거나 연결 종료 후 새 시험을 준비하세요.",
            )
        elif issues:
            stage, action = 0, "ARM 비활성: 설정이 미완료입니다. 아래 항목을 수정하세요."
        elif self._can_start:
            stage, action = 3, "ARM 완료 · 4. START를 누르면 측정합니다."
        elif self._can_arm:
            stage, action = 2, "연결 완료 · 3. ARM으로 장비 설정을 검증하세요."
        elif self.setup_policy.currentData() == "verified_fixture" and not self._commissioning.get(
            "ready"
        ):
            stage, action = 2, "ARM 대기 · 진단 화면에서 현재 연결의 인터록을 확인하세요."
        else:
            stage, action = 2, "장비 ARM 조건 확인 필요 · 진단 기록을 확인하세요."
        self.workflow_label.setText(action)
        for index, label in enumerate(self.stage_labels):
            active = index == stage
            label.setStyleSheet(
                "padding:8px;border-radius:4px;"
                + (
                    "background:#d8edf7;color:#12516c;font-weight:700"
                    if active
                    else "background:#edf1f4;color:#697684"
                )
            )
        self.arm_button.setToolTip(
            "ARM 실행 가능 · 출력은 켜지지 않습니다."
            if self.arm_button.isEnabled()
            else ("ARM 비활성: " + arm_issue if issues else action)
        )
        self.start_button.setToolTip(
            "START 실행 가능"
            if self.start_button.isEnabled()
            else ("START 대기: ARM을 먼저 완료하세요." if self._can_arm and not issues else action)
        )
        commission_needed = (
            self._connected
            and not issues
            and self.transport.currentData() == "visa"
            and not started
            and self.setup_policy.currentData() == "verified_fixture"
            and not self._commissioning.get("ready")
        )
        self.repair_button.setText(
            "현재 연결의 인터록 확인"
            if commission_needed
            else ("연결 종료 후 설정 수정" if self._connected else "설정 확인")
        )
        self.repair_button.setEnabled(
            not self._closing and not self._busy and (not self._connected or output == "OFF")
        )
        self.connection_guide.set_context(
            simulation=self.transport.currentData() != "visa",
            resource=self.resource.text().strip(),
            backend=self.backend.text().strip() or None,
            busy=self._busy,
            closing=self._closing,
            setup_policy=self.setup_policy.currentData(),
            operator_setup_acknowledged=self.operator_setup_ack.isChecked(),
            arm_issue=arm_issue,
        )

    def _repair_settings(self) -> None:
        if self._busy or self._closing:
            return
        if (
            self._connected
            and not self._preparation_issues
            and self.transport.currentData() == "visa"
            and not self._last_worker_status.get("run_started")
            and self.setup_policy.currentData() == "verified_fixture"
            and not self._commissioning.get("ready")
        ):
            self.main_tabs.setCurrentIndex(1)
        elif self._connected:
            if self.output_label.text() == "OUTPUT OFF":
                self._edit_after_disconnect = True
                self._send("disconnect")
        else:
            self._setup_test()

    def _load_controls(self, data: dict) -> None:
        self._loading_controls = True
        self._base_config = dict(data)
        self.advanced.setPlainText(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False))
        self.transport.setCurrentIndex(1 if data.get("transport") == "visa" else 0)
        policy = data.get("setup_policy", "verified_fixture")
        self.setup_policy.setCurrentIndex(max(0, self.setup_policy.findData(policy)))
        self._setup_policy_changed()
        self.operator_setup_ack.setChecked(data.get("operator_setup_acknowledged", False))
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
        self._loading_controls = False
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
            setup_policy=self.setup_policy.currentData(),
            operator_setup_acknowledged=self.operator_setup_ack.isChecked(),
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
            field = next(iter(getattr(self, "_preparation_issues", [])), {}).get("field")
            dialog = TestSetupDialog(current, self, resources=resources, focus_field=field)
            if dialog.exec() and dialog.result_config is not None:
                self._load_controls(dialog.result_config.to_dict())
                self.log.appendPlainText(
                    "초안을 적용했습니다. ARM 준비 항목을 확인하세요."
                    if getattr(dialog, "applied_as_draft", False)
                    else "측정 설정을 적용했습니다. 다음: 연결 → ARM → START"
                )
        except Exception as exc:
            self._on_error(str(exc))

    def _discover(self) -> None:
        if self._connected or self._busy or self._closing:
            return
        self._busy = True
        self.settings.setEnabled(False)
        self._update_buttons()
        self.command.emit(
            (
                "discover",
                dict(
                    backend=self.backend.text().strip() or None,
                    output_directory=str(
                        Path(self.output_dir.text() or "runs") / "connection_checks"
                    ),
                ),
            )
        )

    @Slot(list)
    def _on_resources(self, resources: list) -> None:
        self.resource_choices.clear()
        self.resource_choices.addItem("GPIB resource를 직접 선택하세요")
        self.resource_choices.addItems(resources)
        self.log.appendPlainText(
            f"VISA GPIB 목록 {len(resources)}개 · 선택 장비에만 명령을 보냅니다."
        )
        self.connection_guide.update_resources(resources)

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
        self.connection_guide.update_diagnostic(report)
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
            self._last_error = ""
            self._last_run_result = {}
            self._last_run_directory = None
            self.path_label.setText("저장 위치: ARM 후 생성됩니다")
            self.result_status_label.hide()
            self._busy = True
            self.settings.setEnabled(False)
            self._update_buttons()
            self.command.emit(("connect", config))
        except Exception as exc:
            self._on_error(str(exc))

    def _send(self, action: str) -> None:
        if action == "arm":
            self._last_error = ""
        self._busy = True
        self._update_buttons()
        self.command.emit((action, None))

    def _start(self) -> None:
        self.rows.clear()
        self._last_elapsed = None
        self._last_sample_time = None
        for key, unit in (("voltage", "V"), ("current", "A"), ("resistance", "Ω")):
            self.value_labels[key].setText(f"— {unit}")
        self.reading_state_label.setText("판독 대기 · 첫 측정값을 기다립니다")
        for trace in self.traces:
            trace.rows = self.rows
            trace.redraw()
        self._send("start")

    def _stop(self, reason: str) -> None:
        self.worker.request_stop(reason)
        self.log.appendPlainText(f"{reason} 요청 · I/O timeout에 따라 지연될 수 있음")
        self._busy = True
        self._update_buttons()
        self.command.emit(("cancel_pending", reason))

    def _review_results(self) -> None:
        if (
            self._closing
            or self._busy
            or (self._connected and self.output_label.text() != "OUTPUT OFF")
        ):
            return
        from .result_dialog import SavedResultDialog

        path = self._last_run_result.get("run_directory") or None
        dialog = SavedResultDialog(path=path, parent=self)
        dialog.exec()

    @Slot(dict)
    def _on_status(self, status: dict) -> None:
        self._last_worker_status = dict(status)
        self._state = status.get("state", self._state)
        self._can_arm = status.get("can_arm", False)
        self._can_start = status.get("can_start", False)
        if status.get("interlock_query") in (0, "0"):
            self._can_arm = self._can_start = False
        self._commissioning = status.get("commissioning", {}) or {}
        self._connected = self._state != "DISCONNECTED"
        self._busy = bool(status.get("worker_busy")) or self._state in {
            "CONNECTED_UNVERIFIED",
            "CONFIGURING",
            "RAMPING",
            "SETTLING",
            "ACQUIRING",
            "STOPPING",
        }
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
        result = status.get("run_result")
        if result:
            self._last_run_result = dict(result)
            if result.get("status") == "aborted":
                self._last_error = str(result.get("reason") or self._last_error)
            title = {
                "completed": "정상 완료",
                "stopped": "사용자 중지",
                "aborted": "오류 종료",
            }.get(result.get("status"), "종료 상태 확인")
            count = result.get("reading_count")
            saved = f" · 저장 {count}행" if count is not None else ""
            elapsed = result.get("elapsed_s")
            duration = f" · {elapsed:.3g} s" if isinstance(elapsed, (int, float)) else ""
            self.result_status_label.setText(title + saved + duration)
            self.result_status_label.setToolTip(str(result.get("reason", "")))
            self.result_status_label.setStyleSheet(
                "color:#a32e28" if result.get("status") == "aborted" else "color:#176b88"
            )
            self.result_status_label.show()
        self.settings.setEnabled(not self._connected and not self._busy and not self._closing)
        self.connection_guide.update_status(status)
        self._update_buttons()
        self._mark_stale()
        if self._edit_after_disconnect and self._state == "DISCONNECTED" and not self._busy:
            self._edit_after_disconnect = False
            QTimer.singleShot(0, self._setup_test)

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
        self.value_labels["voltage"].setText(
            _display_si(row.get("voltage_programmed_readback_V"), "V")
        )
        self.value_labels["current"].setText(_display_si(row.get("current_raw_A"), "A"))
        self.value_labels["resistance"].setText(_display_si(display["_display_r"], "Ω"))
        self.reading_state_label.setText(
            "판독 중" if elapsed is None else f"판독 중 · {elapsed:g} s"
        )
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
        if event.get("event") == "abort":
            self._last_error = str(event.get("reason") or "측정 중단")
            self._refresh_connection_guide()

    @Slot(str)
    def _on_error(self, message: str) -> None:
        self._busy = False
        self._last_error = message
        self._edit_after_disconnect = False
        self.log.appendPlainText("ERROR · " + message)
        self._update_buttons()

    def _update_buttons(self) -> None:
        closing = self._closing
        self.connect_button.setEnabled(not self._connected and not self._busy and not closing)
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
        review_ready = (
            not closing
            and not self._busy
            and (not self._connected or self.output_label.text() == "OUTPUT OFF")
        )
        self.review_results_button.setEnabled(review_ready)
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
            and self.setup_policy.currentData() == "verified_fixture"
        )
        self.commission_open_button.setEnabled(can_commission)
        self.commission_closed_button.setEnabled(can_commission)
        self._refresh_connection_guide()

    def _mark_stale(self) -> None:
        stale = (
            self._last_sample_time is None
            or self._state not in {"RAMPING", "SETTLING", "ACQUIRING"}
            or time.monotonic() - self._last_sample_time > max(3 * self.interval.value(), 2)
        )
        if stale and not self.live_label.property("stale"):
            self.live_label.setText("STALE · 현재 새 판독값 아님\n" + self.live_label.text())
            self.live_label.setProperty("stale", True)
        self.reading_state_label.setProperty("stale", stale)
        if stale and self._last_sample_time is not None:
            self.reading_state_label.setText("마지막 판독값 · 현재 실시간 값 아님")

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
