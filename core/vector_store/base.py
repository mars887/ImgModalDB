# Path: core/vector_store/base.py
# Purpose: Define the VectorStore interface for indexing and searching embeddings.
# Layer: core/vector_store.
# Details: Provides abstract methods for persistence and payload retrieval.

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np


class VectorStore(ABC):
    """Abstract base class for pluggable vector store backends."""

    name: str
    dim: int

    @abstractmethod
    def add(self, ids: List[int], vectors: np.ndarray, payloads: Optional[List[Dict]] = None) -> None:
        """Add vectors and optional payloads into the index."""

    @abstractmethod
    def search(self, query: np.ndarray, k: int, filter: Optional[Dict[str, str]] = None) -> List[Tuple[int, float]]:
        """Search for nearest neighbors and return (id, distance) pairs."""

    @abstractmethod
    def save(self, path: str) -> None:
        """Persist the index to disk."""

    @abstractmethod
    def load(self, path: str) -> None:
        """Load a serialized index from disk."""

    @abstractmethod
    def get_payload(self, id: int) -> Optional[Dict]:
        """Return stored payload data for the given identifier if available."""
