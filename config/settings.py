# Path: config/settings.py
# Purpose: Provide typed application configuration models.
# Layer: config.
# Details: Centralizes settings for embedders, vector stores, paths, and batching parameters.

from pathlib import Path

from pydantic import BaseModel, Field


class EmbedderSettings(BaseModel):
    """Settings describing which embedder implementation to use and how to load it."""

    name: str = Field(default="clip", description="Identifier of the embedder implementation.")
    model_name: str = Field(default="ViT-B-32", description="Model variant used by the embedder.")
    device: str = Field(default="cpu", description="Target device for model execution.")
    image_size: int = Field(default=224, description="Default image size for preprocessing pipelines.")


class VectorStoreSettings(BaseModel):
    """Settings controlling vector store selection and persistence paths."""

    name: str = Field(default="faiss", description="Identifier of the vector store implementation.")
    dim: int = Field(default=512, description="Expected embedding dimensionality for the index.")
    index_path: Path = Field(default=Path("storage/indexes/index.faiss"), description="Path to the serialized index file.")


class AppSettings(BaseModel):
    """Top-level application settings shared across services and interfaces."""

    image_folder: Path = Field(
        default=Path(r"C:\Users\prio7\OneDrive\Desktop\tgcat\filtered"),
        description="Root folder containing user images.",
    )
    database_path: Path = Field(default=Path("storage/db/metadata.sqlite3"), description="Path to local metadata database.")
    batch_size: int = Field(default=8, description="Batch size for indexing tasks.")
    embedder: EmbedderSettings = Field(default_factory=EmbedderSettings)
    vector_store: VectorStoreSettings = Field(default_factory=VectorStoreSettings)
    default_strategy: str = Field(default="image_only", description="Fallback search strategy identifier.")
    gui_enabled: bool = Field(default=True, description="Flag indicating if the GUI should be initialized.")
    api_enabled: bool = Field(default=False, description="Flag indicating if the HTTP API should be initialized.")
    log_level: str = Field(default="INFO", description="Verbosity level for application logs.")

    @classmethod
    def from_env(cls) -> "AppSettings":
        """Instantiate settings from environment variables when available."""

        # pydantic BaseModel `.model_validate` will pull from environment via `model_config` only in BaseSettings,
        # so this method allows explicit use of environment overrides in future extensions.
        return cls()


__all__ = ["AppSettings", "EmbedderSettings", "VectorStoreSettings"]
