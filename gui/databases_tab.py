# Path: gui/databases_tab.py
# Purpose: Provide the Databases tab UI for managing workspaces and their records.
# Layer: gui.
# Details: Uses WorkspaceManager to store workspace metadata (JSON) and explicit/implicit records (SQLite).

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
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
    QWidget,
)

from core.workspaces import WorkspaceManager, WorkspaceRecord, Workspace


class DatabasesTab(QWidget):
    """Workspace management tab with split view for workspaces and explicit records."""

    def __init__(self, manager: WorkspaceManager, parent=None) -> None:
        super().__init__(parent)
        self.manager = manager
        self.workspace_list = QListWidget()
        self.records_list = QListWidget()
        self.current_workspace_label = QLabel("No workspace selected")
        self.status_label = QLabel()
        self._build_ui()
        self._refresh_workspaces()

    def _build_ui(self) -> None:
        root_layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        root_layout.addWidget(splitter)

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
        right_layout.addWidget(QLabel("Explicit records"))
        right_layout.addWidget(self.current_workspace_label)
        right_layout.addWidget(self.records_list)

        buttons_row = QHBoxLayout()
        add_btn = QPushButton("Add path")
        remove_btn = QPushButton("Remove selected")
        add_btn.clicked.connect(self._add_path)
        remove_btn.clicked.connect(self._remove_selected)
        buttons_row.addWidget(add_btn)
        buttons_row.addWidget(remove_btn)
        right_layout.addLayout(buttons_row)
        right_layout.addWidget(self.status_label)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(1, 4)
        splitter.setSizes([200, 800])

    def _refresh_workspaces(self) -> None:
        self.workspace_list.clear()
        for workspace in self.manager.list_workspaces():
            item = QListWidgetItem(workspace.name)
            item.setData(Qt.UserRole, workspace.id)
            self.workspace_list.addItem(item)
            if workspace.id == self.manager.current_workspace_id:
                self.workspace_list.setCurrentItem(item)
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
        for record in self.manager.list_explicit_records(workspace_id):
            item = QListWidgetItem(record.path.as_posix())
            item.setData(Qt.UserRole, record.id)
            self.records_list.addItem(item)
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

    def _add_path(self) -> None:
        workspace_id = self.manager.current_workspace_id
        if not workspace_id:
            QMessageBox.information(self, "Workspace", "Select or create a workspace first.")
            return
        dialog = QFileDialog(self)
        dialog.setFileMode(QFileDialog.ExistingFiles)
        dialog.setOption(QFileDialog.ShowDirsOnly, False)
        dialog.setViewMode(QFileDialog.Detail)
        if dialog.exec():
            for selected in dialog.selectedFiles():
                self.manager.add_path(workspace_id, Path(selected))
            self._refresh_records(workspace_id)
            self.status_label.setText("Paths added")

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
        self.status_label.setText("Record removed")

