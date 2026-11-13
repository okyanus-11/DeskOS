"""Notification-area icon with the DeskOS quick menu."""

from __future__ import annotations

import logging

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from deskos.core.context import DeskOSContext

log = logging.getLogger(__name__)


class DeskTray(QSystemTrayIcon):
    def __init__(self, context: DeskOSContext, main_window) -> None:
        super().__init__(context.icons.logo_icon())
        self.ctx = context
        self.main_window = main_window
        self.setToolTip("DeskOS — desktop environment companion")

        menu = QMenu()
        show_action = QAction(context.icons.icon("dashboard", 16), "Show DeskOS", menu)
        show_action.triggered.connect(self._show_shell)
        menu.addAction(show_action)

        launcher_action = QAction(context.icons.icon("apps", 16), "Applications", menu)
        launcher_action.triggered.connect(main_window.show_launcher)
        menu.addAction(launcher_action)

        palette_action = QAction(context.icons.icon("terminal", 16), "Command palette", menu)
        palette_action.triggered.connect(main_window.show_palette)
        menu.addAction(palette_action)

        menu.addSeparator()

        ai_action = QAction(context.icons.icon("ai", 16), "DeskAI", menu)
        ai_action.triggered.connect(lambda: context.services["launcher"].open_ai())
        menu.addAction(ai_action)

        settings_action = QAction(context.icons.icon("settings", 16), "Control Center", menu)
        settings_action.triggered.connect(lambda: context.services["launcher"].open_settings())
        menu.addAction(settings_action)

        menu.addSeparator()

        quit_action = QAction(context.icons.icon("power", 16), "Quit DeskOS", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)

    def _show_shell(self) -> None:
        self.main_window.showNormal()
        self.main_window.raise_()
        self.main_window.activateWindow()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.DoubleClick,
            QSystemTrayIcon.ActivationReason.Trigger,
        ):
            self._show_shell()

    def _quit(self) -> None:
        app = self.ctx.services.get("app")
        if app is not None:
            app.shutdown()
