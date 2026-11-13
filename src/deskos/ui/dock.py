"""DeskOS dock: pinned applications, clock, system status and quick settings.

The dock lives next to the native Windows taskbar (it never replaces it), can be
placed at the top or bottom of the screen, resized, made translucent, and set to
auto-hide behind an activation strip.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import psutil
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from deskos.applications.catalog import BuiltinCatalog
from deskos.core.context import DeskOSContext
from deskos.system.monitor import MonitorSnapshot
from deskos.ui.components import Divider, IconButton, apply_shadow
from deskos.platform.base import AppEntry

log = logging.getLogger(__name__)


class ActivationStrip(QWidget):
    """Thin invisible strip at the screen edge that reveals an auto-hidden dock."""

    def __init__(self, on_enter) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self._on_enter = on_enter
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: rgba(0, 0, 0, 8);")
        self.setToolTip("Show the DeskOS dock")

    def enterEvent(self, event) -> None:  # noqa: N802
        self._on_enter()
        super().enterEvent(event)


class DockItem(QWidget):
    """A single dock button with a running indicator dot."""

    def __init__(
        self,
        context: DeskOSContext,
        command: str,
        label: str,
        icon,
        size: int,
        on_click,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.context = context
        self.command = command
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)
        self.button = QPushButton()
        self.button.setObjectName("DockButton")
        self.button.setFixedSize(size, size)
        self.button.setIcon(icon)
        self.button.setIconSize(self.button.size() * 0.55)
        self.button.setToolTip(label)
        self.button.setAccessibleName(label)
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.clicked.connect(on_click)
        layout.addWidget(self.button, 0, Qt.AlignmentFlag.AlignHCenter)
        self.indicator = QFrame()
        self.indicator.setFixedSize(4, 4)
        self.indicator.setStyleSheet(
            f"background: {context.theme.accent}; border-radius: 2px;"
        )
        self.indicator.setVisible(False)
        layout.addWidget(self.indicator, 0, Qt.AlignmentFlag.AlignHCenter)

    def set_running(self, running: bool) -> None:
        self.indicator.setVisible(running)

    def set_icon(self, icon) -> None:
        self.button.setIcon(icon)


class Dock(QWidget):
    def __init__(self, context: DeskOSContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = context
        self.catalog: BuiltinCatalog = context.services["catalog"]
        self.setObjectName("DockWindow")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._items: dict[str, DockItem] = {}
        self._running_names: set[str] = set()
        self._activation_strip: QWidget | None = None
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(650)
        self._hide_timer.timeout.connect(self._maybe_hide)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        self.panel = QWidget()
        self.panel.setObjectName("Dock")
        apply_shadow(self.panel, 40, 6, 130)
        outer.addWidget(self.panel)

        self.panel_layout = QHBoxLayout(self.panel)
        self.panel_layout.setContentsMargins(10, 6, 10, 6)
        self.panel_layout.setSpacing(4)

        self.launcher_button = QPushButton()
        self.launcher_button.setObjectName("DockButton")
        self.launcher_button.setToolTip("Applications (launcher)")
        self.launcher_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.launcher_button.clicked.connect(self.ctx.services["shell"].show_launcher)
        self.panel_layout.addWidget(self.launcher_button)

        self.divider = Divider(vertical=True)
        self.divider.setFixedHeight(28)
        self.panel_layout.addWidget(self.divider)

        self.items_container = QWidget()
        self.items_layout = QHBoxLayout(self.items_container)
        self.items_layout.setContentsMargins(0, 0, 0, 0)
        self.items_layout.setSpacing(2)
        self.panel_layout.addWidget(self.items_container)

        self.trailing = QHBoxLayout()
        self.trailing.setSpacing(6)
        self.panel_layout.addLayout(self.trailing)

        self.workspace_button = QPushButton()
        self.workspace_button.setObjectName("DockButton")
        self.workspace_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.workspace_button.setToolTip("Active workspace")
        self.workspace_button.clicked.connect(self._show_workspace_menu)
        self.trailing.addWidget(self.workspace_button)

        self.status_label = QLabel()
        self.status_label.setObjectName("Muted")
        self.status_label.setToolTip("Live system utilisation")
        self.trailing.addWidget(self.status_label)

        self.clock_label = QLabel()
        self.clock_label.setObjectName("Subheading")
        self.clock_label.setToolTip("Current time")
        self.trailing.addWidget(self.clock_label)

        self.settings_button = IconButton(self.ctx.icons, "settings", "Control Center", 30, 16)
        self.settings_button.clicked.connect(lambda: self.ctx.services["launcher"].open_settings())
        self.trailing.addWidget(self.settings_button)

        self.panel.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.panel.customContextMenuRequested.connect(self._show_menu)

        context.bus.subscribe("dock.changed", lambda **_: self.refresh_pins())
        context.bus.subscribe("theme.changed", lambda **_: self.apply_config())
        context.bus.subscribe("workspace.changed", lambda **_: self.refresh_pins())
        context.monitor.sampled.connect(self._on_snapshot)

        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(1000)
        self._clock_timer.timeout.connect(self._tick)
        self._clock_timer.start()

        self._running_timer = QTimer(self)
        self._running_timer.setInterval(3000)
        self._running_timer.timeout.connect(self._refresh_running)
        self._running_timer.start()

        self.refresh_pins()
        self.apply_config()
        self._tick()

    # ------------------------------------------------------------------ setup
    def refresh_pins(self) -> None:
        while self.items_layout.count():
            item = self.items_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._items.clear()

        size = max(30, int(self.ctx.config.get("dock.size", 56)) - 12)
        launcher_icon = self.ctx.icons.logo_pixmap(size)
        self.launcher_button.setFixedSize(size, size)
        self.launcher_button.setIcon(launcher_icon)
        self.launcher_button.setIconSize(launcher_icon.size() * 0.86)

        commands = self.ctx.workspaces.pinned_commands()
        launcher_service = self.ctx.services["launcher"]
        for command in commands:
            if command == "app.launcher":
                continue
            app = self.catalog.get(command)
            entry: AppEntry | None = self.ctx.app_registry.get(command) if command.startswith("ext:") else None
            if app is None and entry is None:
                continue
            label = app.title if app else entry.name  # type: ignore[union-attr]
            icon = (
                self.ctx.icons.icon(app.icon, int(size * 0.6), self.ctx.theme.palette.subtext1)
                if app
                else self.ctx.icons.file_icon(entry)  # type: ignore[arg-type]
            )
            item = DockItem(
                self.ctx,
                command,
                label,
                icon,
                size,
                lambda _checked=False, cmd=command: self._launch(cmd),
            )
            item.button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            item.button.customContextMenuRequested.connect(
                lambda position, cmd=command, widget=item: self._item_menu(cmd, widget, position)
            )
            self.items_layout.addWidget(item)
            self._items[command] = item

        self.workspace_button.setIcon(
            self.ctx.icons.icon(
                self.ctx.workspaces.active().icon or "workspace",
                16,
                self.ctx.theme.palette.subtext1,
            )
        )
        self.workspace_button.setFixedSize(max(26, size - 6), max(26, size - 6))
        self._refresh_running()
        self.adjustSize()

    def apply_config(self) -> None:
        """Re-apply size, opacity, position and stay-on-top settings."""
        always_on_top = bool(self.ctx.config.get("dock.always_on_top", False))
        flags = Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
        if always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setWindowOpacity(float(self.ctx.config.get("dock.opacity", 0.92)))
        self.ctx.icons.clear_cache()
        self.refresh_pins()
        self.reposition()
        self._setup_autohide()
        self.show()
        self.raise_()

    def _setup_autohide(self) -> None:
        autohide = bool(self.ctx.config.get("dock.autohide", False))
        if autohide:
            if self._activation_strip is None:
                self._activation_strip = ActivationStrip(self.show_dock)
            self.hide_dock()
        elif self._activation_strip is not None:
            self._activation_strip.deleteLater()
            self._activation_strip = None
            self.show_dock()

    # -------------------------------------------------------------- geometry
    def _screen(self):
        screen = QGuiApplication.screenAt(QCursor.pos())
        return screen or QGuiApplication.primaryScreen()

    def reposition(self) -> None:
        screen = self._screen()
        if screen is None:
            return
        available = screen.availableGeometry()
        self.adjustSize()
        width = self.sizeHint().width()
        height = self.sizeHint().height()
        x = available.center().x() - width // 2
        if self.ctx.config.get("dock.position", "bottom") == "top":
            y = available.top() + 6
        else:
            y = available.bottom() - height - 6
        self.move(max(available.left() + 4, x), y)
        if self._activation_strip is not None:
            strip_height = 4
            strip_width = min(520, available.width() // 2)
            strip_x = available.center().x() - strip_width // 2
            if self.ctx.config.get("dock.position", "bottom") == "top":
                strip_y = available.top()
            else:
                strip_y = available.bottom() - strip_height
            self._activation_strip.setGeometry(strip_x, strip_y, strip_width, strip_height)
            self._activation_strip.show()
            self._activation_strip.raise_()

    # ------------------------------------------------------------- behaviour
    def show_dock(self) -> None:
        self.show()
        self.raise_()

    def hide_dock(self) -> None:
        self.hide()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self.ctx.config.get("dock.autohide", False):
            self._hide_timer.start()
        super().leaveEvent(event)

    def _maybe_hide(self) -> None:
        if self.ctx.config.get("dock.autohide", False) and not self.underMouse():
            self.hide_dock()

    def _launch(self, command: str) -> None:
        launcher = self.ctx.services["launcher"]
        item = self._items.get(command)
        if item is not None:
            item.set_running(True)
        launcher.launch_command(command)

    def _tick(self) -> None:
        self.clock_label.setText(datetime.now().strftime("%H:%M"))

    def _on_snapshot(self, snapshot: MonitorSnapshot) -> None:
        if not self.ctx.config.get("dock.show_system_status", True):
            self.status_label.hide()
            return
        self.status_label.show()
        battery = snapshot.battery
        text = f"CPU {snapshot.cpu_percent:.0f}%  ·  RAM {snapshot.memory_percent:.0f}%"
        if battery:
            text += f"  ·  {battery['percent']}%{'⚡' if battery['plugged'] else ''}"
        self.status_label.setText(text)

    def _running_command_names(self) -> set[str]:
        names: set[str] = set()
        try:
            for process in psutil.process_iter(["name"]):
                name = (process.info.get("name") or "").lower()
                if name:
                    names.add(name)
        except Exception:
            log.debug("process enumeration failed", exc_info=True)
        return names

    def _refresh_running(self) -> None:
        launcher = self.ctx.services["launcher"]
        names = self._running_command_names() if any(
            command.startswith("ext:") for command in self._items
        ) else set()
        for command, item in self._items.items():
            if self.catalog.get(command) is not None:
                item.set_running(launcher.is_running(command))
                continue
            entry = self.ctx.app_registry.get(command)
            if entry is None:
                item.set_running(False)
                continue
            executable = (entry.path or entry.target or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
            item.set_running(bool(executable) and executable in names)

    def _show_workspace_menu(self) -> None:
        menu = QMenu(self)
        active = self.ctx.workspaces.active_id
        for workspace in self.ctx.workspaces.list():
            action = menu.addAction(
                self.ctx.icons.icon(workspace.icon or "workspace", 15),
                workspace.name + ("  ✓" if workspace.id == active else ""),
            )
            action.triggered.connect(
                lambda _checked=False, wid=workspace.id: self.ctx.workspaces.switch(wid)
            )
        menu.addSeparator()
        menu.addAction("Manage workspaces…", lambda: self.ctx.services["shell"].select_page("workspaces"))
        menu.exec(self.workspace_button.mapToGlobal(QPoint(0, -menu.sizeHint().height())))

    def _item_menu(self, command: str, widget: DockItem, position) -> None:
        menu = QMenu(self)
        menu.addAction("Open", lambda: self._launch(command))
        menu.addSeparator()
        menu.addAction(
            "Unpin from dock",
            lambda: self._unpin(command),
        )
        menu.exec(widget.button.mapToGlobal(position))

    def _unpin(self, command: str) -> None:
        pinned = [str(item) for item in self.ctx.config.get("dock.pinned", [])]
        if command in pinned:
            pinned.remove(command)
            self.ctx.config.set("dock.pinned", pinned)
        self.ctx.workspaces.set_pinned(pinned)
        self.ctx.bus.emit("dock.changed")
        self.ctx.toast("Unpinned from dock")

    def _show_menu(self, position) -> None:
        menu = QMenu(self)
        menu.addAction(self.ctx.icons.icon("settings", 16), "Dock settings…", lambda: self.ctx.services["launcher"].open_settings("appearance"))
        menu.addAction(
            "Auto-hide dock",
            lambda: self._toggle("dock.autohide"),
        )
        menu.addAction(
            "Always on top",
            lambda: self._toggle("dock.always_on_top"),
        )
        menu.addSeparator()
        menu.addAction("Hide dock", self.hide_dock)
        menu.exec(self.panel.mapToGlobal(position))

    def _toggle(self, key: str) -> None:
        self.ctx.config.set(key, not bool(self.ctx.config.get(key, False)))
        self.apply_config()
