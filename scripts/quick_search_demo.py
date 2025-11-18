# Path: scripts/quick_search_demo.py
# Purpose: Simple CLI to run a search query against a stored index.
# Layer: scripts.
# Details: Demonstrates text search by loading embedder, vector store, and pipeline.

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure project root is on sys.path when running as a script.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import AppSettings
from core.embedders.clip_embedder import ClipEmbedder
from core.models.domain import SearchQuery
from core.search.pipeline import SearchPipeline
from core.vector_store.faiss_store import FaissStore


def main() -> None:
    """Execute a quick search from the command line."""

    parser = argparse.ArgumentParser(description="Run a quick search against ImgModalDB index")
    parser.add_argument("--text", type=str, required=True, help="Text query to search for")
    parser.add_argument("--k", type=int, default=5, help="Number of results to return")
    args = parser.parse_args()

    settings = AppSettings()
    embedder = ClipEmbedder(dim=settings.vector_store.dim)
    vector_store = FaissStore(dim=settings.vector_store.dim)
    vector_store.load(str(settings.vector_store.index_path))

    pipeline = SearchPipeline(embedder=embedder, vector_store=vector_store)
    query = SearchQuery(text=args.text, strategy_id="text_only")
    results = pipeline.search(query, k=args.k)

    for result in results:
        print(f"id={result.id} score={result.score} path={result.payload.get('path') if result.payload else 'n/a'}")


if __name__ == "__main__":
    main()
