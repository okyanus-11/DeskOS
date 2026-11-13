"""Window and application launching for built-in and discovered apps.

A single service owns the "one window per application" rule, records launches
for the recent/most-used lists, and routes ``app.*`` commands from the dock, the
launcher and the command palette.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QObject, Signal

from deskos.applications.base import DeskAppWindow
from deskos.applications.catalog import BuiltinCatalog
from deskos.core.context import DeskOSContext
from deskos.platform.base import AppEntry, LaunchError

log = logging.getLogger(__name__)


class LauncherService(QObject):
    window_opened = Signal(str, object)
    launch_failed = Signal(str, str)

    def __init__(self, context: DeskOSContext, catalog: BuiltinCatalog, parent=None) -> None:
        super().__init__(parent)
        self.ctx = context
        self.catalog = catalog
        self._windows: dict[str, Any] = {}

    # --------------------------------------------------------------- built-ins
    def open_builtin(self, app_id: str) -> Any | None:
        app = self.catalog.get(app_id)
        if app is None:
            log.warning("unknown built-in app %s", app_id)
            return None
        existing = self._windows.get(app_id)
        if existing is not None:
            try:
                existing.showNormal()
                existing.raise_()
                existing.activateWindow()
                if hasattr(existing, "page"):
                    existing.page.on_activated()
                return existing
            except RuntimeError:
                self._windows.pop(app_id, None)

        try:
            page = app.create_page(self.ctx)
            window = DeskAppWindow(
                self.ctx, app.title, app.icon, page, app.width, app.height, app.description
            )
            window.closed.connect(lambda i=app_id: self._forget(i))
            self._windows[app_id] = window
            window.show_centered()
            self._record(app_id, app.title)
            self.window_opened.emit(app_id, window)
            return window
        except Exception as exc:
            log.exception("failed to open %s", app_id)
            self.launch_failed.emit(app_id, str(exc))
            self.ctx.toast(f"Could not open {app.title}: {exc}")
            return None

    def open_settings(self, page: str | None = None) -> Any | None:
        window = self._windows.get("app.settings")
        if window is None:
            from deskos.control_center.window import ControlCenterWindow

            window = ControlCenterWindow(self.ctx)
            window.closed.connect(lambda: self._forget("app.settings"))
            self._windows["app.settings"] = window
            window.show_centered()
        else:
            window.showNormal()
            window.raise_()
            window.activateWindow()
        if page and hasattr(window, "select_page"):
            window.select_page(page)
        return window

    def open_ai(self) -> Any | None:
        window = self._windows.get("app.ai")
        if window is None:
            from deskos.ai.view import DeskAIWindow

            window = DeskAIWindow(self.ctx)
            window.closed.connect(lambda: self._forget("app.ai"))
            self._windows["app.ai"] = window
            window.show_centered()
        else:
            window.showNormal()
            window.raise_()
            window.activateWindow()
        return window

    def open_launcher(self) -> None:
        shell = self.ctx.services.get("shell")
        if shell is not None:
            shell.show_launcher()

    # -------------------------------------------------------------- discovered
    def launch_entry(self, entry: AppEntry) -> bool:
        try:
            self.ctx.app_registry.launch(entry)
        except LaunchError as exc:
            log.warning("launch failed for %s: %s", entry.name, exc)
            self.launch_failed.emit(entry.id, str(exc))
            self.ctx.toast(str(exc))
            return False
        except Exception as exc:
            log.exception("unexpected launch failure for %s", entry.name)
            self.launch_failed.emit(entry.id, str(exc))
            self.ctx.toast(f"Could not launch {entry.name}")
            return False
        self.ctx.toast(f"Launched {entry.name}", 1800)
        return True

    # ------------------------------------------------------------------ router
    def launch_command(self, command: str) -> None:
        """Launch by id: built-in app, discovered app or palette command."""
        command = (command or "").strip()
        if not command:
            return
        if command == "app.settings":
            self.open_settings()
            return
        if command == "app.ai":
            self.open_ai()
            return
        if command == "app.launcher":
            self.open_launcher()
            return
        if self.catalog.get(command) is not None:
            self.open_builtin(command)
            return
        if command.startswith("ext:"):
            entry = self.ctx.app_registry.get(command)
            if entry is None:
                self.ctx.toast("That application is no longer installed")
                return
            self.launch_entry(entry)
            return
        palette_command = self.ctx.commands.get(command)
        if (
            palette_command is not None
            and palette_command.requires_confirmation
            and bool(self.ctx.config.get("general.confirm_commands", True))
        ):
            if not self._confirm(palette_command):
                return
        result = self.ctx.commands.execute(command)
        if not result.ok:
            self.ctx.toast(result.error or f"Command {command} failed")

    def _confirm(self, command) -> bool:
        """Ask before running anything that shells out."""
        from PySide6.QtWidgets import QApplication, QMessageBox

        parent = QApplication.activeWindow()
        detail = command.confirm_text or command.description or command.title
        answer = QMessageBox.question(
            parent,
            "Confirm command",
            f"{detail}\n\nDeskOS runs this command as your user account.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def toggle_builtin(self, app_id: str) -> None:
        window = self._windows.get(app_id)
        if window is not None and window.isVisible():
            window.close()
        else:
            self.open_builtin(app_id)

    def is_running(self, app_id: str) -> bool:
        window = self._windows.get(app_id)
        try:
            return bool(window is not None and window.isVisible())
        except RuntimeError:
            return False

    def running_ids(self) -> set[str]:
        return {key for key in self._windows if self.is_running(key)}

    def close_all(self) -> None:
        for key, window in list(self._windows.items()):
            try:
                window.close()
            except RuntimeError:
                pass
            self._windows.pop(key, None)

    def _record(self, app_id: str, name: str) -> None:
        try:
            self.ctx.usage.record_launch(app_id, name)
        except Exception:
            log.exception("could not record launch of %s", app_id)

    def _forget(self, app_id: str) -> None:
        self._windows.pop(app_id, None)
