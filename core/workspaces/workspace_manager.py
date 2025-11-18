# Path: core/workspaces/workspace_manager.py
# Purpose: Manage workspaces and their records persisted to JSON and SQLite.
# Layer: core/workspaces.
# Details: Handles workspace metadata stored in JSON and explicit/implicit records stored in SQLite.

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


@dataclass
class Workspace:
    """Metadata describing a workspace and its configuration."""

    id: str
    name: str
    embeddings_db: Path
    records_db: Path
    auto_refresh: bool = False
    auto_index: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "embeddings_db": str(self.embeddings_db),
            "records_db": str(self.records_db),
            "auto_refresh": self.auto_refresh,
            "auto_index": self.auto_index,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "Workspace":
        return cls(
            id=payload["id"],
            name=payload["name"],
            embeddings_db=Path(payload["embeddings_db"]),
            records_db=Path(payload["records_db"]),
            auto_refresh=payload.get("auto_refresh", False),
            auto_index=payload.get("auto_index", False),
        )


@dataclass
class WorkspaceRecord:
    """Represents a path tracked by a workspace."""

    id: int
    workspace_id: str
    path: Path
    is_explicit: bool
    is_directory: bool


class WorkspaceManager:
    """Handles workspace creation, selection, and record storage."""

    def __init__(self, base_dir: Path | str) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_file = self.base_dir / "workspaces.json"
        self.default_records_db = self.base_dir / "workspace_records.sqlite"
        self._workspaces: dict[str, Workspace] = {}
        self.current_workspace_id: Optional[str] = None
        self._load_workspaces()
        self._ensure_records_schema()

    # Workspace metadata management
    def _load_workspaces(self) -> None:
        if self.workspace_file.exists():
            payload = json.loads(self.workspace_file.read_text(encoding="utf-8"))
            for item in payload.get("workspaces", []):
                workspace = Workspace.from_dict(item)
                self._workspaces[workspace.id] = workspace
            self.current_workspace_id = payload.get("current_workspace_id")
        else:
            self.workspace_file.write_text(json.dumps({"workspaces": []}, indent=2), encoding="utf-8")

    def _persist_workspaces(self) -> None:
        data = {
            "workspaces": [ws.to_dict() for ws in self._workspaces.values()],
            "current_workspace_id": self.current_workspace_id,
        }
        self.workspace_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def list_workspaces(self) -> List[Workspace]:
        return list(self._workspaces.values())

    def get_workspace(self, workspace_id: str) -> Optional[Workspace]:
        return self._workspaces.get(workspace_id)

    def create_workspace(self, name: str) -> Workspace:
        workspace_id = uuid.uuid4().hex
        embeddings_db = self.base_dir / f"{workspace_id}_embeddings.faiss"
        workspace = Workspace(
            id=workspace_id,
            name=name,
            embeddings_db=embeddings_db,
            records_db=self.default_records_db,
        )
        self._workspaces[workspace_id] = workspace
        self.current_workspace_id = workspace_id
        self._persist_workspaces()
        return workspace

    def set_current_workspace(self, workspace_id: str) -> None:
        if workspace_id not in self._workspaces:
            raise KeyError(f"Workspace {workspace_id} not found")
        self.current_workspace_id = workspace_id
        self._persist_workspaces()

    # Record storage
    def _ensure_records_schema(self) -> None:
        with sqlite3.connect(self.default_records_db) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workspace_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    is_explicit INTEGER NOT NULL,
                    is_directory INTEGER NOT NULL,
                    UNIQUE(workspace_id, path)
                )
                """
            )
            conn.commit()

    def _insert_record(
        self, workspace_id: str, path: Path, is_explicit: bool, is_directory: bool
    ) -> None:
        with sqlite3.connect(self.default_records_db) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO records (workspace_id, path, is_explicit, is_directory) VALUES (?, ?, ?, ?)",
                (workspace_id, path.as_posix(), int(is_explicit), int(is_directory)),
            )
            conn.commit()

    def _iter_files(self, directory: Path) -> Iterable[Path]:
        for root, _, files in os.walk(directory):
            for file in files:
                yield Path(root) / file

    def add_path(self, workspace_id: str, path: Path) -> None:
        workspace = self.get_workspace(workspace_id)
        if not workspace:
            raise KeyError(f"Workspace {workspace_id} not found")
        path = path.resolve()
        if path.is_dir():
            self._insert_record(workspace_id, path, is_explicit=True, is_directory=True)
            for file_path in self._iter_files(path):
                self._insert_record(workspace_id, file_path, is_explicit=False, is_directory=False)
        elif path.is_file():
            self._insert_record(workspace_id, path, is_explicit=True, is_directory=False)
        else:
            raise FileNotFoundError(f"Path {path} not found")

    def list_explicit_records(self, workspace_id: str) -> List[WorkspaceRecord]:
        with sqlite3.connect(self.default_records_db) as conn:
            cursor = conn.execute(
                "SELECT id, path, is_directory FROM records WHERE workspace_id = ? AND is_explicit = 1 ORDER BY path",
                (workspace_id,),
            )
            rows = cursor.fetchall()
        return [
            WorkspaceRecord(
                id=row[0],
                workspace_id=workspace_id,
                path=Path(row[1]),
                is_explicit=True,
                is_directory=bool(row[2]),
            )
            for row in rows
        ]

    def remove_explicit_record(self, workspace_id: str, record_id: int) -> None:
        with sqlite3.connect(self.default_records_db) as conn:
            cursor = conn.execute(
                "SELECT path, is_directory FROM records WHERE id = ? AND workspace_id = ? AND is_explicit = 1",
                (record_id, workspace_id),
            )
            row = cursor.fetchone()
            if not row:
                return
            path_str, is_directory = row
            if is_directory:
                like_pattern = f"{path_str.rstrip('/')}/%"
                conn.execute(
                    "DELETE FROM records WHERE workspace_id = ? AND (path = ? OR path LIKE ?)",
                    (workspace_id, path_str, like_pattern),
                )
            else:
                conn.execute(
                    "DELETE FROM records WHERE workspace_id = ? AND path = ?",
                    (workspace_id, path_str),
                )
            conn.commit()

    def list_all_records(self, workspace_id: str) -> List[WorkspaceRecord]:
        with sqlite3.connect(self.default_records_db) as conn:
            cursor = conn.execute(
                "SELECT id, path, is_explicit, is_directory FROM records WHERE workspace_id = ? ORDER BY path",
                (workspace_id,),
            )
            rows = cursor.fetchall()
        return [
            WorkspaceRecord(
                id=row[0],
                workspace_id=workspace_id,
                path=Path(row[1]),
                is_explicit=bool(row[2]),
                is_directory=bool(row[3]),
            )
            for row in rows
        ]

