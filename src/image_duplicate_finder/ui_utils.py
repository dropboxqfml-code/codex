from threading import Event

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import QMessageBox


def warning(parent, title, text):
    box = QMessageBox(parent)
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(title)
    box.setText(text)
    box.exec()


def format_size(size: int) -> str:
    return f"{size / 1024 / 1024:.2f} MB" if size >= 1024 * 1024 else f"{size / 1024:.1f} KB"


class TaskThread(QThread):
    progress = Signal(str, int, int)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, operation, parent=None):
        super().__init__(parent)
        self.operation = operation
        self.cancel = Event()

    def run(self):
        try:
            self.completed.emit(self.operation(self.cancel, self.progress.emit))
        except Exception as error:
            self.failed.emit(f"{type(error).__name__}: {error}")
