# Path: core/tasks/registry.py
# Purpose: Load and expose global task configuration defined in global_config.json.
# Layer: core/tasks.
# Details: Provides typed accessors for task definitions and workspace root paths.

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


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


@dataclass
class GlobalConfig:
    """Top-level configuration loaded from global_config.json."""

    version: int
    workspaces_dir: Path
    global_index_db: Path
    hash_db: Path
    tasks: Dict[str, TaskDefinition]
    current_workspace_id: Optional[str] = None


class TaskRegistry:
    """Load and expose global task and workspace configuration.

    This registry is the canonical source of:
    - workspace root directory.
    - global index / hash database locations.
    - indexing task definitions.
    """

    def __init__(self, config: GlobalConfig, config_path: Optional[Path] = None) -> None:
        self._config = config
        self._config_path = config_path or Path("global_config.json")

    @classmethod
    def from_file(cls, path: Path | str = "global_config.json") -> "TaskRegistry":
        """Load GlobalConfig and task definitions from a JSON file."""

        cfg_path = Path(path)
        payload = json.loads(cfg_path.read_text(encoding="utf-8"))

        version = int(payload.get("version", 1))
        workspaces_dir = Path(payload.get("workspaces_dir", "workspaces"))
        global_index_db = Path(payload.get("global_index_db", "global_index.sqlite"))
        hash_db = Path(payload.get("hash_db", "image_hashes.sqlite"))
        current_workspace_id = payload.get("current_workspace_id")

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
            current_workspace_id=current_workspace_id,
        )
        return cls(config, config_path=cfg_path)

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

    @property
    def current_workspace_id(self) -> Optional[str]:
        """Return the currently selected workspace id if set."""

        return self._config.current_workspace_id

    def set_current_workspace_id(self, workspace_id: Optional[str]) -> None:
        """Persist the currently selected workspace id back to the config file."""

        self._config.current_workspace_id = workspace_id
        self._save()

    def get_task(self, name: str) -> Optional[TaskDefinition]:
        """Return the definition for a given task name if present."""

        return self._config.tasks.get(name)

    def iter_tasks(self) -> Iterable[TaskDefinition]:
        """Iterate over all registered task definitions."""

        return self._config.tasks.values()

    def _save(self) -> None:
        """Persist the current GlobalConfig back to the JSON file."""

        payload: Dict[str, Any] = {
            "version": self._config.version,
            "workspaces_dir": str(self._config.workspaces_dir),
            "global_index_db": str(self._config.global_index_db),
            "hash_db": str(self._config.hash_db),
        }
        if self._config.current_workspace_id is not None:
            payload["current_workspace_id"] = self._config.current_workspace_id

        tasks_payload: Dict[str, Dict[str, Any]] = {}
        for name, task in self._config.tasks.items():
            task_payload: Dict[str, Any] = {
                "type": task.type,
                "backend": task.backend,
                "mode": task.mode,
            }
            if task.dim is not None:
                task_payload["dim"] = task.dim
            if task.bits is not None:
                task_payload["bits"] = task.bits
            if task.model_ref is not None:
                task_payload["model_ref"] = task.model_ref
            if task.version is not None:
                task_payload["version"] = task.version
            if task.algorithm is not None:
                task_payload["algorithm"] = task.algorithm
            tasks_payload[name] = task_payload

        payload["tasks"] = tasks_payload
        self._config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
