"""Windows shell integration for DeskTerminal.

DeskTerminal does not emulate a terminal: it attaches to a real PowerShell,
PowerShell 7 or Command Prompt process through pipes, and can hand the session
over to Windows Terminal in its own window.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess  # noqa: S404 - launching a shell is the feature
from pathlib import Path

from deskos.platform.base import LaunchError, ShellSpec, TerminalBackend

log = logging.getLogger(__name__)
CREATE_NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)


class WindowsTerminal(TerminalBackend):
    def available_shells(self) -> list[ShellSpec]:
        shells: list[ShellSpec] = []
        pwsh = shutil.which("pwsh")
        if pwsh:
            shells.append(
                ShellSpec(
                    id="pwsh",
                    label="PowerShell 7",
                    executable=pwsh,
                    repl_args=["-NoLogo", "-NoProfile", "-Command", "-"],
                    external_args=["-NoLogo", "-NoExit"],
                )
            )
        powershell = shutil.which("powershell") or str(
            Path(os.environ.get("SystemRoot", r"C:\Windows"))
            / "System32"
            / "WindowsPowerShell"
            / "v1.0"
            / "powershell.exe"
        )
        if Path(powershell).is_file():
            shells.append(
                ShellSpec(
                    id="powershell",
                    label="Windows PowerShell",
                    executable=powershell,
                    repl_args=["-NoLogo", "-NoProfile", "-Command", "-"],
                    external_args=["-NoLogo", "-NoExit"],
                )
            )
        cmd = shutil.which("cmd") or str(
            Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "cmd.exe"
        )
        if Path(cmd).is_file():
            shells.append(
                ShellSpec(
                    id="cmd",
                    label="Command Prompt",
                    executable=cmd,
                    repl_args=["/Q", "/D", "/K"],
                    external_args=["/K"],
                )
            )
        wt = shutil.which("wt")
        if wt:
            shells.append(
                ShellSpec(
                    id="wt",
                    label="Windows Terminal",
                    executable=wt,
                    is_external_only=True,
                )
            )
        return shells

    def launch_external(self, shell: ShellSpec, cwd: str | None = None) -> None:
        try:
            if shell.id == "wt":
                arguments = [shell.executable]
                if cwd:
                    arguments.extend(["-d", cwd])
                arguments.extend(["-p", "Windows PowerShell"])
                subprocess.Popen(arguments, close_fds=True)  # noqa: S603
                return
            arguments = [shell.executable, *shell.external_args]
            subprocess.Popen(  # noqa: S603 - absolute shell path
                arguments,
                cwd=cwd or None,
                close_fds=True,
                creationflags=CREATE_NEW_CONSOLE,
            )
        except OSError as exc:
            raise LaunchError(f"Could not start {shell.label}: {exc}") from exc
