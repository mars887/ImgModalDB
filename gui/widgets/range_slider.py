# Path: gui/widgets/range_slider.py
# Purpose: Provide a simple dual-handle slider widget for selecting numeric ranges.
# Layer: gui.
# Details: Emits rangeChanged(lower, upper) as handles move; horizontal orientation only.

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPoint, Qt, QRect, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class RangeSlider(QWidget):
    """Lightweight two-handle slider for integer ranges."""

    rangeChanged = Signal(int, int)
    rangeChangeCommitted = Signal(int, int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._minimum = 0
        self._maximum = 100
        self._lower = 0
        self._upper = 100
        self._handle_radius = 7
        self._padding = 12
        self._active_handle: Optional[str] = None
        self.setMinimumHeight(32)

    def setRange(self, minimum: int, maximum: int) -> None:  # noqa: N802 - align with Qt naming
        maximum = max(minimum + 1, maximum)
        self._minimum = minimum
        self._maximum = maximum
        self._lower = max(self._minimum, min(self._lower, self._maximum))
        self._upper = max(self._minimum, min(self._upper, self._maximum))
        if self._lower > self._upper:
            self._lower = self._upper
        self.update()

    def setValues(self, lower: int, upper: int) -> None:  # noqa: N802 - align with Qt naming
        lower = max(self._minimum, min(lower, self._maximum))
        upper = max(self._minimum, min(upper, self._maximum))
        if lower > upper:
            lower, upper = upper, lower
        self._lower = lower
        self._upper = upper
        self.update()
        self.rangeChanged.emit(self._lower, self._upper)

    def values(self) -> tuple[int, int]:
        return self._lower, self._upper

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        groove_rect = QRect(
            self._padding,
            self.height() // 2 - 3,
            self.width() - 2 * self._padding,
            6,
        )

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#cccccc"))
        painter.drawRoundedRect(groove_rect, 3, 3)

        lower_x = self._value_to_pos(self._lower)
        upper_x = self._value_to_pos(self._upper)
        selection_rect = QRect(lower_x, groove_rect.y(), upper_x - lower_x, groove_rect.height())
        painter.setBrush(QColor("#4caf50"))
        painter.drawRoundedRect(selection_rect, 3, 3)

        handle_pen = QPen(QColor("#2f2f2f"))
        handle_pen.setWidth(1)
        painter.setPen(handle_pen)
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QPoint(lower_x, groove_rect.center().y()), self._handle_radius, self._handle_radius)
        painter.drawEllipse(QPoint(upper_x, groove_rect.center().y()), self._handle_radius, self._handle_radius)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        pos = event.position().toPoint().x()
        lower_x = self._value_to_pos(self._lower)
        upper_x = self._value_to_pos(self._upper)
        if abs(pos - lower_x) < abs(pos - upper_x):
            self._active_handle = "lower"
        else:
            self._active_handle = "upper"
        self._move_active_handle(pos)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._active_handle is None:
            return
        pos = event.position().toPoint().x()
        self._move_active_handle(pos)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        self._active_handle = None
        self.rangeChangeCommitted.emit(self._lower, self._upper)
        super().mouseReleaseEvent(event)

    def _move_active_handle(self, x: int) -> None:
        value = self._pos_to_value(x)
        if self._active_handle == "lower":
            self._lower = min(value, self._upper)
        elif self._active_handle == "upper":
            self._upper = max(value, self._lower)
        else:
            return
        self.update()
        self.rangeChanged.emit(self._lower, self._upper)

    def _value_to_pos(self, value: int) -> int:
        span = self._maximum - self._minimum
        if span <= 0:
            return self._padding
        relative = (value - self._minimum) / span
        usable = self.width() - 2 * self._padding
        return int(self._padding + relative * usable)

    def _pos_to_value(self, x: int) -> int:
        usable = self.width() - 2 * self._padding
        if usable <= 0:
            return self._minimum
        relative = (x - self._padding) / usable
        relative = max(0.0, min(1.0, relative))
        value = self._minimum + relative * (self._maximum - self._minimum)
        return int(round(value))
