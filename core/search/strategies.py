# Path: core/search/strategies.py
# Purpose: Define search strategies that build query embeddings from user input.
# Layer: core/search.
# Details: Strategies combine image and text embeddings using pluggable embedders.

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Optional, Set

import numpy as np
from PIL import Image

from core.embedders.base import Embedder


class SearchStrategy(ABC):
    """Interface for composing query embeddings from multimodal inputs."""

    id: str
    description: str
    required_modalities: Set[str]

    @abstractmethod
    def build_query_embedding(
        self, embedder: Embedder, image: Optional[Image.Image], text: Optional[str], extra: Optional[Dict] = None
    ) -> np.ndarray:
        """Create a normalized query embedding using the supplied embedder."""


class ImageOnlySearch(SearchStrategy):
    """Strategy that consumes only image input."""

    id = "image_only"
    description = "Encode image queries using the configured embedder."
    required_modalities: Set[str] = {"image"}

    def build_query_embedding(
        self, embedder: Embedder, image: Optional[Image.Image], text: Optional[str], extra: Optional[Dict] = None
    ) -> np.ndarray:
        if image is None:
            raise ValueError("ImageOnlySearch requires an image input.")
        return embedder.embed_image(image)


class TextOnlySearch(SearchStrategy):
    """Strategy that consumes only textual input."""

    id = "text_only"
    description = "Encode text queries using the configured embedder."
    required_modalities: Set[str] = {"text"}

    def build_query_embedding(
        self, embedder: Embedder, image: Optional[Image.Image], text: Optional[str], extra: Optional[Dict] = None
    ) -> np.ndarray:
        if text is None:
            raise ValueError("TextOnlySearch requires a text input.")
        return embedder.embed_text(text)


class ImageTextWeightedFusion(SearchStrategy):
    """Strategy that fuses image and text embeddings with configurable weights."""

    id = "image_text_weighted"
    description = "Blend image and text embeddings using weighted sum before normalization."
    required_modalities: Set[str] = {"image", "text"}

    def build_query_embedding(
        self, embedder: Embedder, image: Optional[Image.Image], text: Optional[str], extra: Optional[Dict] = None
    ) -> np.ndarray:
        if image is None or text is None:
            raise ValueError("ImageTextWeightedFusion requires both image and text inputs.")

        weights = extra or {}
        image_weight = float(weights.get("image_weight", 0.5))
        text_weight = float(weights.get("text_weight", 0.5))
        if image_weight + text_weight == 0:
            raise ValueError("Image and text weights must not sum to zero.")

        image_vector = embedder.embed_image(image)
        text_vector = embedder.embed_text(text)
        blended = (image_weight * image_vector) + (text_weight * text_vector)
        return Embedder._normalize(blended)
