"""Application context: the single place where services are wired together.

Passing this object around (instead of importing globals) keeps the UI testable:
the test-suite can build a context pointing at a temporary data directory and an
off-screen Qt platform.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from deskos.core.commands import CommandRegistry
from deskos.core.config import ConfigManager
from deskos.core.database import Database
from deskos.core.events import EventBus
from deskos.core.theme import ThemeManager
from deskos.data.repositories import (
    AIHistoryRepository,
    NotesRepository,
    PluginStateRepository,
    TasksRepository,
    UsageRepository,
    WorkspaceRepository,
)
from deskos.platform.base import PlatformBackend
from deskos.services.app_registry import ApplicationRegistry
from deskos.services.workspace_manager import WorkspaceManager
from deskos.system.monitor import SystemMonitor

if TYPE_CHECKING:  # pragma: no cover - typing only
    from deskos.plugins.manager import PluginManager
    from deskos.ui.icons import IconProvider
    from deskos.widgets.registry import WidgetRegistry


@dataclass
class DeskOSContext:
    config: ConfigManager
    bus: EventBus
    db: Database
    theme: ThemeManager
    icons: "IconProvider"
    platform: PlatformBackend
    commands: CommandRegistry
    monitor: SystemMonitor
    app_registry: ApplicationRegistry
    workspaces: WorkspaceManager
    notes: NotesRepository
    tasks: TasksRepository
    workspace_repo: WorkspaceRepository
    usage: UsageRepository
    ai_history: AIHistoryRepository
    plugin_state: PluginStateRepository
    widget_registry: "WidgetRegistry"
    plugins: "PluginManager | None" = None
    services: dict[str, Any] = field(default_factory=dict)

    # Convenience accessors used by views.
    def get_service(self, name: str) -> Any:
        return self.services.get(name)

    def put_service(self, name: str, value: Any) -> None:
        self.services[name] = value

    def toast(self, message: str, timeout_ms: int = 3200) -> None:
        """Show a transient notification if the shell is running."""
        notifier = self.services.get("notifier")
        if callable(notifier):
            notifier(message, timeout_ms)
