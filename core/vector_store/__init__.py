# Path: core/vector_store/__init__.py
# Purpose: Package initializer for vector store interfaces and implementations.
# Layer: core/vector_store.
# Details: Exposes the base vector store contract and FAISS-based reference class.

from .base import VectorStore
from .faiss_store import FaissStore

__all__ = ["VectorStore", "FaissStore"]
