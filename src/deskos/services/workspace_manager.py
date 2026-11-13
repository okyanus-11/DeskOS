"""DeskOS-managed workspaces (not Windows virtual desktops).

A workspace groups pinned applications, dashboard widgets and layout metadata.
Switching workspaces reconfigures the DeskOS dashboard and dock only; it does
not touch native Windows virtual desktops.
"""

from __future__ import annotations

import logging
from typing import Any

from deskos.core.config import ConfigManager
from deskos.core.events import EventBus
from deskos.data.repositories import Workspace, WorkspaceRepository

log = logging.getLogger(__name__)


class WorkspaceManager:
    def __init__(
        self,
        repository: WorkspaceRepository,
        config: ConfigManager,
        bus: EventBus | None = None,
    ) -> None:
        self.repository = repository
        self.config = config
        self.bus = bus
        self._active_id = self._resolve_active_id()
        self._ensure_seed_workspaces()

    # ---------------------------------------------------------------- state
    def _resolve_active_id(self) -> str:
        stored = str(self.config.get("workspaces.active", "default"))
        return stored if self.repository.get(stored) else WorkspaceRepository.DEFAULT_ID

    def _ensure_seed_workspaces(self) -> None:
        self.repository.ensure_default()
        if self.repository.count() == 1 and not self.config.get("workspaces.seeded", False):
            # Offer the example workspaces described in the documentation once.
            for name, icon in (
                ("Development", "terminal"),
                ("School", "notes"),
                ("Personal", "home"),
                ("Monitoring", "monitor"),
            ):
                self.repository.create(name=name, icon=icon)
            self.config.set("workspaces.seeded", True)

    @property
    def active_id(self) -> str:
        return self._active_id

    def list(self) -> list[Workspace]:
        return self.repository.list()

    def active(self) -> Workspace:
        workspace = self.repository.get(self._active_id)
        if workspace is None:
            workspace = self.repository.ensure_default()
            self._active_id = workspace.id
        return workspace

    # -------------------------------------------------------------- mutations
    def switch(self, workspace_id: str) -> Workspace:
        workspace = self.repository.get(workspace_id)
        if workspace is None:
            raise KeyError(f"unknown workspace: {workspace_id}")
        self._active_id = workspace_id
        self.config.set("workspaces.active", workspace_id)
        if self.bus is not None:
            self.bus.emit("workspace.changed", workspace=workspace)
        log.info("switched to workspace %s", workspace.name)
        return workspace

    def create(self, name: str, icon: str = "workspace") -> Workspace:
        widgets = list(self.config.get("dashboard.widgets", []))
        layout = {"columns": int(self.config.get("dashboard.columns", 4))}
        workspace_id = self.repository.create(
            name=name,
            icon=icon,
            apps=list(self.config.get("dock.pinned", [])),
            widgets=widgets,
            layout=layout,
        )
        workspace = self.repository.get(workspace_id)
        assert workspace is not None
        if self.bus is not None:
            self.bus.emit("workspaces.updated")
        return workspace

    def update(self, workspace_id: str, **fields: Any) -> None:
        self.repository.update(workspace_id, **fields)
        if self.bus is not None:
            self.bus.emit("workspaces.updated")
            if workspace_id == self._active_id:
                workspace = self.repository.get(workspace_id)
                if workspace is not None:
                    self.bus.emit("workspace.changed", workspace=workspace)

    def delete(self, workspace_id: str) -> bool:
        if workspace_id == self._active_id:
            log.warning("cannot delete the active workspace")
            return False
        deleted = self.repository.delete(workspace_id)
        if deleted and self.bus is not None:
            self.bus.emit("workspaces.updated")
        return deleted

    def set_pinned(self, commands: list[str]) -> None:
        self.update(self._active_id, apps=[{"command": command} for command in commands])

    def set_widgets(self, widgets: list[dict[str, Any]]) -> None:
        self.update(self._active_id, widgets=widgets)

    def set_layout(self, layout: dict[str, Any]) -> None:
        current = dict(self.active().layout)
        current.update(layout)
        self.update(self._active_id, layout=current)

    def pinned_commands(self) -> list[str]:
        workspace = self.active()
        commands: list[str] = []
        for entry in workspace.apps:
            command = entry.get("command") if isinstance(entry, dict) else None
            if isinstance(command, str) and command:
                commands.append(command)
        if commands:
            return commands
        return [str(item) for item in self.config.get("dock.pinned", [])]

    def widget_layout(self) -> list[dict[str, Any]]:
        workspace = self.active()
        if workspace.widgets:
            return [dict(item) for item in workspace.widgets if isinstance(item, dict)]
        return [dict(item) for item in self.config.get("dashboard.widgets", [])]

    def columns(self) -> int:
        try:
            return int(self.active().layout.get("columns", self.config.get("dashboard.columns", 4)))
        except (TypeError, ValueError):
            return 4
