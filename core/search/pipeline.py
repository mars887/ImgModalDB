# Path: core/search/pipeline.py
# Purpose: Orchestrate search workflow by combining strategies, embedders, and vector stores.
# Layer: core/search.
# Details: Resolves query embeddings then delegates retrieval to the configured vector store.

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from core.embedders.base import Embedder
from core.models.domain import ImageRecord, SearchQuery, SearchResult
from core.vector_store.base import VectorStore
from .strategies import ImageOnlySearch, ImageTextWeightedFusion, SearchStrategy, TextOnlySearch


class SearchPipeline:
    """High-level service bridging GUI/API layers with embedders and vector stores."""

    def __init__(
        self,
        embedder: Embedder,
        vector_store: VectorStore,
        strategies: Optional[Dict[str, SearchStrategy]] = None,
    ) -> None:
        self.embedder = embedder
        self.vector_store = vector_store
        self.strategies: Dict[str, SearchStrategy] = strategies or {
            ImageOnlySearch.id: ImageOnlySearch(),
            TextOnlySearch.id: TextOnlySearch(),
            ImageTextWeightedFusion.id: ImageTextWeightedFusion(),
        }

    def search(self, query: SearchQuery, k: int = 5, extra: Optional[Dict] = None) -> List[SearchResult]:
        """
        Execute a search query through the configured strategy and vector store.

        External calls:
        - core/search/strategies.py::SearchStrategy.build_query_embedding - constructs the query embedding.
        - core/vector_store/faiss_store.py::FaissStore.search - retrieves nearest neighbors from the index.
        - core/vector_store/faiss_store.py::FaissStore.get_payload - fetches metadata for matched ids.
        """

        strategy = self.strategies.get(query.strategy_id)
        if strategy is None:
            raise ValueError(f"Unknown search strategy: {query.strategy_id}")

        query_embedding = strategy.build_query_embedding(self.embedder, query.image, query.text, extra)

        raw_results = self.vector_store.search(query_embedding.astype(np.float32), k=k, filter=query.filters)
        results: List[SearchResult] = []
        for result_id, score in raw_results:
            payload = self.vector_store.get_payload(result_id)
            image_record = None
            if payload and payload.get("path"):
                image_record = ImageRecord(id=result_id, path=payload.get("path"))
            results.append(SearchResult(id=result_id, score=score, image=image_record, payload=payload))
        return results
