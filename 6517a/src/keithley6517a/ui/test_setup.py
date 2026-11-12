"""Prepare a trial configuration without touching a VISA session or enabling output."""

from __future__ import annotations

import math
from collections.abc import Sequence

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import ConfigurationError, RunConfig
from .readiness import configuration_issues, humanize_issue


class TestSetupDialog(QDialog):
    """A settings form, not commissioning: the connected worker observes the lid later.

    ``resources`` is supplied by the caller after explicit discovery. This dialog
    does no device, filesystem, or network I/O, including while applying settings.
    """

    def __init__(
        self, config: RunConfig, parent=None, *, resources: Sequence[str] = (), focus_field=None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("6517A · 측정 설정")
        self.resize(900, 760)
        self._original = config
        self.result_config: RunConfig | None = None
        self.applied_as_draft: bool | None = None
        self._edits: list[QWidget] = []
        root = QVBoxLayout(self)
        intro = QLabel("설정 적용 후 메인 화면에서 연결 → ARM → START 순서로 진행합니다.")
        intro.setWordWrap(True)
        root.addWidget(intro)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        basic = self._tab(self.tabs, "1. 기본 설정")
        advanced = self._tab(self.tabs, "2. 상세 설정")
        approval = self._tab(self.tabs, "3. fixture 기록")

        self.real_mode = QCheckBox("실제 장비 사용 · REAL VISA")
        self.real_mode.setChecked(not config.simulation)
        self._edits.append(self.real_mode)
        basic.addRow(self.real_mode)
        self.setup_policy = QComboBox()
        self.setup_policy.addItem("검증된 fixture", "verified_fixture")
        self.setup_policy.addItem("사용자 관리 · 저전압 시험 ≤10 V", "operator_low_voltage")
        self.setup_policy.setCurrentIndex(1 if config.setup_policy == "operator_low_voltage" else 0)
        self._edits.append(self.setup_policy)
        basic.addRow("운용 방식", self.setup_policy)
        self.resource = QComboBox()
        self.resource.setEditable(True)
        self.resource.addItems(list(dict.fromkeys(resources)))
        self.resource.setCurrentText(config.resource)
        self.resource.setToolTip("NI MAX와 같은 GPIB 주소를 선택하거나 입력합니다.")
        self._edits.append(self.resource)
        basic.addRow("GPIB 주소", self.resource)
        self.sample_id = self._text(config.sample_id)
        basic.addRow("시료 ID", self.sample_id)
        self.reference_preset_button = QPushButton("1 GΩ · 1 V 시험값 적용")
        self.reference_preset_button.setToolTip(
            "1 V · software trip 10 nA · 명목 기준저항 1 GΩ. 확인 항목은 자동 선택하지 않습니다."
        )
        self.reference_preset_button.clicked.connect(self._apply_reference_preset)
        basic.addRow(self.reference_preset_button)
        self.voltages = self._text(", ".join(str(v) for v in config.voltages))
        basic.addRow("전압 (V, 쉼표로 구분)", self.voltages)
        self.current_trip = self._text(self._optional_text(config.current_trip_A))
        self.current_trip.setPlaceholderText("예: 1e-8 = 10 nA")
        basic.addRow("Software current trip (A)", self.current_trip)
        self.dwell = self._text(str(config.dwell_s))
        basic.addRow("전압별 측정 시간 (s)", self.dwell)
        self.reference_current_label = QLabel()
        self.reference_current_label.setWordWrap(True)
        basic.addRow(self.reference_current_label)
        self.resistive_limit = QComboBox()
        self.resistive_limit.addItem("선택 필요", None)
        self.resistive_limit.addItem("OFF · 내부 저항성 전류 제한 미사용", False)
        self.resistive_limit.addItem("ON · 내부 저항성 전류 제한 사용", True)
        self.resistive_limit.setCurrentIndex(
            0
            if config.resistive_limit_enabled is None
            else (2 if config.resistive_limit_enabled else 1)
        )
        self._edits.append(self.resistive_limit)
        basic.addRow("Resistive-limit", self.resistive_limit)
        self.operator_ack = QCheckBox("연결·정격·외부 보호를 사용자가 관리함을 확인합니다")
        self.operator_ack.setChecked(config.operator_setup_acknowledged)
        self._edits.append(self.operator_ack)
        basic.addRow(self.operator_ack)
        self.residual_ack = QCheckBox("출력 OFF와 방전 완료가 다름을 확인했습니다")
        self.residual_ack.setChecked(config.residual_warning_ack)
        self._edits.append(self.residual_ack)
        basic.addRow(self.residual_ack)
        self.policy_note = QLabel()
        self.policy_note.setWordWrap(True)
        basic.addRow(self.policy_note)

        self.output_directory = self._text(config.output_directory)
        advanced.addRow("결과 저장 폴더", self.output_directory)
        self.mode = QComboBox()
        self.mode.addItems(["FVMI_CURRENT", "NATIVE_RESISTANCE"])
        self.mode.setCurrentText(config.mode)
        self._edits.append(self.mode)
        advanced.addRow("측정 모드", self.mode)
        self.ceiling = self._text(str(config.voltage_ceiling_V))
        advanced.addRow("소프트웨어 상한 (V)", self.ceiling)
        self.source_range = QComboBox()
        self.source_range.addItems(["100", "1000"])
        self.source_range.setCurrentText(str(int(config.source_range_V)))
        self._edits.append(self.source_range)
        advanced.addRow("V-Source 범위 (V)", self.source_range)
        self.reference_resistance = self._text(
            self._optional_text(config.sample_metadata.get("reference_resistance_ohm"))
        )
        advanced.addRow("기준저항 명목값 (Ω)", self.reference_resistance)
        self.simulation_resistance = self._text(str(config.simulation_resistance_ohm))
        self.simulation_resistance.setToolTip("SIMULATION 전용 가상 저항값입니다.")
        self.simulation_resistance.setEnabled(not self.real_mode.isChecked())
        advanced.addRow("SIM 저항 모델 (Ω)", self.simulation_resistance)
        self.nplc = self._text(str(config.nplc))
        self.line_frequency = QComboBox()
        self.line_frequency.addItems(["50", "60"])
        self.line_frequency.setCurrentText(str(int(config.line_frequency_hz)))
        self._edits.append(self.line_frequency)
        self.interval = self._text(str(config.sample_interval_s))
        self.summary_window = self._text(str(config.summary_window_s))
        self.exclude_initial = self._text(str(config.exclude_initial_s))
        for label, widget in (
            ("NPLC", self.nplc),
            ("전원 주파수 (Hz)", self.line_frequency),
            ("Sample interval (s)", self.interval),
            ("요약 window (s)", self.summary_window),
            ("초기 제외 구간 (s)", self.exclude_initial),
        ):
            advanced.addRow(label, widget)
        self.visa_backend = self._text(config.visa_backend or "")
        self.visa_backend.setPlaceholderText("기본 VISA / @ivi / library 경로")
        self.backend_profiles = QComboBox()
        self.backend_profiles.addItem("NI-VISA · 기본 권장", "@ivi")
        self.backend_profiles.addItem("NI-488.2 전용 · 선택 확장 필요", "@py")
        self.backend_profiles.addItem("라이브러리 경로 직접 지정", "custom")
        self._edits.append(self.backend_profiles)
        advanced.addRow("통신 방식", self.backend_profiles)
        advanced.addRow("VISA backend / library", self.visa_backend)
        self.backend_profiles.currentIndexChanged.connect(self._select_backend)
        self.visa_backend.textChanged.connect(self._sync_backend)
        self._sync_backend()
        self.timeout_ms = QSpinBox()
        self.timeout_ms.setRange(1, 60000)
        self.timeout_ms.setValue(config.timeout_ms)
        self._edits.append(self.timeout_ms)
        advanced.addRow("I/O timeout (ms)", self.timeout_ms)
        self.send_end = QCheckBox("EOI / send_end 사용")
        self.send_end.setChecked(config.send_end)
        self._edits.append(self.send_end)
        advanced.addRow(self.send_end)
        self.read_termination = self._termination(config.read_termination)
        self.write_termination = self._termination(config.write_termination)
        advanced.addRow("읽기 terminator", self.read_termination)
        advanced.addRow("쓰기 terminator", self.write_termination)
        self.note = QPlainTextEdit(config.note)
        self.note.setMaximumHeight(75)
        self._edits.append(self.note)
        advanced.addRow("메모", self.note)

        self.approval_note = QLabel()
        self.approval_note.setWordWrap(True)
        approval.addRow(self.approval_note)
        self.sample_rating = self._text(self._optional_text(config.sample_limit_V))
        self.fixture_rating = self._text(self._optional_text(config.fixture_limit_V))
        self.cable_rating = self._text(self._optional_text(config.cable_limit_V))
        approval.addRow("시료 최대 전압 (V)", self.sample_rating)
        approval.addRow("Fixture 최대 전압 (V)", self.fixture_rating)
        approval.addRow("케이블 최대 전압 (V)", self.cable_rating)
        self.rating_approval = self._text(config.rating_approval)
        self.fixture_id = self._text(str(config.commissioning.get("fixture_id", "")))
        self.approved_by = self._text(str(config.commissioning.get("approved_by", "")))
        approval.addRow("정격·실험 승인 기록", self.rating_approval)
        approval.addRow("Fixture ID", self.fixture_id)
        approval.addRow("담당자", self.approved_by)
        self.installation = self._record_check(
            "installation_confirmed", "결선·정격·인터록 설치를 확인했습니다"
        )
        self.hardware_protection = self._record_check(
            "hardware_protection_reviewed", "독립 보호·차단·방전 절차를 검토했습니다"
        )
        self.lid_open = self._record_check("lid_open_zero", "출력 OFF에서 lid-open=0 확인 기록")
        self.lid_closed = self._record_check(
            "lid_closed_one", "출력 OFF에서 lid-closed=1 확인 기록"
        )
        for widget in (self.installation, self.hardware_protection, self.lid_open, self.lid_closed):
            approval.addRow(widget)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        self.issue_list = QListWidget()
        self.issue_list.setMaximumHeight(112)
        self.issue_list.setToolTip("항목을 누르면 해당 입력란으로 이동합니다.")
        self.issue_list.itemClicked.connect(
            lambda item: self.focus_field(item.data(Qt.ItemDataRole.UserRole))
        )
        root.addWidget(self.issue_list)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.ready_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ready_button.setText("측정 설정 적용")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        self.draft_button = self.buttons.addButton(
            "초안 적용", QDialogButtonBox.ButtonRole.ActionRole
        )
        self.draft_button.clicked.connect(self.accept)
        self.buttons.accepted.connect(self.accept_ready)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)
        self._focus_targets = {}
        for index, pairs in enumerate(
            (
                {
                    "resource": self.resource,
                    "sample_id": self.sample_id,
                    "voltages": self.voltages,
                    "current_trip_A": self.current_trip,
                    "dwell_s": self.dwell,
                    "resistive_limit_enabled": self.resistive_limit,
                    "operator_setup_acknowledged": self.operator_ack,
                    "residual_warning_ack": self.residual_ack,
                    "setup_policy": self.setup_policy,
                },
                {
                    "voltage_ceiling_V": self.ceiling,
                    "source_range_V": self.source_range,
                    "nplc": self.nplc,
                    "sample_interval_s": self.interval,
                    "summary_window_s": self.summary_window,
                    "exclude_initial_s": self.exclude_initial,
                    "simulation_resistance_ohm": self.simulation_resistance,
                    "mode": self.mode,
                },
                {
                    "sample_limit_V": self.sample_rating,
                    "fixture_limit_V": self.fixture_rating,
                    "cable_limit_V": self.cable_rating,
                    "rating_approval": self.rating_approval,
                    "commissioning.fixture_id": self.fixture_id,
                    "commissioning.approved_by": self.approved_by,
                    "commissioning.installation_confirmed": self.installation,
                    "commissioning.hardware_protection_reviewed": self.hardware_protection,
                    "commissioning.lid_open_zero": self.lid_open,
                    "commissioning.lid_closed_one": self.lid_closed,
                },
            )
        ):
            self._focus_targets.update({key: (index, value) for key, value in pairs.items()})
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
        if focus_field:
            QTimer.singleShot(0, lambda: self.focus_field(focus_field))

    def focus_field(self, field) -> bool:
        target = self._focus_targets.get(field)
        if target is None:
            return False
        index, widget = target
        self.tabs.setCurrentIndex(index)
        scroll = self.tabs.widget(index)
        scroll.ensureWidgetVisible(widget)
        widget.setFocus(Qt.FocusReason.OtherFocusReason)
        if isinstance(widget, QLineEdit):
            widget.selectAll()
        return True

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
                "사용자 관리 시험 · 최대 10 V · 장비 상태 검사는 ARM에서 진행합니다."
            )
            self.approval_note.setText(
                "이 방식에서 정격·fixture 기록은 선택 입력입니다. "
                "입력한 전압 정격은 상한 계산에 사용하며, "
                "물리적 설치 확인 기록은 자동 승인하지 않습니다."
            )
        else:
            self.policy_note.setText(
                "검증된 fixture · 현재 연결에서 인터록 열림 0 → 닫힘 1 확인이 필요합니다."
            )
            self.approval_note.setText(
                "이 방식의 실장비 ARM에는 아래 정격·설치·승인 기록이 필요합니다."
            )
        self.tabs.setTabText(2, "3. fixture 기록" if not operator else "3. 추가 기록 (선택)")
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

    def _show_issues(self, issues):
        self.issue_list.clear()
        for issue in issues:
            item = QListWidgetItem(issue["message"])
            item.setData(Qt.ItemDataRole.UserRole, issue.get("field", ""))
            self.issue_list.addItem(item)
        self.issue_list.setVisible(bool(issues))

    def _refresh_status(self, *_):
        try:
            config = self._draft_config()
            self._reference_preview(config)
            issues = configuration_issues(config)
            self._show_issues(issues)
            if issues:
                self.status_label.setText(f"초안 적용 가능 · ARM 준비 미완료 ({len(issues)}개)")
                self.status_label.setStyleSheet("color:#805c15")
                return
            requested = list(config.voltages)
            quantized = [config.quantize_voltage(v) for v in config.voltages]
            scope = "SIMULATION" if config.simulation else "실장비"
            self.status_label.setText(
                f"{scope} 설정 준비됨 · 요청 {requested} V → 적용 {quantized} V · "
                "연결은 메인 화면에서 진행합니다."
            )
            self.status_label.setStyleSheet("color:#16667a")
        except (ValueError, TypeError) as exc:
            self.reference_current_label.setText("설정값을 확인하면 명목 예상 전류를 표시합니다.")
            message = humanize_issue(exc)
            self.status_label.setText(f"설정 확인 필요: {message}")
            self.status_label.setStyleSheet("color:#a32e28")
            self._show_issues([{"message": message, "field": ""}])

    def accept_ready(self):
        """Default apply requires measurement-ready values, but never performs instrument I/O."""
        try:
            config = self._draft_config()
            issues = configuration_issues(config)
            if issues:
                self.result_config = None
                self.applied_as_draft = None
                self._show_issues(issues)
                self.status_label.setText(
                    f"설정 적용 안 됨 · 필수 설정 {len(issues)}개를 확인하세요"
                )
                self.status_label.setStyleSheet("color:#a32e28")
                self.focus_field(issues[0].get("field"))
                return
            self.result_config = self._ready_config(config)
            self.applied_as_draft = False
        except (ValueError, TypeError) as exc:
            self.result_config = None
            self.applied_as_draft = None
            message = humanize_issue(exc)
            self.status_label.setText(f"설정 적용 안 됨: {message}")
            self.status_label.setStyleSheet("color:#a32e28")
            self._show_issues([{"message": message, "field": ""}])
            return
        super().accept()

    def accept(self):
        """Explicit draft apply preserves incomplete settings without claiming ARM readiness."""
        try:
            self.result_config = self._draft_config()
            self.applied_as_draft = True
        except (ValueError, TypeError) as exc:
            self.result_config = None
            self.applied_as_draft = None
            message = humanize_issue(exc)
            self.status_label.setText(f"설정 적용 안 됨: {message}")
            self.status_label.setStyleSheet("color:#a32e28")
            self._show_issues([{"message": message, "field": ""}])
            return
        super().accept()
