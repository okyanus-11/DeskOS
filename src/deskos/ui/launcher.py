"""Full-screen application launcher with search, recents and pinning."""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QCursor
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
from deskos.ui.apps_view import AppTile
from deskos.ui.components import SearchField, SectionTitle, apply_shadow, scrollable
from deskos.ui.flowgrid import AdaptiveGrid

log = logging.getLogger(__name__)

MAX_TILES = 48


class LauncherOverlay(QWidget):
    def __init__(self, context: DeskOSContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = context
        self.catalog: BuiltinCatalog = context.services["catalog"]
        self.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle("DeskOS Launcher")

        root = QVBoxLayout(self)
        root.setContentsMargins(60, 60, 60, 60)
        root.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.panel = QWidget()
        self.panel.setObjectName("LauncherPanel")
        self.panel.setMaximumWidth(1020)
        self.panel.setMinimumWidth(720)
        self.panel.setMinimumHeight(560)
        apply_shadow(self.panel, 62, 18, 150)
        root.addWidget(self.panel)

        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(22, 20, 22, 18)
        panel_layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Applications")
        title.setObjectName("Heading")
        header.addWidget(title)
        header.addStretch(1)
        self.esc_hint = QLabel("Esc")
        self.esc_hint.setObjectName("Pill")
        header.addWidget(self.esc_hint)
        panel_layout.addLayout(header)

        self.search = SearchField(self.ctx.icons, "Search applications and DeskOS tools…")
        self.search.textChanged.connect(self._apply_filter)
        self.search.installEventFilter(self)
        panel_layout.addWidget(self.search)

        self.results_label = QLabel("")
        self.results_label.setObjectName("Muted")
        panel_layout.addWidget(self.results_label)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)

        self.pinned_title = SectionTitle("Pinned and DeskOS apps")
        content_layout.addWidget(self.pinned_title)
        self.builtin_grid = AdaptiveGrid(158, 6, 10)
        content_layout.addWidget(self.builtin_grid)

        self.installed_title = SectionTitle("Installed applications")
        content_layout.addWidget(self.installed_title)
        self.installed_grid = AdaptiveGrid(158, 6, 10)
        content_layout.addWidget(self.installed_grid)
        content_layout.addStretch(1)

        panel_layout.addWidget(scrollable(content), 1)

        footer = QHBoxLayout()
        self.recent_label = QLabel("")
        self.recent_label.setObjectName("Muted")
        footer.addWidget(self.recent_label)
        footer.addStretch(1)
        hint = QLabel("Enter to launch · right-click to pin")
        hint.setObjectName("Muted")
        footer.addWidget(hint)
        panel_layout.addLayout(footer)

        self._tiles: list[AppTile] = []
        self._index = -1
        self.ctx.app_registry.updated.connect(lambda _entries: self._populate())
        self._populate()

    # ------------------------------------------------------------------- open
    def open_overlay(self) -> None:
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is not None:
            self.setGeometry(screen.availableGeometry())
        self._populate()
        self.search.clear()
        self.search.setFocus()
        self.show()
        self.raise_()
        self.activateWindow()
        QTimer.singleShot(60, self._focus_first)

    def _focus_first(self) -> None:
        if self._tiles:
            self._select(0)

    def _populate(self) -> None:
        self.builtin_grid.clear()
        self.installed_grid.clear()
        self._tiles.clear()
        self._index = -1
        launcher = self.ctx.services["launcher"]

        for app in self.catalog.all():
            tile = AppTile(
                self.ctx, app.id, app.title, self.ctx.icons.icon(app.icon, 30, self.ctx.theme.accent),
                app.description,
            )
            tile.clicked.connect(lambda _checked=False, cmd=app.id: self._launch_command(cmd))
            self.builtin_grid.add(tile)
            self._tiles.append(tile)

        entries = self.ctx.app_registry.entries[:MAX_TILES]
        for entry in entries:
            tile = AppTile(
                self.ctx, entry.id, entry.name, self.ctx.icons.file_icon(entry),
                entry.comment or entry.path or entry.target,
            )
            tile.clicked.connect(lambda _checked=False, item=entry: self._launch_entry(item))
            self.installed_grid.add(tile)
            self._tiles.append(tile)

        recent = self.ctx.app_registry.recent(3)
        if recent:
            names = ", ".join(item["name"] for item in recent)
            self.recent_label.setText(f"Recently used: {names}")
        else:
            self.recent_label.setText("")

        loading = self.ctx.app_registry.loading
        self.installed_title.setText(
            "Installed applications (scanning…)" if loading and not entries else "Installed applications"
        )
        self._apply_filter(self.search.text())
        if self._tiles and self._index < 0:
            self._select(0)

    # ----------------------------------------------------------------- filter
    def _apply_filter(self, text: str) -> None:
        query = text.strip()
        visible_tiles: list[AppTile] = []
        for tile in self._tiles:
            label = tile.text()
            if query:
                from deskos.utils.fuzzy import fuzzy_score

                matches = fuzzy_score(query, label) is not None
            else:
                matches = True
            tile.setVisible(matches)
            if matches:
                visible_tiles.append(tile)
        self._visible = visible_tiles
        self.results_label.setText(
            f"{len(visible_tiles)} matching applications" if query else "All applications"
        )
        if visible_tiles:
            self._select(0)
        else:
            self._index = -1

    def _select(self, index: int) -> None:
        if not getattr(self, "_visible", None):
            return
        index = max(0, min(len(self._visible) - 1, index))
        for position, tile in enumerate(self._visible):
            tile.setProperty("active", position == index)
            tile.style().unpolish(tile)
            tile.style().polish(tile)
        self._index = index
        self._visible[index].setFocus()

    def _move_selection(self, delta: int) -> None:
        if getattr(self, "_visible", None):
            self._select(self._index + delta)

    # ------------------------------------------------------------- activation
    def _launch_command(self, command: str) -> None:
        self.hide()
        self.ctx.services["launcher"].launch_command(command)

    def _launch_entry(self, entry: AppEntry) -> None:
        self.hide()
        self.ctx.services["launcher"].launch_entry(entry)

    def _activate_current(self) -> None:
        if not getattr(self, "_visible", None):
            return
        tile = self._visible[max(0, self._index)]
        tile.click()

    # ---------------------------------------------------------------- events
    def eventFilter(self, watched, event) -> None:  # noqa: N802
        if watched is self.search and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Right):
                self._move_selection(1)
                return True
            if key in (Qt.Key.Key_Up, Qt.Key.Key_Left):
                self._move_selection(-1)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._activate_current()
                return True
            if key == Qt.Key.Key_Escape:
                self.hide()
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._activate_current()
            return
        if event.key() == Qt.Key.Key_Down:
            self._move_selection(1)
            return
        if event.key() == Qt.Key.Key_Up:
            self._move_selection(-1)
            return
        super().keyPressEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.search.setFocus()
