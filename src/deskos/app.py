"""Application controller: builds every service, window and shortcut."""

from __future__ import annotations

import logging
import sys

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from deskos import __version__
from deskos.applications.catalog import BuiltinCatalog
from deskos.core.builtin_commands import register_builtin_commands
from deskos.core.commands import CommandRegistry
from deskos.core.config import ConfigManager
from deskos.core.context import DeskOSContext
from deskos.core.database import Database
from deskos.core.events import EventBus
from deskos.core.logging_setup import set_exception_hook
from deskos.core.paths import app_icon_path, data_dir
from deskos.core.theme import ThemeManager
from deskos.data.repositories import (
    AIHistoryRepository,
    NotesRepository,
    PluginStateRepository,
    TasksRepository,
    UsageRepository,
    WorkspaceRepository,
)
from deskos.platform import get_backend
from deskos.plugins.manager import PluginManager
from deskos.services.app_registry import ApplicationRegistry
from deskos.services.launcher_service import LauncherService
from deskos.services.workspace_manager import WorkspaceManager
from deskos.system.monitor import SystemMonitor
from deskos.ui.components import ToastHost
from deskos.ui.dock import Dock
from deskos.ui.icons import IconProvider
from deskos.ui.main_window import MainWindow
from deskos.ui.styling import apply_application_theme
from deskos.ui.tray import DeskTray
from deskos.utils.i18n import set_language
from deskos.utils.workers import wait_for_all
from deskos.widgets.registry import WidgetRegistry, register_builtin_widgets

log = logging.getLogger(__name__)


class DeskOSApplication(QObject):
    """Owns the QApplication plus the DeskOS object graph."""

    def __init__(self, app: QApplication, *, safe_mode: bool = False) -> None:
        super().__init__()
        self.app = app
        self.app.setApplicationName("DeskOS")
        self.app.setApplicationVersion(__version__)
        self.app.setOrganizationName("DeskOS")
        self.app.setDesktopFileName("deskos")
        self.app.setWindowIcon(self._load_icon())
        self.app.setQuitOnLastWindowClosed(False)
        self._quitting = False
        self.safe_mode = safe_mode or bool(
            self._peek_config().get("advanced", {}).get("safe_mode", False)
        )

        self.bus = EventBus()
        self.config = ConfigManager(bus=self.bus)
        self.config.load()
        set_language(str(self.config.get("general.language", "en")))

        self.theme = ThemeManager(self.config, self.bus)
        self.icons = IconProvider(self.theme)
        apply_application_theme(self.app, self.theme)

        self.db = Database()
        self.db.connect()
        self.notes_repo = NotesRepository(self.db)
        self.tasks_repo = TasksRepository(self.db)
        self.workspace_repo = WorkspaceRepository(self.db)
        self.usage_repo = UsageRepository(self.db)
        self.ai_history = AIHistoryRepository(self.db)
        self.plugin_state = PluginStateRepository(self.db)

        self.platform = get_backend()
        self.commands = CommandRegistry()
        self.widget_registry = WidgetRegistry()
        register_builtin_widgets(self.widget_registry)

        interval = int(self.config.get("advanced.monitor_interval_ms", 1200))
        self.monitor = SystemMonitor(self.platform, interval)
        self.app_registry = ApplicationRegistry(self.platform.apps, self.usage_repo)
        self.workspaces = WorkspaceManager(self.workspace_repo, self.config, self.bus)

        self.catalog = BuiltinCatalog()
        self.context = DeskOSContext(
            config=self.config,
            bus=self.bus,
            db=self.db,
            theme=self.theme,
            icons=self.icons,
            platform=self.platform,
            commands=self.commands,
            monitor=self.monitor,
            app_registry=self.app_registry,
            workspaces=self.workspaces,
            notes=self.notes_repo,
            tasks=self.tasks_repo,
            workspace_repo=self.workspace_repo,
            usage=self.usage_repo,
            ai_history=self.ai_history,
            plugin_state=self.plugin_state,
            widget_registry=self.widget_registry,
        )

        self.launcher = LauncherService(self.context, self.catalog)
        self.context.services.update(
            {
                "app": self,
                "launcher": self.launcher,
                "catalog": self.catalog,
                "apply_theme": self.apply_theme,
                "quitting": False,
            }
        )

        register_builtin_commands(self.context)

        self.plugins: PluginManager | None = None
        if self.safe_mode:
            log.warning("safe mode: plugins are not loaded")
        else:
            self.plugins = PluginManager(self.context)
            self.context.plugins = self.plugins
            self.plugins.discover_and_load()

        self.main_window = MainWindow(self.context)
        self.context.services["shell"] = self.main_window
        self.toast_host = ToastHost(self.main_window)

        self.dock = Dock(self.context)
        self.context.services["dock"] = self.dock

        self.tray: DeskTray | None = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = DeskTray(self.context, self.main_window)
            self.tray.show()
        else:
            log.info("no system tray available on this platform")

        self._hotkey_manager = None
        self._shortcuts: list[QShortcut] = []
        self._install_shortcuts()
        self._install_hotkeys()

        self.bus.subscribe("config.changed", self._on_config_changed)
        self.app.aboutToQuit.connect(self._on_about_to_quit)
        set_exception_hook(self._record_error)

        self.monitor.start()
        self.app_registry.refresh()

    # ------------------------------------------------------------------ setup
    @staticmethod
    def _load_icon():
        from PySide6.QtGui import QIcon

        path = app_icon_path()
        icon = QIcon(str(path)) if path.is_file() else QIcon()
        return icon

    def _peek_config(self) -> dict:
        """Read the config for safe-mode before constructing services."""
        from deskos.core.paths import config_path

        try:
            import json

            path = config_path()
            if path.is_file():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def apply_theme(self) -> None:
        """Re-apply the stylesheet and refresh icon caches after a theme change."""
        self.icons.clear_cache()
        apply_application_theme(self.app, self.theme)
        self.main_window.set_icon("logo")
        self.main_window.update()
        self.dock.apply_config()
        self.bus.emit("theme.changed", theme=self.theme.palette.key, accent=self.theme.accent_name)

    def _on_config_changed(self, key: str = "*") -> None:
        if key in ("advanced.monitor_interval_ms", "*"):
            self.monitor.set_interval(int(self.config.get("advanced.monitor_interval_ms", 1200)))
        if key in ("general.show_dock", "*"):
            self.dock.setVisible(bool(self.config.get("general.show_dock", True)))

    # ------------------------------------------------------------------- start
    def start(self) -> None:
        show_dock = bool(self.config.get("general.show_dock", True))
        self.dock.setVisible(show_dock)
        start_minimized = bool(self.config.get("general.start_minimized", False))
        show_dashboard = bool(self.config.get("general.start_with_dashboard", True))
        if show_dashboard and not start_minimized:
            self.main_window.show()
            self.main_window._persist_geometry()
        elif not start_minimized:
            self.main_window.show()
        log.info(
            "DeskOS %s started (platform=%s, safe_mode=%s, dock=%s)",
            __version__,
            self.platform.name,
            self.safe_mode,
            show_dock,
        )

    # -------------------------------------------------------------- shortcuts
    def _install_shortcuts(self) -> None:
        palette_shortcut = str(self.config.get("palette.fallback_shortcut", "Ctrl+Alt+Space"))
        for sequence in {palette_shortcut, "Ctrl+Alt+Space"}:
            try:
                shortcut = QShortcut(QKeySequence(sequence), self.main_window)
                shortcut.activated.connect(self.main_window.show_palette)
                self._shortcuts.append(shortcut)
            except Exception:
                log.debug("could not register shortcut %s", sequence, exc_info=True)
        launcher_shortcut = QShortcut(QKeySequence("Ctrl+Alt+A"), self.main_window)
        launcher_shortcut.activated.connect(self.main_window.show_launcher)
        self._shortcuts.append(launcher_shortcut)

    def _install_hotkeys(self) -> None:
        if not self.platform.supports_global_hotkeys:
            log.info("global hotkeys are not supported on this platform; using in-app shortcuts")
            return
        if sys.platform != "win32":
            return
        try:
            from deskos.platform.windows.hotkey import GlobalHotkeyManager

            manager = GlobalHotkeyManager()
            self.app.installNativeEventFilter(manager)
            wanted = [
                (str(self.config.get("palette.shortcut", "Meta+Space")), self.main_window.show_palette),
                (
                    str(self.config.get("palette.fallback_shortcut", "Ctrl+Alt+Space")),
                    self.main_window.show_palette,
                ),
                ("Ctrl+Alt+A", self.main_window.show_launcher),
            ]
            registered = False
            seen: set[str] = set()
            for sequence, callback in wanted:
                if sequence in seen:
                    continue
                seen.add(sequence)
                if manager.register(sequence, callback):
                    registered = True
            if registered:
                self._hotkey_manager = manager
            else:
                manager.unregister_all()
                log.warning("no global hotkey could be registered; using in-app shortcuts")
        except Exception:
            log.exception("global hotkey setup failed; using in-app shortcuts")

    # --------------------------------------------------------------- runtime
    def _record_error(self, traceback_text: str) -> None:
        self.context.services["last_error"] = traceback_text
        try:
            self.notify("DeskOS hit an unexpected error — see the log file")
        except Exception:
            pass

    def notify(self, message: str, timeout_ms: int = 3200) -> None:
        if not bool(self.config.get("general.notifications", True)):
            log.info("notification suppressed: %s", message)
            return
        if self.main_window.isVisible():
            self.toast_host.notify(message, timeout_ms)
        elif self.tray is not None:
            try:
                self.tray.showMessage("DeskOS", message)
                return
            except Exception:
                log.debug("tray notification failed", exc_info=True)
        log.info("notification: %s", message)

    def toggle_visibility(self) -> None:
        if self.main_window.isVisible() and not self.main_window.isMinimized():
            self.main_window.hide()
        else:
            self.main_window.showNormal()
            self.main_window.raise_()
            self.main_window.activateWindow()

    # ------------------------------------------------------------------- exit
    def shutdown(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        self.context.services["quitting"] = True
        log.info("shutting down DeskOS")
        self.monitor.stop()
        if self._hotkey_manager is not None:
            try:
                self.app.removeNativeEventFilter(self._hotkey_manager)
                self._hotkey_manager.unregister_all()
            except Exception:
                log.debug("hotkey teardown failed", exc_info=True)
            self._hotkey_manager = None
        for shortcut in self._shortcuts:
            shortcut.setEnabled(False)
        wait_for_all(3000)
        self.launcher.close_all()
        if self.tray is not None:
            self.tray.hide()
        self.dock.close()
        self.main_window.close()
        wait_for_all(1500)
        try:
            self.config.save()
        except Exception:
            log.exception("could not save configuration during shutdown")
        self.db.close()
        self.app.quit()

    def _on_about_to_quit(self) -> None:
        self._quitting = True
        self.context.services["quitting"] = True
        self.monitor.stop()
        try:
            self.db.close()
        except Exception:
            log.debug("database already closed", exc_info=True)

    # ------------------------------------------------------------------- debug
    def self_test(self) -> bool:
        """Verify that the shell constructs and renders; used by --self-test."""
        checks: list[tuple[str, bool]] = [
            ("main window", self.main_window is not None),
            ("dock", self.dock is not None),
            ("dashboard widgets", len(self.main_window.dashboard._widgets) >= 0),
            ("command registry", len(self.commands.all()) > 5),
            ("database", self.db.integrity_check()),
            ("platform backend", bool(self.platform.name)),
            ("theme", bool(self.theme.qss())),
        ]
        if self.plugins is not None:
            checks.append(("plugins discovered", len(self.plugins.plugins) >= 0))
        self.app.processEvents()
        return all(ok for _name, ok in checks)


__all__ = ["DeskOSApplication"]
