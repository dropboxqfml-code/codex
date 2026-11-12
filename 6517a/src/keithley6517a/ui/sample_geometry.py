"""Optional rectangular sample dimensions; presentation only, with no instrument I/O."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from ..config import ConfigurationError


class SampleGeometryFields(QWidget):
    """Keep physical L/W/D separate from the explicitly chosen current-flow axis."""

    changed = Signal()

    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self._loading = False
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)
        dimensions = QHBoxLayout()
        dimensions.setSpacing(6)
        self.fields = {}
        for name, label in (
            ("sample_length_mm", "길이 L"),
            ("sample_width_mm", "폭 W"),
            ("sample_depth_mm", "두께 D"),
        ):
            column = QVBoxLayout()
            column.setSpacing(2)
            title = QLabel(label)
            field = QLineEdit()
            field.setMinimumWidth(0)
            field.setPlaceholderText("mm")
            field.setAccessibleName(label + " (mm)")
            field.setToolTip(label + "의 실제 치수(mm). 비워 두면 치수를 미지정으로 저장합니다.")
            field.textChanged.connect(self._notify)
            column.addWidget(title)
            column.addWidget(field)
            dimensions.addLayout(column, 1)
            self.fields[name] = field
        self.length = self.fields["sample_length_mm"]
        self.width = self.fields["sample_width_mm"]
        self.depth = self.fields["sample_depth_mm"]
        root.addLayout(dimensions)
        direction = QHBoxLayout()
        direction.setSpacing(6)
        direction.addWidget(QLabel("전류 방향"))
        self.axis = QComboBox()
        self.axis.addItem("미지정", None)
        for key, label, explanation in (
            ("L", "L · 길이 방향", "단면적 A = W × D, 전류 경로 ℓ = L"),
            ("W", "W · 폭 방향", "단면적 A = L × D, 전류 경로 ℓ = W"),
            ("D", "D · 두께 방향", "단면적 A = L × W, 전류 경로 ℓ = D"),
        ):
            self.axis.addItem(label, key)
            self.axis.setItemData(self.axis.count() - 1, explanation, Qt.ItemDataRole.ToolTipRole)
        self.axis.setToolTip(
            "전류가 흐르는 방향을 선택합니다. L/W/D와 방향이 모두 있어야 비저항을 계산합니다.\n"
            "ρ = R × A / ℓ. 직육면체 시료의 단면 전체에 전극이 접촉하는 경우를 기준으로 합니다."
        )
        self.axis.currentIndexChanged.connect(self._notify)
        direction.addWidget(self.axis, 1)
        root.addLayout(direction)
        self.load_config(config)

    def _notify(self, *_):
        if not self._loading:
            self.changed.emit()

    def load_config(self, config):
        data = config.to_dict() if hasattr(config, "to_dict") else (config or {})
        self._loading = True
        try:
            for name, field in self.fields.items():
                value = data.get(name)
                field.setText("" if value is None else str(value))
            index = self.axis.findData(data.get("current_path_axis"))
            self.axis.setCurrentIndex(max(0, index))
            legacy = data.get("area_m2") is not None and data.get("thickness_m") is not None
            self.setToolTip(
                "기존 설정의 단면적(area_m2)·전류 경로 길이(thickness_m)를 유지합니다. "
                "새 치수를 입력하면 새 치수·전류 방향을 기준으로 합니다."
                if legacy
                else "직육면체의 실제 치수를 mm로 입력하고 전류가 흐르는 축을 선택합니다. "
                "세 치수와 방향이 모두 지정돼야 비저항을 계산합니다."
            )
        finally:
            self._loading = False

    def raw_values(self):
        """Retain incomplete typed metadata while another control resets electrical settings."""
        return {
            **{name: field.text() for name, field in self.fields.items()},
            "current_path_axis": self.axis.currentData(),
        }

    def config_values(self):
        values = {}
        for name, field in self.fields.items():
            token = field.text().strip()
            if not token:
                values[name] = None
                continue
            try:
                value = float(token)
            except (ValueError, OverflowError) as exc:
                raise ConfigurationError(
                    f"{field.accessibleName()}에 0보다 큰 유한한 숫자를 입력하세요."
                ) from exc
            if not math.isfinite(value) or value <= 0:
                raise ConfigurationError(
                    f"{field.accessibleName()}에 0보다 큰 유한한 숫자를 입력하세요."
                )
            values[name] = value
        values["current_path_axis"] = self.axis.currentData()
        return values
