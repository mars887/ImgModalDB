# Path: core/embedders/base.py
# Purpose: Define the Embedder interface for image, text, and multimodal embeddings.
# Layer: core/embedders.
# Details: Provides abstract methods to ensure pluggable embedder implementations.

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import numpy as np
from PIL import Image


class Embedder(ABC):
    """Abstract base class for all embedders used in the search pipeline."""

    name: str
    dim: int

    @abstractmethod
    def embed_image(self, image: Image.Image) -> np.ndarray:
        """Return an embedding for a given image."""

    @abstractmethod
    def embed_text(self, text: str) -> np.ndarray:
        """Return an embedding for a given text query."""

    @abstractmethod
    def embed_multimodal(self, image: Optional[Image.Image] = None, text: Optional[str] = None) -> np.ndarray:
        """Return a joint embedding for combined image/text inputs."""

    @staticmethod
    def _normalize(vector: np.ndarray) -> np.ndarray:
        """Normalize embedding vectors to unit length to simplify similarity comparisons."""

        norm = np.linalg.norm(vector)
        if norm == 0:
            return vector.astype(np.float32)
        return (vector / norm).astype(np.float32)
