"""Reusable modal dialogs (widget options, confirmations)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from deskos.core.context import DeskOSContext
from deskos.ui.components import Muted, apply_shadow
from deskos.widgets.base import DeskWidget


class PromptDialog(QDialog):
    """Small themed text prompt used for renaming and creation flows."""

    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        label: str,
        text: str = "",
        placeholder: str = "",
        confirm_label: str = "Save",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setModal(True)
        self.setMinimumWidth(400)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        panel = QWidget()
        panel.setObjectName("Panel")
        apply_shadow(panel, 40, 8, 110)
        outer.addWidget(panel)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        heading = QLabel(title)
        heading.setObjectName("Subheading")
        layout.addWidget(heading)
        layout.addWidget(Muted(label))
        self.field = QLineEdit(text)
        self.field.setPlaceholderText(placeholder)
        self.field.selectAll()
        self.field.returnPressed.connect(self.accept)
        layout.addWidget(self.field)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        confirm = QPushButton(confirm_label)
        confirm.setObjectName("PrimaryButton")
        confirm.setDefault(True)
        confirm.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(confirm)
        layout.addLayout(buttons)

    def value(self) -> str:
        return self.field.text().strip()


class WidgetSettingsDialog(QDialog):
    """Edit a dashboard widget's own options."""

    def __init__(self, parent: QWidget | None, widget: DeskWidget, context: DeskOSContext):
        super().__init__(parent)
        self.widget = widget
        self.context = context
        self.setWindowTitle(f"{widget.title} settings")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setModal(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        panel = QWidget()
        panel.setObjectName("Panel")
        apply_shadow(panel, 40, 8, 110)
        outer.addWidget(panel)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        heading = QLabel(widget.title)
        heading.setObjectName("Subheading")
        layout.addWidget(heading)
        description = Muted(widget.description or "Options for this widget.")
        layout.addWidget(description)

        form = widget.build_settings_form()
        if form is None:
            layout.addWidget(Muted("This widget has no configurable options."))
        else:
            layout.addWidget(form)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save")
        save.setObjectName("PrimaryButton")
        save.setDefault(True)
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def _save(self) -> None:
        settings = {}
        try:
            settings = self.widget.collect_settings()
        except Exception:  # a widget form error should not close the app
            import logging

            logging.getLogger(__name__).exception("widget settings collection failed")
        self.widget.context.save_settings(settings)
        self.widget.apply_settings(settings)
        self.accept()
