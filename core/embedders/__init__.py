# Path: core/embedders/__init__.py
# Purpose: Package initializer for embedder implementations and interfaces.
# Layer: core/embedders.
# Details: Exposes base interface and reference implementations.

from .base import Embedder
from .clip_embedder import ClipEmbedder
from .jina_embedder import JinaEmbedder

__all__ = ["Embedder", "ClipEmbedder", "JinaEmbedder"]
