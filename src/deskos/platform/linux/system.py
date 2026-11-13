"""POSIX/Desktop Linux system information."""

from __future__ import annotations

import logging
import os
import platform
import socket
from typing import Any

import psutil

from deskos.platform.base import SystemBackend

log = logging.getLogger(__name__)


def _pretty_name() -> str:
    try:
        with open("/etc/os-release", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return platform.system()


class LinuxSystem(SystemBackend):
    def os_info(self) -> dict[str, str]:
        return {
            "name": _pretty_name(),
            "version": platform.release(),
            "release": platform.release(),
            "build": platform.version(),
            "edition": platform.system(),
            "architecture": platform.machine(),
            "hostname": socket.gethostname(),
            "user": os.environ.get("USER", ""),
        }

    def hardware_info(self) -> dict[str, str]:
        cpu_freq = psutil.cpu_freq()
        memory = psutil.virtual_memory()
        return {
            "processor": platform.processor() or _cpu_model(),
            "cores_physical": str(psutil.cpu_count(logical=False) or 0),
            "cores_logical": str(psutil.cpu_count(logical=True) or 0),
            "cpu_mhz": f"{cpu_freq.max:.0f}" if cpu_freq else "—",
            "memory_total": str(memory.total),
            "machine": platform.machine(),
        }

    def network_interfaces(self) -> list[dict[str, Any]]:
        addresses = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        counters = psutil.net_io_counters(pernic=True)
        interfaces: list[dict[str, Any]] = []
        for name, entries in addresses.items():
            ipv4 = next(
                (
                    entry.address
                    for entry in entries
                    if entry.family == socket.AF_INET and not entry.address.startswith("127.")
                ),
                "",
            )
            mac = next(
                (entry.address for entry in entries if getattr(entry, "family", None) == psutil.AF_LINK),
                "",
            )
            stat = stats.get(name)
            counter = counters.get(name)
            interfaces.append(
                {
                    "name": name,
                    "ipv4": ipv4,
                    "mac": mac,
                    "is_up": bool(stat.isup) if stat else False,
                    "speed_mbps": stat.speed if stat else 0,
                    "bytes_sent": counter.bytes_sent if counter else 0,
                    "bytes_recv": counter.bytes_recv if counter else 0,
                }
            )
        interfaces.sort(key=lambda item: (not item["is_up"], not item["ipv4"], item["name"]))
        return interfaces

    def battery(self) -> dict[str, Any] | None:
        try:
            battery = psutil.sensors_battery()
        except (AttributeError, OSError):
            return None
        if battery is None:
            return None
        seconds = battery.secsleft
        return {
            "percent": round(float(battery.percent)),
            "plugged": bool(battery.power_plugged),
            "seconds_left": None if seconds in (psutil.POWER_TIME_UNLIMITED, -1) else seconds,
        }


def _cpu_model() -> str:
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as handle:
            for line in handle:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return "Unknown CPU"
