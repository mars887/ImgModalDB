# Path: core/tasks/hash_tasks.py
# Purpose: Implement hash-based task executor and database adapters (starting with phash_144).
# Layer: core/tasks.
# Details: Provides HashExecutor and HashDatabase for perceptual hashing tasks.

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Tuple

import numpy as np
from PIL import Image

from .base import TaskContext, TaskCoordinator, TaskDatabase, TaskExecutor


class HashExecutor(TaskExecutor):
    """Execute hash-based tasks over image files.

    Initially supports:
    - phash_144: perceptual hash using a 12x12 low-frequency DCT region.
    """

    SUPPORTED_TASKS = {"phash_144"}

    def can_execute(self, task_name: str) -> bool:
        return task_name in self.SUPPORTED_TASKS

    def run_batch(
        self,
        ctx: TaskContext,
        images: Iterable[Tuple[int, Path]],
        db: TaskDatabase,
        coordinator: TaskCoordinator,
    ) -> None:
        db.prepare(ctx)
        try:
            for image_id, image_path in images:
                try:
                    result = self._compute(ctx.task_name, image_path)
                except Exception as exc:  # noqa: BLE001 - propagate as task failure to coordinator
                    coordinator.mark_task_failure(ctx, image_id, str(exc))
                    continue

                try:
                    db.save_result(ctx, image_id, result)
                except Exception as exc:  # noqa: BLE001 - DB-level error
                    coordinator.mark_task_failure(ctx, image_id, f"DB error: {exc}")
                    continue

                coordinator.mark_task_success(ctx, image_id)
        finally:
            db.finalize(ctx)

    def _compute(self, task_name: str, image_path: Path) -> int:
        if task_name == "phash_144":
            return self._compute_phash_144(image_path)
        raise ValueError(f"Unsupported hash task: {task_name}")

    def _compute_phash_144(self, image_path: Path) -> int:
        """Compute a 144-bit perceptual hash for an image using imagehash."""

        try:
            import imagehash  # type: ignore[import]
        except ImportError as exc:  # pragma: no cover - runtime dependency
            raise RuntimeError("imagehash package is required for phash_144 task.") from exc

        with Image.open(image_path) as img:
            rgb = img.convert("RGB")
            ph = imagehash.phash(rgb, hash_size=12)

        # ph.hash is a 12x12 boolean numpy array.
        bits = ph.hash.astype(np.uint8).flatten()
        bit_string = "".join("1" if b else "0" for b in bits)
        return int(bit_string, 2)


class HashDatabase(TaskDatabase):
    """TaskDatabase implementation backed by a per-task SQLite file.

    For phash_144 the schema is kept intentionally simple:
    - one row per image_id storing the integer hash value.
    """

    SUPPORTED_TASKS = {"phash_144"}

    def __init__(self) -> None:
        self._conn: sqlite3.Connection | None = None
        self._table_name: str | None = None

    def can_handle_task(self, task_name: str) -> bool:
        return task_name in self.SUPPORTED_TASKS

    def prepare(self, ctx: TaskContext) -> None:
        index_path = ctx.workspace_dir / "index" / f"{ctx.task_name}.sqlite"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(index_path)
        # Derive a stable table name from the task name.
        sanitized = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in ctx.task_name)
        self._table_name = f"{sanitized}_index"
        assert self._conn is not None
        self._conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self._table_name} (
                image_id INTEGER PRIMARY KEY,
                hash_value INTEGER NOT NULL
            )
            """
        )
        self._conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{self._table_name}_hash_value "
            f"ON {self._table_name}(hash_value)"
        )
        self._conn.commit()

    def save_result(self, ctx: TaskContext, image_id: int, result: int) -> None:
        if self._conn is None or self._table_name is None:
            raise RuntimeError("HashDatabase.save_result called before prepare().")
        hash_int = int(result)
        self._conn.execute(
            f"""
            INSERT INTO {self._table_name} (image_id, hash_value)
            VALUES (?, ?)
            ON CONFLICT(image_id) DO UPDATE SET hash_value = excluded.hash_value
            """,
            (image_id, hash_int),
        )
        self._conn.commit()

    def finalize(self, ctx: TaskContext) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None