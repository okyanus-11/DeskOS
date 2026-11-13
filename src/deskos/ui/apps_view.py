"""Applications page: built-ins plus everything discovered on the system."""

from __future__ import annotations

import logging

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from deskos.applications.catalog import BuiltinCatalog
from deskos.core.context import DeskOSContext
from deskos.platform.base import AppEntry
from deskos.ui.components import Muted, SearchField, SectionTitle, scrollable
from deskos.ui.flowgrid import AdaptiveGrid
from deskos.utils.fuzzy import filter_items

log = logging.getLogger(__name__)

TILE_WIDTH = 168
TILE_HEIGHT = 96


class AppTile(QPushButton):
    def __init__(self, context: DeskOSContext, app_id: str, name: str, icon, description: str = ""):
        super().__init__()
        self.context = context
        self.app_id = app_id
        self.setObjectName("LauncherTile")
        self.setFixedSize(TILE_WIDTH, TILE_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIcon(icon)
        self.setIconSize(QSize(30, 30))
        self.setText(name)
        self.setToolTip(description or name)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

    def _menu(self, position) -> None:
        menu = QMenu(self)
        pinned = self.app_id in [str(item) for item in self.context.config.get("dock.pinned", [])]
        if pinned:
            menu.addAction("Unpin from dock", self._unpin)
        else:
            menu.addAction("Pin to dock", self._pin)
        menu.addSeparator()
        menu.addAction("Open", self.click)
        menu.exec(self.mapToGlobal(position))

    def _pin(self) -> None:
        pinned = [str(item) for item in self.context.config.get("dock.pinned", [])]
        if self.app_id not in pinned:
            pinned.append(self.app_id)
        self.context.config.set("dock.pinned", pinned)
        self.context.bus.emit("dock.changed")
        self.context.toast(f"Pinned {self.text()} to the dock")

    def _unpin(self) -> None:
        pinned = [str(item) for item in self.context.config.get("dock.pinned", [])]
        self.context.config.set("dock.pinned", [item for item in pinned if item != self.app_id])
        self.context.bus.emit("dock.changed")
        self.context.toast(f"Unpinned {self.text()}")


class AppsView(QWidget):
    def __init__(self, context: DeskOSContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = context
        self.catalog: BuiltinCatalog = context.services["catalog"]
        self._entries: list[AppEntry] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 8, 26, 20)
        root.setSpacing(14)

        header = QHBoxLayout()
        column = QVBoxLayout()
        column.setSpacing(2)
        title = QLabel("Applications")
        title.setObjectName("Heading")
        subtitle = Muted("DeskOS tools and every application found on this computer.")
        subtitle.setWordWrap(False)
        column.addWidget(title)
        column.addWidget(subtitle)
        header.addLayout(column)
        header.addStretch(1)
        self.refresh_button = QPushButton("Rescan")
        self.refresh_button.setIcon(self.ctx.icons.icon("refresh", 15))
        self.refresh_button.clicked.connect(self._rescan)
        header.addWidget(self.refresh_button)
        root.addLayout(header)

        self.search = SearchField(
            self.ctx.icons, "Filter by name — DeskOS apps and installed programs"
        )
        self.search.textChanged.connect(self._apply_filter)
        root.addWidget(self.search)

        self.count_label = Muted("")
        root.addWidget(self.count_label)

        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(10)

        self.builtin_title = SectionTitle("DeskOS applications")
        self.container_layout.addWidget(self.builtin_title)
        self.builtin_grid = AdaptiveGrid(TILE_WIDTH, 6)
        self.container_layout.addWidget(self.builtin_grid)

        self.installed_title = SectionTitle("Installed applications")
        self.container_layout.addWidget(self.installed_title)
        self.installed_hint = Muted("Scanning the Start Menu and installed programs…")
        self.container_layout.addWidget(self.installed_hint)
        self.installed_grid = AdaptiveGrid(TILE_WIDTH, 6)
        self.container_layout.addWidget(self.installed_grid)
        self.container_layout.addStretch(1)

        root.addWidget(scrollable(self.container), 1)

        self.ctx.app_registry.updated.connect(self._on_registry_updated)
        self.ctx.app_registry.failed.connect(self._on_registry_failed)
        self.refresh()

    # ------------------------------------------------------------------ data
    def refresh(self) -> None:
        self._populate_builtins()
        self._entries = self.ctx.app_registry.entries
        if self._entries:
            self.installed_hint.setText(f"{len(self._entries)} applications discovered on this system.")
        self._populate_installed(self._entries)
        self._apply_filter(self.search.text())

    def _rescan(self) -> None:
        self.refresh_button.setEnabled(False)
        self.installed_hint.setText("Rescanning installed applications…")
        self.ctx.app_registry.refresh(force=True)

    def _on_registry_updated(self, entries) -> None:
        self.refresh_button.setEnabled(True)
        self._entries = entries
        self.refresh()

    def _on_registry_failed(self, message: str) -> None:
        self.refresh_button.setEnabled(True)
        self.installed_hint.setText(f"Application discovery failed: {message}")

    def _populate_builtins(self) -> None:
        self.builtin_grid.clear()
        launcher = self.ctx.services.get("launcher")
        for app in self.catalog.all():
            tile = AppTile(
                self.ctx,
                app.id,
                app.title,
                self.ctx.icons.icon(app.icon, 30, self.ctx.theme.accent),
                app.description,
            )
            tile.clicked.connect(lambda _checked=False, command=app.id: launcher.launch_command(command))
            self.builtin_grid.add(tile)

    def _populate_installed(self, entries: list[AppEntry]) -> None:
        self.installed_grid.clear()
        launcher = self.ctx.services.get("launcher")
        for entry in entries:
            tile = AppTile(
                self.ctx,
                entry.id,
                entry.name,
                self.ctx.icons.file_icon(entry),
                entry.comment or entry.path or entry.target,
            )
            tile.clicked.connect(
                lambda _checked=False, item=entry: launcher.launch_entry(item)
            )
            self.installed_grid.add(tile)
        self.installed_hint.setVisible(not entries)

    def _apply_filter(self, text: str) -> None:
        query = text.strip()
        visible = 0
        builtin_tiles = self.builtin_grid.items()
        builtin_matches = (
            filter_items(query, builtin_tiles, key=lambda tile: tile.text())
            if query
            else builtin_tiles
        )
        allowed = {id(tile) for tile in builtin_matches}
        for tile in builtin_tiles:
            tile.setVisible(id(tile) in allowed)
            visible += int(id(tile) in allowed)

        installed_tiles = self.installed_grid.items()
        installed_matches = (
            filter_items(query, installed_tiles, key=lambda tile: tile.text())
            if query
            else installed_tiles
        )
        allowed_installed = {id(tile) for tile in installed_matches}
        for tile in installed_tiles:
            tile.setVisible(id(tile) in allowed_installed)
            visible += int(id(tile) in allowed_installed)

        total = len(builtin_tiles) + len(installed_tiles)
        self.count_label.setText(
            f"Showing {visible} of {total} applications" if query else f"{total} applications available"
        )
