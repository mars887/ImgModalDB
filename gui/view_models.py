# Path: gui/view_models.py
# Purpose: Provide view models mediating between GUI interactions and the search pipeline.
# Layer: gui.
# Details: Encapsulates search requests and presents results suitable for GUI rendering.

from __future__ import annotations

from typing import List

from core.search.pipeline import SearchPipeline
from core.models.domain import SearchQuery, SearchResult


class SearchViewModel:
    """View model encapsulating search orchestration for the GUI."""

    def __init__(self, pipeline: SearchPipeline) -> None:
        self.pipeline = pipeline

    def run_search(self, query: SearchQuery) -> List[SearchResult]:
        """Execute a search through the pipeline and return structured results."""

        # core/search/pipeline.py::SearchPipeline.search - executes the core retrieval logic.
        return self.pipeline.search(query)
