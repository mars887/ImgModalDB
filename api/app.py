# Path: api/app.py
# Purpose: Expose a FastAPI application for multimodal search operations.
# Layer: api.
# Details: Provides health checks and a minimal search endpoint delegating to the core pipeline.

from __future__ import annotations

from typing import Any, Dict, Optional

from core.models.domain import SearchQuery
from core.search.pipeline import SearchPipeline


def create_app(pipeline: Optional[SearchPipeline] = None):  # type: ignore[override]
    """Create a FastAPI app instance configured with the provided search pipeline."""

    from fastapi import FastAPI, HTTPException

    app = FastAPI(title="ImgModalDB API", version="0.1.0")

    @app.get("/health")
    def health() -> Dict[str, str]:
        """Return a simple health status payload."""

        return {"status": "ok"}

    @app.post("/search")
    def search(payload: Dict[str, Any]):
        """Run a search query using the configured pipeline."""

        if pipeline is None:
            raise HTTPException(status_code=500, detail="Search pipeline is not configured.")

        query = SearchQuery(text=payload.get("text"), strategy_id=payload.get("strategy_id", "text_only"))
        results = pipeline.search(query, k=int(payload.get("k", 5)))
        return {"results": [result.__dict__ for result in results]}

    return app
