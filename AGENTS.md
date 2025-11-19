0. Project context
- This codebase is a Python-based desktop application for multimodal search over an image database.
- Core concepts:
  - Embedders: components that produce vector representations (CLIP, Jina Embeddings v4, etc.).
  - Vector stores: components that index and search embeddings (FAISS, Qdrant, Milvus, etc.).
  - Search strategies: logic that combines image, text and other signals into a single query embedding.
  - Indexing pipeline: batch jobs that scan image folders, generate embeddings/captions/tags and update indexes.
  - GUI/API layer: user-facing interface that sends queries to the core services.
- Keep these concepts explicit in folder structure, naming and Dev.md.

1. General principles
- Maintain high readability and ease of navigation across the project.
- Prefer explicit, discoverable structure over “magic” and hidden coupling.
- Make core abstractions (Embedder, VectorStore, SearchStrategy, Indexer, GUI/API) very clear and stable.
- Keep comments and documentation concise and focused on intent and contracts, not trivial details.

2. File headers
- Each source file must start with a short header comment:
  - Path from project root.
  - Purpose of the file (high-level responsibility).
  - Layer / role (e.g. core/embedders, core/vector_store, core/search, indexing, gui, api, config).
  - Key details or constraints, if any (caching, performance assumptions, external protocols).
- Example:
  # Path: root/core/embedders/clip_embedder.py
  # Purpose: CLIP-based Embedder implementation.
  # Layer: core/embedders.
  # Details: loads OpenCLIP model once, provides image/text encoding API.

- When a file’s role changes, update its header accordingly.

3. Comments for external functions (cross-file calls)
- When a function uses functions or methods defined in other files, document non-obvious or cross-layer calls.
- Prioritize documenting:
  - Calls that cross architectural boundaries (gui → service, service → vector_store, service → embedder or indexer).
  - Calls into modules with side effects (I/O, networking, background jobs, long-running tasks).
- For a small number of such calls, add a single-line comment directly above each call:
  # root/core/vector_store/faiss_store.py::remove_vectors  - remove entries from FAISS index
  remove_vectors(...)

- If there are many cross-file calls, add a compact “External calls” block at the start of the function:
  def process_query(...):
      """
      External calls:
      - root/core/embedders/clip_embedder.py::encode_image   - encode user image into vector
      - root/core/search/strategies.py::build_query_vector   - combine image/text into query embedding
      - root/core/vector_store/faiss_store.py::search        - run ANN search in FAISS index
      """
      ...

- Always include:
  - Full relative path to the file.
  - Function name.
  - One-line description of its purpose.
- If the purpose is unclear, make a reasonable guess and mark it as TODO or (?) for later clarification.

4. Dev.md (developer documentation)
- A Dev.md file must exist at the project root and be read before starting development.
- Dev.md should describe at least:
  - Project overview and goals (multimodal search over images, supported models and vector stores).
  - High-level structure: key packages and their responsibilities (core, embedders, vector_store, search, indexing, gui/api, config, tests).
  - Core abstractions and extension points:
    - How to add a new Embedder.
    - How to add a new VectorStore implementation.
    - How to add a new SearchStrategy.
    - How to add new indexing jobs (caption/tag generation, reindexing).
  - Conventions (naming, logging, error handling, comments, configuration).
  - How-to recipes: adding CLI args, new GUI actions, new background jobs, new search strategies.
  - Important TODOs or architectural constraints (e.g. max dataset size, GPU/CPU assumptions).

- Keep Dev.md in sync with the actual project:
  - When structure, responsibilities or conventions change, update Dev.md automatically.
  - When adding a new embedder, vector store or search strategy, document it in the relevant section.
  - Do not ask for permission to update; apply changes directly when they are clear and incremental.
  - Ask clarifying questions only if the change is large, ambiguous, or may conflict with existing design decisions.

5. Configuration and environments
- Centralize configuration (paths, model names, vector store type, search strategy, batch sizes) in a config module/file (e.g. config.py or config.yaml).
- Do not hardcode filesystem paths, model names, magic thresholds or index file names inside business logic.
- When adding new parameters:
  - Update the config schema and defaults.
  - Ensure Dev.md and any relevant docstrings reflect the configuration changes.
- Clearly separate development/test/production-like settings when needed (e.g. small test dataset vs large real dataset).

6. Navigation, layering and cross-references
- Keep clear layering:
  - GUI/API layer: UI events, user input, simple validation, calling services.
  - Core services/search layer: query building, routing to embedders and vector stores.
  - Embedders layer: model loading, image/text/multimodal encoding.
  - Vector store layer: indexing and ANN search.
  - Indexing and batch jobs: dataset scanning, embedding generation, captions/tags generation.
- Do not import heavy core logic directly into GUI files; instead, call well-defined service functions.
- When modifying a widely used function or class, consider where it is used and whether behavior changes might affect other modules.
- When appropriate, briefly explain in comments or docstrings:
  - Which layer a given file belongs to.
  - Which neighboring modules are logically related or dependent.

7. Performance and scaling assumptions
- Assume the image dataset may contain hundreds of thousands or millions of entries.
- Avoid O(N^2) algorithms on the full dataset unless explicitly marked as experimental and documented.
- Reuse loaded models and vector indexes; never reload large models in hot paths or tight loops.
- For batch operations (indexing, reindexing), prefer streaming/batch processing instead of loading everything into memory at once.
- When implementing new features that may impact performance (e.g. new search strategies, reranking passes), document their complexity and intended usage in Dev.md.

8. Consistency and reminders
- When adding or changing CLI/args or GUI actions:
  - Ensure help/usage, Dev.md and any relevant docstrings are consistent.
- When adding new modules or layers:
  - Ensure they are integrated into Dev.md’s structure section.
- When changing function/class signatures or behavior:
  - Check that comments, docstrings and Dev.md references remain accurate.
- When adding new embedders, vector stores or search strategies:
  - Register them in a central registry/factory if one exists.
  - Add short examples of how to use them (e.g. in Dev.md or tests).

9. Clarifications
- Ask clarifying questions only when necessary:
  - When behavior cannot be inferred from existing code, naming, or documentation.
  - When multiple plausible interpretations exist and the choice affects architecture or APIs.
- Prefer reasonable, documented assumptions (with TODO markers) over excessive questioning.

10. Testing and validation
- When implementing new core components (Embedder, VectorStore, SearchStrategy, Indexer), add at least basic tests or scripts that:
  - Verify that embeddings have expected shapes and types.
  - Verify that indexing and search run end-to-end on a small sample dataset.
- When adding new behavior in the search pipeline, consider adding small regression tests or reproducible “example queries”.
- Keep tests fast and easy to run locally.

11. Language rules
- All comments, docstrings and documentation inside the codebase (including Dev.md) must be written in English.
- Answers provided to the user during development must be in Russian, unless explicitly requested otherwise.
