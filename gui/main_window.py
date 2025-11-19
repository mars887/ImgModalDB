# Path: gui/main_window.py
# Purpose: Define the main desktop application window with tabbed navigation.
# Layer: gui.
# Details: Implements fullscreen toggle (F11) and Databases tab wired to workspace management.

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel, QTabWidget, QVBoxLayout, QWidget, QHBoxLayout

from core.search.pipeline import SearchPipeline
from core.models.domain import SearchQuery
from core.workspaces import WorkspaceManager
from .databases_tab import DatabasesTab
from .widgets.image_tile import ImageTile
from .view_models import SearchViewModel


class MainWindow(QMainWindow):
    """Main application window that hosts viewer, search, and databases tabs."""

    def __init__(self, pipeline: SearchPipeline, project_root: Path | str = Path(".")) -> None:
        super().__init__()
        self.pipeline = pipeline
        self.view_model = SearchViewModel(pipeline)
        self.workspace_manager = WorkspaceManager(project_root)
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
        layout = QVBoxLayout(container)
        layout.addWidget(QLabel("Viewer"))
        tiles_row = QHBoxLayout()
        for _ in range(3):
            tiles_row.addWidget(ImageTile())
        layout.addLayout(tiles_row)
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


if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)
    pipeline = SearchPipeline(embedder=None, vector_store=None, strategies={})  # type: ignore[arg-type]
    window = MainWindow(pipeline)
    window.show()
    sys.exit(app.exec())

