"""DeskNotes: notes with categories, tags, search and debounced autosave."""

from __future__ import annotations

import logging
from datetime import datetime

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from deskos.applications.base import AppPage
from deskos.data.repositories import Note
from deskos.ui.components import IconButton, Muted, SearchField, SectionTitle
from deskos.utils.formatting import relative_time

log = logging.getLogger(__name__)


class NotesPage(AppPage):
    def __init__(self, context, parent: QWidget | None = None) -> None:
        super().__init__(context, parent)
        self._current_id: int | None = None
        self._loading = False
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(700)
        self._save_timer.timeout.connect(self._save_current)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 6, 18, 16)
        root.setSpacing(10)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        heading = QLabel("Notes")
        heading.setObjectName("Heading")
        toolbar.addWidget(heading)
        toolbar.addStretch(1)
        self.search = SearchField(self.icons, "Search notes, tags, content…")
        self.search.setMinimumWidth(280)
        self.search.textChanged.connect(self._reload_list)
        toolbar.addWidget(self.search)
        self.new_button = QPushButton("New note")
        self.new_button.setObjectName("PrimaryButton")
        self.new_button.setIcon(self.icons.icon("plus", 15, self.theme.palette.crust))
        self.new_button.clicked.connect(self.create_note)
        toolbar.addWidget(self.new_button)
        root.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        list_panel = QWidget()
        list_layout = QVBoxLayout(list_panel)
        list_layout.setContentsMargins(0, 0, 8, 0)
        list_layout.setSpacing(8)
        list_layout.addWidget(SectionTitle("All notes"))
        self.category_filter = QComboBox()
        self.category_filter.addItem("All")
        self.category_filter.currentTextChanged.connect(self._reload_list)
        list_layout.addWidget(self.category_filter)
        self.note_list = QListWidget()
        self.note_list.setIconSize(QSize(16, 16))
        self.note_list.currentItemChanged.connect(self._on_note_selected)
        list_layout.addWidget(self.note_list, 1)
        self.count_label = Muted("")
        list_layout.addWidget(self.count_label)
        splitter.addWidget(list_panel)

        editor_panel = QWidget()
        editor_layout = QVBoxLayout(editor_panel)
        editor_layout.setContentsMargins(8, 0, 0, 0)
        editor_layout.setSpacing(8)

        meta_row = QHBoxLayout()
        self.title_field = QLineEdit()
        self.title_field.setPlaceholderText("Note title")
        font = self.title_field.font()
        font.setPixelSize(self.theme.font_px(18))
        font.setBold(True)
        self.title_field.setFont(font)
        self.title_field.textChanged.connect(self._schedule_save)
        meta_row.addWidget(self.title_field, 1)
        self.pin_button = IconButton(self.icons, "pin", "Pin note", 32, 16)
        self.pin_button.setCheckable(True)
        self.pin_button.clicked.connect(self._toggle_pin)
        meta_row.addWidget(self.pin_button)
        self.delete_button = IconButton(self.icons, "trash", "Delete note", 32, 16)
        self.delete_button.clicked.connect(self.delete_note)
        meta_row.addWidget(self.delete_button)
        editor_layout.addLayout(meta_row)

        meta_row2 = QHBoxLayout()
        meta_row2.setSpacing(8)
        self.category_field = QComboBox()
        self.category_field.setEditable(True)
        self.category_field.setMinimumWidth(160)
        self.category_field.addItems(["General", "Work", "Personal", "Ideas", "School"])
        self.category_field.currentTextChanged.connect(self._schedule_save)
        meta_row2.addWidget(self.category_field)
        self.tags_field = QLineEdit()
        self.tags_field.setPlaceholderText("Tags, comma separated")
        self.tags_field.textChanged.connect(self._schedule_save)
        meta_row2.addWidget(self.tags_field, 1)
        editor_layout.addLayout(meta_row2)

        self.body_field = QTextEdit()
        self.body_field.setPlaceholderText("Start writing… notes save automatically.")
        self.body_field.textChanged.connect(self._schedule_save)
        editor_layout.addWidget(self.body_field, 1)

        footer = QHBoxLayout()
        self.saved_label = Muted("")
        footer.addWidget(self.saved_label)
        footer.addStretch(1)
        self.meta_label = Muted("")
        footer.addWidget(self.meta_label)
        editor_layout.addLayout(footer)

        splitter.addWidget(editor_panel)
        splitter.setSizes([300, 720])
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

        self._refresh_categories()
        self._reload_list()
        notes = self.ctx.notes.list()
        if notes:
            self._select_note(notes[0].id)
        else:
            self._set_editor_enabled(False)

    # -------------------------------------------------------------------- data
    def _refresh_categories(self) -> None:
        current = self.category_filter.currentText()
        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem("All")
        for category in self.ctx.notes.categories():
            self.category_filter.addItem(category)
        index = self.category_filter.findText(current)
        self.category_filter.setCurrentIndex(max(0, index))
        self.category_filter.blockSignals(False)

    def _reload_list(self) -> None:
        category = self.category_filter.currentText() or "All"
        notes = self.ctx.notes.list(self.search.text(), None if category == "All" else category)
        self.note_list.blockSignals(True)
        self.note_list.clear()
        for note in notes:
            snippet = note.body.strip().splitlines()[0] if note.body.strip() else "No content"
            label = note.display_title
            item = QListWidgetItem(
                self.icons.icon("pin" if note.pinned else "notes", 15, self.theme.accent if note.pinned else self.theme.palette.subtext1),
                f"{label}\n{snippet[:60]}",
            )
            item.setToolTip(f"{note.display_title} · {relative_time(note.updated_at)}")
            item.setData(Qt.ItemDataRole.UserRole, note.id)
            self.note_list.addItem(item)
        self.note_list.blockSignals(False)
        self.count_label.setText(f"{len(notes)} notes · autosave enabled")
        if self._current_id is not None:
            for row in range(self.note_list.count()):
                if self.note_list.item(row).data(Qt.ItemDataRole.UserRole) == self._current_id:
                    self.note_list.setCurrentRow(row)
                    break

    def _select_note(self, note_id: int) -> None:
        note = self.ctx.notes.get(note_id)
        if note is None:
            return
        self._loading = True
        self._current_id = note_id
        self._set_editor_enabled(True)
        self.title_field.setText(note.title)
        self.body_field.setPlainText(note.body)
        self.category_field.setCurrentText(note.category)
        self.tags_field.setText(", ".join(note.tags))
        self.pin_button.setChecked(note.pinned)
        self.pin_button.setIcon(
            self.icons.icon("pin", 16, self.theme.accent if note.pinned else None)
        )
        self.meta_label.setText(
            f"Created {relative_time(note.created_at)} · updated {relative_time(note.updated_at)}"
        )
        self.saved_label.setText("Saved")
        self._loading = False
        for row in range(self.note_list.count()):
            if self.note_list.item(row).data(Qt.ItemDataRole.UserRole) == note_id:
                self.note_list.setCurrentRow(row)
                break

    def _on_note_selected(self, current: QListWidgetItem | None, _previous=None) -> None:
        if current is None:
            return
        note_id = current.data(Qt.ItemDataRole.UserRole)
        if note_id is None or note_id == self._current_id:
            return
        self._save_current()
        self._select_note(int(note_id))

    # ------------------------------------------------------------------ editing
    def _set_editor_enabled(self, enabled: bool) -> None:
        for widget in (
            self.title_field,
            self.body_field,
            self.category_field,
            self.tags_field,
            self.pin_button,
            self.delete_button,
        ):
            widget.setEnabled(enabled)
        if not enabled:
            self.title_field.clear()
            self.body_field.clear()
            self.tags_field.clear()
            self.saved_label.setText("No note selected")

    def create_note(self) -> None:
        note_id = self.ctx.notes.create(
            title="", body="", category=self.category_field.currentText() or "General"
        )
        self._refresh_categories()
        self._reload_list()
        self._select_note(note_id)
        self.title_field.setFocus()
        self.ctx.toast("Note created")

    def delete_note(self) -> None:
        if self._current_id is None:
            return
        note = self.ctx.notes.get(self._current_id)
        if note is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete note",
            f"Delete “{note.display_title}”? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.ctx.notes.delete(self._current_id)
        self._current_id = None
        self._refresh_categories()
        self._reload_list()
        remaining = self.ctx.notes.list()
        if remaining:
            self._select_note(remaining[0].id)
        else:
            self._set_editor_enabled(False)
        self.ctx.toast("Note deleted")

    def _toggle_pin(self) -> None:
        if self._current_id is None:
            return
        pinned = self.ctx.notes.toggle_pin(self._current_id)
        self.pin_button.setChecked(pinned)
        self.pin_button.setIcon(
            self.icons.icon("pin", 16, self.theme.accent if pinned else None)
        )
        self._reload_list()

    def _schedule_save(self) -> None:
        if self._loading or self._current_id is None:
            return
        self.saved_label.setText("Editing…")
        self._save_timer.start()

    def _save_current(self) -> None:
        if self._current_id is None:
            return
        title = self.title_field.text()
        body = self.body_field.toPlainText()
        category = self.category_field.currentText().strip() or "General"
        tags = [tag.strip() for tag in self.tags_field.text().split(",") if tag.strip()]
        try:
            self.ctx.notes.update(
                self._current_id, title=title, body=body, category=category, tags=tags
            )
        except Exception:
            log.exception("note save failed")
            self.saved_label.setText("Save failed")
            return
        self.saved_label.setText(f"Saved {datetime.now().strftime('%H:%M:%S')}")
        self._refresh_categories()
        self._reload_list()

    def on_closing(self) -> None:
        self._save_timer.stop()
        self._save_current()
