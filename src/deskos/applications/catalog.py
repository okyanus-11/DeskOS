"""Catalogue of DeskOS's own applications.

Factories import their implementation lazily so starting the shell does not pay
for loading every application module.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from deskos.core.context import DeskOSContext
from deskos.applications.base import AppPage


@dataclass(frozen=True)
class BuiltinApp:
    id: str
    title: str
    icon: str
    description: str
    factory: Callable[[DeskOSContext], AppPage]
    width: int = 1000
    height: int = 700
    keywords: tuple[str, ...] = ()

    def create_page(self, context: DeskOSContext) -> AppPage:
        return self.factory(context)


def _files(context: DeskOSContext) -> AppPage:
    from deskos.applications.files.view import FilesPage

    return FilesPage(context)


def _terminal(context: DeskOSContext) -> AppPage:
    from deskos.applications.terminal.view import TerminalPage

    return TerminalPage(context)


def _monitor(context: DeskOSContext) -> AppPage:
    from deskos.applications.monitor.view import MonitorPage

    return MonitorPage(context)


def _notes(context: DeskOSContext) -> AppPage:
    from deskos.applications.notes.view import NotesPage

    return NotesPage(context)


def _clock(context: DeskOSContext) -> AppPage:
    from deskos.applications.clock.view import ClockPage

    return ClockPage(context)


def _tasks(context: DeskOSContext) -> AppPage:
    from deskos.applications.tasks.view import TasksPage

    return TasksPage(context)


BUILTIN_APPS: tuple[BuiltinApp, ...] = (
    BuiltinApp(
        id="app.files",
        title="DeskFiles",
        icon="files",
        description="Browse, search and organise local files.",
        factory=_files,
        width=1080,
        height=720,
        keywords=("explorer", "files", "documents", "browse"),
    ),
    BuiltinApp(
        id="app.terminal",
        title="DeskTerminal",
        icon="terminal",
        description="Run PowerShell, PowerShell 7 or Command Prompt.",
        factory=_terminal,
        width=940,
        height=620,
        keywords=("shell", "powershell", "cmd", "console"),
    ),
    BuiltinApp(
        id="app.monitor",
        title="DeskMonitor",
        icon="monitor",
        description="CPU, memory, disk, network and process monitoring.",
        factory=_monitor,
        width=1100,
        height=740,
        keywords=("system", "cpu", "memory", "processes", "performance"),
    ),
    BuiltinApp(
        id="app.notes",
        title="DeskNotes",
        icon="notes",
        description="Markdown-free quick notes with tags and autosave.",
        factory=_notes,
        width=1060,
        height=700,
        keywords=("notes", "write", "journal"),
    ),
    BuiltinApp(
        id="app.clock",
        title="DeskClock",
        icon="clock",
        description="Clock, calendar, stopwatch, timer and world clocks.",
        factory=_clock,
        width=980,
        height=680,
        keywords=("time", "timer", "stopwatch", "calendar", "world"),
    ),
    BuiltinApp(
        id="app.tasks",
        title="DeskTasks",
        icon="tasks",
        description="Tasks with due dates, priorities and completion state.",
        factory=_tasks,
        width=980,
        height=700,
        keywords=("todo", "tasks", "reminders"),
    ),
)

_APP_INDEX = {app.id: app for app in BUILTIN_APPS}


class BuiltinCatalog:
    """Lookup helper handed to the UI through ``ctx.services['catalog']``."""

    def all(self) -> tuple[BuiltinApp, ...]:
        return BUILTIN_APPS

    def get(self, app_id: str) -> BuiltinApp | None:
        return _APP_INDEX.get(app_id)
