# Path: gui/databases_tab.py
# Purpose: Provide the Databases tab UI for managing workspaces and their records.
# Layer: gui.
# Details: Uses WorkspaceManager to store workspace metadata (JSON) and explicit/implicit records (SQLite).

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QCheckBox,
    QWidget,
)

from core.workspaces import WorkspaceManager, WorkspaceRecord, Workspace, RecordStats, WorkspaceStats


class _StatsWorker(QThread):
    """Background worker for recomputing workspace statistics without blocking the GUI thread."""

    finished_with_id = Signal(str)

    def __init__(self, manager: WorkspaceManager, workspace_id: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._workspace_id = workspace_id

    def run(self) -> None:  # type: ignore[override]
        """
        External calls:
        - core/workspaces/workspace_manager.py::WorkspaceManager.rebuild_stats - recompute and persist workspace stats.
        """

        self._manager.rebuild_stats(self._workspace_id)
        self.finished_with_id.emit(self._workspace_id)


class _AddPathsWorker(QThread):
    """Background worker for inserting new paths into a workspace without freezing the UI."""

    finished_with_id = Signal(str)
    failed = Signal(str, str)

    def __init__(
        self,
        manager: WorkspaceManager,
        workspace_id: str,
        paths: list[Path],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._manager = manager
        self._workspace_id = workspace_id
        self._paths = paths

    def run(self) -> None:  # type: ignore[override]
        """
        External calls:
        - core/workspaces/workspace_manager.py::WorkspaceManager.add_path - insert explicit and implicit records.
        """

        try:
            for path in self._paths:
                self._manager.add_path(self._workspace_id, path)
            self.finished_with_id.emit(self._workspace_id)
        except Exception as exc:  # noqa: BLE001 - catch-all to report errors back to the GUI
            self.failed.emit(self._workspace_id, str(exc))


class WorkspaceListItemWidget(QWidget):
    """Custom widget for displaying workspace name and aggregated statistics."""

    def __init__(
        self,
        workspace: Workspace,
        stats: WorkspaceStats,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)

        name_label = QLabel(workspace.name)
        name_label.setStyleSheet("font-weight: bold;")

        records_text = f"Records: {stats.total_records}"
        images_text = f"Images indexed: {stats.indexed_images}/{stats.total_images}"
        stats_label = QLabel(f"{records_text} | {images_text}")
        stats_label.setStyleSheet("color: #555555;")

        layout.addWidget(name_label)
        layout.addWidget(stats_label)
        self.setMinimumHeight(52)


class RecordListItemWidget(QWidget):
    """Custom widget for displaying explicit records with type-specific metadata."""

    def __init__(
        self,
        record: WorkspaceRecord,
        stats: RecordStats | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.record = record
        self.recursive_checkbox: QCheckBox | None = None

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(6, 4, 6, 4)
        root_layout.setSpacing(8)

        total_images = stats.total_images if stats else 0
        indexed_images = stats.indexed_images if stats else 0
        is_indexed = bool(indexed_images > 0 and not record.is_directory)

        # Status indicator for files: green = indexed, red = not indexed.
        if not record.is_directory:
            status_label = QLabel()
            status_label.setFixedSize(12, 12)
            color = "#2ecc71" if is_indexed else "#e74c3c"
            status_label.setStyleSheet(f"background-color: {color}; border-radius: 2px;")
            root_layout.addWidget(status_label, alignment=Qt.AlignTop)
        else:
            root_layout.addSpacing(4)

        content_layout = QVBoxLayout()
        content_layout.setSpacing(2)

        title = QLabel(record.path.name or record.path.as_posix())
        title.setStyleSheet("font-weight: bold;")
        content_layout.addWidget(title)

        path_label = QLabel(record.path.as_posix())
        path_label.setStyleSheet("color: #555555;")
        path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        content_layout.addWidget(path_label)

        if record.is_directory:
            stats_label = QLabel(f"Images (indexed/total): {indexed_images}/{total_images}")
            content_layout.addWidget(stats_label)

            self.recursive_checkbox = QCheckBox("Recursive search")
            self.recursive_checkbox.setChecked(record.is_recursive)
            content_layout.addWidget(self.recursive_checkbox)
        else:
            info_label = QLabel(self._build_file_info(record, stats))
            content_layout.addWidget(info_label)

        root_layout.addLayout(content_layout)
        self.setMinimumHeight(64)

    @staticmethod
    def _build_file_info(record: WorkspaceRecord, stats: RecordStats | None) -> str:
        """Return a compact string describing image format, resolution, and size."""

        size_bytes = stats.size_bytes if stats and stats.size_bytes is not None else None  # type: ignore[union-attr]
        size_text = (
            RecordListItemWidget._format_size(size_bytes)
            if size_bytes is not None
            else "size: n/a"
        )

        fmt = stats.format if stats and stats.format else record.path.suffix.lstrip(".").upper() or "unknown"
        if stats and stats.width is not None and stats.height is not None:
            resolution_text = f"{stats.width}x{stats.height}px"
        else:
            resolution_text = "resolution: n/a"

        return f"{fmt} | {resolution_text} | {size_text}"

    @staticmethod
    def _format_size(num_bytes: int) -> str:
        """Return human-readable file size."""

        for unit in ("B", "KB", "MB", "GB"):
            if num_bytes < 1024 or unit == "GB":
                return f"{num_bytes:.1f}{unit}"
            num_bytes /= 1024.0
        return f"{num_bytes:.1f}GB"


class DatabasesTab(QWidget):
    """Workspace management tab with split view for workspaces and explicit records."""

    def __init__(self, manager: WorkspaceManager, parent=None) -> None:
        super().__init__(parent)
        self.manager = manager
        self.workspace_list = QListWidget()
        self.records_list = QListWidget()
        self.current_workspace_label = QLabel("No workspace selected")
        self.status_label = QLabel()
        self._stats_workers: dict[str, _StatsWorker] = {}
        self._add_path_workers: list[_AddPathsWorker] = []
        self._build_ui()
        self._refresh_workspaces()

    def _build_ui(self) -> None:
        root_layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        root_layout.addWidget(splitter)

        self.workspace_list.setSpacing(4)
        self.records_list.setSpacing(4)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(QLabel("Workspaces"))
        left_layout.addWidget(self.workspace_list)

        controls_layout = QHBoxLayout()
        self.new_workspace_input = QLineEdit()
        self.new_workspace_input.setPlaceholderText("New workspace name")
        create_btn = QPushButton("Create")
        create_btn.clicked.connect(self._create_workspace)
        controls_layout.addWidget(self.new_workspace_input)
        controls_layout.addWidget(create_btn)
        left_layout.addLayout(controls_layout)

        self.workspace_list.itemClicked.connect(self._on_workspace_selected)
        splitter.addWidget(left_panel)
        splitter.setStretchFactor(0, 1)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.addWidget(self.current_workspace_label)
        right_layout.addWidget(self.records_list)

        buttons_row = QHBoxLayout()
        add_file_btn = QPushButton("Add file")
        add_folder_btn = QPushButton("Add folder")
        remove_btn = QPushButton("Remove selected")
        add_file_btn.clicked.connect(self._add_files)
        add_folder_btn.clicked.connect(self._add_folder)
        remove_btn.clicked.connect(self._remove_selected)
        buttons_row.addWidget(add_file_btn)
        buttons_row.addWidget(add_folder_btn)
        buttons_row.addWidget(remove_btn)
        right_layout.addLayout(buttons_row)
        right_layout.addWidget(self.status_label)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(1, 4)
        splitter.setSizes([200, 800])

    def _refresh_workspaces(self) -> None:
        self.workspace_list.clear()
        for workspace in self.manager.list_workspaces():
            item = QListWidgetItem()
            item.setData(Qt.UserRole, workspace.id)
            self.workspace_list.addItem(item)
            stats = self.manager.get_workspace_stats(workspace.id)
            widget = WorkspaceListItemWidget(workspace, stats, self.workspace_list)
            self.workspace_list.setItemWidget(item, widget)
            item.setSizeHint(widget.sizeHint())
            if workspace.id == self.manager.current_workspace_id:
                self.workspace_list.setCurrentItem(item)
            if not self.manager.has_stats(workspace.id):
                self._schedule_stats_rebuild(workspace.id)
        if self.manager.current_workspace_id:
            current = self.manager.get_workspace(self.manager.current_workspace_id)
            if current:
                self._load_workspace(current)

    def _load_workspace(self, workspace: Workspace) -> None:
        self.manager.set_current_workspace(workspace.id)
        self.current_workspace_label.setText(f"Selected: {workspace.name}")
        self._refresh_records(workspace.id)

    def _refresh_records(self, workspace_id: str) -> None:
        self.records_list.clear()
        record_stats = self.manager.get_record_stats_for_workspace(workspace_id)
        for record in self.manager.list_explicit_records(workspace_id):
            stats = record_stats.get(record.id)

            item = QListWidgetItem()
            item.setData(Qt.UserRole, record.id)
            self.records_list.addItem(item)
            widget = RecordListItemWidget(
                record=record,
                stats=stats,
                parent=self.records_list,
            )
            if record.is_directory and widget.recursive_checkbox is not None:
                widget.recursive_checkbox.toggled.connect(
                    lambda checked, r_id=record.id: self._on_recursive_toggled(r_id, checked)
                )
            self.records_list.setItemWidget(item, widget)
            item.setSizeHint(widget.sizeHint())
        self.status_label.setText("")

    def _create_workspace(self) -> None:
        name = self.new_workspace_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Please provide a workspace name.")
            return
        workspace = self.manager.create_workspace(name)
        self.new_workspace_input.clear()
        self._refresh_workspaces()
        self._load_workspace(workspace)

    def _on_workspace_selected(self, item: QListWidgetItem) -> None:
        workspace_id = item.data(Qt.UserRole)
        workspace = self.manager.get_workspace(workspace_id)
        if workspace:
            self._load_workspace(workspace)

    def _add_files(self) -> None:
        workspace_id = self.manager.current_workspace_id
        if not workspace_id:
            QMessageBox.information(self, "Workspace", "Select or create a workspace first.")
            return
        dialog = QFileDialog(self)
        dialog.setFileMode(QFileDialog.ExistingFiles)
        dialog.setOption(QFileDialog.ShowDirsOnly, False)
        dialog.setViewMode(QFileDialog.Detail)
        if dialog.exec():
            paths = [Path(selected) for selected in dialog.selectedFiles()]
            if not paths:
                return
            worker = _AddPathsWorker(self.manager, workspace_id, paths, self)
            worker.finished_with_id.connect(self._on_paths_added)
            worker.failed.connect(self._on_paths_add_failed)
            self._add_path_workers.append(worker)
            self.status_label.setText("Adding files...")
            worker.start()

    def _add_folder(self) -> None:
        workspace_id = self.manager.current_workspace_id
        if not workspace_id:
            QMessageBox.information(self, "Workspace", "Select or create a workspace first.")
            return
        directory = QFileDialog.getExistingDirectory(self, "Select folder")
        if directory:
            worker = _AddPathsWorker(self.manager, workspace_id, [Path(directory)], self)
            worker.finished_with_id.connect(self._on_paths_added)
            worker.failed.connect(self._on_paths_add_failed)
            self._add_path_workers.append(worker)
            self.status_label.setText("Adding folder...")
            worker.start()

    def _remove_selected(self) -> None:
        workspace_id = self.manager.current_workspace_id
        if not workspace_id:
            return
        item = self.records_list.currentItem()
        if not item:
            return
        record_id = item.data(Qt.UserRole)
        self.manager.remove_explicit_record(workspace_id, record_id)
        self._refresh_records(workspace_id)
        self._refresh_workspaces()
        self.status_label.setText("Record removed")

    def _on_recursive_toggled(self, record_id: int, checked: bool) -> None:
        workspace_id = self.manager.current_workspace_id
        if not workspace_id:
            return
        self.manager.set_record_recursive(workspace_id, record_id, checked)
        self.status_label.setText("Folder recursion updated")
        self._schedule_stats_rebuild(workspace_id)

    def _on_paths_added(self, workspace_id: str) -> None:
        # Drop finished workers.
        self._add_path_workers = [w for w in self._add_path_workers if w.isRunning()]
        if self.manager.current_workspace_id == workspace_id:
            self._refresh_records(workspace_id)
        self._refresh_workspaces()
        self._schedule_stats_rebuild(workspace_id)
        self.status_label.setText("Paths added")

    def _on_paths_add_failed(self, workspace_id: str, message: str) -> None:
        self._add_path_workers = [w for w in self._add_path_workers if w.isRunning()]
        QMessageBox.warning(self, "Add paths", f"Failed to add paths for workspace {workspace_id}:\n{message}")
        self.status_label.setText("Failed to add paths")

    def _schedule_stats_rebuild(self, workspace_id: str) -> None:
        if not workspace_id:
            return
        existing = self._stats_workers.get(workspace_id)
        if existing is not None and existing.isRunning():
            return
        worker = _StatsWorker(self.manager, workspace_id, self)
        worker.finished_with_id.connect(self._on_stats_rebuilt)
        self._stats_workers[workspace_id] = worker
        worker.start()

    def _on_stats_rebuilt(self, workspace_id: str) -> None:
        self._stats_workers.pop(workspace_id, None)
        if self.manager.current_workspace_id == workspace_id:
            self._refresh_records(workspace_id)
        self._refresh_workspaces()
        self.status_label.setText("Statistics updated")

