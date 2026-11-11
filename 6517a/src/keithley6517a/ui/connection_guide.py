"""Read-only connection guidance; every operation is an explicit parent-owned action.

A diagnostic observation is not a live session approval. This widget never opens
a transport, and it has no ARM, START, voltage, or output-ON action.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)


class ConnectionGuide(QGroupBox):
    request_real_mode = Signal()
    request_discover = Signal()
    request_identify = Signal()
    request_off_check = Signal()
    request_prepare_settings = Signal()

    def __init__(self, parent=None):
        super().__init__("NI 실장비 연결 시험 안내", parent)
        self._simulation = True
        self._resource = ""
        self._backend = ""
        self._busy = False
        self._closing = False
        self._resources = []
        self._status = {"state": "DISCONNECTED", "output_state": "UNKNOWN"}
        self._diagnostic = None
        self._changed_while_connected = False
        self.current_step = 0
        self.setMaximumHeight(215)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)
        heading = QHBoxLayout()
        self.context_label = self._label()
        self.real_mode_button = QPushButton("NI 실장비 연결 시험 시작 (출력 ON 없음)")
        self.real_mode_button.clicked.connect(self.request_real_mode.emit)
        heading.addWidget(self.context_label, 1)
        heading.addWidget(self.real_mode_button)
        layout.addLayout(heading)
        self.stage_label = self._label()
        self.next_label = self._label()
        self.next_label.setStyleSheet("font-weight:600;color:#1b6284")
        self.detail_label = self._label()
        self.detail_label.setMaximumHeight(55)
        layout.addWidget(self.stage_label)
        layout.addWidget(self.next_label)
        layout.addWidget(self.detail_label)
        actions = QHBoxLayout()
        self.discover_button = QPushButton("1. GPIB 목록 조회")
        self.identify_button = QPushButton("2. 선택 주소 IDN 확인")
        self.off_check_button = QPushButton("3. 선택 장비 보호 OFF 시험")
        self.settings_button = QPushButton("4. 시료·시험 설정 입력")
        for button, signal in (
            (self.discover_button, self.request_discover),
            (self.identify_button, self.request_identify),
            (self.off_check_button, self.request_off_check),
            (self.settings_button, self.request_prepare_settings),
        ):
            actions.addWidget(button)
            button.clicked.connect(signal.emit)
        layout.addLayout(actions)
        self._render()

    @staticmethod
    def _label():
        label = QLabel()
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setMinimumWidth(0)
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        return label

    def set_context(
        self, *, simulation: bool, resource: str = "", backend=None, busy=False, closing=False
    ):
        """Update selected controls; changing a target invalidates old observations."""
        old = self._simulation, self._resource, self._backend
        new = bool(simulation), resource.strip(), (backend or "").strip()
        if old != new:
            self._diagnostic = None
            if self._status.get("state") != "DISCONNECTED":
                self._changed_while_connected = True
        self._simulation, self._resource, self._backend = new
        self._busy, self._closing = bool(busy), bool(closing)
        self._render()

    def update_resources(self, resources):
        self._resources = list(resources)
        self._render()

    def update_status(self, status=None, **values):
        """Accept the worker snapshot; no cached session approval survives disconnect."""
        incoming = deepcopy(dict(status or {}, **values))
        previous_state = self._status.get("state", "DISCONNECTED")
        state = incoming.get("state", previous_state)
        if state == "DISCONNECTED":
            if previous_state != "DISCONNECTED":
                self._diagnostic = None
            self._changed_while_connected = False
            self._status = {"state": "DISCONNECTED", "output_state": "UNKNOWN"}
        else:
            self._status.update(incoming)
        self._render()

    def update_diagnostic(self, report):
        self._diagnostic = deepcopy(dict(report))
        self._render()

    def _matching_report(self):
        report = self._diagnostic
        if not report:
            return None
        settings = report.get("settings") or {}
        discovery = report.get("mode") == "DISCOVERY" and settings.get("resource") is None
        if not discovery and settings.get("resource") != self._resource:
            return None
        if (settings.get("backend") or "").strip() != self._backend:
            return None
        return report

    @staticmethod
    def _real_identity(identity):
        return identity.get("model") == "6517A" and identity.get("simulation") is False

    def _observations(self):
        report = self._matching_report()
        is_real_report = bool(
            report
            and report.get("simulation") is False
            and report.get("transport_origin") == "visa"
        )
        identity = self._status.get("identity") or {}
        current_identity = self._real_identity(identity)
        reported_identity = (report or {}).get("identity") or {}
        idn_observed = bool(
            current_identity
            or (is_real_report and report.get("ok") and reported_identity.get("model") == "6517A")
        )
        off_observed = bool(
            is_real_report
            and report.get("ok")
            and report.get("mode") == "OUTPUT_OFF_CHECK"
            and report.get("output_OFF_confirmed") is True
            and report.get("output_state") == "OFF"
        )
        return report, idn_observed, off_observed

    def _render(self):
        state = self._status.get("state", "DISCONNECTED")
        connected = state != "DISCONNECTED"
        output = self._status.get("output_state", "UNKNOWN")
        report, idn_observed, off_observed = self._observations()
        real = not self._simulation
        available = real and not connected and not self._busy and not self._closing
        self.real_mode_button.setEnabled(
            self._simulation and not connected and not self._busy and not self._closing
        )
        self.discover_button.setEnabled(available)
        self.identify_button.setEnabled(available and bool(self._resource))
        self.off_check_button.setEnabled(available and bool(self._resource) and idn_observed)
        self.settings_button.setEnabled(available)
        backend = self._backend or "기본 VISA"
        self.context_label.setText(
            "SIMULATION · 시뮬레이션 화면이 열린 것은 정상입니다."
            if self._simulation
            else f"REAL 연결 시험 · {self._resource or '주소 미선택'} · {backend}"
        )
        self.current_step = 0
        detail = "NI MAX에서 보이는 장비와 같은 GPIB 주소를 직접 선택하세요."
        if self._simulation:
            next_action = (
                "시뮬레이션 연결을 종료한 뒤 ‘NI 실장비 연결 시험 시작’을 선택하세요."
                if connected
                else "다음: 실제 장비 시험은 오른쪽 ‘NI 실장비 연결 시험 시작’을 선택하세요."
            )
            detail = "이 선택은 모드만 바꿉니다. 장비 연결·ARM·출력 ON은 자동 실행하지 않습니다."
        elif self._changed_while_connected:
            next_action = "연결 중 설정이 달라졌습니다. 연결 종료 후 주소와 모드를 다시 확인하세요."
        elif state == "HV_STATE_UNKNOWN" or (connected and output == "UNKNOWN"):
            next_action = "출력 상태 UNKNOWN · 승인된 현장 차단·잔류 전압 확인 절차를 따르세요."
        elif state == "FAULT":
            next_action = (
                "오류가 유지됩니다. 오류 기록을 확인하고 연결을 종료한 뒤 다시 점검하세요."
            )
        elif self._busy or state in {"CONFIGURING", "RAMPING", "SETTLING", "ACQUIRING", "STOPPING"}:
            self.current_step = 6 if output == "ON" else 5
            next_action = f"현재 작업: {state} · OUTPUT {output} · 추가 명령 완료를 기다리세요."
        elif connected:
            identity = self._status.get("identity") or {}
            detail = (
                f"{identity.get('model', '모델 미확인')} · "
                f"Serial {identity.get('serial', '?')} · "
                f"Firmware {identity.get('firmware', '?')} · "
                f"현재 OUTPUT {output} · 잔류 전압 UNVERIFIED"
            )
            if self._status.get("can_start") is True:
                self.current_step = 6
                next_action = "ARM 완료 · 인가 계획을 검토한 뒤 기존 START 버튼을 직접 누르세요."
            elif self._status.get("can_arm") is True:
                self.current_step = 5
                next_action = "현재 연결 확인 완료 · 기존 ARM 버튼으로 설정·저장 준비를 검증하세요."
            else:
                self.current_step = 5
                next_action = "현재 연결의 출력 OFF에서 인터록 열림 0 → 닫힘 1을 확인하세요."
        elif not self._resource:
            self.current_step = 2
            next_action = "다음: GPIB 목록 조회 후 NI MAX와 같은 주소를 선택하세요."
            if self._resources:
                detail = (
                    f"조회된 주소 {len(self._resources)}개 · "
                    "자동으로 선택하거나 장비를 제어하지 않습니다."
                )
        elif not idn_observed:
            self.current_step = 3
            next_action = "다음: 선택 주소의 IDN을 확인하세요. 출력 변경 없는 진단입니다."
        elif not off_observed:
            self.current_step = 4
            next_action = "6517A 응답 확인 · 다음: 선택 장비의 보호 OFF 시험을 별도로 실행하세요."
        else:
            self.current_step = 5
            next_action = "진단 시 OFF 관찰 · 다음: 시료·시험 설정을 입력하고 별도로 연결하세요."
            detail = (
                "과거 진단은 현재 연결의 승인 상태가 아닙니다. "
                "연결 후 lid 0→1, ARM, START는 별도입니다."
            )

        if report:
            simulation = (
                report.get("simulation") is True or report.get("transport_origin") == "injected"
            )
            if simulation:
                detail = (
                    "가상/주입 transport 진단입니다. 실제 NI 장비 응답 확인으로 표시하지 않습니다."
                )
            elif not report.get("ok"):
                issues = report.get("issues") or []
                issue = next(
                    (item for item in issues if item.get("code") == "OUTPUT_OFF_UNCONFIRMED"),
                    issues[0] if issues else {},
                )
                action = issue.get("action") or issue.get("message", "보고서를 확인하세요.")
                detail = f"{issue.get('code', '진단 실패')} · {action}"
            elif not connected:
                identity = report.get("identity") or {}
                detail += (
                    f" · 진단 응답: {identity.get('model', '?')} / "
                    f"{identity.get('serial', '?')} / {identity.get('firmware', '?')}"
                )
            path = report.get("report_path")
            if path:
                detail += f" · 보고서 {Path(path).name}"
            else:
                detail += " · 보고서 경로 없음"
            self.detail_label.setToolTip(detail + f"\n전체 보고서: {path or '저장되지 않음'}")
        else:
            self.detail_label.setToolTip(detail)
        self.next_label.setText(next_action)
        self.detail_label.setText(detail)
        stages = (
            "1 NI MAX 확인",
            "2 주소 선택",
            "3 IDN 응답",
            "4 보호 OFF",
            "5 설정·인터록",
            "6 ARM·START",
        )
        self.stage_label.setText(
            " → ".join(
                f"[{name}]" if index == self.current_step else name
                for index, name in enumerate(stages, 1)
            )
        )
