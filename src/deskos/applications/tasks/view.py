"""DeskTasks: tasks with priorities, due dates and completion state."""

from __future__ import annotations

import logging
from datetime import date, datetime

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from deskos.applications.base import AppPage
from deskos.data.repositories import Task
from deskos.ui.components import IconButton, Muted, SearchField, SectionTitle, scrollable
from deskos.ui.dialogs import PromptDialog

log = logging.getLogger(__name__)

PRIORITY_COLORS = {1: "red", 2: "yellow", 3: "teal"}


class TaskDialog(QDialog):
    def __init__(self, parent: QWidget, task: Task | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit task" if task else "New task")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        heading = QLabel("Edit task" if task else "New task")
        heading.setObjectName("Subheading")
        layout.addWidget(heading)

        layout.addWidget(QLabel("Title"))
        self.title_field = QLineEdit(task.title if task else "")
        self.title_field.setPlaceholderText("What needs doing?")
        layout.addWidget(self.title_field)

        layout.addWidget(QLabel("Notes"))
        self.notes_field = QTextEdit(task.notes if task else "")
        self.notes_field.setPlaceholderText("Optional details")
        self.notes_field.setMaximumHeight(90)
        layout.addWidget(self.notes_field)

        row = QHBoxLayout()
        date_column = QVBoxLayout()
        date_column.addWidget(QLabel("Due date"))
        self.has_due = QCheckBox("Set a due date")
        date_column.addWidget(self.has_due)
        self.due_edit = QDateEdit()
        self.due_edit.setCalendarPopup(True)
        self.due_edit.setDate(QDate.currentDate())
        self.due_edit.setEnabled(False)
        self.has_due.toggled.connect(self.due_edit.setEnabled)
        date_column.addWidget(self.due_edit)
        row.addLayout(date_column, 1)

        priority_column = QVBoxLayout()
        priority_column.addWidget(QLabel("Priority"))
        self.priority_combo = QComboBox()
        self.priority_combo.addItem("High", 1)
        self.priority_combo.addItem("Normal", 2)
        self.priority_combo.addItem("Low", 3)
        priority_column.addWidget(self.priority_combo)
        priority_column.addStretch(1)
        row.addLayout(priority_column, 1)

        category_column = QVBoxLayout()
        category_column.addWidget(QLabel("Category"))
        self.category_field = QLineEdit(task.category if task else "General")
        category_column.addWidget(self.category_field)
        category_column.addStretch(1)
        row.addLayout(category_column, 1)
        layout.addLayout(row)

        if task is not None:
            self.has_due.setChecked(bool(task.due_date))
            if task.due_date:
                parsed = QDate.fromString(task.due_date, "yyyy-MM-dd")
                if parsed.isValid():
                    self.due_edit.setDate(parsed)
            index = self.priority_combo.findData(task.priority)
            self.priority_combo.setCurrentIndex(max(0, index))

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save task")
        save.setObjectName("PrimaryButton")
        save.setDefault(True)
        save.clicked.connect(self._accept)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def _accept(self) -> None:
        if not self.title_field.text().strip():
            self.title_field.setFocus()
            return
        self.accept()

    def values(self) -> dict:
        due = self.due_edit.date().toString("yyyy-MM-dd") if self.has_due.isChecked() else None
        return {
            "title": self.title_field.text().strip(),
            "notes": self.notes_field.toPlainText().strip(),
            "due_date": due,
            "priority": int(self.priority_combo.currentData()),
            "category": self.category_field.text().strip() or "General",
        }


class TaskRow(QWidget):
    toggled = Signal(int, bool)
    edit_requested = Signal(int)
    delete_requested = Signal(int)

    def __init__(self, task: Task, theme, icons, parent=None) -> None:
        super().__init__(parent)
        self.task = task
        self.setObjectName("Card")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(10)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(task.completed)
        self.checkbox.toggled.connect(lambda checked: self.toggled.emit(task.id, checked))
        layout.addWidget(self.checkbox)

        column = QVBoxLayout()
        column.setSpacing(1)
        title = QLabel(task.title)
        title.setObjectName("Subheading" if not task.completed else "Muted")
        if task.completed:
            title.setStyleSheet("text-decoration: line-through;")
        column.addWidget(title)
        meta_parts = [task.category, f"{task.priority_label} priority"]
        if task.due_date:
            meta_parts.append(f"due {task.due_date}")
        meta = Muted(" · ".join(meta_parts))
        column.addWidget(meta)
        if task.notes:
            notes = Muted(task.notes.splitlines()[0][:110])
            column.addWidget(notes)
        layout.addLayout(column, 1)

        badge = QLabel(task.priority_label)
        badge.setObjectName("Badge")
        badge.setStyleSheet(
            f"color: {theme.palette.accents[PRIORITY_COLORS.get(task.priority, 'yellow')]};"
        )
        layout.addWidget(badge)

        if task.due_date and not task.completed:
            try:
                due = datetime.strptime(task.due_date, "%Y-%m-%d").date()
                if due < date.today():
                    overdue = QLabel("Overdue")
                    overdue.setObjectName("Badge")
                    overdue.setStyleSheet(f"color: {theme.palette.accents['red']};")
                    layout.addWidget(overdue)
            except ValueError:
                pass

        edit = IconButton(icons, "edit", "Edit task", 28, 14)
        edit.clicked.connect(lambda: self.edit_requested.emit(task.id))
        layout.addWidget(edit)
        delete = IconButton(icons, "trash", "Delete task", 28, 14)
        delete.clicked.connect(lambda: self.delete_requested.emit(task.id))
        layout.addWidget(delete)


class TasksPage(AppPage):
    def __init__(self, context, parent: QWidget | None = None) -> None:
        super().__init__(context, parent)
        self._rows: list[TaskRow] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 6, 20, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        column = QVBoxLayout()
        column.setSpacing(2)
        title = QLabel("Tasks")
        title.setObjectName("Heading")
        self.counts = Muted("")
        column.addWidget(title)
        column.addWidget(self.counts)
        header.addLayout(column)
        header.addStretch(1)
        self.search = SearchField(self.icons, "Search tasks…")
        self.search.setMinimumWidth(240)
        self.search.textChanged.connect(self.refresh)
        header.addWidget(self.search)
        self.filter_combo = QComboBox()
        self.filter_combo.addItem("All", "all")
        self.filter_combo.addItem("Active", "active")
        self.filter_combo.addItem("Completed", "completed")
        self.filter_combo.currentIndexChanged.connect(self.refresh)
        header.addWidget(self.filter_combo)
        new_button = QPushButton("New task")
        new_button.setObjectName("PrimaryButton")
        new_button.setIcon(self.icons.icon("plus", 15, self.theme.palette.crust))
        new_button.clicked.connect(self.create_task)
        header.addWidget(new_button)
        root.addLayout(header)

        self.list_host = QWidget()
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(8)
        self.list_layout.addStretch(1)
        root.addWidget(scrollable(self.list_host), 1)

        footer = QHBoxLayout()
        self.cleared_label = Muted("")
        footer.addWidget(self.cleared_label)
        footer.addStretch(1)
        clear_button = QPushButton("Clear completed")
        clear_button.clicked.connect(self.clear_completed)
        footer.addWidget(clear_button)
        root.addLayout(footer)

        self.refresh()

    # -------------------------------------------------------------------- data
    def refresh(self) -> None:
        for row in self._rows:
            row.setParent(None)
            row.deleteLater()
        self._rows.clear()

        tasks = self.ctx.tasks.list(
            view=str(self.filter_combo.currentData() or "all"), search=self.search.text()
        )
        for task in tasks:
            row = TaskRow(task, self.theme, self.icons)
            row.toggled.connect(self._set_completed)
            row.edit_requested.connect(self.edit_task)
            row.delete_requested.connect(self.delete_task)
            self.list_layout.insertWidget(self.list_layout.count() - 1, row)
            self._rows.append(row)

        if not tasks:
            empty = Muted("Nothing here yet — create your first task with “New task”.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.list_layout.insertWidget(0, empty)
            self._rows.append(empty)  # type: ignore[arg-type]

        total, done = self.ctx.tasks.counts()
        self.counts.setText(f"{total - done} active · {done} completed · {total} total")
        self.cleared_label.setText("Completed tasks stay here until you clear them.")

    def _set_completed(self, task_id: int, completed: bool) -> None:
        self.ctx.tasks.set_completed(task_id, completed)
        self.refresh()

    def create_task(self) -> None:
        dialog = TaskDialog(self)
        if dialog.exec():
            values = dialog.values()
            self.ctx.tasks.create(**values)
            self.refresh()
            self.ctx.toast("Task created")

    def edit_task(self, task_id: int) -> None:
        task = self.ctx.tasks.get(task_id)
        if task is None:
            return
        dialog = TaskDialog(self, task)
        if dialog.exec():
            self.ctx.tasks.update(task_id, **dialog.values())
            self.refresh()

    def delete_task(self, task_id: int) -> None:
        task = self.ctx.tasks.get(task_id)
        if task is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete task",
            f"Delete “{task.title}”?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.ctx.tasks.delete(task_id)
            self.refresh()

    def clear_completed(self) -> None:
        removed = self.ctx.tasks.clear_completed()
        self.ctx.toast(f"Removed {removed} completed task(s)")
        self.refresh()
