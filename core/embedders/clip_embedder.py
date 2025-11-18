# Path: core/embedders/clip_embedder.py
# Purpose: Provide a lightweight CLIP-style embedder implementation.
# Layer: core/embedders.
# Details: Uses deterministic numpy-based projections as a placeholder for OpenCLIP loading.

from __future__ import annotations

import hashlib
from typing import Optional

import numpy as np
from PIL import Image

from .base import Embedder


class ClipEmbedder(Embedder):
    """Stub implementation that mimics CLIP behavior with lightweight operations."""

    def __init__(self, model_name: str = "ViT-B-32", device: str = "cpu", dim: int = 512) -> None:
        self.model_name = model_name
        self.device = device
        self.dim = dim
        self.name = "clip"

    def embed_image(self, image: Image.Image) -> np.ndarray:
        """Generate a deterministic image embedding based on pixel statistics."""

        resized = image.convert("RGB").resize((32, 32))
        vector = np.asarray(resized, dtype=np.float32).flatten()
        pooled = np.concatenate([
            [vector.mean(), vector.std()],
            np.percentile(vector, [25, 50, 75]).astype(np.float32),
        ])
        padded = np.pad(pooled, (0, max(0, self.dim - pooled.size)), mode="wrap")
        return self._normalize(padded[: self.dim])

    def embed_text(self, text: str) -> np.ndarray:
        """Generate a deterministic text embedding based on hashing."""

        hash_bytes = hashlib.sha256(text.encode("utf-8")).digest()
        expanded = np.frombuffer(hash_bytes * (self.dim // len(hash_bytes) + 1), dtype=np.uint8)
        vector = expanded[: self.dim].astype(np.float32)
        return self._normalize(vector)

    def embed_multimodal(self, image: Optional[Image.Image] = None, text: Optional[str] = None) -> np.ndarray:
        """Combine image and text signals using average pooling."""

        image_vector = self.embed_image(image) if image is not None else None
        text_vector = self.embed_text(text) if text is not None else None

        if image_vector is None and text_vector is None:
            raise ValueError("At least one modality must be provided for multimodal embedding.")

        if image_vector is not None and text_vector is not None:
            return self._normalize((image_vector + text_vector) / 2)

        return image_vector if image_vector is not None else text_vector
