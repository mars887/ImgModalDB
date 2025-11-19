# Path: core/tasks/registry.py
# Purpose: Load and expose global task configuration defined in global_config.json.
# Layer: core/tasks.
# Details: Provides typed accessors for task definitions and workspace root paths.

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional


@dataclass(frozen=True)
class TaskDefinition:
    """Describe a single indexing task configuration.

    Examples include:
    - CLIP image embeddings (vector + faiss backend).
    - Perceptual hashes (hash + sqlite backend).
    - Caption generation (text + sqlite backend).
    """

    name: str
    type: str
    backend: str
    mode: str
    dim: Optional[int] = None
    bits: Optional[int] = None
    model_ref: Optional[str] = None
    version: Optional[str] = None
    algorithm: Optional[str] = None


@dataclass(frozen=True)
class GlobalConfig:
    """Top-level configuration loaded from global_config.json."""

    version: int
    workspaces_dir: Path
    global_index_db: Path
    hash_db: Path
    tasks: Dict[str, TaskDefinition]


class TaskRegistry:
    """Load and expose global task and workspace configuration.

    This registry is the canonical source of:
    - workspace root directory.
    - global index / hash database locations.
    - indexing task definitions.
    """

    def __init__(self, config: GlobalConfig) -> None:
        self._config = config

    @classmethod
    def from_file(cls, path: Path | str = "global_config.json") -> "TaskRegistry":
        """Load GlobalConfig and task definitions from a JSON file."""

        cfg_path = Path(path)
        payload = json.loads(cfg_path.read_text(encoding="utf-8"))

        version = int(payload.get("version", 1))
        workspaces_dir = Path(payload.get("workspaces_dir", "workspaces"))
        global_index_db = Path(payload.get("global_index_db", "global_index.sqlite"))
        hash_db = Path(payload.get("hash_db", "image_hashes.sqlite"))

        raw_tasks = payload.get("tasks") or {}
        tasks: Dict[str, TaskDefinition] = {}
        for name, definition in raw_tasks.items():
            tasks[name] = TaskDefinition(
                name=name,
                type=str(definition.get("type", "")),
                backend=str(definition.get("backend", "")),
                mode=str(definition.get("mode", "")),
                dim=definition.get("dim"),
                bits=definition.get("bits"),
                model_ref=definition.get("model_ref"),
                version=definition.get("version"),
                algorithm=definition.get("algorithm"),
            )

        config = GlobalConfig(
            version=version,
            workspaces_dir=workspaces_dir,
            global_index_db=global_index_db,
            hash_db=hash_db,
            tasks=tasks,
        )
        return cls(config)

    @property
    def config(self) -> GlobalConfig:
        """Return the full global configuration."""

        return self._config

    @property
    def workspaces_root(self) -> Path:
        """Return the root directory where all workspaces are stored."""

        return self._config.workspaces_dir

    @property
    def global_index_path(self) -> Path:
        """Return the path to the global index SQLite database."""

        return self._config.global_index_db

    @property
    def hash_db_path(self) -> Path:
        """Return the path to the global image hashes SQLite database."""

        return self._config.hash_db

    def get_task(self, name: str) -> Optional[TaskDefinition]:
        """Return the definition for a given task name if present."""

        return self._config.tasks.get(name)

    def iter_tasks(self) -> Iterable[TaskDefinition]:
        """Iterate over all registered task definitions."""

        return self._config.tasks.values()

