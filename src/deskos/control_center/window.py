"""Control Center window: navigation rail plus configuration pages."""

from __future__ import annotations

import logging

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from deskos.control_center.pages import (
    AppearancePage,
    ApplicationsPage,
    GeneralPage,
    NetworkPage,
    PluginsPage,
    SystemPage,
)
from deskos.core.context import DeskOSContext
from deskos.ui.chrome import DeskWindow
from deskos.ui.components import Muted
from deskos.utils.i18n import tr

log = logging.getLogger(__name__)

PAGE_DEFINITIONS = (
    ("appearance", "Appearance", "palette", tr("settings.appearance")),
    ("system", "System", "monitor", tr("settings.system")),
    ("network", "Network", "network", tr("settings.network")),
    ("applications", "Applications", "apps", tr("settings.applications")),
    ("general", "General", "settings", tr("settings.general")),
    ("plugins", "Plugins", "plugins", tr("settings.plugins")),
)


class ControlCenterWindow(DeskWindow):
    def __init__(self, context: DeskOSContext) -> None:
        super().__init__(context, "Control Center", "settings", "Configure DeskOS")
        self.ctx = context
        self.resize(1020, 720)
        self.setMinimumSize(860, 600)

        nav = QWidget()
        nav.setObjectName("Sidebar")
        nav.setFixedWidth(220)
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(12, 16, 12, 16)
        nav_layout.setSpacing(8)

        heading = QLabel("Control Center")
        heading.setObjectName("TitleLabel")
        nav_layout.addWidget(heading)
        nav_layout.addWidget(Muted("Changes are saved automatically."))
        nav_layout.addSpacing(8)

        self.nav_list = QListWidget()
        self.nav_list.setObjectName("SettingsNav")
        self.nav_list.setIconSize(QSize(17, 17))
        self.nav_list.setFrameShape(QListWidget.Shape.NoFrame)
        self.nav_list.currentRowChanged.connect(self._on_nav_changed)
        for key, label, icon, translated in PAGE_DEFINITIONS:
            item = QListWidgetItem(self.ctx.icons.icon(icon, 17, self.ctx.theme.palette.subtext1), translated or label)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.nav_list.addItem(item)
        nav_layout.addWidget(self.nav_list, 1)

        self.version_label = Muted("")
        nav_layout.addWidget(self.version_label)
        self.body_layout.addWidget(nav)

        self.stack = QStackedWidget()
        self.pages = {
            "appearance": AppearancePage(context),
            "system": SystemPage(context),
            "network": NetworkPage(context),
            "applications": ApplicationsPage(context),
            "general": GeneralPage(context),
            "plugins": PluginsPage(context),
        }
        for key, _label, _icon, _translated in PAGE_DEFINITIONS:
            self.stack.addWidget(self.pages[key])
        self.body_layout.addWidget(self.stack, 1)

        self.nav_list.setCurrentRow(0)
        from deskos import __version__

        self.version_label.setText(f"DeskOS {__version__} · {context.platform.display_name}")

    def select_page(self, key: str) -> None:
        keys = [definition[0] for definition in PAGE_DEFINITIONS]
        if key in keys:
            self.nav_list.setCurrentRow(keys.index(key))

    def _on_nav_changed(self, row: int) -> None:
        if row < 0:
            return
        self.stack.setCurrentIndex(row)
        page = self.stack.currentWidget()
        refresh = getattr(page, "refresh", None)
        if callable(refresh):
            try:
                refresh()
            except Exception:
                log.exception("control center page refresh failed")
