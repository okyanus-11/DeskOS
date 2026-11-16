"""Plugins page: installed plugins, permissions, enablement and errors."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from deskos.core.context import DeskOSContext
from deskos.core.paths import user_plugins_dir
from deskos.plugins.api import ALLOWED_PERMISSIONS
from deskos.ui.components import Card, Muted, SectionTitle, scrollable

log = logging.getLogger(__name__)


class PluginsPage(QWidget):
    def __init__(self, context: DeskOSContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = context

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 10, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Plugins")
        title.setObjectName("Heading")
        layout.addWidget(title)
        layout.addWidget(
            Muted(
                "Plugins run inside the DeskOS process and receive only the API described in "
                "docs/PLUGIN_DEVELOPMENT.md. Permissions are an explicit contract, not a sandbox."
            )
        )

        body = QHBoxLayout()
        body.setSpacing(14)

        list_card = Card()
        list_header = QHBoxLayout()
        list_header.addWidget(SectionTitle("Installed plugins"))
        list_header.addStretch(1)
        reload_button = QPushButton("Reload all")
        reload_button.clicked.connect(self._reload)
        list_header.addWidget(reload_button)
        list_card.layout.addLayout(list_header)
        self.plugin_list = QListWidget()
        self.plugin_list.setMinimumWidth(300)
        self.plugin_list.currentRowChanged.connect(self._show_details)
        list_card.layout.addWidget(self.plugin_list, 1)
        self.plugin_list.setMinimumHeight(340)
        body.addWidget(list_card, 1)

        self.detail_card = Card()
        self.detail_card.layout.addWidget(SectionTitle("Details"))
        self.name_label = QLabel("Select a plugin")
        self.name_label.setObjectName("Subheading")
        self.detail_card.layout.addWidget(self.name_label)
        self.meta_label = Muted("")
        self.detail_card.layout.addWidget(self.meta_label)
        self.description_label = Muted("")
        self.description_label.setWordWrap(True)
        self.detail_card.layout.addWidget(self.description_label)
        self.permissions_label = Muted("")
        self.permissions_label.setWordWrap(True)
        self.detail_card.layout.addWidget(self.permissions_label)
        self.status_label = Muted("")
        self.status_label.setWordWrap(True)
        self.detail_card.layout.addWidget(self.status_label)

        self.enable_box = QCheckBox("Enable this plugin")
        self.enable_box.toggled.connect(self._toggle_enabled)
        self.detail_card.layout.addWidget(self.enable_box)
        self.detail_card.layout.addStretch(1)

        button_row = QHBoxLayout()
        open_folder = QPushButton("Open plugin folder")
        open_folder.clicked.connect(self._open_folder)
        button_row.addWidget(open_folder)
        button_row.addStretch(1)
        self.detail_card.layout.addLayout(button_row)
        body.addWidget(self.detail_card, 2)
        layout.addLayout(body)

        self.folder_label = Muted("")
        layout.addWidget(self.folder_label)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scrollable(container))
        self._records = []
        self.refresh()

    # ------------------------------------------------------------------ state
    def refresh(self) -> None:
        if self.ctx.plugins is None:
            self.folder_label.setText("Plugin system is not available.")
            return
        self._records = self.ctx.plugins.plugins
        current = self.plugin_list.currentRow()
        self.plugin_list.blockSignals(True)
        self.plugin_list.clear()
        for record in self._records:
            status = record.status
            icon = {
                "active": "check",
                "disabled": "pause",
                "error": "alert",
                "not loaded": "plugins",
            }.get(status, "plugins")
            item = QListWidgetItem(
                self.ctx.icons.icon(
                    icon,
                    16,
                    self.ctx.theme.palette.accents["green"]
                    if status == "active"
                    else (
                        self.ctx.theme.palette.accents["red"]
                        if status == "error"
                        else self.ctx.theme.palette.subtext0
                    ),
                ),
                f"{record.metadata.name}  ·  {status}",
            )
            item.setData(Qt.ItemDataRole.UserRole, record.metadata.id)
            self.plugin_list.addItem(item)
        self.plugin_list.blockSignals(False)
        if self._records:
            self.plugin_list.setCurrentRow(min(max(current, 0), len(self._records) - 1))
        else:
            self.name_label.setText("No plugins installed")
            self.meta_label.setText("")
        self.folder_label.setText(
            f"Bundled plugins: <project>/plugins · User plugins: {user_plugins_dir()}"
        )

    def _current_record(self):
        row = self.plugin_list.currentRow()
        if 0 <= row < len(self._records):
            return self._records[row]
        return None

    def _show_details(self, _row: int) -> None:
        record = self._current_record()
        if record is None:
            return
        metadata = record.metadata
        self.name_label.setText(metadata.name)
        self.meta_label.setText(
            f"Version {metadata.version} · API v{metadata.api_version} · by {metadata.author or 'unknown'}"
            + (f"\n{metadata.homepage}" if metadata.homepage else "")
        )
        self.description_label.setText(metadata.description or "No description provided.")
        permissions = metadata.permissions or []
        if permissions:
            lines = [
                f"• {permission} — {ALLOWED_PERMISSIONS.get(permission, permission)}"
                for permission in permissions
            ]
            self.permissions_label.setText("Declared permissions:\n" + "\n".join(lines))
        else:
            self.permissions_label.setText("No permissions declared.")
        details = [f"Path: {metadata.path}", f"Status: {record.status}"]
        if record.error:
            details.append(f"Error: {record.error}")
        if record.loaded:
            details.append("Loaded and registered with the running shell.")
        self.status_label.setText("\n".join(str(item) for item in details))
        self.enable_box.blockSignals(True)
        self.enable_box.setChecked(bool(record.enabled) and not record.error)
        self.enable_box.setEnabled(not bool(record.error))
        self.enable_box.blockSignals(False)

    # ---------------------------------------------------------------- actions
    def _toggle_enabled(self, checked: bool) -> None:
        record = self._current_record()
        if record is None or self.ctx.plugins is None:
            return
        if checked:
            plugin_path = record.metadata.path
            is_user_plugin = (
                plugin_path is not None
                and plugin_path.resolve().parent == user_plugins_dir().resolve()
            )
            if is_user_plugin:
                answer = QMessageBox.warning(
                    self,
                    "Run third-party plugin code?",
                    "This user-installed plugin will execute Python code inside "
                    "DeskOS with your account's permissions. Plugin permissions "
                    "are not a security sandbox. Only enable it if you trust "
                    "its source.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    self.enable_box.blockSignals(True)
                    self.enable_box.setChecked(False)
                    self.enable_box.blockSignals(False)
                    return

        self.ctx.plugins.set_enabled(record.metadata.id, checked)
        self.refresh()
        self.ctx.toast(f"{record.metadata.name} {'enabled' if checked else 'disabled'}")

    def _reload(self) -> None:
        if self.ctx.plugins is None:
            return
        self.ctx.plugins.reload_all()
        self.refresh()
        self.ctx.toast("Plugins reloaded")

    def _open_folder(self) -> None:
        if self.ctx.plugins is not None:
            self.ctx.plugins.open_folder()
