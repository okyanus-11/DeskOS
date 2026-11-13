"""Widget framework base classes.

A dashboard widget is a themed card with a header (icon, title, menu) and a body
that subclasses fill.  Widgets receive system snapshots from the dashboard's
single monitor subscription, so adding widgets does not add polling.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QMimeData, QPoint, Qt, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from deskos.core.context import DeskOSContext
from deskos.system.monitor import MonitorSnapshot
from deskos.ui.components import IconButton
from deskos.ui.icons import IconProvider

WIDGET_MIME_TYPE = "application/x-deskos-widget"


@dataclass
class WidgetContext:
    """Everything a widget needs, without global state."""

    ctx: DeskOSContext
    icons: IconProvider
    settings: dict[str, Any] = field(default_factory=dict)
    save_settings: Callable[[dict[str, Any]], None] = lambda settings: None

    @property
    def monitor(self):
        return self.ctx.monitor


class DeskWidget(QFrame):
    """Base dashboard widget."""

    widget_type: str = "base"
    title: str = "Widget"
    icon: str = "dashboard"
    description: str = ""
    default_span: int = 1
    minimum_body_height: int = 110

    request_remove = Signal(str)
    request_settings = Signal(str)
    request_move = Signal(str, int)

    def __init__(self, context: WidgetContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.ctx = context.ctx
        self.theme = context.ctx.theme
        self.icons = context.icons
        self._drag_origin: QPoint | None = None

        self.setObjectName("WidgetCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(self.minimum_body_height + 54)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 14)
        outer.setSpacing(8)

        self.header = QWidget()
        self.header.setObjectName("WidgetHeader")
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        self.header.setCursor(Qt.CursorShape.OpenHandCursor)
        self.header.setToolTip("Drag to rearrange this widget")

        self.icon_label = QLabel()
        self.icon_label.setPixmap(self.icons.pixmap(self.icon, 16, self.theme.palette.subtext1))
        header_layout.addWidget(self.icon_label)
        self.title_label = QLabel(self.title)
        self.title_label.setObjectName("SectionTitle")
        header_layout.addWidget(self.title_label)
        header_layout.addStretch(1)

        self.menu_button = IconButton(self.icons, "more", "Widget options", 26, 14)
        self.menu_button.clicked.connect(self._show_menu)
        header_layout.addWidget(self.menu_button)
        outer.addWidget(self.header)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(8)
        outer.addWidget(self.body, 1)

        self.build()
        self.apply_settings(context.settings)

    # ------------------------------------------------------------- subclassing
    def build(self) -> None:
        """Create the widget's content inside ``self.body_layout``."""

    def refresh(self, snapshot: MonitorSnapshot | None) -> None:
        """Update from the shared system snapshot."""

    def build_settings_form(self) -> QWidget | None:
        """Return a form for per-widget options, or ``None`` when there are none."""
        return None

    def collect_settings(self) -> dict[str, Any]:
        """Read the form and return the settings to persist."""
        return dict(self.context.settings)

    def apply_settings(self, settings: dict[str, Any]) -> None:
        """Apply persisted settings (called after construction and edits)."""
        self.context.settings = dict(settings or {})

    # ---------------------------------------------------------------- actions
    def _show_menu(self) -> None:
        menu = QMenu(self)
        menu.addAction(self.icons.icon("settings", 16), "Widget settings…", self._open_settings)
        menu.addAction(self.icons.icon("arrow-up", 16), "Move earlier", lambda: self.request_move.emit(self.widget_type, -1))
        menu.addAction(self.icons.icon("arrow-down", 16), "Move later", lambda: self.request_move.emit(self.widget_type, 1))
        menu.addSeparator()
        menu.addAction(self.icons.icon("trash", 16), "Remove widget", lambda: self.request_remove.emit(self.widget_type))
        menu.exec(self.menu_button.mapToGlobal(QPoint(0, self.menu_button.height())))

    def _open_settings(self) -> None:
        self.request_settings.emit(self.widget_type)

    # ------------------------------------------------------------------- drag
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.header.underMouse():
            self._drag_origin = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_origin is None:
            return super().mouseMoveEvent(event)
        distance = (event.position().toPoint() - self._drag_origin).manhattanLength()
        if distance < 12:
            return super().mouseMoveEvent(event)

        drag = QDrag(self)
        mime = QMimeData()
        payload = json.dumps({"type": self.widget_type}).encode("utf-8")
        mime.setData(WIDGET_MIME_TYPE, payload)
        drag.setMimeData(mime)
        preview = self.grab()
        drag.setPixmap(preview.scaledToWidth(min(320, preview.width()), Qt.TransformationMode.SmoothTransformation))
        drag.setHotSpot(QPoint(preview.width() // 2, 18))
        drag.exec(Qt.DropAction.MoveAction)
        self._drag_origin = None

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_origin = None
        super().mouseReleaseEvent(event)
