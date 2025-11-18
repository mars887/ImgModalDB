# Path: gui/__init__.py
# Purpose: Package initializer for GUI layer.
# Layer: gui.
# Details: Provides access to main window and view model stubs.

from .main_window import MainWindow
from .view_models import SearchViewModel

__all__ = ["MainWindow", "SearchViewModel"]
