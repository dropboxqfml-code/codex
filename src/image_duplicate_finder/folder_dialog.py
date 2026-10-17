"""A local directory picker without Windows shell/network/cloud providers."""

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
)

from .privacy import local_path


class LocalFolderDialog(QDialog):
    def __init__(self, parent=None, initial: str = ""):
        super().__init__(parent)
        self.setWindowTitle("로컬 폴더 선택")
        self.resize(620, 480)
        self.selected_path = ""
        self.address = QLineEdit(initial or str(Path.home()))
        self.drives = QComboBox()
        if os.name == "nt":
            for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                path = letter + ":\\"
                try:
                    from .privacy import windows_local_drive

                    windows_local_drive(path)
                    self.drives.addItem(path)
                except ValueError:
                    continue
        else:
            self.drives.addItem("/")
        go = QPushButton("열기")
        up = QPushButton("상위 폴더")
        self.folders = QListWidget()
        self.message = QLabel("네트워크·링크·클라우드 폴더는 표시하지 않습니다.")
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.setWordWrap(True)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.choose = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.choose.setText("이 폴더 선택")
        row = QHBoxLayout()
        row.addWidget(self.drives)
        row.addWidget(up)
        row.addWidget(go)
        layout = QVBoxLayout(self)
        layout.addWidget(self.address)
        layout.addLayout(row)
        layout.addWidget(self.folders)
        layout.addWidget(self.message)
        layout.addWidget(buttons)
        go.clicked.connect(self.open_folder)
        self.address.returnPressed.connect(self.open_folder)
        up.clicked.connect(lambda: self.navigate(str(Path(self.address.text()).parent)))
        self.drives.textActivated.connect(self.navigate)
        self.folders.itemDoubleClicked.connect(
            lambda item: self.navigate(str(Path(self.address.text()) / item.text()))
        )
        buttons.accepted.connect(self.accept_folder)
        buttons.rejected.connect(self.reject)
        self.open_folder()

    def navigate(self, path):
        self.address.setText(path)
        self.open_folder()

    def open_folder(self):
        self.folders.clear()
        self.choose.setEnabled(False)
        try:
            folder = local_path(Path(self.address.text()))
            names = []
            with os.scandir(folder) as entries:
                for entry in entries:
                    try:
                        local_path(Path(entry.path))
                        if entry.is_dir(follow_symlinks=False):
                            names.append(entry.name)
                    except (OSError, ValueError):
                        continue
            self.address.setText(str(folder))
            self.folders.addItems(sorted(names, key=str.casefold))
            self.choose.setEnabled(True)
            self.message.setText("로컬 하위 폴더를 더블 클릭하거나 현재 폴더를 선택하세요.")
        except (OSError, ValueError) as error:
            self.message.setText(str(error))

    def accept_folder(self):
        self.open_folder()
        if self.choose.isEnabled():
            self.selected_path = self.address.text()
            self.accept()
