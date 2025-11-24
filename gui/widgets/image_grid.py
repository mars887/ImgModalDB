# Path: gui/widgets/image_grid.py
# Purpose: Provide a scroll-friendly grid of ImageTile widgets with adjustable columns.
# Layer: gui.
# Details: Reflows tiles on resize and column changes for reuse across tabs.

from __future__ import annotations

from typing import Dict, Iterable, List, Optional
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt, QThreadPool, QRunnable, Signal, QObject
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QGridLayout, QSizePolicy, QWidget

from core.models.domain import ImageRecord
from .image_tile import ImageTile


class _LoaderSignals(QObject):
    imageLoaded = Signal(str, QImage)


class ImageGrid(QWidget):
    """Grid container that arranges ImageTile widgets."""

    def __init__(self, parent: Optional[QWidget] = None, columns: int = 4) -> None:
        super().__init__(parent)
        self._columns = max(1, columns)
        self._grid = QGridLayout(self)
        self._grid.setSpacing(8)
        self._grid.setContentsMargins(8, 8, 8, 8)
        self._tiles: List[ImageTile] = []
        self._images: List[ImageRecord] = []
        self._tile_size = 140
        self._available_width: Optional[int] = None
        self._path_to_tile: Dict[str, ImageTile] = {}
        self._loader_signals = _LoaderSignals()
        self._loader_signals.imageLoaded.connect(self._on_image_loaded)
        self._thread_pool = QThreadPool.globalInstance()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_columns(self, columns: int) -> None:
        self._columns = max(1, columns)
        self._relayout()

    def set_available_width(self, width: int) -> None:
        """Provide viewport width to avoid horizontal scrollbars."""

        self._available_width = max(0, width)
        self._relayout()

    def set_images(self, images: Iterable[ImageRecord]) -> None:
        self._destroy_tiles()
        self._images = list(images)
        self._tiles = []
        self._path_to_tile.clear()
        self._compute_tile_size()
        for record in self._images:
            tile = ImageTile()
            tile.setFixedSize(self._tile_size, self._tile_size)
            self._tiles.append(tile)
            self._path_to_tile[str(record.path)] = tile
            self._queue_load(record.path)
        self._relayout()

    def append_images(self, images: Iterable[ImageRecord]) -> None:
        new_records = list(images)
        if not new_records:
            return
        start_index = len(self._tiles)
        self._images.extend(new_records)
        self._compute_tile_size()
        for record in new_records:
            tile = ImageTile()
            tile.setFixedSize(self._tile_size, self._tile_size)
            self._tiles.append(tile)
            self._path_to_tile[str(record.path)] = tile
            self._queue_load(record.path)
        for idx in range(start_index, len(self._tiles)):
            row = idx // self._columns
            col = idx % self._columns
            self._grid.addWidget(self._tiles[idx], row, col)
        self._relayout()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._relayout()

    def _compute_tile_size(self) -> None:
        margins = self._grid.contentsMargins()
        spacing = self._grid.spacing()
        available_width = self._available_width or self.width()
        available = available_width - margins.left() - margins.right()
        if self._columns > 0:
            width = (available - spacing * (self._columns - 1)) / float(self._columns)
            self._tile_size = max(32, int(width))

    def _relayout(self) -> None:
        if not self._tiles:
            return
        self._compute_tile_size()
        self._clear_grid_positions()
        for idx, tile in enumerate(self._tiles):
            tile.setFixedSize(self._tile_size, self._tile_size)
            row = idx // self._columns
            col = idx % self._columns
            self._grid.addWidget(tile, row, col)

    def _destroy_tiles(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._tiles = []
        self._path_to_tile.clear()

    def _clear_grid_positions(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                self._grid.removeWidget(widget)

    def _queue_load(self, path: Path) -> None:
        target = self._tile_size
        task = _ImageLoadTask(str(path), target, self._loader_signals)
        self._thread_pool.start(task)

    def _on_image_loaded(self, path_str: str, image: QImage) -> None:
        tile = self._path_to_tile.get(path_str)
        if tile is None:
            return
        if image.isNull():
            tile.set_image()
            return
        pixmap = QPixmap.fromImage(image)
        tile.set_image(pixmap=pixmap)


class _ImageLoadTask(QRunnable):
    """Load and scale images off the UI thread."""

    def __init__(self, path: str, target_size: int, signals: _LoaderSignals) -> None:
        super().__init__()
        self.path = path
        self.target_size = target_size
        self.signals = signals

    def run(self) -> None:
        image = QImage(self.path)
        if not image.isNull() and self.target_size > 0:
            image = image.scaled(
                QSize(self.target_size, self.target_size),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        self.signals.imageLoaded.emit(self.path, image)
