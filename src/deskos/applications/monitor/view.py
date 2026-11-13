"""DeskMonitor: CPU, memory, disk, network, uptime and process overview."""

from __future__ import annotations

import logging
from collections import deque

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from deskos.applications.base import AppPage
from deskos.system.info import (
    battery_status,
    disk_usage,
    hardware_info,
    network_summary,
    os_info,
    top_processes,
    uptime_seconds,
)
from deskos.ui.components import (
    Card,
    Muted,
    ProgressStat,
    RingGauge,
    SectionTitle,
    Sparkline,
    scrollable,
)
from deskos.utils.formatting import (
    format_bytes,
    format_duration,
    format_percent,
    format_rate,
)
from deskos.utils.workers import run_async

log = logging.getLogger(__name__)


class MonitorPage(AppPage):
    def __init__(self, context, parent: QWidget | None = None) -> None:
        super().__init__(context, parent)
        self._net_history: deque[float] = deque(maxlen=60)
        self._process_timer = QTimer(self)
        self._process_timer.setInterval(2500)
        self._process_timer.timeout.connect(self._refresh_processes)
        self._info_loaded = False

        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(22, 8, 22, 18)
        root.setSpacing(14)

        header = QHBoxLayout()
        column = QVBoxLayout()
        column.setSpacing(2)
        title = QLabel("System monitor")
        title.setObjectName("Heading")
        self.subtitle = Muted("Live readings from psutil")
        column.addWidget(title)
        column.addWidget(self.subtitle)
        header.addLayout(column)
        header.addStretch(1)
        self.uptime_label = QLabel("—")
        self.uptime_label.setObjectName("Subheading")
        header.addWidget(self.uptime_label)
        root.addLayout(header)

        # ---- top gauges
        gauges = QGridLayout()
        gauges.setHorizontalSpacing(14)
        gauges.setVerticalSpacing(14)

        cpu_card = Card()
        cpu_card.layout.addWidget(SectionTitle("Processor"))
        cpu_row = QHBoxLayout()
        self.cpu_gauge = RingGauge(self.theme, "CPU", "blue", 132)
        cpu_row.addWidget(self.cpu_gauge)
        cpu_details = QVBoxLayout()
        cpu_details.setSpacing(4)
        self.cpu_model = Muted("Reading hardware information…")
        self.cpu_freq = Muted("")
        self.cpu_cores = Muted("")
        cpu_details.addWidget(self.cpu_model)
        cpu_details.addWidget(self.cpu_freq)
        cpu_details.addWidget(self.cpu_cores)
        cpu_details.addStretch(1)
        cpu_row.addLayout(cpu_details, 1)
        cpu_card.layout.addLayout(cpu_row)
        gauges.addWidget(cpu_card, 0, 0)

        memory_card = Card()
        memory_card.layout.addWidget(SectionTitle("Memory"))
        memory_row = QHBoxLayout()
        self.memory_gauge = RingGauge(self.theme, "RAM", "green", 132)
        memory_row.addWidget(self.memory_gauge)
        memory_details = QVBoxLayout()
        memory_details.setSpacing(4)
        self.memory_used = Muted("—")
        self.swap_stat = ProgressStat(self.theme, "Swap")
        self.swap_stat.setMaximumHeight(52)
        memory_details.addWidget(self.memory_used)
        memory_details.addWidget(self.swap_stat)
        memory_details.addStretch(1)
        memory_row.addLayout(memory_details, 1)
        memory_card.layout.addLayout(memory_row)
        gauges.addWidget(memory_card, 0, 1)

        storage_card = Card()
        storage_card.layout.addWidget(SectionTitle("Storage"))
        self.disk_rows = QVBoxLayout()
        self.disk_rows.setSpacing(8)
        storage_card.layout.addLayout(self.disk_rows)
        storage_card.layout.addStretch(1)
        self._disk_signature: tuple = ()
        gauges.addWidget(storage_card, 0, 2)
        for column_index in range(3):
            gauges.setColumnStretch(column_index, 1)
        root.addLayout(gauges)

        # ---- graphs
        graph_card = Card()
        graph_header = QHBoxLayout()
        graph_header.addWidget(SectionTitle("Throughput history"))
        graph_header.addStretch(1)
        self.interval_label = Muted("")
        graph_header.addWidget(self.interval_label)
        graph_card.layout.addLayout(graph_header)

        graphs = QHBoxLayout()
        graphs.setSpacing(18)
        self.cpu_graph = Sparkline(self.theme, "blue", 120)
        self.memory_graph = Sparkline(self.theme, "green", 120)
        self.net_graph = Sparkline(self.theme, "teal", 120)
        for spark, label in (
            (self.cpu_graph, "CPU %"),
            (self.memory_graph, "Memory %"),
            (self.net_graph, "Network"),
        ):
            column = QVBoxLayout()
            column.setSpacing(2)
            caption = QLabel(label)
            caption.setObjectName("StatLabel")
            column.addWidget(caption)
            column.addWidget(spark)
            graphs.addLayout(column, 1)
        graph_card.layout.addLayout(graphs)
        root.addWidget(graph_card)

        # ---- network + hardware
        info_grid = QGridLayout()
        info_grid.setHorizontalSpacing(14)
        network_card = Card()
        network_card.layout.addWidget(SectionTitle("Network"))
        self.network_rows = QVBoxLayout()
        self.network_rows.setSpacing(6)
        network_card.layout.addLayout(self.network_rows)
        network_card.layout.addStretch(1)
        self._network_signature: tuple = ()
        info_grid.addWidget(network_card, 0, 0)

        hardware_card = Card()
        hardware_card.layout.addWidget(SectionTitle("Hardware & OS"))
        self.hardware_rows = QVBoxLayout()
        self.hardware_rows.setSpacing(4)
        hardware_card.layout.addLayout(self.hardware_rows)
        hardware_card.layout.addStretch(1)
        info_grid.addWidget(hardware_card, 0, 1)
        info_grid.setColumnStretch(0, 1)
        info_grid.setColumnStretch(1, 1)
        root.addLayout(info_grid)

        # ---- processes
        process_card = Card()
        process_header = QHBoxLayout()
        process_header.addWidget(SectionTitle("Top processes"))
        process_header.addStretch(1)
        self.process_note = Muted("Sorted by CPU")
        process_header.addWidget(self.process_note)
        process_card.layout.addLayout(process_header)

        self.process_table = QTableWidget(0, 4)
        self.process_table.setHorizontalHeaderLabels(["Process", "PID", "CPU %", "Memory"])
        self.process_table.verticalHeader().setVisible(False)
        self.process_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.process_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.process_table.setAlternatingRowColors(False)
        self.process_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        for column in (1, 2, 3):
            self.process_table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        self.process_table.setMinimumHeight(260)
        process_card.layout.addWidget(self.process_table)
        root.addWidget(process_card)

        root.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scrollable(page))

        self.ctx.monitor.sampled.connect(self._on_snapshot)
        self.ctx.bus.subscribe("theme.changed", self._on_theme_changed)

    # ---------------------------------------------------------------- lifecycle
    def on_activated(self) -> None:
        if not self._info_loaded:
            self._load_static_info()
        self._refresh_processes()
        self._process_timer.start()

    def on_closing(self) -> None:
        self._process_timer.stop()

    def _load_static_info(self) -> None:
        self._info_loaded = True
        run_async(hardware_info, self._apply_hardware, None, self.ctx.platform)
        run_async(os_info, self._apply_os, None, self.ctx.platform)

    def _apply_hardware(self, info: dict) -> None:
        self.cpu_model.setText(info.get("processor", "Unknown CPU"))
        self.cpu_cores.setText(
            f"{info.get('cores_physical', '?')} cores · {info.get('cores_logical', '?')} threads"
            + (f" · {info.get('machine', '')}" if info.get("machine") else "")
        )
        freq = info.get("cpu_mhz")
        if freq and freq != "—":
            self.cpu_freq.setText(f"Max frequency {float(freq) / 1000:.2f} GHz")
        self._hardware = info
        self._render_hardware()

    def _apply_os(self, info: dict) -> None:
        self._os = info
        self._render_hardware()

    def _render_hardware(self) -> None:
        if not hasattr(self, "_os") or not hasattr(self, "_hardware"):
            return
        while self.hardware_rows.count():
            item = self.hardware_rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        rows = [
            ("OS", self._os.get("name", "—")),
            ("Version", self._os.get("release", "—")),
            ("Build", self._os.get("build", "—")),
            ("Architecture", self._os.get("architecture", "—")),
            ("Hostname", self._os.get("hostname", "—")),
            ("User", self._os.get("user", "—")),
            ("Total memory", format_bytes(self._hardware.get("memory_total"))),
        ]
        for label, value in rows:
            row = QHBoxLayout()
            name = QLabel(label)
            name.setObjectName("StatLabel")
            name.setFixedWidth(112)
            row.addWidget(name)
            value_label = QLabel(str(value))
            value_label.setWordWrap(True)
            row.addWidget(value_label, 1)
            holder = QWidget()
            holder.setLayout(row)
            self.hardware_rows.addWidget(holder)

    # ----------------------------------------------------------------- refresh
    def _on_snapshot(self, snapshot) -> None:
        self.cpu_gauge.set_value(snapshot.cpu_percent, f"{snapshot.cpu_percent:.0f}%")
        self.memory_gauge.set_value(
            snapshot.memory_percent, f"{snapshot.memory_percent:.0f}%"
        )
        self.memory_used.setText(
            f"{format_bytes(snapshot.memory_used)} of {format_bytes(snapshot.memory_total)} in use"
        )
        self.swap_stat.set_value(
            snapshot.swap_percent,
            f"{format_bytes(snapshot.swap_used)} / {format_bytes(snapshot.swap_total)}",
        )
        self.uptime_label.setText(f"Uptime {format_duration(snapshot.uptime)}")
        self.cpu_graph.set_values(self.ctx.monitor.cpu_history, 100.0)
        self.memory_graph.set_values(self.ctx.monitor.memory_history, 100.0)
        self._net_history.append(snapshot.net_recv_rate / 1024.0)
        peak = max(64.0, max(self._net_history) if self._net_history else 64.0)
        self.net_graph.set_values(self._net_history, peak)
        self.interval_label.setText(f"sampling every {self.ctx.monitor.interval_ms} ms")

        self._render_disks(snapshot.disks)
        self._render_network(snapshot.network_interfaces, snapshot)
        battery = snapshot.battery
        if battery:
            self.subtitle.setText(
                f"Battery {battery['percent']}% · {'charging' if battery['plugged'] else 'on battery'}"
            )
        else:
            self.subtitle.setText(f"Live readings · {self.ctx.platform.display_name}")

    def _render_disks(self, disks) -> None:
        signature = tuple(disk["mountpoint"] for disk in disks)
        if signature != self._disk_signature:
            while self.disk_rows.count():
                item = self.disk_rows.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self._disk_stats = []
            for disk in disks[:3]:
                stat = ProgressStat(
                    self.theme, f"{disk['mountpoint']} ({disk['fstype'] or 'disk'})"
                )
                self.disk_rows.addWidget(stat)
                self._disk_stats.append(stat)
            self._disk_signature = signature
        for stat, disk in zip(getattr(self, "_disk_stats", []), disks, strict=False):
            stat.set_value(
                disk["percent"],
                f"{format_bytes(disk['used'])} / {format_bytes(disk['total'])}",
                self.theme.palette.accents["red"]
                if disk["percent"] > 90
                else self.theme.palette.accents["teal"],
            )

    def _render_network(self, interfaces, snapshot) -> None:
        signature = tuple(item["name"] for item in interfaces)
        if signature != self._network_signature:
            while self.network_rows.count():
                item = self.network_rows.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self._network_labels = {}
            for interface in interfaces[:5]:
                row = QHBoxLayout()
                name = QLabel(interface["name"])
                name.setObjectName("StatLabel")
                row.addWidget(name)
                value = Muted("")
                row.addWidget(value, 1, Qt.AlignmentFlag.AlignRight)
                holder = QWidget()
                holder.setLayout(row)
                self.network_rows.addWidget(holder)
                self._network_labels[interface["name"]] = value
            self._network_signature = signature
        for interface in interfaces:
            label = getattr(self, "_network_labels", {}).get(interface["name"])
            if label is None:
                continue
            state = "up" if interface["is_up"] else "down"
            ip = interface["ipv4"] or "no IPv4"
            speed = f"{interface['speed_mbps']} Mbps" if interface["speed_mbps"] else "—"
            label.setText(f"{state} · {ip} · {speed}")
        if not interfaces:
            self.network_rows.addWidget(Muted("No network adapters detected"))
        if not hasattr(self, "_totals_label"):
            self._totals_label = Muted("")
            self.network_rows.addWidget(self._totals_label)
        self._totals_label.setText(
            f"Total ↓ {format_bytes(snapshot.net_recv_total)} · "
            f"↑ {format_bytes(snapshot.net_sent_total)} · "
            f"now {format_rate(snapshot.net_recv_rate)} down / {format_rate(snapshot.net_sent_rate)} up"
        )

    def _refresh_processes(self) -> None:
        if not self.isVisible():
            return
        run_async(top_processes, self._apply_processes, None, limit=14, sort_by="cpu")

    def _apply_processes(self, rows) -> None:
        self.process_table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            self.process_table.setItem(index, 0, QTableWidgetItem(str(row["name"])))
            pid_item = QTableWidgetItem(str(row["pid"]))
            pid_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.process_table.setItem(index, 1, pid_item)
            cpu_item = QTableWidgetItem(format_percent(row["cpu"], 1))
            cpu_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.process_table.setItem(index, 2, cpu_item)
            memory_item = QTableWidgetItem(
                f"{format_bytes(row['memory'])} ({row['memory_percent']:.1f}%)"
            )
            memory_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.process_table.setItem(index, 3, memory_item)
        self.process_note.setText("Sorted by CPU · refreshes every 2.5 s")

    def _on_theme_changed(self, **_payload) -> None:  # pragma: no cover - visual only
        self.update()
