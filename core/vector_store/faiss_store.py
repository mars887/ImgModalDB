# Path: core/vector_store/faiss_store.py
# Purpose: Provide an in-memory FAISS-like vector store.
# Layer: core/vector_store.
# Details: Implements add/search/save/load using numpy to keep external dependencies optional.

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from .base import VectorStore


class FaissStore(VectorStore):
    """Minimal vector store compatible with the core pipeline.

    This implementation does not depend on the faiss package yet; it uses
    numpy operations for deterministic behavior and simplicity.
    """

    def __init__(self, dim: int, name: str = "faiss") -> None:
        self.dim = dim
        self.name = name
        self._ids: List[int] = []
        self._vectors: Optional[np.ndarray] = None
        self._payloads: Dict[int, Dict] = {}

    def add(self, ids: List[int], vectors: np.ndarray, payloads: Optional[List[Dict]] = None) -> None:
        """Add vectors to the store with optional payload metadata."""

        if vectors.shape[1] != self.dim:
            raise ValueError(f"Vector dimensionality {vectors.shape[1]} does not match store dimension {self.dim}.")

        payloads = payloads or [{} for _ in ids]
        if len(payloads) != len(ids):
            raise ValueError("Payloads length must match ids length.")

        if self._vectors is None:
            self._vectors = vectors.astype(np.float32)
            self._ids = list(ids)
        else:
            self._vectors = np.vstack([self._vectors, vectors.astype(np.float32)])
            self._ids.extend(ids)

        for idx, payload in zip(ids, payloads):
            self._payloads[idx] = payload

    def search(self, query: np.ndarray, k: int, filter: Optional[Dict[str, str]] = None) -> List[Tuple[int, float]]:
        """Return the k nearest neighbors using L2 distance."""

        if self._vectors is None or len(self._ids) == 0:
            return []

        if query.shape[0] != self.dim:
            raise ValueError(f"Query dimensionality {query.shape[0]} does not match store dimension {self.dim}.")

        # root/core/search/pipeline.py::SearchPipeline.search - uses this method to retrieve candidate ids.
        distances = np.linalg.norm(self._vectors - query.reshape(1, -1), axis=1)
        ranked_indices = np.argsort(distances)

        results: List[Tuple[int, float]] = []
        for idx in ranked_indices:
            item_id = self._ids[idx]
            payload = self._payloads.get(item_id)
            if filter and payload:
                if any(payload.get(key) != value for key, value in filter.items()):
                    continue
            results.append((item_id, float(distances[idx])))
            if len(results) >= k:
                break
        return results

    def save(self, path: str) -> None:
        """Persist vectors and payloads to disk as lightweight JSON + numpy arrays."""

        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        np.save(target.with_suffix(".npy"), self._vectors if self._vectors is not None else np.empty((0, self.dim)))
        target.with_suffix(".json").write_text(json.dumps({"ids": self._ids, "payloads": self._payloads}))

    def load(self, path: str) -> None:
        """Load vectors and payloads previously saved by :meth:`save`."""

        target = Path(path)
        vector_path = target.with_suffix(".npy")
        metadata_path = target.with_suffix(".json")
        if not vector_path.exists() or not metadata_path.exists():
            raise FileNotFoundError(f"Missing vector store files for {path}.")

        self._vectors = np.load(vector_path).astype(np.float32)
        metadata = json.loads(metadata_path.read_text())
        self._ids = list(metadata.get("ids", []))
        self._payloads = {int(k): v for k, v in metadata.get("payloads", {}).items()}

    def get_payload(self, id: int) -> Optional[Dict]:
        """Retrieve payload previously associated with the given id."""

        return self._payloads.get(id)
