"""Base classes for the built-in DeskOS applications."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from deskos.core.context import DeskOSContext
from deskos.ui.chrome import DeskWindow

log = logging.getLogger(__name__)


class AppPage(QWidget):
    """Common base for application bodies hosted in a :class:`DeskAppWindow`."""

    def __init__(self, context: DeskOSContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = context
        self.theme = context.theme
        self.icons = context.icons

    def on_activated(self) -> None:
        """Called when the hosting window is shown or restored."""

    def on_closing(self) -> None:
        """Called before the hosting window closes; release resources here."""


class DeskAppWindow(DeskWindow):
    """Frameless window wrapper for a built-in application page."""

    def __init__(
        self,
        context: DeskOSContext,
        title: str,
        icon: str,
        page: AppPage,
        width: int = 1000,
        height: int = 700,
        subtitle: str = "",
    ) -> None:
        super().__init__(context, title, icon, subtitle)
        self.page = page
        self.resize(width, height)
        self.set_content(page)

    def show_centered(self) -> None:
        super().show_centered()
        try:
            self.page.on_activated()
        except Exception:
            log.exception("application activation hook failed")

    def closeEvent(self, event) -> None:  # noqa: N802
        try:
            self.page.on_closing()
        except Exception:
            log.exception("application close hook failed")
        super().closeEvent(event)
