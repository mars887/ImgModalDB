# Path: core/models/domain.py
# Purpose: Define domain models shared across embedding, search, and indexing workflows.
# Layer: core/models.
# Details: Lightweight dataclasses simplify serialization between GUI, API, and core services.

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image
import numpy as np


@dataclass
class ImageRecord:
    """Metadata describing a stored image and its annotations."""

    id: int
    path: Path
    width: Optional[int] = None
    height: Optional[int] = None
    tags: List[str] = field(default_factory=list)
    caption: Optional[str] = None


@dataclass
class EmbeddingRecord:
    """Link between an image and its embedding stored in a vector index."""

    id: int
    image_id: int
    embedder_name: str
    vector_store: str
    dim: int


@dataclass
class SearchQuery:
    """User-facing query structure supplied by GUI/API layers."""

    image: Optional[Image.Image] = None
    text: Optional[str] = None
    strategy_id: str = "image_only"
    filters: Dict[str, str] | None = None


@dataclass
class SearchResult:
    """Search result item combining index scores with image metadata."""

    id: int
    score: float
    image: Optional[ImageRecord] = None
    payload: Optional[Dict[str, str]] = None
    embedding: Optional[np.ndarray] = None
