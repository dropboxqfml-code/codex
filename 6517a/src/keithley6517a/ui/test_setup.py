"""Prepare a trial configuration without touching a VISA session or enabling output."""

from __future__ import annotations

import math
from collections.abc import Sequence

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import ConfigurationError, RunConfig


class TestSetupDialog(QDialog):
    """A settings form, not commissioning: the connected worker observes the lid later.

    ``resources`` is supplied by the caller after explicit discovery. This dialog
    does no device, filesystem, or network I/O, including while applying settings.
    """

    def __init__(self, config: RunConfig, parent=None, *, resources: Sequence[str] = ()) -> None:
        super().__init__(parent)
        self.setWindowTitle("6517A · USB-GPIB 시험 설정")
        self.resize(800, 760)
        self._original = config
        self.result_config: RunConfig | None = None
        self._edits: list[QWidget] = []
        root = QVBoxLayout(self)
        intro = QLabel(
            "이 창은 설정만 준비합니다. 연결·ARM·출력 ON은 실행하지 않습니다.\n"
            "실장비는 연결 후 출력 OFF 상태에서 lid 열림 0 → 닫힘 1을 다시 확인해야 합니다. "
            "출력 OFF나 이 확인 절차는 시료 방전 또는 하드웨어 안전 인증이 아닙니다."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)
        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        connection = self._tab(tabs, "1. 연결")
        self.real_mode = QCheckBox("REAL VISA · 실제 6517A 시험 설정을 명시적으로 선택")
        self.real_mode.setChecked(not config.simulation)
        connection.addRow(self.real_mode)
        self._edits.append(self.real_mode)
        self.resource = QComboBox()
        self.resource.setEditable(True)
        self.resource.addItems(list(dict.fromkeys(resources)))
        self.resource.setCurrentText(config.resource)
        self.resource.setToolTip(
            "GPIB resource를 선택하거나 입력합니다. 주소를 자동 탐색하지 않습니다."
        )
        self._edits.append(self.resource)
        connection.addRow("선택한 VISA GPIB resource", self.resource)
        self.visa_backend = self._text(config.visa_backend or "")
        self.visa_backend.setPlaceholderText("기본 VISA 사용 시 비움 / @ivi 또는 VISA library 경로")
        connection.addRow("VISA backend / library", self.visa_backend)
        self.backend_profiles = QComboBox()
        self.backend_profiles.addItem("NI-VISA · 기본 권장", "@ivi")
        self.backend_profiles.addItem("NI-488.2 전용 · 선택 확장 설치 필요 · 시험 기능", "@py")
        self.backend_profiles.addItem("라이브러리 경로 직접 지정", "custom")
        self._edits.append(self.backend_profiles)
        connection.addRow("통신 방식", self.backend_profiles)
        self.backend_profiles.currentIndexChanged.connect(self._select_backend)
        self.visa_backend.textChanged.connect(self._sync_backend)
        self._sync_backend()
        self.timeout_ms = QSpinBox()
        self.timeout_ms.setRange(1, 60000)
        self.timeout_ms.setValue(config.timeout_ms)
        self._edits.append(self.timeout_ms)
        connection.addRow("I/O timeout (ms)", self.timeout_ms)
        self.send_end = QCheckBox("EOI / send_end 사용")
        self.send_end.setChecked(config.send_end)
        self._edits.append(self.send_end)
        connection.addRow(self.send_end)
        self.read_termination = self._termination(config.read_termination)
        self.write_termination = self._termination(config.write_termination)
        connection.addRow("읽기 terminator", self.read_termination)
        connection.addRow("쓰기 terminator", self.write_termination)
        driver_note = QLabel(
            "기본 경로는 NI-VISA입니다. NI-488.2 전용 @py 시험 기능은 선택 확장을 "
            "따로 설치해야 하며 NI-488.2 드라이버는 여전히 필요합니다. "
            "NI MAX에서 주소를 확인한 뒤 다른 제어 프로그램의 test panel은 종료하세요."
        )
        driver_note.setWordWrap(True)
        connection.addRow(driver_note)

        experiment = self._tab(tabs, "2. 시료·측정")
        self.sample_id = self._text(config.sample_id)
        self.output_directory = self._text(config.output_directory)
        experiment.addRow("시료 ID", self.sample_id)
        experiment.addRow("결과 저장 폴더", self.output_directory)
        self.mode = QComboBox()
        self.mode.addItems(["FVMI_CURRENT", "NATIVE_RESISTANCE"])
        self.mode.setCurrentText(config.mode)
        self._edits.append(self.mode)
        experiment.addRow("측정 모드 (실장비는 FVMI_CURRENT)", self.mode)
        self.voltages = self._text(", ".join(str(v) for v in config.voltages))
        experiment.addRow("요청 전압 (V, 쉼표로 구분)", self.voltages)
        self.ceiling = self._text(str(config.voltage_ceiling_V))
        experiment.addRow("소프트웨어 전압 상한 (V)", self.ceiling)
        self.source_range = QComboBox()
        self.source_range.addItems(["100", "1000"])
        self.source_range.setCurrentText(str(int(config.source_range_V)))
        self._edits.append(self.source_range)
        experiment.addRow("V-Source 범위 (V)", self.source_range)
        self.current_trip = self._text(self._optional_text(config.current_trip_A))
        self.current_trip.setPlaceholderText("사용자가 결정해야 하는 software trip, A 단위")
        experiment.addRow("Software current trip (A)", self.current_trip)
        self.nplc = self._text(str(config.nplc))
        self.line_frequency = QComboBox()
        self.line_frequency.addItems(["50", "60"])
        self.line_frequency.setCurrentText(str(int(config.line_frequency_hz)))
        self._edits.append(self.line_frequency)
        self.interval = self._text(str(config.sample_interval_s))
        self.dwell = self._text(str(config.dwell_s))
        self.summary_window = self._text(str(config.summary_window_s))
        self.exclude_initial = self._text(str(config.exclude_initial_s))
        for label, widget in (
            ("NPLC", self.nplc),
            ("전원 주파수 입력값 (Hz)", self.line_frequency),
            ("요청 sample interval (s)", self.interval),
            ("전압별 dwell / duration (s)", self.dwell),
            ("마지막 요약 window (s)", self.summary_window),
            ("초기 제외 구간 (s)", self.exclude_initial),
        ):
            experiment.addRow(label, widget)
        self.note = QPlainTextEdit(config.note)
        self.note.setMaximumHeight(90)
        self._edits.append(self.note)
        experiment.addRow("실험 메모", self.note)

        approval = self._tab(tabs, "3. 정격·승인 기록")
        self.sample_rating = self._text(self._optional_text(config.sample_limit_V))
        self.fixture_rating = self._text(self._optional_text(config.fixture_limit_V))
        self.cable_rating = self._text(self._optional_text(config.cable_limit_V))
        approval.addRow("확인한 시료 최대 전압 (V)", self.sample_rating)
        approval.addRow("확인한 fixture 최대 전압 (V)", self.fixture_rating)
        approval.addRow("확인한 케이블·커넥터 최대 전압 (V)", self.cable_rating)
        self.rating_approval = self._text(config.rating_approval)
        approval.addRow("정격·실험 승인 문서 / 기록", self.rating_approval)
        self.fixture_id = self._text(str(config.commissioning.get("fixture_id", "")))
        self.approved_by = self._text(str(config.commissioning.get("approved_by", "")))
        approval.addRow("Fixture ID", self.fixture_id)
        approval.addRow("승인 담당자", self.approved_by)
        self.resistive_limit = QComboBox()
        self.resistive_limit.addItem("미결정 — 실장비 ARM 불가", None)
        self.resistive_limit.addItem("OFF — 승인된 하드웨어 보호 계획", False)
        self.resistive_limit.addItem("ON — 내부 resistive-limit 사용 승인", True)
        self.resistive_limit.setCurrentIndex(
            0
            if config.resistive_limit_enabled is None
            else (2 if config.resistive_limit_enabled else 1)
        )
        self._edits.append(self.resistive_limit)
        approval.addRow("Resistive-limit 정책", self.resistive_limit)
        self.installation = self._record_check(
            "installation_confirmed", "승인된 저측 FVMI 결선·정격·인터록 설치를 확인했습니다"
        )
        self.hardware_protection = self._record_check(
            "hardware_protection_reviewed", "독립적인 하드웨어 보호·차단·방전 절차를 검토했습니다"
        )
        self.lid_open = self._record_check(
            "lid_open_zero", "출력 OFF 상태의 lid-open=0 검증 기록이 있습니다"
        )
        self.lid_closed = self._record_check(
            "lid_closed_one", "출력 OFF 상태의 lid-closed=1 검증 기록이 있습니다"
        )
        self.residual_ack = QCheckBox("출력 OFF와 잔류 전압 미확인이 별개임을 확인했습니다")
        self.residual_ack.setChecked(config.residual_warning_ack)
        self._edits.append(self.residual_ack)
        for checkbox in (
            self.installation,
            self.hardware_protection,
            self.lid_open,
            self.lid_closed,
            self.residual_ack,
        ):
            approval.addRow(checkbox)
        limits = QLabel(
            "전압 상한은 장비·사용자·시료·fixture·케이블 정격의 최솟값입니다. "
            "10 V 초기 제한도 시료 안전 전압의 보증이 아닙니다. "
            "Software current trip은 장비의 programmable compliance가 아닙니다."
        )
        limits.setWordWrap(True)
        approval.addRow(limits)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("설정 적용 · 연결하지 않음")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)
        for widget in self._edits:
            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(self._refresh_status)
            elif isinstance(widget, QPlainTextEdit):
                widget.textChanged.connect(self._refresh_status)
            elif isinstance(widget, QComboBox):
                widget.currentTextChanged.connect(self._refresh_status)
            elif isinstance(widget, QSpinBox):
                widget.valueChanged.connect(self._refresh_status)
            elif isinstance(widget, QCheckBox):
                widget.toggled.connect(self._refresh_status)
        self._refresh_status()

    @staticmethod
    def _tab(tabs, title):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        form = QFormLayout(content)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        scroll.setWidget(content)
        tabs.addTab(scroll, title)
        return form

    def _text(self, text):
        widget = QLineEdit(text)
        self._edits.append(widget)
        return widget

    @staticmethod
    def _optional_text(value):
        return "" if value is None else str(value)

    def _select_backend(self):
        value = self.backend_profiles.currentData()
        if value != "custom":
            self.visa_backend.setText(value)

    def _sync_backend(self):
        value = self.visa_backend.text().strip()
        index = 1 if value == "@py" else (0 if value in ("", "@ivi") else 2)
        self.backend_profiles.blockSignals(True)
        self.backend_profiles.setCurrentIndex(index)
        self.backend_profiles.blockSignals(False)

    def _termination(self, selected):
        widget = QComboBox()
        for label, value in (
            ("LF (\\n)", "\n"),
            ("CR+LF (\\r\\n)", "\r\n"),
            ("CR (\\r)", "\r"),
            ("없음 — EOI 등 사용", None),
        ):
            widget.addItem(label, value)
        match = next((i for i in range(widget.count()) if widget.itemData(i) == selected), None)
        if match is None:
            widget.addItem(f"기존 설정 {selected!r}", selected)
            match = widget.count() - 1
        widget.setCurrentIndex(match)
        self._edits.append(widget)
        return widget

    def _record_check(self, key, text):
        checkbox = QCheckBox(text)
        checkbox.setChecked(self._original.commissioning.get(key) is True)
        self._edits.append(checkbox)
        return checkbox

    @staticmethod
    def _number(edit: QLineEdit, label: str, *, optional=False):
        text = edit.text().strip()
        if not text and optional:
            return None
        try:
            value = float(text)
        except ValueError as exc:
            raise ConfigurationError(f"{label}: SI 단위의 숫자를 입력하세요") from exc
        if not math.isfinite(value):
            raise ConfigurationError(f"{label}: NaN/Infinity를 사용할 수 없습니다")
        return value

    def build_config(self) -> RunConfig:
        """Build an immutable snapshot; this does not authorize a connected instrument."""
        data = self._original.to_dict()
        tokens = self.voltages.text().split(",")
        values = []
        for token in tokens:
            try:
                value = float(token.strip())
            except ValueError as exc:
                raise ConfigurationError(
                    "요청 전압: 쉼표로 구분한 V 단위 숫자가 필요합니다"
                ) from exc
            if not math.isfinite(value):
                raise ConfigurationError("요청 전압: NaN/Infinity를 사용할 수 없습니다")
            values.append(value)
        protocol = self._original.protocol
        if protocol == "constant" and len(values) > 1:
            protocol = "list"
        record = dict(data["commissioning"])
        record_values = {
            "fixture_id": self.fixture_id.text().strip(),
            "approved_by": self.approved_by.text().strip(),
            "installation_confirmed": self.installation.isChecked(),
            "hardware_protection_reviewed": self.hardware_protection.isChecked(),
            "lid_open_zero": self.lid_open.isChecked(),
            "lid_closed_one": self.lid_closed.isChecked(),
        }
        for key, value in record_values.items():
            if key in record or value:
                record[key] = value
        real = self.real_mode.isChecked()
        data.update(
            simulation=not real,
            transport="visa" if real else "simulation",
            resource=self.resource.currentText().strip(),
            visa_backend=self.visa_backend.text().strip() or None,
            timeout_ms=self.timeout_ms.value(),
            send_end=self.send_end.isChecked(),
            read_termination=self.read_termination.currentData(),
            write_termination=self.write_termination.currentData(),
            mode=self.mode.currentText(),
            sample_id=self.sample_id.text().strip(),
            output_directory=self.output_directory.text().strip(),
            note=self.note.toPlainText(),
            voltages=values,
            protocol=protocol,
            voltage_ceiling_V=self._number(self.ceiling, "전압 상한"),
            source_range_V=float(self.source_range.currentText()),
            current_trip_A=self._number(self.current_trip, "Current trip", optional=True),
            nplc=self._number(self.nplc, "NPLC"),
            line_frequency_hz=float(self.line_frequency.currentText()),
            sample_interval_s=self._number(self.interval, "Sample interval"),
            dwell_s=self._number(self.dwell, "Dwell"),
            summary_window_s=self._number(self.summary_window, "Summary window"),
            exclude_initial_s=self._number(self.exclude_initial, "초기 제외 구간"),
            sample_limit_V=self._number(self.sample_rating, "시료 정격", optional=True),
            fixture_limit_V=self._number(self.fixture_rating, "Fixture 정격", optional=True),
            cable_limit_V=self._number(self.cable_rating, "케이블 정격", optional=True),
            rating_approval=self.rating_approval.text().strip(),
            resistive_limit_enabled=self.resistive_limit.currentData(),
            residual_warning_ack=self.residual_ack.isChecked(),
            commissioning=record,
        )
        return RunConfig.from_dict(data)

    def _ready_config(self) -> RunConfig:
        config = self.build_config()
        if not config.simulation:
            if not self.hardware_protection.isChecked():
                raise ConfigurationError("독립적인 하드웨어 보호·차단·방전 검토 기록이 필요합니다")
            config.validate(for_arm=True)
        return config

    def _refresh_status(self, *_):
        try:
            config = self._ready_config()
            if config.simulation:
                text = "SIMULATION 설정 · 실제 장비 연결 없음. 적용 후 별도로 ARM·START합니다."
            else:
                requested = list(config.voltages)
                quantized = [config.quantize_voltage(v) for v in config.voltages]
                text = (
                    f"실장비 설정 준비됨 · 상한 {config.effective_ceiling:g} V · "
                    f"요청 {requested} V → 설정 분해능 기준 {quantized} V\n"
                    "아직 연결·출력 승인이 아닙니다. 연결 후 OFF 상태의 lid 전이를 확인하세요."
                )
            self.status_label.setText(text)
            self.status_label.setStyleSheet("color:#16667a")
        except (ValueError, TypeError) as exc:
            self.status_label.setText(f"설정 확인 필요: {exc}")
            self.status_label.setStyleSheet("color:#a32e28")

    def accept(self):
        try:
            self.result_config = self._ready_config()
        except (ValueError, TypeError) as exc:
            self.result_config = None
            self.status_label.setText(f"설정 적용 안 됨: {exc}")
            self.status_label.setStyleSheet("color:#a32e28")
            return
        super().accept()
