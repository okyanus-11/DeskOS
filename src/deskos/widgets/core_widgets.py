"""Built-in dashboard widgets backed by live system data."""

from __future__ import annotations

import logging
import math
from collections import deque
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCalendarWidget,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from deskos.system.monitor import MonitorSnapshot
from deskos.ui.components import Muted, ProgressStat, Sparkline
from deskos.utils.formatting import (
    format_bytes,
    format_duration,
    format_rate,
)
from deskos.widgets.base import DeskWidget

log = logging.getLogger(__name__)


class ClockWidget(DeskWidget):
    widget_type = "clock"
    title = "Clock"
    icon = "clock"
    description = "Large clock with the current date and time zone."
    default_span = 1

    def build(self) -> None:
        self.time_label = QLabel("--:--")
        self.time_label.setObjectName("AppTitle")
        font = self.time_label.font()
        font.setPixelSize(self.theme.font_px(40))
        font.setBold(True)
        self.time_label.setFont(font)
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body_layout.addWidget(self.time_label)

        self.date_label = QLabel()
        self.date_label.setObjectName("Muted")
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body_layout.addWidget(self.date_label)

        self.zone_label = QLabel()
        self.zone_label.setObjectName("Muted")
        self.zone_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body_layout.addWidget(self.zone_label)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._tick()

    def _tick(self) -> None:
        now = datetime.now()
        pattern = "%H:%M" if self.context.settings.get("format", "24h") == "24h" else "%I:%M %p"
        self.time_label.setText(now.strftime(pattern))
        self.date_label.setText(now.strftime("%A, %d %B %Y"))
        self.zone_label.setText(now.astimezone().tzname() or "")

    def build_settings_form(self) -> QWidget | None:
        from PySide6.QtWidgets import QComboBox

        form = QWidget()
        layout = QVBoxLayout(form)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Time format"))
        self._format_combo = QComboBox()
        self._format_combo.addItem("24-hour", "24h")
        self._format_combo.addItem("12-hour", "12h")
        current = self.context.settings.get("format", "24h")
        index = self._format_combo.findData(current)
        self._format_combo.setCurrentIndex(max(0, index))
        layout.addWidget(self._format_combo)
        return form

    def collect_settings(self) -> dict:
        return {"format": self._format_combo.currentData()}


class CalendarWidget(DeskWidget):
    widget_type = "calendar"
    title = "Calendar"
    icon = "calendar"
    description = "Month view with today highlighted."
    default_span = 2

    def build(self) -> None:
        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(False)
        self.calendar.setVerticalHeaderFormat(
            QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader
        )
        self.calendar.setHorizontalHeaderFormat(
            QCalendarWidget.HorizontalHeaderFormat.ShortDayNames
        )
        self.calendar.setMinimumHeight(190)
        self.calendar.setStyleSheet("background: transparent;")
        self.body_layout.addWidget(self.calendar)


class CpuWidget(DeskWidget):
    widget_type = "cpu"
    title = "CPU"
    icon = "cpu"
    description = "Real-time processor utilisation with frequency and cores."
    default_span = 1

    def build(self) -> None:
        header = QHBoxLayout()
        self.value = QLabel("—")
        self.value.setObjectName("StatValue")
        self.detail = Muted("Waiting for the first sample…")
        column = QVBoxLayout()
        column.setSpacing(0)
        column.addWidget(self.value)
        column.addWidget(self.detail)
        header.addLayout(column)
        header.addStretch(1)
        self.body_layout.addLayout(header)

        self.spark = Sparkline(self.theme, "blue")
        self.body_layout.addWidget(self.spark, 1)

    def refresh(self, snapshot: MonitorSnapshot | None) -> None:
        if snapshot is None:
            return
        self.value.setText(f"{snapshot.cpu_percent:.0f}%")
        frequency = f" · {snapshot.cpu_freq_mhz / 1000:.2f} GHz" if snapshot.cpu_freq_mhz else ""
        self.detail.setText(
            f"{len(snapshot.cpu_per_core)} threads{frequency}"
        )
        self.spark.set_values(self.ctx.monitor.cpu_history, 100.0)


class MemoryWidget(DeskWidget):
    widget_type = "memory"
    title = "Memory"
    icon = "memory"
    description = "RAM utilisation with used/total values."
    default_span = 1

    def build(self) -> None:
        header = QHBoxLayout()
        column = QVBoxLayout()
        column.setSpacing(0)
        self.value = QLabel("—")
        self.value.setObjectName("StatValue")
        self.detail = Muted("Waiting for the first sample…")
        column.addWidget(self.value)
        column.addWidget(self.detail)
        header.addLayout(column)
        header.addStretch(1)
        self.body_layout.addLayout(header)

        self.spark = Sparkline(self.theme, "green")
        self.body_layout.addWidget(self.spark, 1)

    def refresh(self, snapshot: MonitorSnapshot | None) -> None:
        if snapshot is None:
            return
        self.value.setText(f"{snapshot.memory_percent:.0f}%")
        self.detail.setText(
            f"{format_bytes(snapshot.memory_used)} of {format_bytes(snapshot.memory_total)}"
        )
        self.spark.set_values(self.ctx.monitor.memory_history, 100.0)


class StorageWidget(DeskWidget):
    widget_type = "storage"
    title = "Storage"
    icon = "storage"
    description = "Free space per mounted drive."
    default_span = 2
    minimum_body_height = 90

    def build(self) -> None:
        self.rows_layout = QVBoxLayout()
        self.rows_layout.setSpacing(8)
        self.body_layout.addLayout(self.rows_layout)
        self.body_layout.addStretch(1)
        self._rows: list[ProgressStat] = []
        self._signature: tuple = ()

    def refresh(self, snapshot: MonitorSnapshot | None) -> None:
        if snapshot is None:
            return
        disks = snapshot.disks[:3]
        signature = tuple(disk["mountpoint"] for disk in disks)
        if signature != self._signature:
            while self.rows_layout.count():
                item = self.rows_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self._rows.clear()
            for disk in disks:
                label = disk["mountpoint"] or disk["device"]
                row = ProgressStat(self.theme, f"{label} ({disk['fstype'] or 'disk'})")
                self.rows_layout.addWidget(row)
                self._rows.append(row)
            self._signature = signature
        for row, disk in zip(self._rows, disks, strict=False):
            row.set_value(
                disk["percent"],
                f"{format_bytes(disk['free'])} free of {format_bytes(disk['total'])}",
                self.theme.palette.accents["yellow"]
                if disk["percent"] > 90
                else self.theme.palette.accents["teal"],
            )


class NetworkWidget(DeskWidget):
    widget_type = "network"
    title = "Network"
    icon = "network"
    description = "Download/upload throughput and connection status."
    default_span = 1

    def build(self) -> None:
        self.status = QLabel("—")
        self.status.setObjectName("Subheading")
        self.body_layout.addWidget(self.status)

        rates = QHBoxLayout()
        self.down = Muted("↓ —")
        self.up = Muted("↑ —")
        rates.addWidget(self.down)
        rates.addStretch(1)
        rates.addWidget(self.up)
        self.body_layout.addLayout(rates)

        self.spark = Sparkline(self.theme, "teal")
        self.body_layout.addWidget(self.spark, 1)
        self._history: deque[float] = deque(maxlen=60)

    def refresh(self, snapshot: MonitorSnapshot | None) -> None:
        if snapshot is None:
            return
        connected = [item for item in snapshot.network_interfaces if item["is_up"] and item["ipv4"]]
        if connected:
            primary = connected[0]
            label = primary["name"]
            if primary["ipv4"]:
                label = f"{label} · {primary['ipv4']}"
            self.status.setText(label)
        elif snapshot.network_interfaces:
            self.status.setText("No active connection")
        else:
            self.status.setText("No adapters detected")
        self.down.setText(f"↓ {format_rate(snapshot.net_recv_rate)}")
        self.up.setText(f"↑ {format_rate(snapshot.net_sent_rate)}")
        self._history.append(snapshot.net_recv_rate / 1024.0)  # KB/s for the chart
        peak = max(64.0, max(self._history) if self._history else 64.0)
        self.spark.set_values(self._history, peak)


class UptimeWidget(DeskWidget):
    widget_type = "uptime"
    title = "Uptime"
    icon = "timer"
    description = "System uptime, boot time and load average."
    default_span = 1
    minimum_body_height = 80

    def build(self) -> None:
        self.value = QLabel("—")
        self.value.setObjectName("StatValue")
        self.body_layout.addWidget(self.value)
        self.detail = Muted("")
        self.body_layout.addWidget(self.detail)
        self.load = Muted("")
        self.body_layout.addWidget(self.load)
        self.body_layout.addStretch(1)

    def refresh(self, snapshot: MonitorSnapshot | None) -> None:
        if snapshot is None or not snapshot.uptime:
            return
        self.value.setText(format_duration(snapshot.uptime))
        boot = datetime.fromtimestamp(datetime.now().timestamp() - snapshot.uptime)
        self.detail.setText(f"Booted {boot.strftime('%d %b %Y, %H:%M')}")
        if snapshot.load_average:
            one, five, fifteen = snapshot.load_average
            self.load.setText(f"Load average {one:.2f} · {five:.2f} · {fifteen:.2f}")
