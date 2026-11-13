"""Themed SVG icon rendering.

Icons ship as SVG files in ``assets/icons`` using ``currentColor`` so a single
asset works in both the dark and light theme: the provider substitutes the
current text colour before rendering and caches the result per size/colour.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QByteArray, QFileInfo, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPixmap,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QFileIconProvider

from deskos.core.paths import icon_file, images_dir
from deskos.core.theme import ThemeManager
from deskos.platform.base import AppEntry

log = logging.getLogger(__name__)


class IconProvider:
    def __init__(self, theme: ThemeManager) -> None:
        self.theme = theme
        self._cache: dict[tuple[str, str, int], QPixmap] = {}
        self._file_cache: dict[str, QIcon] = {}
        self._file_provider = QFileIconProvider()

    # ----------------------------------------------------------------- basics
    def color(self, role: str = "text") -> str:
        return self.theme.palette.color(role)

    def pixmap(self, name: str, size: int = 20, color: str | None = None) -> QPixmap:
        tone = color or self.theme.palette.text
        key = (name, tone, size)
        cached = self._cache.get(key)
        if cached is not None and not cached.isNull():
            return cached

        path = icon_file(name)
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        try:
            markup = path.read_text(encoding="utf-8").replace("currentColor", tone)
            renderer = QSvgRenderer(QByteArray(markup.encode("utf-8")))
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            renderer.render(painter, QRectF(0, 0, size, size))
            painter.end()
        except Exception:
            log.debug("could not render icon %s", path, exc_info=True)
        self._cache[key] = pixmap
        return pixmap

    def icon(self, name: str, size: int = 20, color: str | None = None) -> QIcon:
        return QIcon(self.pixmap(name, size, color))

    def accent_pixmap(self, name: str, size: int = 20) -> QPixmap:
        return self.pixmap(name, size, self.theme.accent)

    def muted_pixmap(self, name: str, size: int = 20) -> QPixmap:
        return self.pixmap(name, size, self.theme.palette.subtext0)

    # ------------------------------------------------------------------ logo
    def logo_pixmap(self, size: int = 28) -> QPixmap:
        for candidate in (images_dir() / f"deskos-{size}.png", images_dir() / "deskos-256.png"):
            if candidate.is_file():
                pixmap = QPixmap(str(candidate))
                if not pixmap.isNull():
                    return pixmap.scaled(
                        QSize(size, size),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
        # Fall back to the SVG logo rendered directly.
        svg = images_dir() / "deskos-logo.svg"
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        try:
            renderer = QSvgRenderer(str(svg))
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            renderer.render(painter, QRectF(0, 0, size, size))
            painter.end()
        except Exception:
            log.debug("logo rendering failed", exc_info=True)
        return pixmap

    def logo_icon(self) -> QIcon:
        icon = QIcon()
        for size in (16, 24, 32, 48, 64, 128, 256):
            icon.addPixmap(self.logo_pixmap(size))
        return icon

    # ------------------------------------------------------- real file icons
    def file_icon(self, entry: AppEntry) -> QIcon:
        for candidate in (entry.icon_path, entry.path, entry.target):
            if not candidate:
                continue
            icon = self.icon_for_path(candidate)
            if not icon.isNull():
                return icon
        return self.icon("apps", 32, self.theme.accent)

    def icon_for_path(self, path: str) -> QIcon:
        key = path.lower()
        cached = self._file_cache.get(key)
        if cached is not None:
            return cached
        icon = QIcon()
        target = Path(path)
        if target.is_file() or target.is_dir():
            try:
                icon = self._file_provider.icon(QFileInfo(str(target)))
            except Exception:
                icon = QIcon()
        if icon.isNull() and target.suffix.lower() == ".lnk":
            icon = self._file_provider.icon(QFileInfo(str(target)))
        self._file_cache[key] = icon
        return icon

    def clear_cache(self) -> None:
        self._cache.clear()
        self._file_cache.clear()

    def colored(self, color: str) -> None:
        """Convenience for painting code that needs a QColor."""
        return QColor(color).name()
