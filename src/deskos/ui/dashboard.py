"""The DeskOS dashboard: greeting, quick shortcuts and a draggable widget grid."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from deskos.core.context import DeskOSContext
from deskos.system.monitor import MonitorSnapshot
from deskos.ui.components import (
    IconButton,
    Muted,
    SectionTitle,
    clear_layout,
    scrollable,
)
from deskos.ui.dialogs import WidgetSettingsDialog
from deskos.widgets.base import WIDGET_MIME_TYPE, DeskWidget, WidgetContext

log = logging.getLogger(__name__)


class WidgetGrid(QWidget):
    """Grid container that accepts widget drops for reordering."""

    widget_dropped = Signal(str, object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasFormat(WIDGET_MIME_TYPE):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasFormat(WIDGET_MIME_TYPE):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802
        if not event.mimeData().hasFormat(WIDGET_MIME_TYPE):
            event.ignore()
            return
        try:
            payload = json.loads(bytes(event.mimeData().data(WIDGET_MIME_TYPE)).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            event.ignore()
            return
        widget_type = str(payload.get("type", ""))
        if widget_type:
            self.widget_dropped.emit(widget_type, event.position().toPoint())
            event.acceptProposedAction()
        else:
            event.ignore()


class DashboardView(QWidget):
    def __init__(self, ctx: DeskOSContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.theme = ctx.theme
        self.icons = ctx.icons
        self._widgets: dict[str, DeskWidget] = {}
        self._entries: list[dict[str, Any]] = []
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(30_000)
        self._refresh_timer.timeout.connect(self._refresh_greeting)

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 8, 26, 18)
        root.setSpacing(16)

        root.addLayout(self._build_header())

        self.shortcuts = QHBoxLayout()
        self.shortcuts.setSpacing(10)
        root.addLayout(self.shortcuts)

        self.grid_host = WidgetGrid()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(14)
        self.grid_host.widget_dropped.connect(self._on_widget_dropped)
        root.addWidget(scrollable(self.grid_host), 1)

        self._wallpaper: QPixmap | None = None
        self._wallpaper_scaled: QPixmap | None = None
        self._wallpaper_scaled_size: tuple[int, int] | None = None
        self._load_wallpaper()
        self.rebuild()
        ctx.bus.subscribe("workspace.changed", self._on_workspace_changed)
        ctx.bus.subscribe("theme.changed", lambda **_: self.rebuild())
        ctx.bus.subscribe("wallpaper.changed", lambda **_: self._load_wallpaper())
        ctx.monitor.sampled.connect(self.on_snapshot)
        self._refresh_greeting()
        self._refresh_timer.start()

    # ------------------------------------------------------------- wallpaper
    def _load_wallpaper(self) -> None:
        path = str(self.ctx.config.get("appearance.wallpaper", "") or "")
        if not path:
            self._wallpaper = None
            self._wallpaper_scaled = None
            self._wallpaper_scaled_size = None
            self.update()
            return
        pixmap = QPixmap(path)
        self._wallpaper = pixmap if not pixmap.isNull() else None
        self._wallpaper_scaled = None
        self._wallpaper_scaled_size = None
        if pixmap.isNull():
            log.warning("wallpaper could not be loaded: %s", path)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if self._wallpaper is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        available = self.rect()
        target_size = (available.width(), available.height())
        if (
            self._wallpaper_scaled is None
            or self._wallpaper_scaled_size != target_size
        ):
            self._wallpaper_scaled = self._wallpaper.scaled(
                available.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._wallpaper_scaled_size = target_size
        scaled = self._wallpaper_scaled
        source_x = max(0, (scaled.width() - available.width()) // 2)
        source_y = max(0, (scaled.height() - available.height()) // 2)
        painter.drawPixmap(
            available,
            scaled,
            QRect(source_x, source_y, available.width(), available.height()),
        )
        # Keep text legible over photography.
        painter.fillRect(
            available,
            QColor(self.theme.palette.base).darker(115),
        )
        painter.fillRect(available, QColor(0, 0, 0, 90 if self.theme.palette.is_dark else 40))
        painter.end()

    # ---------------------------------------------------------------- header
    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(14)
        column = QVBoxLayout()
        column.setSpacing(2)
        self.greeting = QLabel("Welcome back")
        self.greeting.setObjectName("Heading")
        self.subtitle = Muted("")
        column.addWidget(self.greeting)
        column.addWidget(self.subtitle)
        header.addLayout(column)
        header.addStretch(1)

        self.workspace_combo = QComboBox()
        self.workspace_combo.setMinimumWidth(170)
        self.workspace_combo.setToolTip("Active workspace")
        self.workspace_combo.currentIndexChanged.connect(self._on_workspace_selected)
        header.addWidget(self.workspace_combo)

        self.add_button = QPushButton("Add widget")
        self.add_button.setObjectName("SecondaryButton")
        self.add_button.setIcon(self.icons.icon("plus", 15))
        self.add_button.clicked.connect(self._show_add_menu)
        header.addWidget(self.add_button)

        self.customize_button = QPushButton("Customize")
        self.customize_button.setIcon(self.icons.icon("palette", 15))
        self.customize_button.clicked.connect(self._open_control_center)
        header.addWidget(self.customize_button)
        return header

    def _refresh_greeting(self) -> None:
        hour = datetime.now().hour
        if hour < 5:
            greeting = "Working late"
        elif hour < 12:
            greeting = "Good morning"
        elif hour < 18:
            greeting = "Good afternoon"
        else:
            greeting = "Good evening"
        workspace = self.ctx.workspaces.active()
        self.greeting.setText(f"{greeting}, {workspace.name}")
        self.subtitle.setText(
            datetime.now().strftime("%A, %d %B %Y · ") + f"{len(self._widgets)} widgets active"
        )
        self._sync_workspace_combo()

    def _sync_workspace_combo(self) -> None:
        self.workspace_combo.blockSignals(True)
        self.workspace_combo.clear()
        for workspace in self.ctx.workspaces.list():
            self.workspace_combo.addItem(
                self.icons.icon(workspace.icon or "workspace", 14), workspace.name, workspace.id
            )
        index = self.workspace_combo.findData(self.ctx.workspaces.active_id)
        if index >= 0:
            self.workspace_combo.setCurrentIndex(index)
        self.workspace_combo.blockSignals(False)

    def _on_workspace_selected(self, _index: int) -> None:
        workspace_id = self.workspace_combo.currentData()
        if workspace_id and workspace_id != self.ctx.workspaces.active_id:
            self.ctx.workspaces.switch(str(workspace_id))

    def _on_workspace_changed(self, **_payload: Any) -> None:
        self.rebuild()

    def _open_control_center(self) -> None:
        launcher = self.ctx.services.get("launcher")
        if launcher is not None:
            launcher.open_settings()

    def _show_add_menu(self) -> None:
        menu = QMenu(self)
        existing = {entry.get("type") for entry in self._entries}
        added = 0
        for spec in self.ctx.widget_registry.specs():
            if spec.type in existing:
                continue
            action = menu.addAction(self.icons.icon(spec.icon, 16), spec.title)
            action.setToolTip(spec.description)
            action.triggered.connect(lambda _checked=False, t=spec.type: self.add_widget(t))
            added += 1
        if not added:
            menu.addAction("All widgets are already on the dashboard").setEnabled(False)
        menu.exec(self.add_button.mapToGlobal(QPoint(0, self.add_button.height())))

    # --------------------------------------------------------------- widgets
    def rebuild(self) -> None:
        clear_layout(self.grid)
        self._widgets.clear()
        self._entries = [
            dict(entry)
            for entry in self.ctx.workspaces.widget_layout()
            if isinstance(entry, dict) and entry.get("enabled", True)
        ]
        columns = max(2, min(6, self.ctx.workspaces.columns()))
        row = 0
        column = 0
        for entry in self._entries:
            widget_type = str(entry.get("type", ""))
            spec = self.ctx.widget_registry.get(widget_type)
            if spec is None:
                log.warning("workspace references unknown widget %r", widget_type)
                continue
            context = WidgetContext(
                ctx=self.ctx,
                icons=self.icons,
                settings=dict(entry.get("settings") or {}),
                save_settings=lambda settings, t=widget_type: self._save_widget_settings(t, settings),
            )
            widget = self.ctx.widget_registry.create(widget_type, context)
            if widget is None:
                continue
            widget.request_remove.connect(self.remove_widget)
            widget.request_settings.connect(self.open_widget_settings)
            widget.request_move.connect(self.move_widget)
            span = max(1, min(columns, int(entry.get("span", spec.default_span) or 1)))
            if column + span > columns:
                row += 1
                column = 0
            self.grid.addWidget(widget, row, column, 1, span)
            self._widgets[widget_type] = widget
            column += span
            if column >= columns:
                row += 1
                column = 0
        for index in range(columns):
            self.grid.setColumnStretch(index, 1)
        if not self._widgets:
            empty = QLabel("No widgets yet — use “Add widget” to build your dashboard.")
            empty.setObjectName("Muted")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.grid.addWidget(empty, 0, 0, 1, columns)
        self._rebuild_shortcuts()
        self._refresh_greeting()
        if self.ctx.monitor.latest is not None:
            self.on_snapshot(self.ctx.monitor.latest)

    def _rebuild_shortcuts(self) -> None:
        clear_layout(self.shortcuts)
        if not self.ctx.config.get("dashboard.show_shortcuts", True):
            return
        label = SectionTitle("Shortcuts")
        self.shortcuts.addWidget(label, 0, Qt.AlignmentFlag.AlignVCenter)
        launcher = self.ctx.services.get("launcher")
        catalog = self.ctx.services.get("catalog")
        for shortcut in self.ctx.config.get("dashboard.shortcuts", []):
            command = str(shortcut.get("command", ""))
            label_text = str(shortcut.get("label") or command)
            app = catalog.get(command) if catalog else None
            button = QPushButton(label_text)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setIcon(
                self.icons.icon(app.icon if app else "play", 15, self.theme.palette.subtext1)
            )
            button.setToolTip(app.description if app else command)
            button.clicked.connect(
                lambda _checked=False, c=command: launcher.launch_command(c) if launcher else None
            )
            self.shortcuts.addWidget(button)
        self.shortcuts.addStretch(1)

    def add_widget(self, widget_type: str) -> None:
        if any(entry.get("type") == widget_type for entry in self._entries):
            return
        self._entries.append({"type": widget_type, "enabled": True, "settings": {}})
        self._persist()
        self.rebuild()

    def remove_widget(self, widget_type: str) -> None:
        self._entries = [entry for entry in self._entries if entry.get("type") != widget_type]
        self._persist()
        self.rebuild()
        self.ctx.toast(f"Removed {widget_type} widget")

    def move_widget(self, widget_type: str, delta: int) -> None:
        index = next(
            (i for i, entry in enumerate(self._entries) if entry.get("type") == widget_type), -1
        )
        if index < 0:
            return
        target = max(0, min(len(self._entries) - 1, index + delta))
        if target == index:
            return
        entry = self._entries.pop(index)
        self._entries.insert(target, entry)
        self._persist()
        self.rebuild()

    def _on_widget_dropped(self, widget_type: str, position: QPoint) -> None:
        index = next(
            (i for i, entry in enumerate(self._entries) if entry.get("type") == widget_type), -1
        )
        if index < 0:
            return
        target = len(self._entries) - 1
        for position_index, widget in enumerate(self._widgets.values()):
            if widget.geometry().contains(position):
                target = position_index
                break
        if target == index:
            return
        entry = self._entries.pop(index)
        self._entries.insert(target, entry)
        self._persist()
        self.rebuild()

    def _save_widget_settings(self, widget_type: str, settings: dict[str, Any]) -> None:
        for entry in self._entries:
            if entry.get("type") == widget_type:
                entry["settings"] = dict(settings)
                break
        self._persist()
        widget = self._widgets.get(widget_type)
        if widget is not None:
            widget.apply_settings(dict(settings))

    def open_widget_settings(self, widget_type: str) -> None:
        widget = self._widgets.get(widget_type)
        if widget is None:
            return
        dialog = WidgetSettingsDialog(self, widget, self.ctx)
        if dialog.exec():
            self.rebuild()

    def _persist(self) -> None:
        try:
            self.ctx.workspaces.set_widgets(self._entries)
        except Exception:
            log.exception("could not persist widget layout")

    def on_snapshot(self, snapshot: MonitorSnapshot) -> None:
        for widget in self._widgets.values():
            try:
                widget.refresh(snapshot)
            except Exception:
                log.exception("widget %s failed to refresh", widget.widget_type)
