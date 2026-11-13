"""System overview inside the Control Center."""

from __future__ import annotations

import logging

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from deskos.core.context import DeskOSContext
from deskos.system.info import hardware_info, os_info
from deskos.ui.components import (
    Card,
    Muted,
    ProgressStat,
    RingGauge,
    SectionTitle,
    StatBlock,
    scrollable,
)
from deskos.utils.formatting import format_bytes, format_duration
from deskos.utils.workers import run_async

log = logging.getLogger(__name__)


class SystemPage(QWidget):
    def __init__(self, context: DeskOSContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = context
        self.theme = context.theme
        self.icons = context.icons
        self._static_loaded = False
        self._os: dict = {}
        self._hardware: dict = {}

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 10, 24, 20)
        layout.setSpacing(14)

        title = QLabel("System")
        title.setObjectName("Heading")
        layout.addWidget(title)
        layout.addWidget(Muted("Live hardware and operating system information from this computer."))

        gauges = QHBoxLayout()
        gauges.setSpacing(14)
        cpu_card = Card()
        cpu_card.layout.addWidget(SectionTitle("CPU"))
        self.cpu_gauge = RingGauge(self.theme, "Processor", "blue", 120)
        cpu_card.layout.addWidget(self.cpu_gauge)
        gauges.addWidget(cpu_card)
        memory_card = Card()
        memory_card.layout.addWidget(SectionTitle("Memory"))
        self.memory_gauge = RingGauge(self.theme, "RAM", "green", 120)
        memory_card.layout.addWidget(self.memory_gauge)
        gauges.addWidget(memory_card)

        stats_card = Card()
        stats_card.layout.addWidget(SectionTitle("Current session"))
        stats_grid = QGridLayout()
        self.uptime_stat = StatBlock("Uptime", "—", self.icons, "timer")
        self.swap_stat = StatBlock("Swap", "—", self.icons, "memory")
        self.battery_stat = StatBlock("Battery", "—", self.icons, "storage")
        self.freq_stat = StatBlock("CPU frequency", "—", self.icons, "cpu")
        stats_grid.addWidget(self.uptime_stat, 0, 0)
        stats_grid.addWidget(self.freq_stat, 0, 1)
        stats_grid.addWidget(self.swap_stat, 1, 0)
        stats_grid.addWidget(self.battery_stat, 1, 1)
        stats_card.layout.addLayout(stats_grid)
        stats_card.layout.addStretch(1)
        gauges.addWidget(stats_card, 1)
        layout.addLayout(gauges)

        storage_card = Card()
        storage_card.layout.addWidget(SectionTitle("Storage"))
        self.disk_rows = QVBoxLayout()
        self.disk_rows.setSpacing(8)
        storage_card.layout.addLayout(self.disk_rows)
        storage_card.layout.addStretch(1)
        self._disk_signature: tuple = ()
        layout.addWidget(storage_card)

        info_card = Card()
        info_card.layout.addWidget(SectionTitle("Hardware & operating system"))
        self.info_rows = QGridLayout()
        self.info_rows.setHorizontalSpacing(24)
        self.info_rows.setVerticalSpacing(6)
        info_card.layout.addLayout(self.info_rows)
        layout.addWidget(info_card)
        layout.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scrollable(container))

        self.ctx.monitor.sampled.connect(self._on_snapshot)
        self.refresh()

    # ------------------------------------------------------------------ data
    def refresh(self) -> None:
        if not self._static_loaded:
            self._static_loaded = True
            run_async(os_info, self._apply_os, None, self.ctx.platform)
            run_async(hardware_info, self._apply_hardware, None, self.ctx.platform)

    def _apply_os(self, info: dict) -> None:
        self._os = info
        self._render_info()

    def _apply_hardware(self, info: dict) -> None:
        self._hardware = info
        self._render_info()

    def _render_info(self) -> None:
        if not hasattr(self, "_os") or not hasattr(self, "_hardware"):
            return
        while self.info_rows.count():
            item = self.info_rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        rows = [
            ("Operating system", self._os.get("name", "—")),
            ("Version", self._os.get("release", "—")),
            ("Build", self._os.get("build", "—")),
            ("Architecture", self._os.get("architecture", "—")),
            ("Processor", self._hardware.get("processor", "—")),
            ("Cores / threads", f"{self._hardware.get('cores_physical', '?')} / {self._hardware.get('cores_logical', '?')}"),
            ("Total memory", format_bytes(self._hardware.get("memory_total"))),
            ("Hostname", self._os.get("hostname", "—")),
        ]
        for index, (label, value) in enumerate(rows):
            name = QLabel(label)
            name.setObjectName("StatLabel")
            name.setFixedWidth(150)
            self.info_rows.addWidget(name, index, 0)
            value_label = QLabel(str(value))
            value_label.setWordWrap(True)
            self.info_rows.addWidget(value_label, index, 1)
        self.info_rows.setColumnStretch(1, 1)

    def _on_snapshot(self, snapshot) -> None:
        self.cpu_gauge.set_value(snapshot.cpu_percent, f"{snapshot.cpu_percent:.0f}%")
        self.memory_gauge.set_value(
            snapshot.memory_percent,
            f"{snapshot.memory_percent:.0f}%",
        )
        self.uptime_stat.set_value(format_duration(snapshot.uptime), "Uptime")
        self.swap_stat.set_value(
            f"{snapshot.swap_percent:.0f}%",
            f"Swap ({format_bytes(snapshot.swap_used)})",
        )
        if snapshot.cpu_freq_mhz:
            self.freq_stat.set_value(f"{snapshot.cpu_freq_mhz / 1000:.2f} GHz", "CPU frequency")
        battery = snapshot.battery
        self.battery_stat.set_value(
            f"{battery['percent']}%" if battery else "Not present",
            "Battery" if battery else "Battery (desktop)",
        )
        self._render_disks(snapshot.disks)

    def _render_disks(self, disks) -> None:
        signature = tuple(disk["mountpoint"] for disk in disks)
        if signature != self._disk_signature:
            while self.disk_rows.count():
                item = self.disk_rows.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self._disk_stats = []
            for disk in disks:
                stat = ProgressStat(self.theme, f"{disk['mountpoint']} · {disk['fstype'] or 'disk'}")
                self.disk_rows.addWidget(stat)
                self._disk_stats.append(stat)
            self._disk_signature = signature
        for stat, disk in zip(getattr(self, "_disk_stats", []), disks, strict=False):
            stat.set_value(
                disk["percent"],
                f"{format_bytes(disk['free'])} free of {format_bytes(disk['total'])}",
            )
