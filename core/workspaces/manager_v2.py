# Path: core/workspaces/manager_v2.py
# Purpose: Provide a workspace manager using the new per-workspace directory layout and global registries.
# Layer: core/workspaces.
# Details: Each workspace lives under workspaces/{name}_{id}/ with its own config and SQLite databases.

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import hashlib
import os

from PIL import Image

from core.indexing.scanner import SUPPORTED_EXTENSIONS
from core.tasks import GlobalConfig, TaskContext, TaskCoordinator, TaskRegistry


@dataclass
class WorkspaceConfig:
    """Configuration persisted in workspaces/{workspace_name}_{workspace_id}/config.json."""

    id: str
    name: str
    tasks: List[str]
    auto_refresh: bool = False
    auto_index: bool = False
    task_overrides: Dict[str, Dict] | None = None

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "tasks": list(self.tasks),
            "auto_refresh": self.auto_refresh,
            "auto_index": self.auto_index,
            "task_overrides": self.task_overrides or {},
        }

    @classmethod
    def from_dict(cls, payload: Dict) -> "WorkspaceConfig":
        return cls(
            id=str(payload["id"]),
            name=str(payload["name"]),
            tasks=list(payload.get("tasks", [])),
            auto_refresh=bool(payload.get("auto_refresh", False)),
            auto_index=bool(payload.get("auto_index", False)),
            task_overrides=payload.get("task_overrides") or {},
        )


@dataclass
class WorkspaceRecord:
    """Explicit record entry stored in records.sqlite for a workspace."""

    id: int
    path: Path
    is_directory: bool
    is_recursive: bool = False


@dataclass
class WorkspaceStats:
    """Aggregated statistics for a workspace."""

    total_records: int
    total_images: int
    indexed_images: int


@dataclass
class RecordStats:
    """Per-record statistics describing image and index coverage."""

    total_images: int
    indexed_images: int
    format: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    size_bytes: Optional[int] = None


class WorkspaceManagerV2:
    """Manage workspaces using the new directory-based layout and global configuration.

    Responsibilities:
    - Load global configuration from TaskRegistry.
    - Discover existing workspaces under workspaces_root.
    - Create new workspaces with config.json, records.sqlite, images.sqlite, and index/ directory.
    - Provide basic listing and lookup APIs for GUI/CLI layers.
    """

    def __init__(self, registry: TaskRegistry, project_root: Path | str = Path(".")) -> None:
        self.registry = registry
        self.project_root = Path(project_root)
        self.global_config: GlobalConfig = registry.config
        self.workspaces_root: Path = (self.project_root / self.global_config.workspaces_dir).resolve()
        self.workspaces_root.mkdir(parents=True, exist_ok=True)
        self._workspaces: Dict[str, WorkspaceConfig] = {}
        self._load_workspaces()
        self._ensure_global_dbs()

    # Public helpers
    def workspace_dir_for(self, workspace_id: str) -> Path:
        """Return the resolved directory for a given workspace identifier."""

        return self._workspace_dir(workspace_id)

    # Workspace discovery and metadata
    def _load_workspaces(self) -> None:
        """Scan the workspaces directory for config.json files and load workspace configs."""

        self._workspaces.clear()
        if not self.workspaces_root.exists():
            return

        for entry in self.workspaces_root.iterdir():
            if not entry.is_dir():
                continue
            cfg_path = entry / "config.json"
            if not cfg_path.exists():
                continue
            try:
                payload = json.loads(cfg_path.read_text(encoding="utf-8"))
                cfg = WorkspaceConfig.from_dict(payload)
                self._workspaces[cfg.id] = cfg
            except (json.JSONDecodeError, KeyError):
                continue

    def list_workspaces(self) -> List[WorkspaceConfig]:
        """Return all known workspaces."""

        return list(self._workspaces.values())

    def get_workspace(self, workspace_id: str) -> Optional[WorkspaceConfig]:
        """Return workspace configuration by id if present."""

        return self._workspaces.get(workspace_id)

    # Workspace creation
    def create_workspace(self, name: str, tasks: Optional[List[str]] = None) -> WorkspaceConfig:
        """Create a new workspace directory with initial config and empty databases."""

        workspace_id = uuid.uuid4().hex
        safe_name = name.replace(" ", "_")
        directory = self.workspaces_root / f"{safe_name}_{workspace_id}"
        directory.mkdir(parents=True, exist_ok=True)

        index_dir = directory / "index"
        index_dir.mkdir(exist_ok=True)

        tasks = tasks or list(self.registry.config.tasks.keys())
        cfg = WorkspaceConfig(id=workspace_id, name=name, tasks=tasks)
        self._write_workspace_config(directory, cfg)

        # Initial per-workspace databases
        self._ensure_records_db(directory)
        self._ensure_images_db(directory)

        self._workspaces[cfg.id] = cfg
        return cfg

    # Filesystem helpers
    def _workspace_dir(self, workspace_id: str) -> Path:
        """Return the directory path for a given workspace id."""

        cfg = self.get_workspace(workspace_id)
        if not cfg:
            raise KeyError(f"Workspace {workspace_id} not found")
        safe_name = cfg.name.replace(" ", "_")
        return (self.workspaces_root / f"{safe_name}_{workspace_id}").resolve()

    def _write_workspace_config(self, directory: Path, cfg: WorkspaceConfig) -> None:
        """Persist workspace configuration to config.json in the given directory."""

        cfg_path = directory / "config.json"
        cfg_path.write_text(json.dumps(cfg.to_dict(), indent=2), encoding="utf-8")

    # Global databases (status and hashes)
    def _ensure_global_dbs(self) -> None:
        """Ensure global_index.sqlite and image_hashes.sqlite exist with expected schemas."""

        self._ensure_global_index_db()
        self._ensure_hash_db()

    def _ensure_global_index_db(self) -> None:
        """Create or migrate the global index database.

        Tracks which file in which workspace has been processed by which task.
        """

        db_path = (self.project_root / self.global_config.global_index_db).resolve()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS global_index (
                    path TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    task_name TEXT NOT NULL,
                    last_indexed_hash TEXT,
                    last_indexed_at INTEGER,
                    PRIMARY KEY (path, workspace_id, task_name)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_global_index_hash ON global_index(last_indexed_hash)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_global_index_path ON global_index(path)")
            conn.commit()

    def _ensure_hash_db(self) -> None:
        """Create or migrate the global image hashes database.

        Stores file content hashes and lightweight file metadata used to detect changes.
        """

        db_path = (self.project_root / self.global_config.hash_db).resolve()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS image_hashes (
                    path TEXT PRIMARY KEY,
                    file_hash TEXT NOT NULL,
                    file_size INTEGER,
                    mtime INTEGER
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_image_hashes_hash ON image_hashes(file_hash)")
            conn.commit()

    # Per-workspace databases
    def _ensure_records_db(self, workspace_dir: Path) -> None:
        """Ensure records.sqlite exists with the explicit_records schema."""

        db_path = workspace_dir / "records.sqlite"
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS explicit_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT NOT NULL,
                    is_directory INTEGER NOT NULL,
                    is_recursive INTEGER NOT NULL DEFAULT 0,
                    include_patterns TEXT,
                    exclude_patterns TEXT,
                    note TEXT
                )
                """
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_explicit_records_path ON explicit_records(path)"
            )
            conn.commit()

    def _ensure_images_db(self, workspace_dir: Path) -> None:
        """Ensure images.sqlite exists with images and image_tasks schemas."""

        db_path = workspace_dir / "images.sqlite"
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT NOT NULL,
                    parent_record_id INTEGER,
                    file_hash TEXT,
                    format TEXT,
                    width INTEGER,
                    height INTEGER,
                    size_bytes INTEGER,
                    added_at INTEGER,
                    last_seen_at INTEGER,
                    UNIQUE(path)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_images_parent ON images(parent_record_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_images_hash ON images(file_hash)")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS image_tasks (
                    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
                    task_name TEXT NOT NULL,
                    result_id INTEGER,
                    status TEXT NOT NULL DEFAULT 'done',
                    last_indexed_at INTEGER,
                    PRIMARY KEY (image_id, task_name)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_image_tasks_task ON image_tasks(task_name)")
            conn.commit()

    # Explicit records API (skeleton)
    def add_explicit_record(
        self,
        workspace_id: str,
        path: Path,
        is_directory: bool,
        is_recursive: bool = False,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        note: Optional[str] = None,
    ) -> int:
        """Insert a new explicit record into records.sqlite for the given workspace.

        This method does not scan the filesystem; callers should trigger image discovery separately.
        """

        workspace_dir = self._workspace_dir(workspace_id)
        db_path = workspace_dir / "records.sqlite"
        include_json = json.dumps(include_patterns) if include_patterns is not None else None
        exclude_json = json.dumps(exclude_patterns) if exclude_patterns is not None else None

        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO explicit_records
                    (path, is_directory, is_recursive, include_patterns, exclude_patterns, note)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(path.resolve().as_posix()),
                    int(is_directory),
                    int(is_recursive),
                    include_json,
                    exclude_json,
                    note,
                ),
            )
            conn.commit()
            return cursor.lastrowid or 0

    def list_explicit_records(self, workspace_id: str) -> List[WorkspaceRecord]:
        """Return all explicit records for the given workspace."""

        workspace_dir = self._workspace_dir(workspace_id)
        db_path = workspace_dir / "records.sqlite"
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                """
                SELECT id, path, is_directory, is_recursive
                FROM explicit_records
                ORDER BY path
                """
            )
            rows = cursor.fetchall()

        records: List[WorkspaceRecord] = []
        for row in rows:
            records.append(
                WorkspaceRecord(
                    id=int(row[0]),
                    path=Path(row[1]),
                    is_directory=bool(row[2]),
                    is_recursive=bool(row[3]),
                )
            )
        return records

    # Images API (minimal skeleton)
    def register_image(
        self,
        workspace_id: str,
        path: Path,
        parent_record_id: Optional[int],
        file_hash: Optional[str],
        format: Optional[str],
        width: Optional[int],
        height: Optional[int],
        size_bytes: Optional[int],
    ) -> int:
        """Insert or update an image row in images.sqlite for the given workspace."""

        workspace_dir = self._workspace_dir(workspace_id)
        db_path = workspace_dir / "images.sqlite"
        now = int(time.time())
        abs_path = str(path.resolve().as_posix())

        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO images
                    (path, parent_record_id, file_hash, format, width, height, size_bytes, added_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    parent_record_id=excluded.parent_record_id,
                    file_hash=excluded.file_hash,
                    format=excluded.format,
                    width=excluded.width,
                    height=excluded.height,
                    size_bytes=excluded.size_bytes,
                    last_seen_at=excluded.last_seen_at
                """,
                (abs_path, parent_record_id, file_hash, format, width, height, size_bytes, now, now),
            )
            conn.commit()
            return cursor.lastrowid or self._get_image_id_by_path(db_path, abs_path)

    def _get_image_id_by_path(self, db_path: Path, path: str) -> int:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute("SELECT id FROM images WHERE path = ?", (path,))
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    # Compatibility-style helpers used by existing GUI code
    def add_path(self, workspace_id: str, path: Path) -> None:
        """Add an explicit record and register discovered images for GUI workflows.

        This method mirrors the previous WorkspaceManager.add_path signature while
        delegating actual storage to records.sqlite and images.sqlite.
        """

        cfg = self.get_workspace(workspace_id)
        if cfg is None:
            raise KeyError(f"Workspace {workspace_id} not found")

        path = path.resolve()
        if path.is_dir():
            record_id = self.add_explicit_record(
                workspace_id=workspace_id,
                path=path,
                is_directory=True,
                is_recursive=False,
            )
            for file_path in path.rglob("*"):
                if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                    self._register_image_with_metadata(workspace_id, file_path, parent_record_id=record_id)
        elif path.is_file():
            record_id = self.add_explicit_record(
                workspace_id=workspace_id,
                path=path,
                is_directory=False,
                is_recursive=False,
            )
            if path.suffix.lower() in SUPPORTED_EXTENSIONS:
                self._register_image_with_metadata(workspace_id, path, parent_record_id=record_id)
        else:
            raise FileNotFoundError(f"Path {path} not found")

    def _register_image_with_metadata(
        self,
        workspace_id: str,
        path: Path,
        parent_record_id: Optional[int],
    ) -> None:
        """Register a single image into images.sqlite with basic metadata."""

        format_str: Optional[str]
        width: Optional[int]
        height: Optional[int]
        size_bytes: Optional[int]

        try:
            stat = path.stat()
            size_bytes = stat.st_size
        except OSError:
            size_bytes = None

        try:
            with Image.open(path) as img:
                format_str = img.format or (path.suffix.lstrip(".").upper() or None)
                width, height = img.size
        except (OSError, FileNotFoundError):
            format_str = path.suffix.lstrip(".").upper() or None
            width = None
            height = None

        self.register_image(
            workspace_id=workspace_id,
            path=path,
            parent_record_id=parent_record_id,
            file_hash=None,
            format=format_str,
            width=width,
            height=height,
            size_bytes=size_bytes,
        )

    def remove_explicit_record(self, workspace_id: str, record_id: int) -> None:
        """Remove an explicit record and any images tied to it."""

        workspace_dir = self._workspace_dir(workspace_id)
        records_db = workspace_dir / "records.sqlite"
        images_db = workspace_dir / "images.sqlite"

        with sqlite3.connect(images_db) as conn:
            conn.execute("DELETE FROM images WHERE parent_record_id = ?", (record_id,))
            conn.commit()

        with sqlite3.connect(records_db) as conn:
            conn.execute("DELETE FROM explicit_records WHERE id = ?", (record_id,))
            conn.commit()

    def set_record_recursive(self, workspace_id: str, record_id: int, is_recursive: bool) -> None:
        """Update the recursion flag for an explicit directory record."""

        workspace_dir = self._workspace_dir(workspace_id)
        records_db = workspace_dir / "records.sqlite"
        with sqlite3.connect(records_db) as conn:
            conn.execute(
                "UPDATE explicit_records SET is_recursive = ? WHERE id = ?",
                (int(is_recursive), record_id),
            )
            conn.commit()

    def get_workspace_stats(self, workspace_id: str) -> WorkspaceStats:
        """Return simple aggregated statistics for a workspace."""

        workspace_dir = self._workspace_dir(workspace_id)
        records_db = workspace_dir / "records.sqlite"
        images_db = workspace_dir / "images.sqlite"

        total_records = 0
        total_images = 0
        indexed_images = 0

        with sqlite3.connect(records_db) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM explicit_records")
            row = cursor.fetchone()
            if row:
                total_records = int(row[0])

        if images_db.exists():
            with sqlite3.connect(images_db) as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM images")
                row = cursor.fetchone()
                if row:
                    total_images = int(row[0])

                workspace = self.get_workspace(workspace_id)
                task_name = workspace.tasks[0] if workspace and workspace.tasks else None
                if task_name:
                    cursor = conn.execute(
                        "SELECT COUNT(*) FROM image_tasks WHERE task_name = ? AND status = 'done'",
                        (task_name,),
                    )
                    row = cursor.fetchone()
                    if row:
                        indexed_images = int(row[0])

        return WorkspaceStats(total_records=total_records, total_images=total_images, indexed_images=indexed_images)

    def has_stats(self, workspace_id: str) -> bool:
        """Return True when basic statistics can be provided for the workspace.

        Statistics are computed on demand from SQLite databases, so they are
        always considered available once the workspace exists.
        """

        return self.get_workspace(workspace_id) is not None

    def get_record_stats_for_workspace(self, workspace_id: str) -> Dict[int, RecordStats]:
        """Return per-record statistics keyed by explicit_records.id."""

        workspace_dir = self._workspace_dir(workspace_id)
        images_db = workspace_dir / "images.sqlite"
        stats: Dict[int, RecordStats] = {}

        if not images_db.exists():
            return stats

        workspace = self.get_workspace(workspace_id)
        task_name = workspace.tasks[0] if workspace and workspace.tasks else None

        with sqlite3.connect(images_db) as conn:
            if task_name:
                cursor = conn.execute(
                    """
                    SELECT
                        i.parent_record_id,
                        COUNT(i.id) AS total_images,
                        SUM(CASE WHEN t.status = 'done' THEN 1 ELSE 0 END) AS indexed_images,
                        MAX(i.format) AS format,
                        MAX(i.width) AS width,
                        MAX(i.height) AS height,
                        MAX(i.size_bytes) AS size_bytes
                    FROM images AS i
                    LEFT JOIN image_tasks AS t
                        ON i.id = t.image_id AND t.task_name = ?
                    WHERE i.parent_record_id IS NOT NULL
                    GROUP BY i.parent_record_id
                    """,
                    (task_name,),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT
                        i.parent_record_id,
                        COUNT(i.id) AS total_images,
                        0 AS indexed_images,
                        MAX(i.format) AS format,
                        MAX(i.width) AS width,
                        MAX(i.height) AS height,
                        MAX(i.size_bytes) AS size_bytes
                    FROM images AS i
                    WHERE i.parent_record_id IS NOT NULL
                    GROUP BY i.parent_record_id
                    """
                )

            for row in cursor.fetchall():
                parent_id = int(row[0])
                total_images = int(row[1] or 0)
                indexed_images = int(row[2] or 0)
                fmt = row[3]
                width = int(row[4]) if row[4] is not None else None
                height = int(row[5]) if row[5] is not None else None
                size_bytes = int(row[6]) if row[6] is not None else None
                stats[parent_id] = RecordStats(
                    total_images=total_images,
                    indexed_images=indexed_images,
                    format=fmt,
                    width=width,
                    height=height,
                    size_bytes=size_bytes,
                )

        return stats

    def rebuild_stats(self, workspace_id: str) -> None:
        """Compatibility hook for legacy callers.

        Statistics are computed on demand from SQLite databases, so this
        method currently performs no additional work.
        """

        # Intentionally a no-op; kept for interface compatibility.
        _ = self.get_workspace_stats(workspace_id)


class WorkspaceTaskCoordinator(TaskCoordinator):
    """TaskCoordinator implementation backed by WorkspaceManagerV2 and global databases."""

    def __init__(self, manager: WorkspaceManagerV2) -> None:
        self._manager = manager

    def get_pending_images(self, ctx: TaskContext) -> List[Tuple[int, Path]]:
        """Return images that require work for the given task.

        Currently selects images with no image_tasks row or with status != 'done'.
        """

        workspace_dir = self._manager.workspace_dir_for(ctx.workspace_id)
        db_path = workspace_dir / "images.sqlite"
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                """
                SELECT i.id, i.path, t.status
                FROM images AS i
                LEFT JOIN image_tasks AS t
                    ON i.id = t.image_id AND t.task_name = ?
                ORDER BY i.id
                """,
                (ctx.task_name,),
            )
            rows = cursor.fetchall()

        pending: List[Tuple[int, Path]] = []
        for image_id, path_str, status in rows:
            if status is None or status != "done":
                pending.append((int(image_id), Path(path_str)))
        return pending

    def mark_task_success(
        self,
        ctx: TaskContext,
        image_id: int,
        file_hash: str | None = None,
    ) -> None:
        """Mark task completion for an image and update global tracking tables."""

        workspace_dir = self._manager.workspace_dir_for(ctx.workspace_id)
        images_db = workspace_dir / "images.sqlite"
        now = int(time.time())

        # Load path and existing file_hash for the image.
        with sqlite3.connect(images_db) as conn:
            cursor = conn.execute("SELECT path, file_hash FROM images WHERE id = ?", (image_id,))
            row = cursor.fetchone()
            if not row:
                return
            path_str, existing_hash = row

        image_path = Path(path_str)
        if file_hash is None:
            # Compute a SHA256 hash of the file contents as a stable identifier.
            file_hash = _compute_file_hash(image_path)

        # Update images table with the current file_hash and last_seen_at.
        with sqlite3.connect(images_db) as conn:
            conn.execute(
                """
                UPDATE images
                SET file_hash = ?, last_seen_at = ?
                WHERE id = ?
                """,
                (file_hash, now, image_id),
            )
            # Upsert status into image_tasks.
            conn.execute(
                """
                INSERT INTO image_tasks (image_id, task_name, status, last_indexed_at, result_id)
                VALUES (?, ?, 'done', ?, NULL)
                ON CONFLICT(image_id, task_name) DO UPDATE SET
                    status = excluded.status,
                    last_indexed_at = excluded.last_indexed_at
                """,
                (image_id, ctx.task_name, now),
            )
            conn.commit()

        # Update global_index and image_hashes with the latest hash.
        project_root = self._manager.project_root
        global_index_db = (project_root / self._manager.global_config.global_index_db).resolve()
        hash_db = (project_root / self._manager.global_config.hash_db).resolve()

        abs_path = str(image_path.resolve().as_posix())

        with sqlite3.connect(global_index_db) as conn:
            conn.execute(
                """
                INSERT INTO global_index (path, workspace_id, task_name, last_indexed_hash, last_indexed_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(path, workspace_id, task_name) DO UPDATE SET
                    last_indexed_hash = excluded.last_indexed_hash,
                    last_indexed_at = excluded.last_indexed_at
                """,
                (abs_path, ctx.workspace_id, ctx.task_name, file_hash, now),
            )
            conn.commit()

        with sqlite3.connect(hash_db) as conn:
            # Use filesystem metadata where available.
            try:
                stat = os.stat(image_path)
                size_bytes = stat.st_size
                mtime = int(stat.st_mtime)
            except OSError:
                size_bytes = None
                mtime = None

            conn.execute(
                """
                INSERT INTO image_hashes (path, file_hash, file_size, mtime)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    file_hash = excluded.file_hash,
                    file_size = excluded.file_size,
                    mtime = excluded.mtime
                """,
                (abs_path, file_hash, size_bytes, mtime),
            )
            conn.commit()

    def mark_task_failure(self, ctx: TaskContext, image_id: int, error_message: str) -> None:
        """Record a failed task attempt in image_tasks."""

        workspace_dir = self._manager.workspace_dir_for(ctx.workspace_id)
        images_db = workspace_dir / "images.sqlite"
        now = int(time.time())

        with sqlite3.connect(images_db) as conn:
            conn.execute(
                """
                INSERT INTO image_tasks (image_id, task_name, status, last_indexed_at, result_id)
                VALUES (?, ?, 'failed', ?, NULL)
                ON CONFLICT(image_id, task_name) DO UPDATE SET
                    status = excluded.status,
                    last_indexed_at = excluded.last_indexed_at
                """,
                (image_id, ctx.task_name, now),
            )
            conn.commit()

        # Error messages can be logged via logging frameworks if desired.


def _compute_file_hash(path: Path) -> str:
    """Compute a SHA256 hash for the given file."""

    hasher = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(8192), b""):
                hasher.update(chunk)
    except OSError:
        return ""
    return hasher.hexdigest()
