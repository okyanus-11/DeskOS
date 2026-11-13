"""Frameless, themed window chrome shared by all DeskOS windows.

The window keeps native taskbar/window-manager behaviour (``Qt.Window``) but
draws its own rounded title bar, which is what gives DeskOS its identity while
still allowing minimise/maximise/close and drag-to-move through
``startSystemMove``.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizeGrip,
    QVBoxLayout,
    QWidget,
)

from deskos.core.context import DeskOSContext
from deskos.ui.components import IconButton, apply_shadow
from deskos.ui.icons import IconProvider

log = logging.getLogger(__name__)


class TitleBar(QWidget):
    """Custom title bar with drag support and window buttons."""

    def __init__(self, window: DeskWindow, title: str, icon_name: str, subtitle: str = "") -> None:
        super().__init__(window)
        self.setObjectName("TitleBar")
        self.setFixedHeight(52)
        self._window = window
        self._drag_offset: QPoint | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 10, 4)
        layout.setSpacing(10)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(22, 22)
        layout.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignVCenter)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.setContentsMargins(0, 0, 0, 0)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("TitleLabel")
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("Muted")
        self.subtitle_label.setVisible(bool(subtitle))
        titles.addWidget(self.title_label)
        titles.addWidget(self.subtitle_label)
        layout.addLayout(titles)
        layout.addStretch(1)

        self.extra_layout = QHBoxLayout()
        self.extra_layout.setSpacing(4)
        layout.addLayout(self.extra_layout)

        self.minimize_button = IconButton(window.context.icons, "minimize", "Minimize", 30, 14)
        self.minimize_button.setObjectName("WindowButton")
        self.minimize_button.clicked.connect(window.showMinimized)
        self.maximize_button = IconButton(window.context.icons, "maximize", "Maximize", 30, 14)
        self.maximize_button.setObjectName("WindowButton")
        self.maximize_button.clicked.connect(window.toggle_maximized)
        self.close_button = IconButton(window.context.icons, "close", "Close", 30, 14)
        self.close_button.setObjectName("WindowButtonClose")
        self.close_button.setProperty("class", "close")
        self.close_button.clicked.connect(window.close)
        layout.addWidget(self.minimize_button)
        layout.addWidget(self.maximize_button)
        layout.addWidget(self.close_button)

        self.set_icon(icon_name)
        self.set_title(title, subtitle)

    def set_icon(self, icon_name: str) -> None:
        icons: IconProvider = self._window.context.icons
        if icon_name == "logo":
            self.icon_label.setPixmap(icons.logo_pixmap(22))
        else:
            self.icon_label.setPixmap(icons.pixmap(icon_name, 20, self._window.context.theme.accent))

    def set_title(self, title: str, subtitle: str = "") -> None:
        self.title_label.setText(title)
        self.subtitle_label.setText(subtitle)
        self.subtitle_label.setVisible(bool(subtitle))

    # Dragging (native move keeps Windows snap/aero-snap working)
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self._window.windowHandle()
            if handle is not None:
                handle.startSystemMove()
                event.accept()
                return
            self._drag_offset = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._window.toggle_maximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class DeskWindow(QWidget):
    """Base window: rounded shell, custom title bar, content area."""

    closed = Signal()

    def __init__(
        self,
        context: DeskOSContext,
        title: str,
        icon_name: str = "logo",
        subtitle: str = "",
        *,
        resizable: bool = True,
        minimizable: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.context = context
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.CustomizeWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle(title)
        self.setWindowIcon(context.icons.logo_icon())
        self._maximized = False
        self._resizable = resizable

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(0)
        self._outer = outer

        self.shell = QWidget(self)
        self.shell.setObjectName("Shell")
        outer.addWidget(self.shell)
        apply_shadow(self.shell, blur=48, y_offset=12, alpha=110)

        shell_layout = QVBoxLayout(self.shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        self.title_bar = TitleBar(self, title, icon_name, subtitle)
        shell_layout.addWidget(self.title_bar, 0)
        if not minimizable:
            self.title_bar.minimize_button.hide()

        self.body = QWidget()
        self.body.setObjectName("Body")
        self.body_layout = QHBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(0)
        shell_layout.addWidget(self.body, 1)

        self.footer = QWidget()
        self.footer_layout = QHBoxLayout(self.footer)
        self.footer_layout.setContentsMargins(16, 2, 16, 8)
        self.footer_layout.setSpacing(8)
        self.footer.hide()
        shell_layout.addWidget(self.footer, 0)

        self._size_grip = QSizeGrip(self.shell)
        self._size_grip.setFixedSize(16, 16)
        self._size_grip.setVisible(resizable)
        self._size_grip.raise_()

    # --------------------------------------------------------------- content
    def set_content(self, widget: QWidget) -> None:
        self.body_layout.addWidget(widget, 1)

    def content_column(self) -> QVBoxLayout:
        """Create a padded vertical layout for simple windows."""
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(20, 4, 20, 18)
        layout.setSpacing(14)
        self.body_layout.addWidget(holder, 1)
        return layout

    # ---------------------------------------------------------------- window
    def toggle_maximized(self) -> None:
        if self._maximized:
            self.showNormal()
            self._outer.setContentsMargins(10, 10, 10, 10)
            apply_shadow(self.shell, blur=48, y_offset=12, alpha=110)
            self._maximized = False
        else:
            self.showMaximized()
            self._outer.setContentsMargins(0, 0, 0, 0)
            self.shell.setGraphicsEffect(None)
            self._maximized = True
        self.title_bar.maximize_button.setIcon(
            self.context.icons.icon(
                "restore" if self._maximized else "maximize", 14
            )
        )
        self.title_bar.maximize_button.setToolTip("Restore" if self._maximized else "Maximize")
        self._reposition_grip()

    def _reposition_grip(self) -> None:
        self._size_grip.move(
            self.shell.width() - self._size_grip.width() - 8,
            self.shell.height() - self._size_grip.height() - 8,
        )
        self._size_grip.raise_()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._reposition_grip()

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == event.Type.WindowStateChange:
            if self.isMaximized() and not self._maximized:
                self._maximized = True
                self._outer.setContentsMargins(0, 0, 0, 0)
                self.shell.setGraphicsEffect(None)
            elif not self.isMaximized() and self._maximized:
                self._maximized = False
                self._outer.setContentsMargins(10, 10, 10, 10)
                apply_shadow(self.shell, blur=48, y_offset=12, alpha=110)

    def show_centered(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            size = self.sizeHint().expandedTo(self.minimumSizeHint())
            width = min(max(self.width(), 720), available.width() - 80)
            height = min(max(self.height(), 520), available.height() - 80)
            self.resize(width, height)
            self.move(
                available.center().x() - width // 2,
                available.center().y() - height // 2,
            )
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.closed.emit()
        super().closeEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self.showNormal()
            return
        super().keyPressEvent(event)

    def set_icon(self, name: str) -> None:
        self.title_bar.set_icon(name)

    def set_subtitle(self, text: str) -> None:
        self.title_bar.set_title(self.title_bar.title_label.text(), text)
