"""Visible, asynchronous portable startup checks before opening the measurement UI."""

from __future__ import annotations

import codecs
import json
import os
import re
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import QProcess, QTimer, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_CAPTURE_LIMIT = 2 * 1024 * 1024


def _main_window():
    # Importing/constructing the measurement UI belongs after successful self-checks.
    from .main_window import MainWindow

    return MainWindow()


class StartupChecks(QWidget):
    """Run Bundle -> Simulation sequentially, without any instrument connection.

    The optional factories support isolated Qt tests and native bundle smoke tests.
    Ordinary startup always uses the bundled interpreter and fixed simulation config.
    """

    checks_passed = Signal()
    checks_failed = Signal(str)

    def __init__(
        self,
        root,
        parent=None,
        *,
        process_factory=None,
        command_factory=None,
        main_window_factory=None,
        auto_start=True,
    ):
        super().__init__(parent)
        self.root = Path(root).resolve()
        self.process_factory = process_factory or QProcess
        self.command_factory = command_factory
        self.main_window_factory = main_window_factory or _main_window
        self.process = None
        self.main_window = None
        self.state = "pending"
        self.stage = "bundle"
        self.stage_results = {}
        self.report_path = None
        self._stdout = bytearray()
        self._truncated = False
        self._pending_failure = ""
        self._stderr_decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._kill_timer = QTimer(self)
        self._kill_timer.setSingleShot(True)
        self._kill_timer.timeout.connect(self._kill_process)
        self._build_ui()
        if auto_start:
            QTimer.singleShot(0, self.begin)

    @property
    def status(self):
        return self.state

    def _build_ui(self):
        self.setWindowTitle("6517A · 시작 검사")
        self.resize(620, 275)
        root = QVBoxLayout(self)
        title = QLabel("프로그램 시작 검사")
        title.setStyleSheet("font-size:19px;font-weight:700;color:#176b88")
        root.addWidget(title)
        description = QLabel(
            "파일 검사와 가상 측정을 자동 실행합니다. GPIB 장비에는 연결하지 않습니다."
        )
        description.setWordWrap(True)
        root.addWidget(description)
        self.bundle_label = QLabel("1. Bundle 파일 검사 · 대기")
        self.simulation_label = QLabel("2. Simulation 동작 검사 · 대기")
        root.addWidget(self.bundle_label)
        root.addWidget(self.simulation_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 2)
        self.progress.setValue(0)
        root.addWidget(self.progress)
        self.status_label = QLabel("검사 준비 중…")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumBlockCount(1500)
        self.details.setMinimumHeight(160)
        self.details.hide()
        root.addWidget(self.details)
        actions = QHBoxLayout()
        self.details_toggle = QPushButton("상세 보기")
        self.details_toggle.setCheckable(True)
        self.details_toggle.toggled.connect(self.details.setVisible)
        actions.addWidget(self.details_toggle)
        actions.addStretch()
        self.retry_button = QPushButton("다시 검사")
        self.retry_button.setEnabled(False)
        self.retry_button.clicked.connect(self.begin)
        actions.addWidget(self.retry_button)
        self.close_button = QPushButton("취소")
        self.close_button.clicked.connect(self.close)
        actions.addWidget(self.close_button)
        root.addLayout(actions)

    def begin(self):
        if self.state not in {"pending", "failed"} or self.process is not None:
            return
        self.state = "running"
        self.stage = "bundle"
        self.stage_results = {}
        self.report_path = None
        self._pending_failure = ""
        self.details.clear()
        self.bundle_label.setText("1. Bundle 파일 검사 · 진행 중")
        self.simulation_label.setText("2. Simulation 동작 검사 · 대기")
        self.status_label.setStyleSheet("")
        self.retry_button.setEnabled(False)
        self.close_button.setText("취소")
        self.close_button.setEnabled(True)
        self._start_stage()

    def _command(self):
        python = self.root / "runtime/python.exe"
        script = self.root / (
            "tools/verify_bundle.py" if self.stage == "bundle" else "tools/launch.py"
        )
        if not python.is_file() or not script.is_file():
            raise ValueError("실행 파일이 없습니다. ZIP을 새 폴더에 모두 압축 해제하세요.")
        flags = ["-I", "-B", "-u", "-X", "utf8"]
        if self.stage == "bundle":
            args = [str(script), str(self.root), "--progress", "--save-report"]
        else:
            config_path = self.root / "app/examples/simulation_config.json"
            settings = json.loads(config_path.read_text(encoding="utf-8-sig"))
            if (
                not isinstance(settings, dict)
                or settings.get("simulation") is not True
                or settings.get("transport") != "simulation"
            ):
                raise ValueError("시작 검사는 고정된 가상 측정 설정만 사용할 수 있습니다.")
            args = [
                str(script),
                "cli",
                "simulate",
                "--fast",
                "--progress",
                "--config",
                str(config_path),
                "--output",
                str(self.root / "diagnostics/startup-simulation"),
            ]
        if self.command_factory is not None:
            return self.command_factory(self.stage)
        return str(python), flags + args

    def _start_stage(self):
        self._stdout = bytearray()
        self._truncated = False
        self._stderr_decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._pending_failure = ""
        self.progress.setRange(0, 0)
        name = "Bundle" if self.stage == "bundle" else "Simulation"
        self.status_label.setText(f"{name} 검사 중…")
        self._append_detail(f"[{name}] 시작")
        try:
            program, args = self._command()
            process = self.process_factory(self)
            self.process = process
            process.setWorkingDirectory(str(self.root))
            process.readyReadStandardOutput.connect(self._stdout_ready)
            process.readyReadStandardError.connect(self._stderr_ready)
            process.finished.connect(self._finished)
            process.errorOccurred.connect(self._error)
            process.start(program, [str(value) for value in args])
        except (OSError, ValueError, TypeError) as exc:
            self._fail(str(exc))

    def _append_detail(self, text):
        if text:
            self.details.appendPlainText(text[-8192:].rstrip())

    def _stdout_ready(self):
        self._read_stdout(self.sender())

    def _stderr_ready(self):
        self._read_stderr(self.sender())

    def _finished(self, code, exit_status):
        self._process_finished(self.sender(), code, exit_status)

    def _error(self, error):
        self._process_error(self.sender(), error)

    def _read_stdout(self, process):
        if process is not self.process:
            return
        payload = bytes(process.readAllStandardOutput())
        remaining = _CAPTURE_LIMIT - len(self._stdout)
        if len(payload) > remaining:
            self._truncated = True
        self._stdout.extend(payload[:remaining])

    def _read_stderr(self, process):
        if process is not self.process:
            return
        text = self._stderr_decoder.decode(bytes(process.readAllStandardError()))
        self._append_detail(text)
        if self.state != "running":
            return
        if self.stage == "bundle":
            matches = re.findall(r"\[CHECK\]\s*(\d+)/(\d+)", text)
            if matches:
                checked, total = map(int, matches[-1])
                if total > 0:
                    self.progress.setRange(0, total)
                    self.progress.setValue(min(checked, total))
                    self.status_label.setText(f"Bundle 파일 검사 · {checked:,}/{total:,}")
        elif text.strip():
            self.status_label.setText("Simulation 검사 중 · " + text.strip().splitlines()[-1][:180])

    def _process_error(self, process, error):
        if process is not self.process:
            return
        if error == QProcess.ProcessError.FailedToStart:
            self._kill_timer.stop()
            message = process.errorString()
            self.process = None
            process.deleteLater()
            if self.state in {"cancelling", "cancelled"}:
                self.state = "cancelled"
                self._save_report()
                self.close()
            else:
                self._fail("검사 실행기를 시작하지 못했습니다: " + message)
        elif self.state == "cancelling":
            return
        elif error != QProcess.ProcessError.Crashed:
            self._pending_failure = "검사 실행 오류: " + process.errorString()
            process.terminate()
            self._kill_timer.start(1500)

    def _process_finished(self, process, code, exit_status):
        if process is not self.process:
            return
        self._kill_timer.stop()
        self._read_stdout(process)
        self._read_stderr(process)
        self._append_detail(self._stderr_decoder.decode(b"", final=True))
        self.process = None
        process.deleteLater()
        if self.state in {"cancelling", "cancelled"}:
            self.state = "cancelled"
            self._save_report()
            self.close()
            return
        output = bytes(self._stdout).decode("utf-8", errors="replace")
        self._append_detail(output)
        if self._pending_failure:
            self._fail(self._pending_failure)
            return
        if code != 0 or exit_status != QProcess.ExitStatus.NormalExit:
            self._fail(f"{self.stage} 검사 실패 · 종료 코드 {code}. 상세 내용을 확인하세요.")
            return
        if self._truncated:
            self._fail("검사 결과가 허용 크기를 초과했습니다. 상세 기록을 확인하세요.")
            return
        try:
            report = json.loads(output)
            if not isinstance(report, dict):
                raise ValueError("JSON 객체가 필요합니다.")
            if self.stage == "bundle":
                valid = (
                    report.get("status") == "passed"
                    and report.get("hardware_verified") is False
                    and report.get("errors") == []
                    and type(report.get("verified_files")) is int
                    and report["verified_files"] > 0
                )
            else:
                valid = (
                    report.get("status") == "completed"
                    and report.get("output_state") == "OFF"
                    and type(report.get("reading_count")) is int
                    and report["reading_count"] > 0
                )
            if not valid:
                raise ValueError("정상 완료 조건을 충족하지 못했습니다.")
        except (ValueError, TypeError, RecursionError) as exc:
            self._fail(f"{self.stage} 검사 결과 확인 실패: {exc}")
            return
        self.stage_results[self.stage] = report
        if self.stage == "bundle":
            self.bundle_label.setText("1. Bundle 파일 검사 · 완료")
            self.simulation_label.setText("2. Simulation 동작 검사 · 진행 중")
            self.stage = "simulation"
            self._start_stage()
        else:
            self.simulation_label.setText("2. Simulation 동작 검사 · 완료")
            self._open_main_window()

    def _save_report(self):
        directory = self.root / "diagnostics"
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        path = directory / f"startup-check-{stamp}-{os.getpid()}-{uuid.uuid4().hex[:8]}.json"
        report = dict(
            status=self.state,
            stage=self.stage,
            checks=self.stage_results,
            details=self.details.toPlainText()[-32768:],
            hardware_verified=False,
            automatic_output_enable=False,
            scope="portable file integrity and simulated acquisition only",
        )
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8") as stream:
                json.dump(report, stream, ensure_ascii=False, allow_nan=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
        except (OSError, ValueError) as exc:
            self._append_detail("시작 검사 보고서 저장 실패: " + str(exc))
            return False
        self.report_path = path
        return True

    def _fail(self, message):
        self.state = "failed"
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color:#a32e28")
        self._append_detail("[FAIL] " + message)
        self.progress.setRange(0, 2)
        self.progress.setValue(1 if "bundle" in self.stage_results else 0)
        self.retry_button.setEnabled(True)
        self.close_button.setEnabled(True)
        self.close_button.setText("닫기")
        self._save_report()
        self.checks_failed.emit(message)

    def _open_main_window(self):
        self.state = "passed"
        self.progress.setRange(0, 2)
        self.progress.setValue(2)
        self.status_label.setText("시작 검사 완료 · 프로그램을 여는 중…")
        if not self._save_report():
            self._fail("시작 검사 보고서를 저장하지 못했습니다. 폴더의 쓰기 권한을 확인하세요.")
            return
        try:
            self.main_window = self.main_window_factory()
            self.main_window.show()
        except Exception as exc:
            self._fail("프로그램 화면을 열지 못했습니다: " + str(exc))
            return
        self.checks_passed.emit()
        self.close()

    def _kill_process(self):
        process = self.process
        if process is not None and process.state() != QProcess.ProcessState.NotRunning:
            process.kill()

    def closeEvent(self, event: QCloseEvent):
        process = self.process
        if process is not None and process.state() != QProcess.ProcessState.NotRunning:
            event.ignore()
            if self.state != "cancelling":
                self.state = "cancelling"
                self.status_label.setText("시작 검사를 중지하는 중…")
                self.close_button.setEnabled(False)
                self.retry_button.setEnabled(False)
                process.terminate()
                self._kill_timer.start(1500)
            return
        if self.state in {"pending", "running"}:
            self.state = "cancelled"
            self._save_report()
        event.accept()


def run_gui(root: Path) -> int:
    """Open the portable GUI only after both automatic startup checks pass."""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("6517A High Resistance Measurement")
    startup = StartupChecks(root)
    startup.show()
    code = app.exec()
    if code:
        return code
    return 0 if startup.state == "passed" else (130 if startup.state == "cancelled" else 2)
