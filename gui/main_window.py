# Path: gui/main_window.py
# Purpose: Define the main desktop application window scaffold.
# Layer: gui.
# Details: Provides placeholders for PySide6/PyQt6 widgets without heavy imports.

from __future__ import annotations

from core.search.pipeline import SearchPipeline
from core.models.domain import SearchQuery
from .view_models import SearchViewModel


class MainWindow:
    """Minimal stub representing the GUI entrypoint."""

    def __init__(self, pipeline: SearchPipeline) -> None:
        self.pipeline = pipeline
        self.view_model = SearchViewModel(pipeline)
        self.title = "ImgModalDB"

    def perform_search(self, query: SearchQuery):
        """Delegate search requests to the view model."""

        # gui/view_models.py::SearchViewModel.run_search - performs the actual call to SearchPipeline.
        return self.view_model.run_search(query)

    def show(self) -> None:
        """Placeholder for GUI initialization; kept minimal for headless environments."""

        print(f"Launching {self.title} (GUI not implemented yet)")
