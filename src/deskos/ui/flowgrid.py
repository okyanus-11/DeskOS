"""Responsive grid container.

Qt's layouts are not flow layouts, so tiles are re-arranged into a row/grid
matrix whenever the container is resized.  This keeps the launcher and the
applications page usable from 1280px laptops up to 4K displays with scaling.
"""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QGridLayout, QSizePolicy, QWidget


class AdaptiveGrid(QWidget):
    def __init__(
        self,
        min_item_width: int = 190,
        max_columns: int = 8,
        spacing: int = 12,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.min_item_width = min_item_width
        self.max_columns = max_columns
        self._items: list[QWidget] = []
        self._columns = 0
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(spacing)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def add(self, widget: QWidget) -> None:
        self._items.append(widget)
        widget.setParent(self)
        self._relayout(force=True)

    def clear(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
                item.widget().deleteLater()
        self._items.clear()
        self._columns = 0

    def items(self) -> list[QWidget]:
        return list(self._items)

    def _column_count(self) -> int:
        width = max(self.width(), self.min_item_width)
        columns = max(1, width // (self.min_item_width + 12))
        return max(1, min(self.max_columns, columns))

    def _relayout(self, force: bool = False) -> None:
        columns = self._column_count()
        if columns == self._columns and not force:
            return
        self._columns = columns
        for index, widget in enumerate(self._items):
            self.grid.addWidget(widget, index // columns, index % columns)
        for column in range(self.max_columns):
            self.grid.setColumnStretch(column, 0)
        for column in range(columns):
            self.grid.setColumnStretch(column, 1)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._relayout()

    def sizeHint(self) -> QSize:  # noqa: N802
        return super().sizeHint()
