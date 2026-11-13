"""Windows 10/11 platform backend."""

from __future__ import annotations

from deskos.core.paths import cache_dir
from deskos.platform.base import PlatformBackend
from deskos.platform.windows.apps import WindowsAppDiscovery
from deskos.platform.windows.autostart import WindowsAutostart
from deskos.platform.windows.files import WindowsFiles
from deskos.platform.windows.system import WindowsSystem
from deskos.platform.windows.terminal import WindowsTerminal


class WindowsBackend(PlatformBackend):
    def __init__(self, discovery_cache=None, cache_hours: int = 6) -> None:
        cache = discovery_cache or (cache_dir() / "applications-windows.json")
        super().__init__(
            name="windows",
            display_name="Windows",
            apps=WindowsAppDiscovery(cache_path=cache, cache_hours=cache_hours),
            terminal=WindowsTerminal(),
            files=WindowsFiles(),
            system=WindowsSystem(),
            autostart=WindowsAutostart(),
            supports_global_hotkeys=True,
            notes=[
                "DeskOS runs as a normal desktop application next to the native "
                "taskbar and Start menu; it never replaces Explorer.",
                "Store (UWP) apps are launchable through their AppUserModelID.",
            ],
        )
