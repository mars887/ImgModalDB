# Path: gui/widgets/image_tile.py
# Purpose: Provide a reusable widget for displaying images across the GUI.
# Layer: gui.
# Details: Wraps QLabel with scaling support so it can be embedded in different panels.

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel


class ImageTile(QLabel):
    """Lightweight image display widget that can be reused across tabs."""

    def __init__(self, parent=None, placeholder_text: str = "image") -> None:
        super().__init__(parent)
        self.placeholder_text = placeholder_text
        self._pixmap: Optional[QPixmap] = None
        self.setText(placeholder_text)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(120, 120)
        self.setStyleSheet(
            "border: 1px solid #4caf50; border-radius: 6px; padding: 4px; text-align: center;"
        )

    def set_image(self, path: Optional[Path] = None, pixmap: Optional[QPixmap] = None) -> None:
        if pixmap is None and path is not None:
            pixmap = QPixmap(str(path))
        self._pixmap = pixmap
        if self._pixmap:
            self.setText("")
        else:
            self.setText(self.placeholder_text)
        self._apply_pixmap()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._apply_pixmap()

    def _apply_pixmap(self) -> None:
        if not self._pixmap or self._pixmap.isNull():
            self.setPixmap(QPixmap())
            return
        scaled = self._pixmap.scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.setPixmap(scaled)

