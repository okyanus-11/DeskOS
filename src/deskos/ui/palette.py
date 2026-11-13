"""The universal command palette (Super+Space / Ctrl+Alt+Space)."""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from deskos.core.commands import Command
from deskos.core.context import DeskOSContext
from deskos.ui.components import Muted, SearchField, apply_shadow

log = logging.getLogger(__name__)


class CommandPaletteOverlay(QWidget):
    def __init__(self, context: DeskOSContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = context
        self._commands: list[Command] = []
        self.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle("DeskOS Command Palette")

        root = QVBoxLayout(self)
        root.setContentsMargins(80, 90, 80, 90)
        root.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

        self.panel = QWidget()
        self.panel.setObjectName("PalettePanel")
        self.panel.setFixedWidth(660)
        self.panel.setMaximumHeight(520)
        apply_shadow(self.panel, 56, 16, 150)
        root.addWidget(self.panel)

        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(10)

        self.search = SearchField(self.ctx.icons, "Type a command — try “cpu”, “terminal”, “theme”…")
        self.search.textChanged.connect(self._refresh_results)
        self.search.installEventFilter(self)
        layout.addWidget(self.search)

        self.list = QListWidget()
        self.list.setObjectName("PaletteList")
        self.list.setIconSize(QSize(18, 18))
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.setMaximumHeight(330)
        self.list.itemActivated.connect(lambda _item: self._run_current())
        self.list.itemClicked.connect(lambda _item: self._run_current())
        layout.addWidget(self.list, 1)

        footer = QHBoxLayout()
        self.category_label = QLabel("")
        self.category_label.setObjectName("Muted")
        footer.addWidget(self.category_label)
        footer.addStretch(1)
        hint = QLabel("↑ ↓ navigate · Enter run · Esc close")
        hint.setObjectName("Muted")
        footer.addWidget(hint)
        layout.addLayout(footer)

        self.empty_label = Muted("No command matches that search.")
        self.empty_label.hide()
        layout.addWidget(self.empty_label)

        self.ctx.commands.add_listener(self._refresh_results)
        self._refresh_results("")

    # -------------------------------------------------------------------- open
    def open_overlay(self) -> None:
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is not None:
            geometry = screen.availableGeometry()
            self.setGeometry(geometry)
        self._refresh_results("")
        self.search.clear()
        self.show()
        self.raise_()
        self.activateWindow()
        self.search.setFocus()
        if self.list.count():
            self.list.setCurrentRow(0)

    # ----------------------------------------------------------------- results
    def _refresh_results(self, text: str = "") -> None:
        if isinstance(text, Command):  # registry listener calls without args
            text = self.search.text()
        query = text if isinstance(text, str) else self.search.text()
        self._commands = self.ctx.commands.search(query)
        self.list.clear()
        for command in self._commands:
            item = QListWidgetItem(
                self.ctx.icons.icon(command.icon, 18, self.ctx.theme.palette.subtext1),
                command.title,
            )
            detail = command.category
            if command.shortcut:
                detail += f"  ·  {command.shortcut}"
            item.setToolTip(command.description or command.title)
            item.setData(Qt.ItemDataRole.UserRole, command.id)
            item.setText(f"{command.title}\n{detail}")
            self.list.addItem(item)
        self.empty_label.setVisible(not self._commands)
        if self._commands:
            self.list.setCurrentRow(0)
            self.category_label.setText(
                f"{len(self._commands)} commands · {self._commands[0].category}"
            )
        else:
            self.category_label.setText("")

    def _current_command(self) -> Command | None:
        item = self.list.currentItem()
        if item is None:
            return None
        command_id = item.data(Qt.ItemDataRole.UserRole)
        return self.ctx.commands.get(str(command_id))

    def _run_current(self) -> None:
        command = self._current_command()
        if command is None:
            return
        self.hide()
        self.ctx.services["launcher"].launch_command(command.id)

    # ------------------------------------------------------------------ events
    def eventFilter(self, watched, event) -> None:  # noqa: N802
        if watched is self.search and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Down:
                self.list.setCurrentRow(min(self.list.count() - 1, self.list.currentRow() + 1))
                return True
            if key == Qt.Key.Key_Up:
                self.list.setCurrentRow(max(0, self.list.currentRow() - 1))
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._run_current()
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
            self._run_current()
            return
        super().keyPressEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.search.setFocus()
        QTimer.singleShot(30, lambda: self.list.setCurrentRow(0))
