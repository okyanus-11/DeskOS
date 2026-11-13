"""Runtime services shared by the UI (application registry, workspaces, ...)."""

from deskos.services.app_registry import ApplicationRegistry
from deskos.services.workspace_manager import WorkspaceManager

__all__ = ["ApplicationRegistry", "WorkspaceManager"]
