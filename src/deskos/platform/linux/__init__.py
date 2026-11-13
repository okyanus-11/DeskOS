"""Linux platform backend (priority 2 support)."""

from __future__ import annotations

from deskos.platform.base import PlatformBackend
from deskos.platform.linux.apps import DesktopEntryDiscovery
from deskos.platform.linux.autostart import LinuxAutostart
from deskos.platform.linux.files import LinuxFiles
from deskos.platform.linux.system import LinuxSystem
from deskos.platform.linux.terminal import LinuxTerminal


class LinuxBackend(PlatformBackend):
    def __init__(self) -> None:
        super().__init__(
            name="linux",
            display_name="Linux",
            apps=DesktopEntryDiscovery(),
            terminal=LinuxTerminal(),
            files=LinuxFiles(),
            system=LinuxSystem(),
            autostart=LinuxAutostart(),
            supports_global_hotkeys=False,
            notes=[
                "Linux support covers application discovery, system monitoring, "
                "files, tasks, notes and the shell integration.",
                "Global hotkeys are application-scoped on Linux for now; "
                "Wayland/X11 global grabs are not implemented.",
                "Window effects rely on the compositor; transparency may fall "
                "back to opaque borders on some setups.",
            ],
        )
