"""Application-wide theme application (stylesheets, palette and fonts)."""

from __future__ import annotations

import logging

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from deskos.core.theme import FONT_STACK, ThemeManager

log = logging.getLogger(__name__)


def build_qpalette(theme: ThemeManager) -> QPalette:
    spec = theme.palette_spec()
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(spec["window"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(spec["window_text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(spec["base"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(spec["alternate_base"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(spec["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(spec["button"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(spec["button_text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(spec["highlight"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(spec["highlighted_text"]))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(spec["tooltip_base"]))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(spec["tooltip_text"]))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(spec["placeholder"]))
    palette.setColor(QPalette.ColorRole.Link, QColor(spec["link"]))
    palette.setColor(QPalette.ColorRole.Mid, QColor(spec["mid"]))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(spec["disabled_text"]))
    return palette


def apply_application_theme(app: QApplication, theme: ThemeManager) -> None:
    """Apply the current palette + generated QSS to every widget."""
    app.setPalette(build_qpalette(theme))
    app.setStyleSheet(theme.qss())
    font = QFont()
    font.setFamilies(
        ["Segoe UI Variable Text", "Segoe UI", "Inter", "Noto Sans", "Cantarell", "DejaVu Sans"]
    )
    font.setPixelSize(theme.font_px(13))
    app.setFont(font)
    log.debug("applied theme %s (accent %s)", theme.palette.key, theme.accent_name)


__all__ = ["apply_application_theme", "build_qpalette", "FONT_STACK"]
