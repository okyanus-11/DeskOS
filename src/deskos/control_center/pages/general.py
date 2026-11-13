"""General settings: language, notifications, backup/restore and maintenance."""

from __future__ import annotations

import logging
from datetime import datetime

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from deskos import __version__
from deskos.core.context import DeskOSContext
from deskos.core.logging_setup import get_log_path
from deskos.core.paths import data_dir
from deskos.ui.components import Card, Muted, SectionTitle, scrollable
from deskos.utils.i18n import LANGUAGES, set_language

log = logging.getLogger(__name__)


class GeneralPage(QWidget):
    def __init__(self, context: DeskOSContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = context

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 10, 24, 20)
        layout.setSpacing(14)

        title = QLabel("General")
        title.setObjectName("Heading")
        layout.addWidget(title)
        layout.addWidget(Muted("Language, notifications, configuration backup and maintenance."))

        general_card = Card()
        general_card.layout.addWidget(SectionTitle("Preferences"))
        language_row = QHBoxLayout()
        language_row.addWidget(QLabel("Interface language"))
        self.language_combo = QComboBox()
        for code, label in LANGUAGES.items():
            self.language_combo.addItem(label, code)
        self.language_combo.currentIndexChanged.connect(self._on_language)
        language_row.addWidget(self.language_combo)
        language_row.addStretch(1)
        general_card.layout.addLayout(language_row)

        self.notifications = QCheckBox("Show notification toasts")
        self.notifications.toggled.connect(
            lambda checked: self.ctx.config.set("general.notifications", checked)
        )
        general_card.layout.addWidget(self.notifications)

        self.confirm_commands = QCheckBox("Ask before running custom palette commands")
        self.confirm_commands.toggled.connect(
            lambda checked: self.ctx.config.set("general.confirm_commands", checked)
        )
        general_card.layout.addWidget(self.confirm_commands)

        self.dock_visible = QCheckBox("Show the DeskOS dock")
        self.dock_visible.toggled.connect(self._toggle_dock)
        general_card.layout.addWidget(self.dock_visible)
        layout.addWidget(general_card)

        backup_card = Card()
        backup_card.layout.addWidget(SectionTitle("Configuration backup"))
        backup_card.layout.addWidget(
            Muted(
                "Export preferences (optionally including notes, tasks and workspaces) to a "
                "single .zip archive, then import it on another machine."
            )
        )
        backup_row = QHBoxLayout()
        export_config = QPushButton("Export settings…")
        export_config.setObjectName("PrimaryButton")
        export_config.clicked.connect(lambda: self._export(include_database=False))
        export_all = QPushButton("Export settings + data…")
        export_all.clicked.connect(lambda: self._export(include_database=True))
        import_button = QPushButton("Import…")
        import_button.clicked.connect(self._import)
        backup_row.addWidget(export_config)
        backup_row.addWidget(export_all)
        backup_row.addWidget(import_button)
        backup_row.addStretch(1)
        backup_card.layout.addLayout(backup_row)
        layout.addWidget(backup_card)

        maintenance_card = Card()
        maintenance_card.layout.addWidget(SectionTitle("Data & logs"))
        self.paths_label = Muted("")
        maintenance_card.layout.addWidget(self.paths_label)
        button_row = QHBoxLayout()
        open_data = QPushButton("Open data folder")
        open_data.clicked.connect(lambda: self.ctx.platform.files.open_path(str(data_dir())))
        button_row.addWidget(open_data)
        open_logs = QPushButton("Open log file")
        open_logs.clicked.connect(lambda: self.ctx.platform.files.open_path(str(get_log_path())))
        button_row.addWidget(open_logs)
        reset = QPushButton("Reset all settings")
        reset.setObjectName("DangerButton")
        reset.clicked.connect(self._reset)
        button_row.addWidget(reset)
        button_row.addStretch(1)
        maintenance_card.layout.addLayout(button_row)
        layout.addWidget(maintenance_card)

        about_card = Card()
        about_card.layout.addWidget(SectionTitle("About DeskOS"))
        about_card.layout.addWidget(
            QLabel(
                f"DeskOS {__version__} — desktop environment companion\n"
                "MIT licensed · Python, PySide6, SQLite, psutil\n"
                "DeskOS is not an operating system and does not replace Windows Explorer."
            )
        )
        about_card.layout.addWidget(
            Muted(f"Platform backend: {self.ctx.platform.display_name}")
        )
        layout.addWidget(about_card)
        layout.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scrollable(container))
        self.refresh()

    # ------------------------------------------------------------------ state
    def refresh(self) -> None:
        current = str(self.ctx.config.get("general.language", "en"))
        index = self.language_combo.findData(current)
        self.language_combo.blockSignals(True)
        self.language_combo.setCurrentIndex(max(0, index))
        self.language_combo.blockSignals(False)
        self.notifications.blockSignals(True)
        self.notifications.setChecked(bool(self.ctx.config.get("general.notifications", True)))
        self.notifications.blockSignals(False)
        self.confirm_commands.blockSignals(True)
        self.confirm_commands.setChecked(
            bool(self.ctx.config.get("general.confirm_commands", True))
        )
        self.confirm_commands.blockSignals(False)
        self.dock_visible.blockSignals(True)
        self.dock_visible.setChecked(bool(self.ctx.config.get("general.show_dock", True)))
        self.dock_visible.blockSignals(False)
        self.paths_label.setText(
            f"Data folder: {data_dir()}\nLog file: {get_log_path()}"
        )

    def _on_language(self, _index: int) -> None:
        code = str(self.language_combo.currentData())
        self.ctx.config.set("general.language", code)
        set_language(code)
        self.ctx.toast("Language preference saved — some screens update after restart")

    def _toggle_dock(self, checked: bool) -> None:
        self.ctx.config.set("general.show_dock", checked)
        dock = self.ctx.services.get("dock")
        if dock is not None:
            dock.setVisible(checked)

    # --------------------------------------------------------------- backup
    def _export(self, *, include_database: bool) -> None:
        default_name = f"deskos-backup-{datetime.now():%Y%m%d-%H%M}.zip"
        path, _filter = QFileDialog.getSaveFileName(
            self, "Export DeskOS backup", default_name, "DeskOS backup (*.zip)"
        )
        if not path:
            return
        try:
            self.ctx.config.backup_to(path, include_database=include_database)
        except Exception as exc:
            log.exception("backup export failed")
            QMessageBox.warning(self, "Export failed", str(exc))
            return
        self.ctx.toast("Backup exported")

    def _import(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self, "Import DeskOS backup", "", "DeskOS backup (*.zip)"
        )
        if not path:
            return
        answer = QMessageBox.question(
            self,
            "Import configuration",
            "Importing replaces your current DeskOS configuration "
            "(and database if the archive contains one). Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            issues = self.ctx.config.restore_from(path)
        except Exception as exc:
            log.exception("backup import failed")
            QMessageBox.warning(self, "Import failed", str(exc))
            return
        apply_theme = self.ctx.services.get("apply_theme")
        if callable(apply_theme):
            apply_theme()
        dock = self.ctx.services.get("dock")
        if dock is not None:
            dock.apply_config()
        self.refresh()
        message = "Configuration imported"
        if issues:
            message += f" ({len(issues)} validation note(s) — see the log)"
        self.ctx.toast(message)

    def _reset(self) -> None:
        answer = QMessageBox.question(
            self,
            "Reset settings",
            "Reset all DeskOS preferences to their defaults? Notes, tasks and workspaces "
            "are kept.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.ctx.config.reset()
        self.ctx.theme.apply_config()
        apply_theme = self.ctx.services.get("apply_theme")
        if callable(apply_theme):
            apply_theme()
        dock = self.ctx.services.get("dock")
        if dock is not None:
            dock.apply_config()
        self.refresh()
        self.ctx.toast("Settings reset to defaults")
