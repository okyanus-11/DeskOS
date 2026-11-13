"""XDG autostart entry for Linux desktop sessions."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from deskos.platform.base import AutostartManager

log = logging.getLogger(__name__)


def autostart_file() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return base / "autostart" / "deskos.desktop"


def launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    return f'"{sys.executable}" -m deskos'


class LinuxAutostart(AutostartManager):
    def is_enabled(self) -> bool:
        return autostart_file().is_file()

    def set_enabled(self, enabled: bool) -> bool:
        target = autostart_file()
        try:
            if enabled:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    "[Desktop Entry]\n"
                    "Type=Application\n"
                    "Name=DeskOS\n"
                    "Comment=Desktop environment companion\n"
                    f"Exec={launch_command()}\n"
                    "Terminal=false\n"
                    "X-GNOME-Autostart-enabled=true\n",
                    encoding="utf-8",
                )
            elif target.is_file():
                target.unlink()
        except OSError:
            log.exception("could not update %s", target)
        return self.is_enabled()

    def mechanism(self) -> str:
        return str(autostart_file())
