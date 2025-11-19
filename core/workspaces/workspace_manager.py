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
from typing import Dict, Iterable, List, Optional, Tuple

from PIL import Image

from core.indexing.scanner import SUPPORTED_EXTENSIONS as SUPPORTED_IMAGE_EXTENSIONS


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
    is_recursive: bool = False


@dataclass
class WorkspaceStats:
    """Aggregated statistics for a workspace and its image coverage."""

    total_records: int
    total_images: int
    indexed_images: int


@dataclass
class RecordStats:
    """Per-record statistics describing image counts and index coverage."""

    total_images: int
    indexed_images: int
    format: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    size_bytes: Optional[int] = None


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
        self._workspace_stats_cache: Dict[str, WorkspaceStats] = {}
        self._record_stats_cache: Dict[str, Dict[int, RecordStats]] = {}
        for workspace_id in self._workspaces:
            self._load_stats_for_workspace(workspace_id)

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
                    is_recursive INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(workspace_id, path)
                )
                """
            )
            # Ensure new columns are present for existing databases.
            cursor = conn.execute("PRAGMA table_info(records)")
            columns = [row[1] for row in cursor.fetchall()]
            if "is_recursive" not in columns:
                conn.execute("ALTER TABLE records ADD COLUMN is_recursive INTEGER NOT NULL DEFAULT 0")
            conn.commit()

    def _insert_record(
        self,
        workspace_id: str,
        path: Path,
        is_explicit: bool,
        is_directory: bool,
        is_recursive: bool = False,
    ) -> None:
        with sqlite3.connect(self.default_records_db) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO records (workspace_id, path, is_explicit, is_directory, is_recursive)
                VALUES (?, ?, ?, ?, ?)
                """,
                (workspace_id, path.as_posix(), int(is_explicit), int(is_directory), int(is_recursive)),
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
            self._insert_record(workspace_id, path, is_explicit=True, is_directory=True, is_recursive=False)
            for file_path in self._iter_files(path):
                self._insert_record(workspace_id, file_path, is_explicit=False, is_directory=False, is_recursive=False)
        elif path.is_file():
            self._insert_record(workspace_id, path, is_explicit=True, is_directory=False, is_recursive=False)
        else:
            raise FileNotFoundError(f"Path {path} not found")

    def list_explicit_records(self, workspace_id: str) -> List[WorkspaceRecord]:
        with sqlite3.connect(self.default_records_db) as conn:
            cursor = conn.execute(
                """
                SELECT id, path, is_directory, is_recursive
                FROM records
                WHERE workspace_id = ? AND is_explicit = 1
                ORDER BY path
                """,
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
                is_recursive=bool(row[3]),
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
                """
                SELECT id, path, is_explicit, is_directory, is_recursive
                FROM records
                WHERE workspace_id = ?
                ORDER BY path
                """,
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
                is_recursive=bool(row[4]),
            )
            for row in rows
        ]

    def _stats_file_path(self, workspace_id: str) -> Path:
        """Return the JSON file path used to persist cached statistics for a workspace."""

        return self.base_dir / f"{workspace_id}_stats.json"

    def _load_stats_for_workspace(self, workspace_id: str) -> None:
        """Load previously computed statistics for a workspace from its JSON file, if present."""

        stats_path = self._stats_file_path(workspace_id)
        if not stats_path.exists():
            return

        try:
            payload = json.loads(stats_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return

        workspace_stats = WorkspaceStats(
            total_records=int(payload.get("total_records", 0)),
            total_images=int(payload.get("total_images", 0)),
            indexed_images=int(payload.get("indexed_images", 0)),
        )
        records_payload = payload.get("records") or {}
        record_stats: Dict[int, RecordStats] = {}
        for record_id_str, stats_item in records_payload.items():
            try:
                record_id = int(record_id_str)
            except (ValueError, TypeError):
                continue
            record_stats[record_id] = RecordStats(
                total_images=int(stats_item.get("total_images", 0)),
                indexed_images=int(stats_item.get("indexed_images", 0)),
                format=stats_item.get("format"),
                width=stats_item.get("width"),
                height=stats_item.get("height"),
                size_bytes=stats_item.get("size_bytes"),
            )
        self._workspace_stats_cache[workspace_id] = workspace_stats
        self._record_stats_cache[workspace_id] = record_stats

    def _persist_stats_for_workspace(
        self,
        workspace_id: str,
        workspace_stats: WorkspaceStats,
        record_stats: Dict[int, RecordStats],
    ) -> None:
        """Persist aggregated and per-record statistics to a JSON file."""

        payload = {
            "total_records": workspace_stats.total_records,
            "total_images": workspace_stats.total_images,
            "indexed_images": workspace_stats.indexed_images,
            "records": {
                str(record_id): {
                    "total_images": stats.total_images,
                    "indexed_images": stats.indexed_images,
                    "format": stats.format,
                    "width": stats.width,
                    "height": stats.height,
                    "size_bytes": stats.size_bytes,
                }
                for record_id, stats in record_stats.items()
            },
        }
        stats_path = self._stats_file_path(workspace_id)
        stats_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def set_record_recursive(self, workspace_id: str, record_id: int, is_recursive: bool) -> None:
        """Update the recursion flag for an explicit directory record.

        Currently this flag is persisted for future indexing logic and does not
        change record storage behavior yet.
        """

        with sqlite3.connect(self.default_records_db) as conn:
            conn.execute(
                """
                UPDATE records
                SET is_recursive = ?
                WHERE workspace_id = ? AND id = ? AND is_explicit = 1 AND is_directory = 1
                """,
                (int(is_recursive), workspace_id, record_id),
            )
            conn.commit()

    def _load_indexed_image_paths(self, workspace_id: str) -> List[Path]:
        """Return a list of image paths that have embeddings stored for this workspace.

        This helper inspects the workspace's embeddings_db JSON sidecar file,
        which is written by FaissStore.save and stores payloads keyed by id.
        """

        workspace = self.get_workspace(workspace_id)
        if not workspace:
            return []

        metadata_path = workspace.embeddings_db.with_suffix(".json")
        if not metadata_path.exists():
            return []

        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []

        indexed_paths: List[Path] = []
        for value in (payload.get("payloads") or {}).values():
            if not isinstance(value, dict):
                continue
            path_str = value.get("path")
            if not path_str:
                continue
            try:
                indexed_paths.append(Path(path_str).resolve())
            except OSError:
                continue
        return indexed_paths

    def _compute_stats(
        self, workspace_id: str
    ) -> Tuple[WorkspaceStats, Dict[int, RecordStats]]:
        """Compute workspace-level and per-record statistics for GUI display."""

        all_records = self.list_all_records(workspace_id)
        explicit_records = self.list_explicit_records(workspace_id)
        indexed_paths = set(self._load_indexed_image_paths(workspace_id))

        total_records = len(all_records)
        workspace_total_images = 0
        workspace_indexed_images = 0

        record_stats: Dict[int, RecordStats] = {}

        explicit_dirs = [record for record in explicit_records if record.is_directory]
        explicit_files = [record for record in explicit_records if not record.is_directory]
        dir_stats: Dict[int, RecordStats] = {
            record.id: RecordStats(total_images=0, indexed_images=0) for record in explicit_dirs
        }

        # Explicit file records: at most one image each.
        for record in explicit_files:
            total = 0
            indexed = 0
            fmt: Optional[str] = None
            width: Optional[int] = None
            height: Optional[int] = None
            size_bytes: Optional[int] = None

            try:
                size_bytes = record.path.stat().st_size
            except OSError:
                size_bytes = None

            suffix = record.path.suffix.lower()
            if suffix in SUPPORTED_IMAGE_EXTENSIONS:
                total = 1
                workspace_total_images += 1
                if record.path.resolve() in indexed_paths:
                    indexed = 1
                    workspace_indexed_images += 1
                try:
                    with Image.open(record.path) as image:
                        fmt = image.format or (suffix.lstrip(".").upper() or "unknown")
                        width, height = image.size
                except (OSError, FileNotFoundError):
                    fmt = suffix.lstrip(".").upper() or "unknown"
                    width = None
                    height = None
            else:
                if suffix:
                    fmt = suffix.lstrip(".").upper()

            record_stats[record.id] = RecordStats(
                total_images=total,
                indexed_images=indexed,
                format=fmt,
                width=width,
                height=height,
                size_bytes=size_bytes,
            )

        # Implicit image records contribute to workspace totals and folder stats.
        for record in all_records:
            if record.is_directory:
                continue
            if record.id in record_stats:
                # Explicit files are already handled above.
                continue
            if record.path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
                continue
            workspace_total_images += 1
            is_indexed = record.path.resolve() in indexed_paths
            if is_indexed:
                workspace_indexed_images += 1

            for dir_record in explicit_dirs:
                try:
                    record.path.relative_to(dir_record.path)
                except ValueError:
                    continue
                stats = dir_stats[dir_record.id]
                stats.total_images += 1
                if is_indexed:
                    stats.indexed_images += 1

        # Merge directory stats into the per-record dictionary.
        for dir_id, stats in dir_stats.items():
            record_stats[dir_id] = stats

        workspace_stats = WorkspaceStats(
            total_records=total_records,
            total_images=workspace_total_images,
            indexed_images=workspace_indexed_images,
        )
        return workspace_stats, record_stats

    def get_workspace_stats(self, workspace_id: str) -> WorkspaceStats:
        """Return aggregated statistics for a workspace using cached data when available."""

        stats = self._workspace_stats_cache.get(workspace_id)
        if stats is not None:
            return stats
        return WorkspaceStats(total_records=0, total_images=0, indexed_images=0)

    def get_record_stats_for_workspace(self, workspace_id: str) -> Dict[int, RecordStats]:
        """Return per-record statistics for the given workspace keyed by record id."""

        return self._record_stats_cache.get(workspace_id, {})

    def rebuild_stats(self, workspace_id: str) -> None:
        """Recompute statistics for the given workspace and persist them to disk."""

        workspace_stats, record_stats = self._compute_stats(workspace_id)
        self._workspace_stats_cache[workspace_id] = workspace_stats
        self._record_stats_cache[workspace_id] = record_stats
        self._persist_stats_for_workspace(workspace_id, workspace_stats, record_stats)

    def has_stats(self, workspace_id: str) -> bool:
        """Return True if cached statistics exist for the given workspace."""

        if workspace_id in self._workspace_stats_cache:
            return True
        return self._stats_file_path(workspace_id).exists()

