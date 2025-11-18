# Path: core/models/__init__.py
# Purpose: Package initializer for domain model definitions.
# Layer: core/models.
# Details: Exposes dataclasses used across embedding, search, and indexing layers.

from .domain import EmbeddingRecord, ImageRecord, SearchQuery, SearchResult

__all__ = ["EmbeddingRecord", "ImageRecord", "SearchQuery", "SearchResult"]
