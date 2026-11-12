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
    QPushButton,
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
            "운용 방식을 선택하고 시험값을 입력한 뒤, 메인 화면에서 연결 → ARM → START합니다."
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
        self.setup_policy = QComboBox()
        self.setup_policy.addItem("검증된 fixture · 기존 승인 기록 사용", "verified_fixture")
        self.setup_policy.addItem("사용자 관리 · 저전압 시험 ≤10 V", "operator_low_voltage")
        self.setup_policy.setCurrentIndex(
            1
            if getattr(config, "setup_policy", "verified_fixture") == "operator_low_voltage"
            else 0
        )
        self._edits.append(self.setup_policy)
        connection.addRow("운용 방식", self.setup_policy)
        self.operator_ack = QCheckBox("연결·부품 정격·외부 보호를 사용자가 관리함을 확인합니다")
        self.operator_ack.setChecked(getattr(config, "operator_setup_acknowledged", False))
        self._edits.append(self.operator_ack)
        connection.addRow(self.operator_ack)
        self.policy_note = QLabel()
        self.policy_note.setWordWrap(True)
        connection.addRow(self.policy_note)
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
        self.reference_preset_button = QPushButton("1 GΩ · 1 V 시험값 적용")
        self.reference_preset_button.setToolTip(
            "요청 1 V, software 상한 10 V, 100 V 범위, software trip 10 nA, "
            "명목 기준저항·SIM 저항 모델 1 GΩ를 입력합니다. 운용 방식과 확인 체크는 유지합니다."
        )
        self.reference_preset_button.clicked.connect(self._apply_reference_preset)
        experiment.addRow(self.reference_preset_button)
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
        self.reference_resistance = self._text(
            self._optional_text(config.sample_metadata.get("reference_resistance_ohm"))
        )
        self.reference_resistance.setPlaceholderText("선택 입력 · 1e9 = 1 GΩ")
        experiment.addRow("기준저항 명목값 (Ω)", self.reference_resistance)
        self.simulation_resistance = self._text(
            str(getattr(config, "simulation_resistance_ohm", 1e12))
        )
        self.simulation_resistance.setToolTip(
            "SIMULATION의 가상 전류를 만드는 저항값입니다. 실장비에서는 사용하지 않습니다."
        )
        self.simulation_resistance.setEnabled(not self.real_mode.isChecked())
        experiment.addRow("SIM 저항 모델 (Ω)", self.simulation_resistance)
        self.reference_current_label = QLabel()
        self.reference_current_label.setWordWrap(True)
        experiment.addRow(self.reference_current_label)
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
        self.approval_note = QLabel()
        self.approval_note.setWordWrap(True)
        approval.addRow(self.approval_note)
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
        self.setup_policy.currentIndexChanged.connect(self._policy_changed)
        self.real_mode.toggled.connect(
            lambda checked: self.simulation_resistance.setEnabled(not checked)
        )
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
        self._policy_changed()

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

    def _policy_changed(self, *_):
        operator = self.setup_policy.currentData() == "operator_low_voltage"
        self.operator_ack.setEnabled(operator)
        model = self.source_range.model()
        model.item(1).setEnabled(not operator)
        if operator:
            self.source_range.setCurrentText("100")
            self.policy_note.setText(
                "사용자 관리 시험은 software 상한 10 V·100 V 범위로 제한됩니다. "
                "실장비의 인터록 오류, limit와 STOP/OFF 처리는 계속 검사합니다."
            )
            self.approval_note.setText(
                "이 방식에서 정격·fixture 기록은 선택 입력입니다. "
                "입력한 전압 정격은 상한 계산에 사용하며, "
                "물리적 설치 확인 기록은 자동 승인하지 않습니다."
            )
        else:
            self.policy_note.setText(
                "검증된 fixture 방식은 승인 기록과 현재 연결의 출력 OFF 상태에서 "
                "인터록 열림 0 → 닫힘 1 확인을 사용합니다."
            )
            self.approval_note.setText(
                "이 방식의 실장비 ARM에는 아래 정격·설치·승인 기록이 필요합니다."
            )
        self._refresh_status()

    def _apply_reference_preset(self):
        self.voltages.setText("1")
        self.ceiling.setText("10")
        self.source_range.setCurrentText("100")
        self.current_trip.setText("1e-8")
        self.reference_resistance.setText("1e9")
        self.simulation_resistance.setText("1e9")
        self._refresh_status()

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
        metadata = dict(data["sample_metadata"])
        reference = self._number(self.reference_resistance, "기준저항", optional=True)
        if reference is None:
            metadata.pop("reference_resistance_ohm", None)
        elif reference <= 0:
            raise ConfigurationError("기준저항은 0보다 커야 합니다")
        else:
            metadata["reference_resistance_ohm"] = reference
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
            setup_policy=self.setup_policy.currentData(),
            operator_setup_acknowledged=self.operator_ack.isChecked(),
            simulation_resistance_ohm=self._number(self.simulation_resistance, "SIM 저항 모델"),
            sample_metadata=metadata,
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

    def _draft_config(self) -> RunConfig:
        config = self.build_config()
        if not config.simulation and config.mode == "NATIVE_RESISTANCE":
            raise ConfigurationError(
                "Real native resistance disabled: measured-current trip unverified"
            )
        return config

    def _ready_config(self, config: RunConfig | None = None) -> RunConfig:
        config = config or self._draft_config()
        if not config.simulation:
            if (
                config.setup_policy == "verified_fixture"
                and not self.hardware_protection.isChecked()
            ):
                raise ConfigurationError("독립적인 하드웨어 보호·차단·방전 검토 기록이 필요합니다")
        config.validate(for_arm=True)
        return config

    @staticmethod
    def _current_text(current):
        if current == 0:
            return "0 A"
        for scale, unit in ((1, "A"), (1e-3, "mA"), (1e-6, "µA"), (1e-9, "nA"), (1e-12, "pA")):
            if abs(current) >= scale:
                return f"{current / scale:g} {unit}"
        return f"{current:g} A"

    def _reference_preview(self, config):
        reference = config.sample_metadata.get("reference_resistance_ohm")
        if reference is None:
            self.reference_current_label.setText(
                "기준저항 명목값을 입력하면 I=V/R 예상값을 표시합니다."
            )
            return
        points = [
            f"{config.quantize_voltage(v):g} V → "
            f"{self._current_text(config.quantize_voltage(v) / reference)}"
            for v in config.voltages[:4]
        ]
        if len(config.voltages) > 4:
            points.append(f"… 총 {len(config.voltages)}점")
        self.reference_current_label.setText(
            "명목 예상 전류 · 설정 분해능 기준 · " + ", ".join(points) + " · 실측값 아님"
        )

    def _refresh_status(self, *_):
        try:
            config = self._draft_config()
            self._reference_preview(config)
            try:
                self._ready_config(config)
            except (ValueError, TypeError) as exc:
                self.status_label.setText(f"초안 적용 가능 · ARM 준비 미완료: {exc}")
                self.status_label.setStyleSheet("color:#805c15")
                self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
                    "초안 적용 · 연결하지 않음"
                )
                return
            requested = list(config.voltages)
            quantized = [config.quantize_voltage(v) for v in config.voltages]
            scope = "SIMULATION" if config.simulation else "실장비"
            text = (
                f"{scope} 설정 준비됨 · 상한 {config.effective_ceiling:g} V · "
                f"요청 {requested} V → 설정 분해능 기준 {quantized} V\n"
                "적용 후 별도로 연결·ARM·START합니다."
            )
            self.status_label.setText(text)
            self.status_label.setStyleSheet("color:#16667a")
            self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
                "설정 적용 · 연결하지 않음"
            )
        except (ValueError, TypeError) as exc:
            self.reference_current_label.setText("설정값을 확인하면 명목 예상 전류를 표시합니다.")
            self.status_label.setText(f"설정 확인 필요: {exc}")
            self.status_label.setStyleSheet("color:#a32e28")

    def accept(self):
        try:
            self.result_config = self._draft_config()
        except (ValueError, TypeError) as exc:
            self.result_config = None
            self.status_label.setText(f"설정 적용 안 됨: {exc}")
            self.status_label.setStyleSheet("color:#a32e28")
            return
        super().accept()
