# Path: core/indexing/index_builder.py
# Purpose: Build and update embedding indexes from scanned image records.
# Layer: core/indexing.
# Details: Coordinates embedder usage and vector store insertion with progress reporting.

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional

import numpy as np
from PIL import Image
from tqdm import tqdm

from core.embedders.base import Embedder
from core.models.domain import ImageRecord
from core.vector_store.base import VectorStore


class IndexBuilder:
    """Batch process images to populate the configured vector store."""

    def __init__(self, embedder: Embedder, vector_store: VectorStore, batch_size: int = 8) -> None:
        self.embedder = embedder
        self.vector_store = vector_store
        self.batch_size = batch_size

    def build_index(self, images: Iterable[ImageRecord]) -> None:
        """
        Encode images and push embeddings into the vector store.

        External calls:
        - core/embedders/base.py::Embedder.embed_image - create embeddings for each image.
        - core/vector_store/faiss_store.py::FaissStore.add - append vectors to the index backend.
        """

        batch_ids: List[int] = []
        batch_vectors: List[np.ndarray] = []
        batch_payloads: List[dict] = []

        for record in tqdm(list(images), desc="Indexing images", unit="img"):
            image = self._load_image(record.path)
            if image is None:
                continue
            vector = self.embedder.embed_image(image)
            batch_ids.append(record.id)
            batch_vectors.append(vector)
            batch_payloads.append({"path": str(record.path)})

            if len(batch_ids) >= self.batch_size:
                self._flush(batch_ids, batch_vectors, batch_payloads)
                batch_ids, batch_vectors, batch_payloads = [], [], []

        if batch_ids:
            self._flush(batch_ids, batch_vectors, batch_payloads)

    def _flush(self, ids: List[int], vectors: List[np.ndarray], payloads: List[dict]) -> None:
        """Send the accumulated batch to the vector store."""

        matrix = np.vstack(vectors).astype(np.float32)
        self.vector_store.add(ids, matrix, payloads)

    @staticmethod
    def _load_image(path: Path) -> Optional[Image.Image]:
        """Open an image from disk, returning None if loading fails."""

        try:
            return Image.open(path)
        except (OSError, FileNotFoundError):
            return None
