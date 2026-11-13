"""Autostart through the per-user ``Run`` registry key.

The command written is the same one used to launch DeskOS: the frozen executable
when packaged, otherwise the current interpreter with ``-m deskos``.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from deskos.platform.base import AutostartManager

log = logging.getLogger(__name__)

try:  # pragma: no cover - Windows only
    import winreg
except ImportError:  # pragma: no cover
    winreg = None  # type: ignore[assignment]

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "DeskOS"


def launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    executable = Path(sys.executable)
    pythonw = executable.with_name("pythonw.exe")
    interpreter = pythonw if pythonw.is_file() else executable
    return f'"{interpreter}" -m deskos'


class WindowsAutostart(AutostartManager):
    def is_enabled(self) -> bool:
        if winreg is None:
            return False
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                value, _ = winreg.QueryValueEx(key, VALUE_NAME)
                return bool(value)
        except OSError:
            return False

    def set_enabled(self, enabled: bool) -> bool:
        if winreg is None:
            log.warning("winreg unavailable; cannot change autostart")
            return False
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                if enabled:
                    winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, launch_command())
                else:
                    try:
                        winreg.DeleteValue(key, VALUE_NAME)
                    except FileNotFoundError:
                        pass
        except OSError:
            log.exception("could not update autostart registry value")
            return self.is_enabled()
        return self.is_enabled()

    def mechanism(self) -> str:
        return r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run"
