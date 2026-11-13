"""System load plugin — a minimal widget plus a palette command."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from deskos.ui.components import ProgressStat
from deskos.utils.formatting import format_bytes
from deskos.widgets.base import DeskWidget


class SystemLoadWidget(DeskWidget):
    widget_type = "system_load"
    title = "System load"
    icon = "cpu"
    description = "CPU, memory and primary disk usage from the shared monitor."
    default_span = 1
    minimum_body_height = 96

    def build(self) -> None:
        self.cpu = ProgressStat(self.theme, "CPU")
        self.memory = ProgressStat(self.theme, "Memory")
        self.disk = ProgressStat(self.theme, "Disk")
        for stat in (self.cpu, self.memory, self.disk):
            self.body_layout.addWidget(stat)
        self.body_layout.addStretch(1)

    def refresh(self, snapshot) -> None:
        if snapshot is None:
            return
        self.cpu.set_value(snapshot.cpu_percent, f"{snapshot.cpu_percent:.0f}%")
        self.memory.set_value(
            snapshot.memory_percent,
            f"{format_bytes(snapshot.memory_used)} / {format_bytes(snapshot.memory_total)}",
        )
        if snapshot.disks:
            primary = snapshot.disks[0]
            self.disk.set_value(
                primary["percent"],
                f"{primary['mountpoint']} · {primary['percent']:.0f}%",
            )


def register(api) -> None:
    api.register_widget(
        "system_load",
        "System load",
        SystemLoadWidget,
        icon="cpu",
        description="CPU, memory and disk usage at a glance.",
        default_span=1,
    )

    def command() -> None:
        snapshot = api.system_snapshot()
        if snapshot is None:
            print("DeskOS has not sampled the system yet.")
            return
        print(
            "DeskOS system status — "
            f"CPU {snapshot.cpu_percent:.1f}%, "
            f"memory {snapshot.memory_percent:.1f}%, "
            f"{format_bytes(snapshot.memory_used)} of {format_bytes(snapshot.memory_total)}"
        )

    api.register_command(
        "print_status",
        "Print system status",
        command,
        description="Print CPU/memory status from the system_monitor plugin to the console.",
        keywords=("plugin", "status", "cpu", "memory"),
    )
    api.log("info", "system_monitor plugin registered")


def unload(api) -> None:
    api.log("info", "system_monitor plugin unloaded")
