# Path: core/workspaces/__init__.py
# Purpose: Export workspace management utilities for persistence of user workspaces.
# Layer: core/workspaces.
# Details: Provides both legacy WorkspaceManager and the new directory-based WorkspaceManagerV2.

from .workspace_manager import Workspace, WorkspaceRecord, WorkspaceManager, WorkspaceStats, RecordStats
from .manager_v2 import WorkspaceManagerV2, WorkspaceConfig, WorkspaceTaskCoordinator

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
