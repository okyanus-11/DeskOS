"""On-demand system information queries (no fabricated values).

Every function returns real data from psutil or the platform backend, or an
empty/``None`` value when the operating system does not expose it.  UI layers
render missing values as an em dash rather than inventing numbers.
"""

from __future__ import annotations

import logging
import shutil
import time
from typing import Any

import psutil

from deskos.platform.base import PlatformBackend

log = logging.getLogger(__name__)


def os_info(backend: PlatformBackend) -> dict[str, str]:
    try:
        return backend.system.os_info()
    except Exception:
        log.exception("could not read OS information")
        return {}


def hardware_info(backend: PlatformBackend) -> dict[str, str]:
    try:
        return backend.system.hardware_info()
    except Exception:
        log.exception("could not read hardware information")
        return {}


def uptime_seconds() -> float:
    try:
        return max(0.0, time.time() - psutil.boot_time())
    except (OSError, RuntimeError):
        return 0.0


def disk_usage(include_optical: bool = False) -> list[dict[str, Any]]:
    """Real per-partition usage; network and pseudo filesystems are skipped."""
    disks: list[dict[str, Any]] = []
    for partition in psutil.disk_partitions(all=False):
        if not include_optical and ("cdrom" in partition.opts or not partition.fstype):
            continue
        try:
            usage = shutil.disk_usage(partition.mountpoint)
        except (OSError, PermissionError):
            continue
        disks.append(
            {
                "device": partition.device,
                "mountpoint": partition.mountpoint,
                "fstype": partition.fstype,
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "percent": (usage.used / usage.total * 100.0) if usage.total else 0.0,
            }
        )
    return disks


def network_summary(backend: PlatformBackend) -> list[dict[str, Any]]:
    try:
        return backend.system.network_interfaces()
    except Exception:
        log.exception("could not read network interfaces")
        return []


def top_processes(limit: int = 15, sort_by: str = "cpu") -> list[dict[str, Any]]:
    """Return the busiest processes.

    ``psutil`` needs two samples to report CPU percentages; the first call after
    startup returns mostly zeros which is expected behaviour, so the caller is
    expected to poll (DeskMonitor does this every two seconds).
    """
    rows: list[dict[str, Any]] = []
    attributes = ["pid", "name", "cpu_percent", "memory_percent", "memory_info"]
    for process in psutil.process_iter(attributes):
        try:
            info = process.info
            memory_info = info.get("memory_info")
            rows.append(
                {
                    "pid": info.get("pid", 0),
                    "name": info.get("name") or "—",
                    "cpu": float(info.get("cpu_percent") or 0.0),
                    "memory_percent": float(info.get("memory_percent") or 0.0),
                    "memory": int(getattr(memory_info, "rss", 0) or 0),
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    key = "memory_percent" if sort_by == "memory" else "cpu"
    rows.sort(key=lambda item: item[key], reverse=True)
    return rows[:limit]


def battery_status(backend: PlatformBackend) -> dict[str, Any] | None:
    try:
        return backend.system.battery()
    except Exception:
        log.debug("battery information unavailable", exc_info=True)
        return None
