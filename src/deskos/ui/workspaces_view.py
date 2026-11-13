"""Workspace management page (DeskOS workspaces, not Windows virtual desktops)."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from deskos.core.context import DeskOSContext
from deskos.data.repositories import Workspace
from deskos.ui.components import IconButton, Muted, apply_shadow, scrollable
from deskos.ui.dialogs import PromptDialog
from deskos.ui.flowgrid import AdaptiveGrid

log = logging.getLogger(__name__)


class WorkspaceCard(QFrame):
    def __init__(self, parent_view: "WorkspacesView", workspace: Workspace, active: bool):
        super().__init__()
        self.view = parent_view
        self.workspace = workspace
        self.setObjectName("Card")
        self.setMinimumHeight(170)
        self.setMinimumWidth(250)
        apply_shadow(self, 28, 6, 70)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        header = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(
            parent_view.ctx.icons.pixmap(
                workspace.icon or "workspace",
                22,
                parent_view.ctx.theme.accent if active else parent_view.ctx.theme.palette.subtext1,
            )
        )
        header.addWidget(icon)
        name = QLabel(workspace.name)
        name.setObjectName("Subheading")
        header.addWidget(name)
        header.addStretch(1)
        if active:
            badge = QLabel("Active")
            badge.setObjectName("Badge")
            header.addWidget(badge)
        layout.addLayout(header)

        counts = Muted(
            f"{len(workspace.apps)} pinned apps · {len(workspace.widgets)} widgets"
        )
        layout.addWidget(counts)
        layout.addStretch(1)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        switch = QPushButton("Activate" if not active else "Active")
        switch.setEnabled(not active)
        switch.clicked.connect(lambda: parent_view.activate(workspace.id))
        actions.addWidget(switch)
        rename = IconButton(parent_view.ctx.icons, "edit", "Rename workspace", 30, 15)
        rename.clicked.connect(lambda: parent_view.rename(workspace.id))
        actions.addWidget(rename)
        if workspace.id != "default":
            delete = IconButton(parent_view.ctx.icons, "trash", "Delete workspace", 30, 15)
            delete.setEnabled(not active)
            delete.clicked.connect(lambda: parent_view.delete(workspace.id))
            actions.addWidget(delete)
        actions.addStretch(1)
        layout.addLayout(actions)


class WorkspacesView(QWidget):
    def __init__(self, ctx: DeskOSContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.icons = ctx.icons

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 8, 26, 20)
        root.setSpacing(14)

        header = QHBoxLayout()
        column = QVBoxLayout()
        column.setSpacing(2)
        title = QLabel("Workspaces")
        title.setObjectName("Heading")
        subtitle = Muted(
            "DeskOS groups your pinned apps and widgets. These are not Windows virtual desktops."
        )
        column.addWidget(title)
        column.addWidget(subtitle)
        header.addLayout(column)
        header.addStretch(1)
        create = QPushButton("New workspace")
        create.setObjectName("PrimaryButton")
        create.setIcon(self.icons.icon("plus", 15, ctx.theme.palette.crust))
        create.clicked.connect(self.create_workspace)
        header.addWidget(create)
        root.addLayout(header)

        self.grid = AdaptiveGrid(260, 4, 14)
        root.addWidget(scrollable(self.grid), 1)
        self.refresh()

    def refresh(self) -> None:
        self.grid.clear()
        active_id = self.ctx.workspaces.active_id
        for workspace in self.ctx.workspaces.list():
            self.grid.add(WorkspaceCard(self, workspace, workspace.id == active_id))

    def activate(self, workspace_id: str) -> None:
        try:
            workspace = self.ctx.workspaces.switch(workspace_id)
        except KeyError:
            self.ctx.toast("Workspace no longer exists")
            return
        self.ctx.toast(f"Workspace: {workspace.name}")
        self.refresh()

    def create_workspace(self) -> None:
        dialog = PromptDialog(
            self,
            "New workspace",
            "Give the workspace a name. It starts with your current dashboard widgets.",
            placeholder="e.g. Deep work",
            confirm_label="Create",
        )
        if dialog.exec() and dialog.value():
            workspace = self.ctx.workspaces.create(dialog.value())
            self.refresh()
            self.ctx.toast(f"Created workspace {workspace.name}")

    def rename(self, workspace_id: str) -> None:
        workspace = self.ctx.workspace_repo.get(workspace_id)
        if workspace is None:
            return
        dialog = PromptDialog(self, "Rename workspace", "New name", text=workspace.name)
        if dialog.exec() and dialog.value():
            self.ctx.workspaces.update(workspace_id, name=dialog.value())
            self.refresh()

    def delete(self, workspace_id: str) -> None:
        if self.ctx.workspaces.delete(workspace_id):
            self.ctx.toast("Workspace deleted")
        else:
            self.ctx.toast("The active workspace cannot be deleted")
        self.refresh()
