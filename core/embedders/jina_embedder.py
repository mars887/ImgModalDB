# Path: core/embedders/jina_embedder.py
# Purpose: Provide a stub Jina Embeddings v4 style embedder.
# Layer: core/embedders.
# Details: Uses simple hashing and pooling to emulate multimodal embeddings without heavy dependencies.

from __future__ import annotations

import hashlib
from typing import Optional

import numpy as np
from PIL import Image

from .base import Embedder


class JinaEmbedder(Embedder):
    """Lightweight placeholder mirroring a multimodal Jina embedder."""

    def __init__(self, name: str = "jina", dim: int = 1024) -> None:
        self.name = name
        self.dim = dim

    def embed_image(self, image: Image.Image) -> np.ndarray:
        """Embed images by pooling resized pixel values."""

        resized = image.convert("RGB").resize((24, 24))
        flattened = np.asarray(resized, dtype=np.float32).flatten()
        pooled = np.concatenate([
            [flattened.mean(), flattened.std()],
            np.percentile(flattened, [10, 50, 90]).astype(np.float32),
        ])
        tiled = np.tile(pooled, self.dim // pooled.size + 1)
        return self._normalize(tiled[: self.dim])

    def embed_text(self, text: str) -> np.ndarray:
        """Embed text using SHA-1 hashing for reproducibility."""

        digest = hashlib.sha1(text.encode("utf-8")).digest()
        expanded = np.frombuffer(digest * (self.dim // len(digest) + 1), dtype=np.uint8)
        return self._normalize(expanded[: self.dim].astype(np.float32))

    def embed_multimodal(self, image: Optional[Image.Image] = None, text: Optional[str] = None) -> np.ndarray:
        """Combine modalities with weighted fusion favoring image content."""

        if image is None and text is None:
            raise ValueError("Image or text input must be supplied for multimodal embedding.")

        image_vector = self.embed_image(image) if image is not None else None
        text_vector = self.embed_text(text) if text is not None else None

        if image_vector is None:
            return text_vector  # type: ignore[return-value]
        if text_vector is None:
            return image_vector

        weighted = (0.6 * image_vector) + (0.4 * text_vector)
        return self._normalize(weighted)
