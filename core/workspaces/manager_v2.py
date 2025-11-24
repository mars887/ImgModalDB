# Path: core/workspaces/manager_v2.py
# Purpose: Provide a workspace manager using the new per-workspace directory layout and global registries.
# Layer: core/workspaces.
# Details: Each workspace lives under workspaces/{name}_{id}/ with its own config and SQLite databases.

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
import fnmatch
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
    indexed_by_task: Dict[str, int] = field(default_factory=dict)


@dataclass
class RecordStats:
    """Per-record statistics describing image and index coverage."""

    total_images: int
    indexed_images: int
    format: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    size_bytes: Optional[int] = None
    indexed_by_task: Dict[str, int] = field(default_factory=dict)


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

    # SQLite helpers
    @staticmethod
    def _connect_sqlite(path: Path) -> sqlite3.Connection:
        """Create a SQLite connection with foreign keys enabled."""

        conn = sqlite3.connect(path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

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
        with self._connect_sqlite(db_path) as conn:
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
        with self._connect_sqlite(db_path) as conn:
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
        with self._connect_sqlite(db_path) as conn:
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
        with self._connect_sqlite(db_path) as conn:
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
        abs_path = str(path.resolve().as_posix())

        with self._connect_sqlite(db_path) as conn:
            existing = conn.execute(
                """
                SELECT id, is_directory, is_recursive, include_patterns, exclude_patterns, note
                FROM explicit_records
                WHERE path = ?
                """,
                (abs_path,),
            ).fetchone()
            if existing:
                record_id = int(existing[0])
                # Update metadata if flags or patterns changed.
                conn.execute(
                    """
                    UPDATE explicit_records
                    SET is_directory = ?, is_recursive = ?, include_patterns = ?, exclude_patterns = ?, note = COALESCE(?, note)
                    WHERE id = ?
                    """,
                    (
                        int(is_directory),
                        int(is_recursive),
                        include_json,
                        exclude_json,
                        note,
                        record_id,
                    ),
                )
                conn.commit()
                return record_id

            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO explicit_records
                    (path, is_directory, is_recursive, include_patterns, exclude_patterns, note)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    abs_path,
                    int(is_directory),
                    int(is_recursive),
                    include_json,
                    exclude_json,
                    note,
                ),
            )
            conn.commit()
            record_id = cursor.lastrowid
            if not record_id:
                row = conn.execute("SELECT id FROM explicit_records WHERE path = ?", (abs_path,)).fetchone()
                record_id = int(row[0]) if row else 0
            return int(record_id)

    def list_explicit_records(self, workspace_id: str) -> List[WorkspaceRecord]:
        """Return all explicit records for the given workspace."""

        workspace_dir = self._workspace_dir(workspace_id)
        db_path = workspace_dir / "records.sqlite"
        with self._connect_sqlite(db_path) as conn:
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

        with self._connect_sqlite(db_path) as conn:
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
        with self._connect_sqlite(db_path) as conn:
            cursor = conn.execute("SELECT id FROM images WHERE path = ?", (path,))
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    # Compatibility-style helpers used by existing GUI code
    def add_path(
        self,
        workspace_id: str,
        path: Path,
        is_recursive: Optional[bool] = None,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        note: Optional[str] = None,
    ) -> None:
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
                is_recursive=bool(is_recursive) if is_recursive is not None else False,
                include_patterns=include_patterns,
                exclude_patterns=exclude_patterns,
                note=note,
            )
            scan_cfg = self._load_record_scan_config(workspace_id, record_id)
            for file_path in self._iter_directory_images(
                path,
                recursive=scan_cfg["is_recursive"],
                include_patterns=scan_cfg["include_patterns"],
                exclude_patterns=scan_cfg["exclude_patterns"],
            ):
                self._register_image_with_metadata(workspace_id, file_path, parent_record_id=record_id)
        elif path.is_file():
            record_id = self.add_explicit_record(
                workspace_id=workspace_id,
                path=path,
                is_directory=False,
                is_recursive=False,
                include_patterns=include_patterns,
                exclude_patterns=exclude_patterns,
                note=note,
            )
            if path.suffix.lower() in SUPPORTED_EXTENSIONS:
                self._register_image_with_metadata(workspace_id, path, parent_record_id=record_id)
        else:
            raise FileNotFoundError(f"Path {path} not found")

    def _load_record_scan_config(self, workspace_id: str, record_id: int) -> Dict[str, object]:
        """Return scanning flags and patterns for a record."""

        workspace_dir = self._workspace_dir(workspace_id)
        db_path = workspace_dir / "records.sqlite"
        with self._connect_sqlite(db_path) as conn:
            row = conn.execute(
                """
                SELECT is_recursive, include_patterns, exclude_patterns
                FROM explicit_records
                WHERE id = ?
                """,
                (record_id,),
            ).fetchone()

        include_patterns: List[str] = []
        exclude_patterns: List[str] = []
        is_recursive = False
        if row:
            is_recursive = bool(row[0])
            try:
                include_patterns = json.loads(row[1]) if row[1] else []
                exclude_patterns = json.loads(row[2]) if row[2] else []
            except json.JSONDecodeError:
                include_patterns = []
                exclude_patterns = []

        return {
            "is_recursive": is_recursive,
            "include_patterns": include_patterns,
            "exclude_patterns": exclude_patterns,
        }

    def _iter_directory_images(
        self,
        directory: Path,
        recursive: bool,
        include_patterns: List[str],
        exclude_patterns: List[str],
    ):
        """Yield images from a directory honoring recursion and include/exclude patterns."""

        iterator = directory.rglob("*") if recursive else directory.iterdir()
        for file_path in iterator:
            if file_path.is_dir():
                continue
            if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            name = file_path.name
            if include_patterns and not any(fnmatch.fnmatch(name, pattern) for pattern in include_patterns):
                continue
            if exclude_patterns and any(fnmatch.fnmatch(name, pattern) for pattern in exclude_patterns):
                continue
            yield file_path

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

        removed_paths: List[str] = []
        with self._connect_sqlite(images_db) as conn:
            cursor = conn.execute("SELECT path FROM images WHERE parent_record_id = ?", (record_id,))
            removed_paths = [str(Path(row[0]).resolve().as_posix()) for row in cursor.fetchall()]
            conn.execute("DELETE FROM images WHERE parent_record_id = ?", (record_id,))
            conn.commit()

        with self._connect_sqlite(records_db) as conn:
            conn.execute("DELETE FROM explicit_records WHERE id = ?", (record_id,))
            conn.commit()

        if removed_paths:
            global_index_db = (self.project_root / self.global_config.global_index_db).resolve()
            hash_db = (self.project_root / self.global_config.hash_db).resolve()
            with self._connect_sqlite(global_index_db) as conn:
                conn.executemany(
                    "DELETE FROM global_index WHERE path = ? AND workspace_id = ?",
                    [(path, workspace_id) for path in removed_paths],
                )
                conn.commit()
            with self._connect_sqlite(hash_db) as conn:
                conn.executemany("DELETE FROM image_hashes WHERE path = ?", [(path,) for path in removed_paths])
                conn.commit()

    def set_record_recursive(self, workspace_id: str, record_id: int, is_recursive: bool) -> None:
        """Update the recursion flag for an explicit directory record."""

        workspace_dir = self._workspace_dir(workspace_id)
        records_db = workspace_dir / "records.sqlite"
        with self._connect_sqlite(records_db) as conn:
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
        indexed_by_task: Dict[str, int] = {}
        workspace = self.get_workspace(workspace_id)
        task_names = workspace.tasks if workspace and workspace.tasks else []

        with self._connect_sqlite(records_db) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM explicit_records")
            row = cursor.fetchone()
            if row:
                total_records = int(row[0])

        if images_db.exists():
            with self._connect_sqlite(images_db) as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM images")
                row = cursor.fetchone()
                if row:
                    total_images = int(row[0])

                for task_name in task_names:
                    cursor = conn.execute(
                        "SELECT COUNT(*) FROM image_tasks WHERE task_name = ? AND status = 'done'",
                        (task_name,),
                    )
                    row = cursor.fetchone()
                    indexed_by_task[task_name] = int(row[0]) if row else 0

        if indexed_by_task:
            indexed_images = min(indexed_by_task.values())

        return WorkspaceStats(
            total_records=total_records,
            total_images=total_images,
            indexed_images=indexed_images,
            indexed_by_task=indexed_by_task,
        )

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
        task_names = workspace.tasks if workspace and workspace.tasks else []

        with self._connect_sqlite(images_db) as conn:
            base_cursor = conn.execute(
                """
                SELECT
                    i.parent_record_id,
                    COUNT(i.id) AS total_images,
                    MAX(i.format) AS format,
                    MAX(i.width) AS width,
                    MAX(i.height) AS height,
                    MAX(i.size_bytes) AS size_bytes
                FROM images AS i
                WHERE i.parent_record_id IS NOT NULL
                GROUP BY i.parent_record_id
                """
            )
            for row in base_cursor.fetchall():
                parent_id = int(row[0])
                total_images = int(row[1] or 0)
                fmt = row[2]
                width = int(row[3]) if row[3] is not None else None
                height = int(row[4]) if row[4] is not None else None
                size_bytes = int(row[5]) if row[5] is not None else None
                stats[parent_id] = RecordStats(
                    total_images=total_images,
                    indexed_images=0,
                    format=fmt,
                    width=width,
                    height=height,
                    size_bytes=size_bytes,
                    indexed_by_task={},
                )

            if task_names:
                placeholders = ",".join("?" for _ in task_names)
                cursor = conn.execute(
                    f"""
                    SELECT
                        i.parent_record_id,
                        t.task_name,
                        COUNT(*) AS indexed_images
                    FROM images AS i
                    JOIN image_tasks AS t
                        ON i.id = t.image_id
                    WHERE i.parent_record_id IS NOT NULL
                        AND t.task_name IN ({placeholders})
                        AND t.status = 'done'
                    GROUP BY i.parent_record_id, t.task_name
                    """,
                    task_names,
                )

                for parent_id_raw, task_name, indexed_count in cursor.fetchall():
                    parent_id = int(parent_id_raw)
                    if parent_id not in stats:
                        continue
                    record_stats = stats[parent_id]
                    record_stats.indexed_by_task[task_name] = int(indexed_count or 0)
                    if record_stats.indexed_by_task:
                        record_stats.indexed_images = min(record_stats.indexed_by_task.values())

        return stats

    def rebuild_stats(self, workspace_id: str) -> None:
        """Compatibility hook for legacy callers.

        Ensures required databases exist and triggers a fresh statistics computation.
        """

        workspace_dir = self._workspace_dir(workspace_id)
        self._ensure_records_db(workspace_dir)
        self._ensure_images_db(workspace_dir)
        _ = self.get_workspace_stats(workspace_id)


class WorkspaceTaskCoordinator(TaskCoordinator):
    """TaskCoordinator implementation backed by WorkspaceManagerV2 and global databases."""

    def __init__(self, manager: WorkspaceManagerV2) -> None:
        self._manager = manager

    def claim_pending_images(self, ctx: TaskContext, limit: int | None = None) -> List[Tuple[int, Path]]:
        """Claim images that require work for the given task and mark them in-progress."""

        workspace_dir = self._manager.workspace_dir_for(ctx.workspace_id)
        db_path = workspace_dir / "images.sqlite"
        if not db_path.exists():
            return []
        now = int(time.time())

        with self._manager._connect_sqlite(db_path) as conn:
            query = """
                SELECT i.id, i.path
                FROM images AS i
                LEFT JOIN image_tasks AS t
                    ON i.id = t.image_id AND t.task_name = ?
                WHERE t.status IS NULL OR t.status NOT IN ('done', 'in_progress')
                ORDER BY i.id
            """
            params: list[object] = [ctx.task_name]
            if limit is not None:
                query += " LIMIT ?"
                params.append(int(limit))

            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            if not rows:
                return []

            image_ids = [int(row[0]) for row in rows]
            conn.executemany(
                """
                INSERT INTO image_tasks (image_id, task_name, status, last_indexed_at, result_id)
                VALUES (?, ?, 'in_progress', ?, NULL)
                ON CONFLICT(image_id, task_name) DO UPDATE SET
                    status = 'in_progress',
                    last_indexed_at = excluded.last_indexed_at
                """,
                [(image_id, ctx.task_name, now) for image_id in image_ids],
            )
            conn.commit()

        return [(int(image_id), Path(path_str)) for image_id, path_str in rows]

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
        with self._manager._connect_sqlite(images_db) as conn:
            cursor = conn.execute("SELECT path, file_hash FROM images WHERE id = ?", (image_id,))
            row = cursor.fetchone()
            if not row:
                return
            path_str, existing_hash = row

        image_path = Path(path_str)
        if file_hash is None:
            # Compute a SHA256 hash of the file contents as a stable identifier.
            file_hash = existing_hash or _compute_file_hash(image_path)

        # Update images table with the current file_hash and last_seen_at.
        with self._manager._connect_sqlite(images_db) as conn:
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

        with self._manager._connect_sqlite(global_index_db) as conn:
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

        with self._manager._connect_sqlite(hash_db) as conn:
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

        with self._manager._connect_sqlite(images_db) as conn:
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
