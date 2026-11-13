"""Extensible command registry backing the DeskOS command palette.

Commands are plain callables plus metadata; the registry supports fuzzy search
by title/keywords, categories, custom user-defined shell commands (which require
explicit confirmation) and safe execution with per-command error isolation.
"""

from __future__ import annotations

import logging
import subprocess  # noqa: S404 - custom commands are user-authored and confirmed
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from deskos.utils.fuzzy import fuzzy_score

log = logging.getLogger(__name__)

CATEGORY_APPS = "Applications"
CATEGORY_SYSTEM = "System"
CATEGORY_APPEARANCE = "Appearance"
CATEGORY_FILES = "Files"
CATEGORY_CUSTOM = "Custom"


@dataclass
class Command:
    id: str
    title: str
    category: str = CATEGORY_SYSTEM
    description: str = ""
    keywords: tuple[str, ...] = ()
    shortcut: str = ""
    icon: str = "terminal"
    callback: Callable[..., Any] | None = None
    requires_confirmation: bool = False
    confirm_text: str = ""

    def search_text(self) -> str:
        return " ".join((self.title, self.description, self.category, *self.keywords))


@dataclass
class CommandResult:
    command: Command
    ok: bool
    value: Any = None
    error: str = ""


class CommandRegistry:
    def __init__(self) -> None:
        self._commands: dict[str, Command] = {}
        self._listeners: list[Callable[[], None]] = []

    # ----------------------------------------------------------- registration
    def register(self, command: Command) -> None:
        if not command.id:
            raise ValueError("command id must not be empty")
        if command.id in self._commands:
            log.debug("replacing command %s", command.id)
        self._commands[command.id] = command
        self._notify()

    def unregister(self, command_id: str) -> None:
        if self._commands.pop(command_id, None) is not None:
            self._notify()

    def register_many(self, commands: Iterable[Command]) -> None:
        for command in commands:
            self._commands[command.id] = command
        self._notify()

    def unregister_prefix(self, prefix: str) -> None:
        removed = [key for key in self._commands if key.startswith(prefix)]
        for key in removed:
            del self._commands[key]
        if removed:
            self._notify()

    def add_listener(self, callback: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(callback)

        def remove() -> None:
            if callback in self._listeners:
                self._listeners.remove(callback)

        return remove

    def _notify(self) -> None:
        for listener in list(self._listeners):
            try:
                listener()
            except Exception:
                log.exception("command registry listener failed")

    # ---------------------------------------------------------------- queries
    def all(self) -> list[Command]:
        return sorted(self._commands.values(), key=lambda item: (item.category, item.title))

    def get(self, command_id: str) -> Command | None:
        return self._commands.get(command_id)

    def categories(self) -> list[str]:
        return sorted({command.category for command in self._commands.values()})

    def search(self, query: str, limit: int = 40) -> list[Command]:
        query = (query or "").strip()
        if not query:
            return self.all()[:limit]
        scored: list[tuple[Command, int]] = []
        for command in self._commands.values():
            score = fuzzy_score(query, command.search_text())
            if score is None:
                continue
            # Slightly favour matches on the title.
            title_score = fuzzy_score(query, command.title)
            if title_score is not None:
                score += title_score // 2
            scored.append((command, score))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return [command for command, _ in scored[:limit]]

    # -------------------------------------------------------------- execution
    def execute(self, command_id: str, **context: Any) -> CommandResult:
        command = self._commands.get(command_id)
        if command is None:
            return CommandResult(
                command=Command(id=command_id, title=command_id),
                ok=False,
                error=f"Unknown command '{command_id}'",
            )
        if command.callback is None:
            return CommandResult(command=command, ok=False, error="Command has no action")
        try:
            value = command.callback(**context)
        except Exception as exc:
            log.exception("command %s failed", command_id)
            return CommandResult(command=command, ok=False, error=str(exc))
        return CommandResult(command=command, ok=True, value=value)


def shell_command_action(shell: str, label: str, description: str = "") -> Callable[[], None]:
    """Build a callback that runs a user-defined shell command.

    The action is only reachable through the palette, which asks for explicit
    confirmation first when ``requires_confirmation`` is set.  Output is captured
    and logged rather than streamed into the UI.
    """

    def action() -> None:
        log.info("running custom command %r", label)
        completed = subprocess.run(  # noqa: S602 - user authored, confirmed
            shell,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if completed.returncode != 0:
            log.warning(
                "custom command %r exited with %s: %s",
                label,
                completed.returncode,
                completed.stderr.strip()[:500],
            )
        else:
            log.info("custom command %r succeeded", label)

    action.__doc__ = description or f"Run: {label}"
    return action


@dataclass
class ShortcutHint:
    """Display helper for the palette footer."""

    label: str
    keys: str
    extras: dict[str, Any] = field(default_factory=dict)
