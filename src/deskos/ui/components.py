"""Reusable UI components that define the DeskOS look.

Every widget here is theme-aware and keyboard accessible; they are the building
blocks for the dashboard, dock, launcher and built-in applications.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from deskos.core.theme import ThemeManager


def apply_shadow(widget: QWidget, blur: int = 42, y_offset: int = 10, alpha: int = 120) -> None:
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setXOffset(0)
    effect.setYOffset(y_offset)
    effect.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(effect)


def repolish(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def hline() -> QFrame:
    line = QFrame()
    line.setObjectName("Divider")
    line.setFixedHeight(1)
    return line


def clear_layout(layout) -> None:  # type: ignore[no-untyped-def]
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()


def scrollable(widget: QWidget, horizontal: bool = False) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(
        Qt.ScrollBarPolicy.ScrollBarAsNeeded if horizontal else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )
    area.setWidget(widget)
    area.viewport().setAutoFillBackground(False)
    return area


class Card(QFrame):
    """Rounded surface used for panels and grouped settings."""

    def __init__(self, parent: QWidget | None = None, *, padding: int = 16, spacing: int = 10):
        super().__init__(parent)
        self.setObjectName("Card")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(padding, padding, padding, padding)
        self.layout.setSpacing(spacing)


class Panel(QFrame):
    def __init__(self, parent: QWidget | None = None, *, padding: int = 18):
        super().__init__(parent)
        self.setObjectName("Panel")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(padding, padding, padding, padding)
        self.layout.setSpacing(12)


class IconButton(QPushButton):
    def __init__(
        self,
        icons,
        icon_name: str,
        tooltip: str = "",
        size: int = 34,
        icon_size: int = 18,
        parent: QWidget | None = None,
        accent: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("IconButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(size, size)
        self.setIconSize(QSize(icon_size, icon_size))
        self.setIcon(
            icons.icon(icon_name, icon_size, icons.theme.accent if accent else None)
        )
        if tooltip:
            self.setToolTip(tooltip)
        self.setAccessibleName(tooltip or icon_name)


class Heading(QLabel):
    def __init__(self, text: str = "", object_name: str = "Heading", parent=None):
        super().__init__(text, parent)
        self.setObjectName(object_name)


class Muted(QLabel):
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("Muted")
        self.setWordWrap(True)


class SectionTitle(QLabel):
    def __init__(self, text: str = "", parent=None):
        super().__init__(text.upper(), parent)
        self.setObjectName("SectionTitle")


class SearchField(QLineEdit):
    def __init__(self, icons, placeholder: str = "Search…", parent=None):
        super().__init__(parent)
        self.setObjectName("SearchField")
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self.addAction(icons.icon("search", 16, icons.theme.palette.subtext0), QLineEdit.ActionPosition.LeadingPosition)
        self.setMinimumHeight(40)


class Divider(QWidget):
    def __init__(self, vertical: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("VDivider" if vertical else "Divider")
        if vertical:
            self.setFixedWidth(1)
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        else:
            self.setFixedHeight(1)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


class StatBlock(QWidget):
    """Large number with a caption, used across dashboard and monitor."""

    def __init__(self, caption: str, value: str = "—", icons=None, icon_name: str = "", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        if icons is not None and icon_name:
            badge = QLabel()
            badge.setPixmap(icons.pixmap(icon_name, 20, icons.theme.accent))
            layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        column = QVBoxLayout()
        column.setSpacing(1)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("StatValue")
        self.caption_label = QLabel(caption)
        self.caption_label.setObjectName("StatLabel")
        column.addWidget(self.value_label)
        column.addWidget(self.caption_label)
        layout.addLayout(column, 1)

    def set_value(self, value: str, caption: str | None = None) -> None:
        self.value_label.setText(value)
        if caption is not None:
            self.caption_label.setText(caption)


class ProgressStat(QWidget):
    def __init__(self, theme: ThemeManager, label: str, parent=None):
        super().__init__(parent)
        self.theme = theme
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        self.name_label = QLabel(label)
        self.name_label.setObjectName("StatLabel")
        self.value_label = QLabel("—")
        self.value_label.setObjectName("Muted")
        header.addWidget(self.name_label)
        header.addStretch(1)
        header.addWidget(self.value_label)
        layout.addLayout(header)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 100)
        self.bar.setFixedHeight(8)
        layout.addWidget(self.bar)
        self._default_color = theme.accent

    def set_value(self, percent: float, text: str | None = None, color: str | None = None) -> None:
        bounded = max(0.0, min(100.0, float(percent or 0)))
        self.bar.setValue(int(round(bounded)))
        if text is not None:
            self.value_label.setText(text)
        tone = color or self._default_color
        radius = self.theme.px(4)
        self.bar.setStyleSheet(
            f"QProgressBar::chunk {{ background: {tone}; border-radius: {radius}px; }}"
        )


class Sparkline(QWidget):
    """Lightweight filled line chart for CPU/RAM/network history."""

    def __init__(self, theme: ThemeManager, color_role: str = "accent", max_points: int = 60, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.color_role = color_role
        self.max_points = max_points
        self._values: list[float] = []
        self._maximum = 100.0
        self.setMinimumHeight(56)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_values(self, values: Sequence[float], maximum: float | None = None) -> None:
        self._values = [float(value) for value in list(values)[-self.max_points :]]
        if maximum is not None and maximum > 0:
            self._maximum = float(maximum)
        self.update()

    def push(self, value: float, maximum: float | None = None) -> None:
        self._values.append(float(value))
        if len(self._values) > self.max_points:
            self._values = self._values[-self.max_points :]
        if maximum is not None and maximum > 0:
            self._maximum = float(maximum)
        self.update()

    def _color(self) -> QColor:
        tokens = self.theme.tokens()
        return QColor(tokens.get(self.color_role, tokens["accent"]))

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1, 3, -1, -3)
        if rect.width() <= 0 or rect.height() <= 0:
            return

        color = self._color()
        baseline_pen = QPen(QColor(self.theme.palette.surface0))
        baseline_pen.setWidth(1)
        painter.setPen(baseline_pen)
        for index in range(1, 4):
            y = rect.top() + rect.height() * index / 4.0
            painter.drawLine(int(rect.left()), int(y), int(rect.right()), int(y))

        if len(self._values) < 2:
            painter.end()
            return

        step = rect.width() / max(1, self.max_points - 1)
        offset = rect.width() - step * (len(self._values) - 1)
        points: list[QPoint] = []
        for index, value in enumerate(self._values):
            ratio = max(0.0, min(1.0, value / self._maximum if self._maximum else 0.0))
            x = rect.left() + offset + index * step
            y = rect.bottom() - ratio * rect.height()
            points.append(QPoint(int(x), int(y)))

        path = QPainterPath()
        path.moveTo(points[0])
        for point in points[1:]:
            path.lineTo(point)

        fill = QPainterPath(path)
        fill.lineTo(points[-1].x(), rect.bottom())
        fill.lineTo(points[0].x(), rect.bottom())
        fill.closeSubpath()
        gradient = QLinearGradient(0, rect.top(), 0, rect.bottom())
        gradient.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), 110))
        gradient.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 8))
        painter.fillPath(fill, gradient)

        pen = QPen(color)
        pen.setWidth(2)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(path)
        painter.end()


class RingGauge(QWidget):
    """Circular percentage gauge with a centred caption."""

    def __init__(self, theme: ThemeManager, caption: str = "", color_role: str = "accent", size: int = 116, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.caption = caption
        self.color_role = color_role
        self._percent = 0.0
        self._label = "—"
        self.setMinimumSize(size, size)

    def set_value(self, percent: float, label: str | None = None) -> None:
        self._percent = max(0.0, min(100.0, float(percent or 0)))
        if label is not None:
            self._label = label
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        side = min(self.width(), self.height())
        margin = 8
        rect = QRectF(
            (self.width() - side) / 2 + margin,
            (self.height() - side) / 2 + margin,
            side - margin * 2,
            side - margin * 2,
        )
        track = QPen(QColor(self.theme.palette.surface0))
        track.setWidth(max(6, int(side * 0.075)))
        track.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track)
        painter.drawArc(rect, 0, 360 * 16)

        color = QColor(self.theme.tokens().get(self.color_role, self.theme.accent))
        arc = QPen(color)
        arc.setWidth(track.width())
        arc.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc)
        span = int(-360 * 16 * (self._percent / 100.0))
        painter.drawArc(rect, 90 * 16, span)

        painter.setPen(QColor(self.theme.palette.text))
        font = QFont(self.font())
        font.setPixelSize(max(14, int(side * 0.20)))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._label)

        if self.caption:
            caption_font = QFont(self.font())
            caption_font.setPixelSize(max(9, int(side * 0.095)))
            painter.setFont(caption_font)
            painter.setPen(QColor(self.theme.palette.subtext0))
            caption_rect = QRectF(rect.left(), rect.center().y() + side * 0.13, rect.width(), side * 0.2)
            painter.drawText(caption_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, self.caption)
        painter.end()


class EmptyState(QWidget):
    def __init__(self, icons, icon_name: str, title: str, description: str = "", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)
        icon = QLabel()
        icon.setPixmap(icons.pixmap(icon_name, 42, icons.theme.palette.overlay0))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)
        heading = QLabel(title)
        heading.setObjectName("Subheading")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(heading)
        if description:
            body = Muted(description)
            body.setAlignment(Qt.AlignmentFlag.AlignCenter)
            body.setMaximumWidth(420)
            layout.addWidget(body, 0, Qt.AlignmentFlag.AlignHCenter)


class Toast(QWidget):
    """Transient message shown near the bottom of a window."""

    def __init__(
        self, parent: QWidget, text: str, timeout_ms: int = 3200, animate: bool = True
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Toast")
        self._animate = animate
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        self.label = QLabel(text)
        self.label.setWordWrap(False)
        layout.addWidget(self.label)
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0 if animate else 1.0)
        self.setGraphicsEffect(self._effect)
        self._animation = QPropertyAnimation(self._effect, b"opacity", self)
        self._animation.setDuration(180)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.adjustSize()
        if animate:
            self._animation.start()
        QTimer.singleShot(timeout_ms, self._fade_out)

    def _fade_out(self) -> None:
        if not self._animate:
            self.deleteLater()
            return
        self._animation.setStartValue(self._effect.opacity())
        self._animation.setEndValue(0.0)
        self._animation.setDuration(220)
        self._animation.finished.connect(self.deleteLater)
        self._animation.start()

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.adjustSize()
        x = (parent.width() - self.width()) // 2
        y = parent.height() - self.height() - 34
        self.move(max(8, x), max(8, y))


class ToastHost(QWidget):
    """Invisible overlay that owns toast widgets for a window."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setObjectName("ToastHost")
        self.hide()
        self._toasts: list[Toast] = []

    def notify(self, message: str, timeout_ms: int = 3200, animate: bool = True) -> None:
        toast = Toast(self.parentWidget() or self, message, timeout_ms, animate)
        toast.show()
        toast.reposition()
        toast.raise_()
        self._toasts.append(toast)
        QTimer.singleShot(timeout_ms + 400, lambda: self._cleanup(toast))

    def _cleanup(self, toast: Toast) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)


def themed_icon_label(icons, name: str, size: int = 20, role: str = "text") -> QLabel:
    label = QLabel()
    label.setPixmap(icons.pixmap(name, size, icons.theme.palette.color(role)))
    label.setFixedSize(size, size)
    return label


def animate_opacity(widget: QWidget, start: float, end: float, duration: int = 160) -> None:
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(duration)
    animation.setStartValue(start)
    animation.setEndValue(end)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    animation.finished.connect(lambda: widget.setVisible(end > 0.01))
    animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    widget._fade_animation = animation  # type: ignore[attr-defined]


def human_join(items: Sequence[str], limit: int = 3) -> str:
    if not items:
        return ""
    if len(items) <= limit:
        return ", ".join(items)
    return ", ".join(items[:limit]) + f" +{len(items) - limit}"
