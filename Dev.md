# ImgModalDB Developer Guide

## Overview and Goals
ImgModalDB is a Python-based desktop application for multimodal search over an image database. The system supports searching by image, by text, and by combined image+text queries, with pluggable embedders, vector stores, and search strategies. The framework is designed for clarity and extensibility, keeping core abstractions stable while allowing concrete implementations to evolve.

## High-Level Architecture
```
root/
├─ config/                # Application settings models
├─ core/
│  ├─ embedders/          # Embedder interfaces and implementations
│  ├─ vector_store/       # Vector store interfaces and implementations
│  ├─ search/             # Search strategies and pipeline orchestration
│  ├─ indexing/           # Dataset scanning, indexing, and captioning helpers
│  ├─ workspaces/         # Workspace metadata and record persistence (JSON + SQLite)
│  └─ models/             # Domain models shared across layers
├─ gui/                   # Desktop GUI scaffolding
├─ api/                   # Optional FastAPI application
├─ scripts/               # CLI utilities for indexing and quick search
├─ storage/               # Data directories (indexes, images, metadata)
└─ Dev.md                 # Developer documentation
```

### Core Abstractions
- **Embedder (`core/embedders/base.py`)**: Interface for generating embeddings from images, text, or multimodal inputs. Concrete implementations include `ClipEmbedder` and `JinaEmbedder`, which currently use deterministic numpy-based projections as placeholders for heavy models.
- **VectorStore (`core/vector_store/base.py`)**: Interface for adding, searching, and persisting embeddings. `FaissStore` provides a numpy-based in-memory implementation mirroring expected FAISS behavior.
- **SearchStrategy (`core/search/strategies.py`)**: Interface for constructing query embeddings. Included strategies cover image-only, text-only, and weighted fusion of image+text signals.
- **SearchPipeline (`core/search/pipeline.py`)**: Orchestrates embedding creation via a chosen strategy and delegates retrieval to the configured vector store, returning structured `SearchResult` objects.
- **Indexing Helpers (`core/indexing/`)**: `ImageScanner` enumerates image files, `IndexBuilder` embeds batches and writes to the vector store, and `CaptionGenerator` stubs caption generation.

### Layering Principles
- GUI/API layers call into the search pipeline rather than accessing embedders or vector stores directly.
- Search strategies rely on embedders for feature generation and delegate retrieval to vector stores.
- Indexing tools reuse embedders and vector stores to generate and persist embeddings in batches.
- Configuration is centralized in `config/settings.py` and should be the single source of truth for paths, defaults, and backend selection.

## Environment Setup
1. Install Python 3.11+.
2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\\Scripts\\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt  # or use `pip install .` if packaged with pyproject
   ```
   Heavy dependencies (OpenCLIP, faiss, PySide6) are listed in `pyproject.toml` but loaded lazily in code.

## Configuration
- `config/settings.py` defines typed settings: embedder selection, vector store parameters, paths, batch sizes, and toggles for GUI/API usage.
- Adjust defaults by instantiating `AppSettings` with overrides or extending `from_env` to load environment variables.

## Running Indexing
Use the provided CLI to scan a folder and build an index:
```bash
python -m scripts.index_images --folder /path/to/images --batch-size 16
```
The script uses `ImageScanner` to collect images, `ClipEmbedder` to generate embeddings, and `FaissStore` to store them. Index files are written to `storage/indexes/`.

## Running a Quick Search
After indexing, run a text search via CLI:
```bash
python -m scripts.quick_search_demo --text "golden retriever" --k 5
```
This loads the stored index, constructs a `SearchPipeline`, and prints the top results.

## GUI Startup
`gui/main_window.py` now builds a PySide6-based window that starts in fullscreen mode and toggles fullscreen/normal with `F11`. Tabs are laid out as `viewer`, `search`, and `Databases`; the viewer uses reusable `ImageTile` widgets from `gui/widgets/image_tile.py` that can be embedded anywhere in the UI. The `Databases` tab uses `DatabasesTab` to manage workspaces and explicit records via a left/right splitter (workspaces on the left, records on the right) and delegates persistence to `WorkspaceManager`.

## API Usage
`api/app.py` exposes a FastAPI application factory. To run the API, supply a configured `SearchPipeline` and mount the app using Uvicorn:
```bash
uvicorn api.app:create_app --factory --reload
```
Endpoints:
- `GET /health`: simple readiness check.
- `POST /search`: accepts JSON with `text`, optional `strategy_id`, and `k` to perform searches through the pipeline.

## Extending the System
- **Add a new Embedder**: Implement `Embedder` in `core/embedders`, ensure lazy model loading, and register it where appropriate (scripts, GUI, or factories). Update this guide with configuration and usage notes.
- **Add a new VectorStore**: Implement `VectorStore` in `core/vector_store`, handling `add`, `search`, `save`, `load`, and `get_payload`. Document persistence formats and configuration toggles here.
- **Add a new SearchStrategy**: Implement `SearchStrategy` in `core/search/strategies.py`, register it in `SearchPipeline`, and describe expected modalities and parameters.
- **Add captioning or tagging**: Extend `CaptionGenerator` to call real models and integrate the output into metadata and payloads stored with embeddings.
- **Manage workspaces and indexing sources**: `core/workspaces/workspace_manager.py` persists workspace metadata to JSON in `storage/db/` and explicit/implicit records to a shared SQLite database. Each workspace gets its own embeddings database path recorded in JSON. The `Databases` tab surfaces creation, selection, and record management.

## Conventions
- All code comments, docstrings, and documentation are written in English; user-facing explanations in this development process should be in Russian.
- Each source file begins with a header comment indicating path, purpose, layer, and key details.
- Cross-layer calls are documented inline or in short external call blocks.
- Avoid heavy model reloads in tight loops; reuse instantiated embedders and vector stores.
- Keep batch operations resumable and memory-efficient for large datasets.

## TODOs and Future Work
- Replace placeholder embedders with actual OpenCLIP and Jina model integrations using lazy loading.
- Swap the numpy-based `FaissStore` with a real FAISS backend and optional remote stores (Qdrant, Milvus).
- Implement rich GUI with background workers for embedding, indexing, and search operations.
- Add regression tests covering embedders, vector stores, and the search pipeline on synthetic data.
