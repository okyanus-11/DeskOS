"""Interfaces implemented by each supported operating system."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class LaunchError(RuntimeError):
    """Raised when an application or shell cannot be started."""


@dataclass
class AppEntry:
    """A discoverable application (a shortcut, executable or store app)."""

    id: str
    name: str
    path: str = ""
    args: list[str] = field(default_factory=list)
    source: str = "start-menu"
    icon_path: str = ""
    comment: str = ""
    target: str = ""
    kind: str = "app"  # app | shortcut | store | desktop-entry

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "path": self.path,
            "args": list(self.args),
            "source": self.source,
            "icon_path": self.icon_path,
            "comment": self.comment,
            "target": self.target,
            "kind": self.kind,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AppEntry:
        return cls(
            id=str(payload.get("id", "")),
            name=str(payload.get("name", "")),
            path=str(payload.get("path", "")),
            args=list(payload.get("args", []) or []),
            source=str(payload.get("source", "start-menu")),
            icon_path=str(payload.get("icon_path", "")),
            comment=str(payload.get("comment", "")),
            target=str(payload.get("target", "")),
            kind=str(payload.get("kind", "app")),
        )


@dataclass
class ShellSpec:
    """A shell that DeskTerminal can drive as a real subprocess."""

    id: str
    label: str
    executable: str
    repl_args: list[str] = field(default_factory=list)
    external_args: list[str] = field(default_factory=list)
    is_external_only: bool = False


class AppLauncher(ABC):
    @abstractmethod
    def discover(self, force: bool = False) -> list[AppEntry]:
        """Return installed applications discovered from the real system."""

    @abstractmethod
    def launch(self, entry: AppEntry) -> None:
        """Start the application; raises :class:`LaunchError` on failure."""


class TerminalBackend(ABC):
    @abstractmethod
    def available_shells(self) -> list[ShellSpec]:
        """Shells that exist on this machine, most preferred first."""

    @abstractmethod
    def launch_external(self, shell: ShellSpec, cwd: str | None = None) -> None:
        """Open the shell in its native terminal window."""


class FileIntegration(ABC):
    @abstractmethod
    def open_path(self, path: str) -> bool:
        """Open a file/folder with the user's default handler."""

    @abstractmethod
    def reveal_path(self, path: str) -> bool:
        """Show the item in the system file manager."""

    @abstractmethod
    def trash(self, path: str) -> bool:
        """Move to the recycle bin / trash (never a permanent delete)."""

    @abstractmethod
    def locations(self) -> list[tuple[str, str]]:
        """Named quick-access locations: ``(label, absolute path)``."""

    @abstractmethod
    def drives(self) -> list[tuple[str, str]]:
        """``(label, root path)`` for mounted drives."""

    @abstractmethod
    def default_path(self) -> str:
        """Initial directory for DeskFiles."""


class SystemBackend(ABC):
    @abstractmethod
    def os_info(self) -> dict[str, str]:
        """Operating system name, version, build and architecture."""

    @abstractmethod
    def hardware_info(self) -> dict[str, str]:
        """CPU model, core counts, total memory, machine type."""

    @abstractmethod
    def network_interfaces(self) -> list[dict[str, Any]]:
        """Adapters with addresses, MAC, speed and traffic counters."""

    @abstractmethod
    def battery(self) -> dict[str, Any] | None:
        """Battery charge/plugged state, or ``None`` when unavailable."""


class AutostartManager(ABC):
    @abstractmethod
    def is_enabled(self) -> bool:
        """Whether DeskOS is registered to start with the session."""

    @abstractmethod
    def set_enabled(self, enabled: bool) -> bool:
        """Enable/disable autostart; returns the resulting state."""

    @abstractmethod
    def mechanism(self) -> str:
        """Human readable description of how autostart is implemented."""


@dataclass
class PlatformBackend:
    name: str
    display_name: str
    apps: AppLauncher
    terminal: TerminalBackend
    files: FileIntegration
    system: SystemBackend
    autostart: AutostartManager
    notes: list[str] = field(default_factory=list)
    supports_global_hotkeys: bool = False
