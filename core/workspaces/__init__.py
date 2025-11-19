# Path: core/workspaces/__init__.py
# Purpose: Export workspace management utilities for persistence of user workspaces.
# Layer: core/workspaces.
# Details: Provides the directory-based WorkspaceManagerV2 and a thin compatibility wrapper.

from __future__ import annotations

from pathlib import Path
from typing import Optional

from core.tasks import TaskRegistry

from .manager_v2 import (
    RecordStats,
    WorkspaceConfig,
    WorkspaceManagerV2,
    WorkspaceRecord,
    WorkspaceStats,
    WorkspaceTaskCoordinator,
)


class WorkspaceManager:
    """Compatibility wrapper exposing a stable interface for GUI and legacy callers.

    Internally delegates all operations to WorkspaceManagerV2 configured from
    global_config.json via TaskRegistry.
    """

    def __init__(self, project_root: Path | str = Path(".")) -> None:
        project_root = Path(project_root)
        registry = TaskRegistry.from_file(project_root / "global_config.json")
        self._registry = registry
        self._manager = WorkspaceManagerV2(registry=registry, project_root=project_root)
        workspace_id = registry.current_workspace_id
        if workspace_id and self._manager.get_workspace(workspace_id) is not None:
            self.current_workspace_id: Optional[str] = workspace_id
        else:
            self.current_workspace_id = None

    # Basic workspace operations
    def list_workspaces(self) -> list[WorkspaceConfig]:
        return self._manager.list_workspaces()

    def get_workspace(self, workspace_id: str) -> Optional[WorkspaceConfig]:
        return self._manager.get_workspace(workspace_id)

    def create_workspace(self, name: str) -> WorkspaceConfig:
        workspace = self._manager.create_workspace(name)
        self.current_workspace_id = workspace.id
        self._registry.set_current_workspace_id(workspace.id)
        return workspace

    def set_current_workspace(self, workspace_id: str) -> None:
        if self._manager.get_workspace(workspace_id) is None:
            raise KeyError(f"Workspace {workspace_id} not found")
        self.current_workspace_id = workspace_id
        self._registry.set_current_workspace_id(workspace_id)

    # Explicit records and images
    def add_path(self, workspace_id: str, path: Path) -> None:
        self._manager.add_path(workspace_id, path)

    def list_explicit_records(self, workspace_id: str) -> list[WorkspaceRecord]:
        return self._manager.list_explicit_records(workspace_id)

    def remove_explicit_record(self, workspace_id: str, record_id: int) -> None:
        self._manager.remove_explicit_record(workspace_id, record_id)

    def set_record_recursive(self, workspace_id: str, record_id: int, is_recursive: bool) -> None:
        self._manager.set_record_recursive(workspace_id, record_id, is_recursive)

    # Statistics
    def get_workspace_stats(self, workspace_id: str) -> WorkspaceStats:
        return self._manager.get_workspace_stats(workspace_id)

    def get_record_stats_for_workspace(self, workspace_id: str) -> dict[int, RecordStats]:
        return self._manager.get_record_stats_for_workspace(workspace_id)

    def rebuild_stats(self, workspace_id: str) -> None:
        self._manager.rebuild_stats(workspace_id)

    def has_stats(self, workspace_id: str) -> bool:
        return self._manager.has_stats(workspace_id)


# Public exports
Workspace = WorkspaceConfig

__all__ = [
    "Workspace",
    "WorkspaceRecord",
    "WorkspaceManager",
    "WorkspaceStats",
    "RecordStats",
    "WorkspaceManagerV2",
    "WorkspaceConfig",
    "WorkspaceTaskCoordinator",
]
