# Path: gui/main_window.py
# Purpose: Define the main desktop application window with tabbed navigation.
# Layer: gui.
# Details: Implements fullscreen toggle (F11) and Databases tab wired to workspace management.

from __future__ import annotations

from pathlib import Path
import math

from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QScrollArea,
    QSlider,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.search.pipeline import SearchPipeline
from core.models.domain import SearchQuery
from core.workspaces import WorkspaceManager
from .databases_tab import DatabasesTab
from .widgets.image_grid import ImageGrid
from .widgets.range_slider import RangeSlider
from .view_models import SearchViewModel


class MainWindow(QMainWindow):
    """Main application window that hosts viewer, search, and databases tabs."""

    def __init__(self, pipeline: SearchPipeline, project_root: Path | str = Path(".")) -> None:
        super().__init__()
        self.pipeline = pipeline
        self.view_model = SearchViewModel(pipeline)
        self.workspace_manager = WorkspaceManager(project_root)
        self._mp_scale = 10  # 0.1 MP increments for range slider
        self._page_size = 80
        self._current_offset = 0
        self._has_more = True
        self._is_loading = False
        self.viewer_scroll = None
        self.setWindowTitle("ImgModalDB")
        self.tabs = QTabWidget()
        self._build_tabs()
        self._configure_shortcuts()
        self.setCentralWidget(self.tabs)
        self.showFullScreen()

    def _configure_shortcuts(self) -> None:
        toggle_action = QAction(self)
        toggle_action.setShortcut(QKeySequence(Qt.Key_F11))
        toggle_action.triggered.connect(self.toggle_fullscreen)
        self.addAction(toggle_action)

    def _build_tabs(self) -> None:
        self.tabs.addTab(self._build_viewer_tab(), "viewer")
        self.tabs.addTab(self._build_search_tab(), "search")
        self.tabs.addTab(self._build_databases_tab(), "Databases")

    def _build_viewer_tab(self) -> QWidget:
        container = QWidget()
        root_layout = QHBoxLayout(container)
        splitter = QSplitter(Qt.Horizontal)
        root_layout.addWidget(splitter)

        controls = QWidget()
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(12, 12, 12, 12)
        controls_layout.setSpacing(10)

        controls_layout.addWidget(QLabel("Grid density"))
        self.scale_slider = QSlider(Qt.Horizontal)
        self.scale_slider.setRange(3, 16)
        self.scale_slider.setValue(6)
        self.scale_slider.valueChanged.connect(self._on_scale_changed)
        controls_layout.addWidget(self.scale_slider)
        self.scale_value_label = QLabel("Columns: 6")
        controls_layout.addWidget(self.scale_value_label)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setFrameShadow(QFrame.Sunken)
        controls_layout.addWidget(divider)

        controls_layout.addWidget(QLabel("Filters"))

        self.file_size_label = QLabel("File size (MB)")
        controls_layout.addWidget(self.file_size_label)
        self.file_size_slider = RangeSlider()
        self.file_size_slider.rangeChanged.connect(self._update_filter_labels)
        self.file_size_slider.rangeChangeCommitted.connect(self._on_filters_committed)
        controls_layout.addWidget(self.file_size_slider)

        self.megapixels_label = QLabel("Megapixels")
        controls_layout.addWidget(self.megapixels_label)
        self.megapixels_slider = RangeSlider()
        self.megapixels_slider.rangeChanged.connect(self._update_filter_labels)
        self.megapixels_slider.rangeChangeCommitted.connect(self._on_filters_committed)
        controls_layout.addWidget(self.megapixels_slider)

        controls_layout.addStretch(1)
        splitter.addWidget(controls)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self.viewer_grid = ImageGrid(columns=self.scale_slider.value())
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self.viewer_grid)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.verticalScrollBar().valueChanged.connect(self._on_viewer_scroll)
        scroll_area.viewport().installEventFilter(self)
        self.viewer_scroll = scroll_area
        self.viewer_grid.set_available_width(scroll_area.viewport().width())
        right_layout.addWidget(scroll_area)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)

        self._configure_viewer_controls()
        return container

    def _build_search_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(QLabel("Search panel placeholder"))
        return container

    def _build_databases_tab(self) -> QWidget:
        return DatabasesTab(self.workspace_manager)

    def perform_search(self, query: SearchQuery):
        """Delegate search requests to the view model."""

        # gui/view_models.py::SearchViewModel.run_search - performs the actual call to SearchPipeline.
        return self.view_model.run_search(query)

    def _configure_viewer_controls(self) -> None:
        workspace_id = self.workspace_manager.current_workspace_id
        stats = self.workspace_manager.get_workspace_stats(workspace_id) if workspace_id else None
        internal = stats.internal if stats else None
        self._apply_internal_stats(internal)
        self._reload_viewer_images(reset=True)

    def _apply_internal_stats(self, internal_stats) -> None:
        min_size_mb = 0
        max_size_mb = 100
        if internal_stats and internal_stats.file_size_max is not None:
            min_size_mb = max(0, int((internal_stats.file_size_min or 0) / 1_000_000))
            max_size_mb = max(min_size_mb + 1, int(math.ceil(internal_stats.file_size_max / 1_000_000)))
        self.file_size_slider.setRange(min_size_mb, max_size_mb)
        self.file_size_slider.setValues(min_size_mb, max_size_mb)

        min_mp = 0
        max_mp = 50
        if internal_stats and internal_stats.megapixels_max is not None:
            min_mp = max(0, int(round((internal_stats.megapixels_min or 0) * self._mp_scale)))
            max_mp = max(min_mp + 1, int(math.ceil(internal_stats.megapixels_max * self._mp_scale)))
        self.megapixels_slider.setRange(min_mp, max_mp)
        self.megapixels_slider.setValues(min_mp, max_mp)
        self._update_filter_labels()

    def _reload_viewer_images(self, reset: bool = True) -> None:
        """Load images for the current workspace and apply UI filters.

        External calls:
        - core/workspaces/manager_v2.py::WorkspaceManagerV2.list_images - fetch image metadata with filters applied.
        """

        workspace_id = self.workspace_manager.current_workspace_id
        if not workspace_id:
            self.viewer_grid.set_images([])
            self._has_more = False
            return

        if reset:
            self._current_offset = 0
            self._has_more = True
            self.viewer_grid.set_images([])

        self._load_next_page(reset=reset)

    def _on_scale_changed(self, value: int) -> None:
        self.scale_value_label.setText(f"Columns: {value}")
        self.viewer_grid.set_columns(value)

    def _on_filters_committed(self, *_args) -> None:
        self._reload_viewer_images(reset=True)

    def _update_filter_labels(self, *_args) -> None:
        size_min_mb, size_max_mb = self.file_size_slider.values()
        mp_min_raw, mp_max_raw = self.megapixels_slider.values()
        self.file_size_label.setText(f"File size (MB): {size_min_mb} - {size_max_mb}")
        mp_min = mp_min_raw / self._mp_scale
        mp_max = mp_max_raw / self._mp_scale
        self.megapixels_label.setText(f"Megapixels: {mp_min:.1f} - {mp_max:.1f}")

    def _load_next_page(self, reset: bool = False) -> None:
        if self._is_loading or not self._has_more:
            return
        workspace_id = self.workspace_manager.current_workspace_id
        if not workspace_id:
            self._is_loading = False
            self._has_more = False
            return

        self._is_loading = True
        size_min_mb, size_max_mb = self.file_size_slider.values()
        mp_min_raw, mp_max_raw = self.megapixels_slider.values()

        try:
            images = self.workspace_manager.list_images(
                workspace_id=workspace_id,
                limit=self._page_size,
                offset=self._current_offset,
                min_size_bytes=size_min_mb * 1_000_000,
                max_size_bytes=size_max_mb * 1_000_000,
                min_megapixels=mp_min_raw / self._mp_scale,
                max_megapixels=mp_max_raw / self._mp_scale,
            )

            if reset:
                self.viewer_grid.set_images(images)
            else:
                self.viewer_grid.append_images(images)

            self._current_offset += len(images)
            if len(images) < self._page_size:
                self._has_more = False
        finally:
            self._is_loading = False

    def _on_viewer_scroll(self, value: int) -> None:
        if not self.viewer_scroll:
            return
        scrollbar = self.viewer_scroll.verticalScrollBar()
        if value >= scrollbar.maximum() - 100:
            self._load_next_page(reset=False)

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() == Qt.Key_F11:
            self.toggle_fullscreen()
        else:
            super().keyPressEvent(event)

    def eventFilter(self, watched, event):  # type: ignore[override]
        if (
            self.viewer_scroll
            and watched is self.viewer_scroll.viewport()
            and event.type() == QEvent.Resize
        ):
            self.viewer_grid.set_available_width(event.size().width())
        return super().eventFilter(watched, event)


if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)
    pipeline = SearchPipeline(embedder=None, vector_store=None, strategies={})  # type: ignore[arg-type]
    window = MainWindow(pipeline)
    window.show()
    sys.exit(app.exec())

