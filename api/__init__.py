# Path: api/__init__.py
# Purpose: Package initializer for HTTP API layer.
# Layer: api.
# Details: Exposes FastAPI application instance when available.

from .app import create_app

__all__ = ["create_app"]
