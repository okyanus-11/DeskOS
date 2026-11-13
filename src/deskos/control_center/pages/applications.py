"""Applications settings: discovery, pinning, startup and preferences."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from deskos.core.context import DeskOSContext
from deskos.platform.base import AppEntry
from deskos.ui.components import Card, Muted, SearchField, SectionTitle, scrollable

log = logging.getLogger(__name__)


class ApplicationsPage(QWidget):
    def __init__(self, context: DeskOSContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = context
        self._entries: list[AppEntry] = []

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 10, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Applications")
        title.setObjectName("Heading")
        layout.addWidget(title)
        layout.addWidget(Muted("Manage what DeskOS starts with and which apps stay pinned."))

        startup_card = Card()
        startup_card.layout.addWidget(SectionTitle("Startup behaviour"))
        self.autostart = QCheckBox("Start DeskOS when I sign in to Windows")
        self.autostart.toggled.connect(self._toggle_autostart)
        startup_card.layout.addWidget(self.autostart)
        self.autostart_note = Muted("")
        startup_card.layout.addWidget(self.autostart_note)

        self.start_minimized = QCheckBox("Start minimised to the notification area")
        self.start_minimized.toggled.connect(
            lambda checked: self.ctx.config.set("general.start_minimized", checked)
        )
        startup_card.layout.addWidget(self.start_minimized)

        self.start_dashboard = QCheckBox("Show the dashboard on launch")
        self.start_dashboard.toggled.connect(
            lambda checked: self.ctx.config.set("general.start_with_dashboard", checked)
        )
        startup_card.layout.addWidget(self.start_dashboard)

        self.close_to_tray = QCheckBox("Keep DeskOS running when the window is closed")
        self.close_to_tray.toggled.connect(
            lambda checked: self.ctx.config.set("general.close_to_tray", checked)
        )
        startup_card.layout.addWidget(self.close_to_tray)
        layout.addWidget(startup_card)

        pinned_card = Card()
        pinned_header = QHBoxLayout()
        pinned_header.addWidget(SectionTitle("Pinned dock applications"))
        pinned_header.addStretch(1)
        move_up = QPushButton("Move up")
        move_up.clicked.connect(lambda: self._move_pin(-1))
        pinned_header.addWidget(move_up)
        move_down = QPushButton("Move down")
        move_down.clicked.connect(lambda: self._move_pin(1))
        pinned_header.addWidget(move_down)
        unpin = QPushButton("Unpin")
        unpin.clicked.connect(self._unpin_selected)
        pinned_header.addWidget(unpin)
        pinned_card.layout.addLayout(pinned_header)
        self.pinned_list = QListWidget()
        self.pinned_list.setMaximumHeight(190)
        self.pinned_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        pinned_card.layout.addWidget(self.pinned_list)
        pinned_card.layout.addWidget(
            Muted("Pin/unpin installed applications below or from the launcher's context menu.")
        )
        layout.addWidget(pinned_card)

        installed_card = Card()
        installed_header = QHBoxLayout()
        installed_header.addWidget(SectionTitle("Installed applications"))
        installed_header.addStretch(1)
        rescan = QPushButton("Rescan")
        rescan.setIcon(self.ctx.icons.icon("refresh", 15))
        rescan.clicked.connect(self._rescan)
        installed_header.addWidget(rescan)
        pin_button = QPushButton("Pin selected")
        pin_button.setObjectName("PrimaryButton")
        pin_button.clicked.connect(self._pin_selected)
        installed_header.addWidget(pin_button)
        installed_card.layout.addLayout(installed_header)

        self.search = SearchField(self.ctx.icons, "Filter installed applications…")
        self.search.textChanged.connect(self._filter_installed)
        installed_card.layout.addWidget(self.search)

        self.installed_list = QListWidget()
        self.installed_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.installed_list.setMinimumHeight(230)
        installed_card.layout.addWidget(self.installed_list)
        self.installed_note = Muted("")
        installed_card.layout.addWidget(self.installed_note)
        layout.addWidget(installed_card)
        layout.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scrollable(container))

        self.ctx.app_registry.updated.connect(self._on_registry_updated)
        self.refresh()

    # ------------------------------------------------------------------ state
    def refresh(self) -> None:
        self.start_minimized.blockSignals(True)
        self.start_dashboard.blockSignals(True)
        self.close_to_tray.blockSignals(True)
        self.autostart.blockSignals(True)

        self.start_minimized.setChecked(bool(self.ctx.config.get("general.start_minimized", False)))
        self.start_dashboard.setChecked(
            bool(self.ctx.config.get("general.start_with_dashboard", True))
        )
        self.close_to_tray.setChecked(bool(self.ctx.config.get("general.close_to_tray", True)))
        try:
            self.autostart.setChecked(self.ctx.platform.autostart.is_enabled())
        except Exception:
            self.autostart.setChecked(False)
        self.autostart_note.setText(
            f"Implemented through {self.ctx.platform.autostart.mechanism()}"
        )

        for widget in (self.start_minimized, self.start_dashboard, self.close_to_tray, self.autostart):
            widget.blockSignals(False)

        self._populate_pinned()
        self._entries = self.ctx.app_registry.entries
        self._populate_installed()

    def _populate_pinned(self) -> None:
        self.pinned_list.clear()
        catalog = self.ctx.services["catalog"]
        for command in self.ctx.workspaces.pinned_commands():
            app = catalog.get(command)
            if app is not None:
                item = QListWidgetItem(self.ctx.icons.icon(app.icon, 16), app.title)
                item.setData(Qt.ItemDataRole.UserRole, command)
                self.pinned_list.addItem(item)
                continue
            entry = self.ctx.app_registry.get(command)
            item = QListWidgetItem(
                self.ctx.icons.icon("apps", 16),
                entry.name if entry else f"{command} (not installed)",
            )
            item.setData(Qt.ItemDataRole.UserRole, command)
            self.pinned_list.addItem(item)

    def _populate_installed(self) -> None:
        self.installed_list.clear()
        pinned = set(self.ctx.workspaces.pinned_commands())
        for entry in self._entries:
            label = f"{entry.name}  ·  {'pinned' if entry.id in pinned else entry.source}"
            item = QListWidgetItem(self.ctx.icons.file_icon(entry), label)
            item.setData(Qt.ItemDataRole.UserRole, entry.id)
            self.installed_list.addItem(item)
        self.installed_note.setText(
            f"{len(self._entries)} applications discovered · "
            + ("scanning…" if self.ctx.app_registry.loading else "cache refreshed on demand")
        )
        self._filter_installed(self.search.text())

    def _filter_installed(self, text: str) -> None:
        query = text.strip().lower()
        for row in range(self.installed_list.count()):
            item = self.installed_list.item(row)
            item.setHidden(bool(query) and query not in item.text().lower())

    def _on_registry_updated(self, _entries) -> None:
        self._entries = self.ctx.app_registry.entries
        self._populate_installed()

    # --------------------------------------------------------------- actions
    def _toggle_autostart(self, checked: bool) -> None:
        result = self.ctx.platform.autostart.set_enabled(checked)
        if result != checked:
            self.autostart.blockSignals(True)
            self.autostart.setChecked(result)
            self.autostart.blockSignals(False)
            self.ctx.toast("Could not change the autostart entry")
        else:
            self.ctx.toast("Autostart " + ("enabled" if result else "disabled"))

    def _pinned_commands(self) -> list[str]:
        return list(self.ctx.workspaces.pinned_commands())

    def _save_pins(self, commands: list[str]) -> None:
        self.ctx.config.set("dock.pinned", commands)
        self.ctx.workspaces.set_pinned(commands)
        self.ctx.bus.emit("dock.changed")
        self._populate_pinned()
        self._populate_installed()

    def _pin_selected(self) -> None:
        commands = self._pinned_commands()
        added = 0
        for item in self.installed_list.selectedItems():
            app_id = item.data(Qt.ItemDataRole.UserRole)
            if app_id and app_id not in commands:
                commands.append(str(app_id))
                added += 1
        if added:
            self._save_pins(commands)
            self.ctx.toast(f"Pinned {added} application(s)")

    def _unpin_selected(self) -> None:
        item = self.pinned_list.currentItem()
        if item is None:
            return
        app_id = str(item.data(Qt.ItemDataRole.UserRole))
        commands = [command for command in self._pinned_commands() if command != app_id]
        self._save_pins(commands)

    def _move_pin(self, delta: int) -> None:
        item = self.pinned_list.currentItem()
        if item is None:
            return
        app_id = str(item.data(Qt.ItemDataRole.UserRole))
        commands = self._pinned_commands()
        if app_id not in commands:
            return
        index = commands.index(app_id)
        target = max(0, min(len(commands) - 1, index + delta))
        if target == index:
            return
        commands.pop(index)
        commands.insert(target, app_id)
        self._save_pins(commands)
        self.pinned_list.setCurrentRow(target)

    def _rescan(self) -> None:
        self.ctx.app_registry.refresh(force=True)
        self.installed_note.setText("Rescanning installed applications…")
