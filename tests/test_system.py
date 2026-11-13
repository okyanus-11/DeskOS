"""System monitoring and information services (real psutil data, fake backend)."""

from __future__ import annotations

import pytest

from deskos.system.info import (
    disk_usage,
    hardware_info,
    network_summary,
    os_info,
    top_processes,
    uptime_seconds,
)
from deskos.system.monitor import HISTORY_POINTS, SystemMonitor


def test_monitor_sample_has_plausible_values(context):
    monitor = SystemMonitor(context.platform, 1000)
    snapshot = monitor.sample()
    assert 0.0 <= snapshot.cpu_percent <= 100.0 * 4  # psutil can exceed 100 on multi-core reads
    assert snapshot.memory_total > 0
    assert 0.0 <= snapshot.memory_percent <= 100.0
    assert snapshot.uptime >= 0
    assert isinstance(snapshot.cpu_per_core, list)
    assert monitor.latest is snapshot


def test_monitor_history_and_intervals(context):
    monitor = SystemMonitor(context.platform, 500)
    for _ in range(3):
        monitor.sample()
    assert len(monitor.cpu_history) == 3
    assert len(monitor.memory_history) == 3
    assert monitor.cpu_history.maxlen == HISTORY_POINTS
    monitor.set_interval(100)
    assert monitor.interval_ms == 400  # clamped to the minimum
    monitor.start()
    assert monitor.running
    monitor.stop()
    assert not monitor.running


def test_snapshot_signal_emitted(context, qapp):
    monitor = SystemMonitor(context.platform, 1000)
    received = []
    monitor.sampled.connect(received.append)
    monitor.sample()
    assert len(received) == 1


def test_top_processes_returns_real_rows():
    rows = top_processes(limit=5)
    assert rows
    assert len(rows) <= 5
    assert {"pid", "name", "cpu", "memory", "memory_percent"} <= set(rows[0])
    memory_sorted = top_processes(limit=5, sort_by="memory")
    assert [row["memory_percent"] for row in memory_sorted] == sorted(
        (row["memory_percent"] for row in memory_sorted), reverse=True
    )


def test_disk_usage_and_uptime():
    disks = disk_usage()
    assert all({"mountpoint", "total", "used", "free", "percent"} <= set(disk) for disk in disks)
    assert uptime_seconds() >= 0


def test_backend_information(context):
    os_data = os_info(context.platform)
    hardware = hardware_info(context.platform)
    interfaces = network_summary(context.platform)
    assert os_data["name"] == "TestOS"
    assert hardware["processor"] == "Test CPU"
    assert interfaces[0]["ipv4"] == "192.0.2.10"


def test_formatting_helpers():
    from deskos.utils.formatting import (
        format_bytes,
        format_duration,
        format_rate,
        format_stopwatch,
        format_timer,
        truncate,
    )

    assert format_bytes(0) == "0 B"
    assert format_bytes(1024) == "1.0 KB"
    assert format_bytes(8 * 1024**3) == "8.0 GB"
    assert format_bytes(None) == "—"
    assert format_rate(2048) == "2.0 KB/s"
    assert format_duration(90061) == "1d 01h 01m"
    assert format_duration(65) == "1m 05s"
    assert format_stopwatch(61_230) == "01:01.23"
    assert format_timer(3661) == "01:01:01"
    assert truncate("abcdefghij", 6) == "abcde…"
