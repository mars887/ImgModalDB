# Path: core/tasks/base.py
# Purpose: Define core task execution interfaces and coordination primitives.
# Layer: core/tasks.
# Details: Provides TaskContext, TaskExecutor, TaskDatabase, TaskCoordinator, and TaskManager.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Protocol, Tuple


@dataclass
class TaskContext:
    """Lightweight context object shared across task components.

    Identifies the workspace and task, and provides the workspace directory.
    """

    workspace_id: str
    task_name: str
    workspace_dir: Path


class TaskDatabase(Protocol):
    """Adapter responsible only for writing task-specific results into an index file."""

    def can_handle_task(self, task_name: str) -> bool:
        """Return True if this DB adapter can handle the given task."""

    def prepare(self, ctx: TaskContext) -> None:
        """Open or create the task index file for the given workspace and task.

        Typically called by the executor inside ``run_batch`` so that the
        executor can control lifetime relative to its own worker threads.
        """

    def save_result(self, ctx: TaskContext, image_id: int, result: Any) -> None:
        """Persist a single task result into the task-specific index."""

    def finalize(self, ctx: TaskContext) -> None:
        """Flush and close connections to the task index.

        Typically invoked by the executor once all work for ``ctx`` is finished.
        """


class TaskCoordinator(Protocol):
    """Coordinate status updates across images.sqlite, global_index.sqlite, and hash databases."""

    def get_pending_images(self, ctx: TaskContext) -> List[Tuple[int, Path]]:
        """Return all images that require work for the given task in the given workspace."""

    def mark_task_success(
        self,
        ctx: TaskContext,
        image_id: int,
        file_hash: str | None = None,
    ) -> None:
        """Mark task completion for an image and update global status tables."""

    def mark_task_failure(self, ctx: TaskContext, image_id: int, error_message: str) -> None:
        """Record a task failure for the given image."""


class TaskExecutor(Protocol):
    """Execute a specific task over a batch of images."""

    def can_execute(self, task_name: str) -> bool:
        """Return True if this executor can handle the given task."""

    def run_batch(
        self,
        ctx: TaskContext,
        images: Iterable[Tuple[int, Path]],
        db: TaskDatabase,
        coordinator: TaskCoordinator,
    ) -> None:
        """Process a batch of images for ctx.task_name in the current thread."""


class TaskManager:
    """Dispatch tasks to appropriate executors and databases.

    The manager itself is synchronous: it calls executors in the caller thread.
    Executors are free to implement their own parallelism internally.
    """

    def __init__(
        self,
        executors: List[TaskExecutor],
        databases: List[TaskDatabase],
        coordinator: TaskCoordinator,
    ) -> None:
        self._executors = executors
        self._databases = databases
        self._coordinator = coordinator

    def _get_executor_for_task(self, task_name: str) -> TaskExecutor:
        for executor in self._executors:
            if executor.can_execute(task_name):
                return executor
        raise RuntimeError(f"No executor found for task {task_name}")

    def _get_db_for_task(self, task_name: str) -> TaskDatabase:
        for db in self._databases:
            if db.can_handle_task(task_name):
                return db
        raise RuntimeError(f"No database handler found for task {task_name}")

    def run_task_for_workspace(self, ctx: TaskContext) -> None:
        """Run a single task for all pending images in a workspace."""

        executor = self._get_executor_for_task(ctx.task_name)
        db = self._get_db_for_task(ctx.task_name)

        pending_images = self._coordinator.get_pending_images(ctx)
        if not pending_images:
            return

        # The executor is responsible for calling db.prepare / db.finalize
        # at appropriate times relative to its own concurrency model.
        executor.run_batch(ctx, pending_images, db, self._coordinator)
