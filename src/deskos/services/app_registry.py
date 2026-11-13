"""Installed-application registry with background discovery.

Discovery is expensive on Windows (PowerShell round-trips), so it happens in a
worker thread and the launcher/control center render whatever is available,
then refresh when the results arrive.  Launches are recorded in SQLite to power
the "recent" and "most used" lists.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

from deskos.data.repositories import UsageRepository
from deskos.platform.base import AppEntry, AppLauncher, LaunchError
from deskos.utils.workers import run_async

log = logging.getLogger(__name__)


class ApplicationRegistry(QObject):
    updated = Signal(list)
    failed = Signal(str)

    def __init__(self, launcher: AppLauncher, usage: UsageRepository, parent=None) -> None:
        super().__init__(parent)
        self.launcher = launcher
        self.usage = usage
        self._entries: list[AppEntry] = []
        self._by_id: dict[str, AppEntry] = {}
        self._loading = False

    # --------------------------------------------------------------- queries
    @property
    def entries(self) -> list[AppEntry]:
        return list(self._entries)

    @property
    def loading(self) -> bool:
        return self._loading

    def get(self, app_id: str) -> AppEntry | None:
        return self._by_id.get(app_id)

    def search(self, query: str) -> list[AppEntry]:
        from deskos.utils.fuzzy import filter_items

        if not query.strip():
            return self.entries
        return filter_items(query, self._entries, key=lambda entry: entry.name)

    def recent(self, limit: int = 8) -> list[dict]:
        return self.usage.recent(limit)

    # ------------------------------------------------------------- discovery
    def refresh(self, force: bool = False) -> None:
        if self._loading:
            return
        self._loading = True
        run_async(self.launcher.discover, self._on_discovered, self._on_failed, force)

    def _on_discovered(self, entries: list[AppEntry]) -> None:
        self._loading = False
        self._entries = list(entries or [])
        self._by_id = {entry.id: entry for entry in self._entries}
        log.info("application registry now holds %d entries", len(self._entries))
        self.updated.emit(self.entries)

    def _on_failed(self, message: str) -> None:
        self._loading = False
        log.warning("application discovery failed: %s", message)
        self.failed.emit(message)

    # ---------------------------------------------------------------- launch
    def launch(self, entry: AppEntry) -> None:
        self.launcher.launch(entry)
        try:
            self.usage.record_launch(entry.id, entry.name, entry.path or entry.target)
        except Exception:
            log.exception("could not record application launch")
        except LaunchError:
            raise
