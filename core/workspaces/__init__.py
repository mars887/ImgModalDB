# Path: core/workspaces/__init__.py
# Purpose: Export workspace management utilities for persistence of user workspaces.
# Layer: core/workspaces.

from .workspace_manager import Workspace, WorkspaceRecord, WorkspaceManager

__all__ = ["Workspace", "WorkspaceRecord", "WorkspaceManager"]
