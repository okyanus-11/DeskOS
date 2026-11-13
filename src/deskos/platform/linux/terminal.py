"""Linux shells for DeskTerminal (bash/zsh/fish) plus terminal emulator launch."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess  # noqa: S404 - launching a shell is the feature

from deskos.platform.base import LaunchError, ShellSpec, TerminalBackend

log = logging.getLogger(__name__)

_EMULATORS = (
    ("x-terminal-emulator", ["-e"]),
    ("gnome-terminal", ["--"]),
    ("konsole", ["-e"]),
    ("alacritty", ["-e"]),
    ("kitty", []),
    ("xterm", ["-e"]),
)


class LinuxTerminal(TerminalBackend):
    def available_shells(self) -> list[ShellSpec]:
        shells: list[ShellSpec] = []
        for identifier, label, args in (
            ("bash", "Bash", ["--noprofile", "--norc"]),
            ("zsh", "Zsh", ["-f"]),
            ("fish", "Fish", ["--no-config"]),
        ):
            executable = shutil.which(identifier)
            if executable:
                shells.append(
                    ShellSpec(
                        id=identifier,
                        label=label,
                        executable=executable,
                        repl_args=args,
                        external_args=["-i"],
                    )
                )
        return shells

    def launch_external(self, shell: ShellSpec, cwd: str | None = None) -> None:
        for name, prefix in _EMULATORS:
            executable = shutil.which(name)
            if not executable:
                continue
            arguments = [executable, *prefix, shell.executable, *shell.external_args]
            try:
                subprocess.Popen(  # noqa: S603 - resolved emulator path
                    arguments,
                    cwd=cwd or os.path.expanduser("~"),
                    close_fds=True,
                    start_new_session=True,
                )
                return
            except OSError:
                log.debug("terminal emulator %s failed", name, exc_info=True)
        raise LaunchError("No terminal emulator found on this system")
