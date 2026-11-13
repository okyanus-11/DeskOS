"""Platform abstraction layer.

UI code only ever talks to :class:`PlatformBackend`, so a new operating system
support effort means implementing one backend rather than touching the UI.
"""

from __future__ import annotations

import logging
import sys

from deskos.platform.base import (
    AppEntry,
    AppLauncher,
    AutostartManager,
    FileIntegration,
    LaunchError,
    PlatformBackend,
    ShellSpec,
    SystemBackend,
    TerminalBackend,
)

log = logging.getLogger(__name__)

__all__ = [
    "AppEntry",
    "AppLauncher",
    "AutostartManager",
    "FileIntegration",
    "LaunchError",
    "PlatformBackend",
    "ShellSpec",
    "SystemBackend",
    "TerminalBackend",
    "get_backend",
]

_backend: PlatformBackend | None = None


def get_backend(
    refresh: bool = False, discovery_cache_hours: int | None = None
) -> PlatformBackend:
    """Return the singleton backend for the current platform."""
    global _backend
    if _backend is not None and not refresh:
        return _backend

    if sys.platform == "win32":
        from deskos.platform.windows import WindowsBackend

        _backend = WindowsBackend(cache_hours=discovery_cache_hours or 6)
    elif sys.platform.startswith("linux"):
        from deskos.platform.linux import LinuxBackend

        _backend = LinuxBackend()
    else:
        from deskos.platform.linux import LinuxBackend

        log.warning("platform %s has no dedicated backend, using the POSIX fallback", sys.platform)
        _backend = LinuxBackend()
    log.info("platform backend: %s", _backend.display_name)
    return _backend
