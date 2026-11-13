"""The DeskOS shell window: navigation rail, pages and global overlays."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from deskos import __version__
from deskos.core.context import DeskOSContext
from deskos.ui.apps_view import AppsView
from deskos.ui.chrome import DeskWindow
from deskos.ui.components import Divider, IconButton, Muted
from deskos.ui.dashboard import DashboardView
from deskos.ui.workspaces_view import WorkspacesView
from deskos.utils.i18n import tr

log = logging.getLogger(__name__)

PAGES = ("dashboard", "applications", "workspaces")


class MainWindow(DeskWindow):
    def __init__(self, context: DeskOSContext) -> None:
        super().__init__(
            context,
            tr("app.name"),
            "logo",
            "Desktop environment companion",
            minimizable=True,
        )
        self.ctx = context
        self.setMinimumSize(940, 620)
        self.resize(
            int(context.config.get("window.width", 1280)),
            int(context.config.get("window.height", 820)),
        )

        self._launcher = None
        self._palette = None
        self._nav_buttons: dict[str, QPushButton] = {}

        # Title-bar extras: search, palette hint, AI.
        search_button = QPushButton("Search or jump to a command")
        search_button.setObjectName("GhostButton")
        search_button.setCursor(Qt.CursorShape.PointingHandCursor)
        search_button.setIcon(self.ctx.icons.icon("search", 14))
        search_button.setMinimumWidth(240)
        search_button.setToolTip("Command palette")
        search_button.clicked.connect(self.show_palette)
        self.title_bar.extra_layout.addWidget(search_button)

        ai_button = IconButton(self.ctx.icons, "ai", "Ask DeskAI", 30, 16)
        ai_button.clicked.connect(self._open_ai)
        self.title_bar.extra_layout.addWidget(ai_button)

        settings_button = IconButton(self.ctx.icons, "settings", "Control Center", 30, 16)
        settings_button.clicked.connect(self._open_settings)
        self.title_bar.extra_layout.addWidget(settings_button)

        self.body_layout.addWidget(self._build_sidebar())
        self.stack = QStackedWidget()
        self.stack.setObjectName("PageStack")
        self.dashboard = DashboardView(context)
        self.apps_view = AppsView(context)
        self.workspaces_view = WorkspacesView(context)
        for page in (self.dashboard, self.apps_view, self.workspaces_view):
            self.stack.addWidget(page)
        self.body_layout.addWidget(self.stack, 1)

        # Footer status bar
        self.footer.show()
        footer_logo = QLabel()
        footer_logo.setPixmap(self.ctx.icons.logo_pixmap(14))
        self.footer_layout.addWidget(footer_logo, 0, Qt.AlignmentFlag.AlignVCenter)
        self.footer_layout.addWidget(Muted(f"DeskOS {__version__}"))
        self.footer_layout.addStretch(1)
        self.status_dot = QLabel("●")
        self.status_dot.setObjectName("Accent")
        self.footer_layout.addWidget(self.status_dot)
        self.footer_layout.addWidget(Muted(f"{context.platform.display_name} backend"))

        self.ctx.monitor.sampled.connect(self._update_status)
        self.ctx.bus.subscribe("theme.changed", self._on_theme_changed)
        self.ctx.bus.subscribe("workspace.changed", lambda **_: self.workspaces_view.refresh())

        self.select_page("dashboard")
        QTimer.singleShot(0, self._persist_geometry)

    # --------------------------------------------------------------- sidebar
    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(208)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(6)

        brand = QWidget()
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(6, 0, 0, 0)
        brand_layout.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(self.ctx.icons.logo_pixmap(28))
        brand_layout.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(0)
        product = QLabel("DeskOS")
        product.setObjectName("TitleLabel")
        names.addWidget(product)
        tagline = Muted("Companion shell")
        names.addWidget(tagline)
        brand_layout.addLayout(names)
        brand_layout.addStretch(1)
        layout.addWidget(brand)
        layout.addSpacing(10)

        group = QButtonGroup(self)
        group.setExclusive(True)
        entries = [
            ("dashboard", "dashboard", tr("nav.dashboard")),
            ("applications", "apps", tr("nav.apps")),
            ("workspaces", "workspace", tr("nav.workspaces")),
        ]
        for key, icon, label in entries:
            button = QPushButton(label)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setIcon(self.ctx.icons.icon(icon, 17, self.ctx.theme.palette.subtext1))
            button.setIconSize(QSize(17, 17))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, name=key: self.select_page(name))
            group.addButton(button)
            layout.addWidget(button)
            self._nav_buttons[key] = button

        layout.addSpacing(12)
        layout.addWidget(Divider())
        layout.addSpacing(6)

        tools_label = QLabel("TOOLS")
        tools_label.setObjectName("SectionTitle")
        tools_label.setContentsMargins(10, 4, 0, 0)
        layout.addWidget(tools_label)

        for app_id in ("app.monitor", "app.files", "app.terminal", "app.notes", "app.tasks", "app.clock"):
            app = self.ctx.services["catalog"].get(app_id)
            if app is None:
                continue
            button = QPushButton(app.title)
            button.setObjectName("NavButton")
            button.setIcon(self.ctx.icons.icon(app.icon, 17, self.ctx.theme.palette.subtext0))
            button.setIconSize(QSize(17, 17))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _checked=False, command=app_id: self.ctx.services["launcher"].launch_command(command)
            )
            layout.addWidget(button)

        layout.addStretch(1)

        palette_row = QWidget()
        palette_layout = QHBoxLayout(palette_row)
        palette_layout.setContentsMargins(6, 0, 0, 0)
        hint = Muted("Command palette")
        palette_layout.addWidget(hint)
        palette_layout.addStretch(1)
        kbd = QLabel("Ctrl+Alt+Space")
        kbd.setObjectName("Pill")
        palette_layout.addWidget(kbd)
        layout.addWidget(palette_row)

        bottom = QHBoxLayout()
        bottom.setSpacing(4)
        theme_button = IconButton(self.ctx.icons, "moon", tr("action.toggle_theme"), 30, 16)
        theme_button.clicked.connect(self._toggle_theme)
        bottom.addWidget(theme_button)
        settings_button = IconButton(self.ctx.icons, "settings", tr("action.settings"), 30, 16)
        settings_button.clicked.connect(self._open_settings)
        bottom.addWidget(settings_button)
        ai_button = IconButton(self.ctx.icons, "ai", tr("action.ai"), 30, 16, accent=True)
        ai_button.clicked.connect(self._open_ai)
        bottom.addWidget(ai_button)
        bottom.addStretch(1)
        layout.addLayout(bottom)
        return sidebar

    # ------------------------------------------------------------------ pages
    def select_page(self, name: str) -> None:
        if name not in PAGES:
            return
        index = PAGES.index(name)
        self.stack.setCurrentIndex(index)
        button = self._nav_buttons.get(name)
        if button is not None:
            button.setChecked(True)
        if name == "applications":
            self.apps_view.refresh()
            self.ctx.app_registry.refresh()
        elif name == "workspaces":
            self.workspaces_view.refresh()
        elif name == "dashboard":
            self.dashboard.rebuild()

    def _toggle_theme(self) -> None:
        self.ctx.theme.toggle()
        self.ctx.toast(f"Theme: {self.ctx.theme.palette.label}")
        self._refresh_icons()

    def _on_theme_changed(self, **_payload: Any) -> None:
        self._refresh_icons()

    def _refresh_icons(self) -> None:
        icons = self.ctx.icons
        icons.clear_cache()
        self.title_bar.set_icon("logo")
        for key, button in self._nav_buttons.items():
            icon = {"dashboard": "dashboard", "applications": "apps", "workspaces": "workspace"}[key]
            button.setIcon(icons.icon(icon, 17, self.ctx.theme.palette.subtext1))

    def _update_status(self, snapshot) -> None:
        self.status_dot.setToolTip(
            f"CPU {snapshot.cpu_percent:.0f}% · RAM {snapshot.memory_percent:.0f}%"
        )

    # ---------------------------------------------------------------- windows
    def _open_settings(self) -> None:
        launcher = self.ctx.services.get("launcher")
        if launcher is not None:
            launcher.open_settings()

    def _open_ai(self) -> None:
        launcher = self.ctx.services.get("launcher")
        if launcher is not None:
            launcher.open_ai()

    # --------------------------------------------------------------- overlays
    def show_launcher(self) -> None:
        from deskos.ui.launcher import LauncherOverlay

        if self._launcher is None:
            self._launcher = LauncherOverlay(self.ctx, self)
        self._launcher.open_overlay()

    def show_palette(self) -> None:
        from deskos.ui.palette import CommandPaletteOverlay

        if self._palette is None:
            self._palette = CommandPaletteOverlay(self.ctx, self)
        self._palette.open_overlay()

    # ------------------------------------------------------------- behaviour
    def _persist_geometry(self) -> None:
        config = self.ctx.config
        if config.get("window.maximized"):
            self.showMaximized()
        else:
            x = config.get("window.x")
            y = config.get("window.y")
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                available = screen.availableGeometry()
                if isinstance(x, int) and isinstance(y, int):
                    if available.contains(x + 60, y + 40):
                        self.move(x, y)
                else:
                    self.move(
                        available.center().x() - self.width() // 2,
                        available.center().y() - self.height() // 2,
                    )

    def closeEvent(self, event) -> None:  # noqa: N802
        config = self.ctx.config
        config.set("window.maximized", self.isMaximized(), save=False)
        if not self.isMaximized():
            config.set("window.width", self.width(), save=False)
            config.set("window.height", self.height(), save=False)
            config.set("window.x", self.x(), save=False)
            config.set("window.y", self.y(), save=False)
        config.save()
        if config.get("general.close_to_tray", True) and not self.ctx.services.get("quitting"):
            event.ignore()
            self.hide()
            self.ctx.toast("DeskOS is still running in the notification area")
            return
        super().closeEvent(event)
