# Path: gui/widgets/image_tile.py
# Purpose: Provide a reusable widget for displaying images across the GUI.
# Layer: gui.
# Details: Wraps QLabel with scaling support so it can be embedded in different panels.

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel


class ImageTile(QLabel):
    """Lightweight image display widget that can be reused across tabs."""

    def __init__(self, parent=None, placeholder_text: str = "image") -> None:
        super().__init__(parent)
        self.setText(placeholder_text)
        self.setScaledContents(True)
        self.setMinimumSize(120, 120)
        self.setStyleSheet(
            "border: 1px solid #4caf50; border-radius: 6px; padding: 4px; text-align: center;"
        )

    def set_image(self, path: Optional[Path] = None, pixmap: Optional[QPixmap] = None) -> None:
        if pixmap is None and path is not None:
            pixmap = QPixmap(str(path))
        if pixmap:
            self.setPixmap(pixmap)
            self.setText("")
        else:
            self.setText("image")
            self.setPixmap(QPixmap())

