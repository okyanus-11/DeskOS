"""Network overview: adapters, addresses and traffic counters."""

from __future__ import annotations

import logging
import socket

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from deskos.core.context import DeskOSContext
from deskos.system.info import network_summary
from deskos.ui.components import Card, Muted, SectionTitle, StatBlock, scrollable
from deskos.utils.formatting import format_bytes

log = logging.getLogger(__name__)


class NetworkPage(QWidget):
    def __init__(self, context: DeskOSContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = context
        self.icons = context.icons
        self._interfaces: list[dict] = []

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 10, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Network")
        title.setObjectName("Heading")
        layout.addWidget(title)
        layout.addWidget(Muted("Adapter information and traffic counters from this machine."))

        stats = QHBoxLayout()
        stats.setSpacing(14)
        self.status_stat = StatBlock("Connection", "Checking…", self.icons, "wifi")
        self.ip_stat = StatBlock("Local IPv4", "—", self.icons, "network")
        self.sent_stat = StatBlock("Uploaded", "—", self.icons, "upload")
        self.received_stat = StatBlock("Downloaded", "—", self.icons, "download")
        for stat in (self.status_stat, self.ip_stat, self.sent_stat, self.received_stat):
            card = Card()
            card.layout.addWidget(stat)
            stats.addWidget(card)
        layout.addLayout(stats)

        table_card = Card()
        header = QHBoxLayout()
        header.addWidget(SectionTitle("Adapters"))
        header.addStretch(1)
        refresh = QPushButton("Refresh")
        refresh.setIcon(self.icons.icon("refresh", 15))
        refresh.clicked.connect(self.refresh)
        header.addWidget(refresh)
        table_card.layout.addLayout(header)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Adapter", "State", "IPv4", "MAC", "Speed", "Traffic (sent / received)"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 6):
            self.table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        self.table.setMinimumHeight(240)
        table_card.layout.addWidget(self.table)
        layout.addWidget(table_card)

        self.note = Muted(
            "Hostname and connection details come from the operating system. "
            "Counters reset when an adapter reconnects."
        )
        layout.addWidget(self.note)
        layout.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scrollable(container))

        self.ctx.monitor.sampled.connect(self._on_snapshot)
        self.refresh()

    def refresh(self) -> None:
        try:
            self._interfaces = network_summary(self.ctx.platform)
        except Exception:
            log.exception("could not read network interfaces")
            self._interfaces = []
        self._render()

    def _on_snapshot(self, snapshot) -> None:
        if snapshot.network_interfaces:
            self._interfaces = snapshot.network_interfaces
            self._render()
        self.sent_stat.set_value(format_bytes(snapshot.net_sent_total), "Uploaded (session)")
        self.received_stat.set_value(format_bytes(snapshot.net_recv_total), "Downloaded (session)")

    def _render(self) -> None:
        connected = [item for item in self._interfaces if item["is_up"] and item["ipv4"]]
        if connected:
            primary = connected[0]
            self.status_stat.set_value("Connected", f"Connected · {primary['name']}")
            self.ip_stat.set_value(primary["ipv4"] or "—", "Local IPv4")
        elif self._interfaces:
            self.status_stat.set_value("Offline", "No active IPv4 connection")
            self.ip_stat.set_value("—", "Local IPv4")
        else:
            self.status_stat.set_value("No adapters", "No network hardware detected")
            self.ip_stat.set_value("—", "Local IPv4")

        self.table.setRowCount(len(self._interfaces))
        for row, interface in enumerate(self._interfaces):
            values = [
                interface["name"],
                "Up" if interface["is_up"] else "Down",
                interface["ipv4"] or "—",
                interface["mac"] or "—",
                f"{interface['speed_mbps']} Mbps" if interface["speed_mbps"] else "—",
                f"{format_bytes(interface['bytes_sent'])} / {format_bytes(interface['bytes_recv'])}",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column in (1, 4, 5):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self.table.setItem(row, column, item)
        try:
            hostname = socket.gethostname()
        except OSError:
            hostname = "unknown"
        self.note.setText(
            f"Hostname: {hostname} · {len(self._interfaces)} adapter(s) detected · "
            f"backend: {self.ctx.platform.display_name}"
        )
