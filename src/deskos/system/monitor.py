"""Single, shared system sampler.

Instead of every widget polling psutil on its own timer, one monitor samples at
the configured interval and broadcasts a snapshot.  That keeps CPU overhead low
and guarantees widgets show consistent numbers.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import psutil
from PySide6.QtCore import QObject, QTimer, Signal

from deskos.system.info import disk_usage, network_summary, uptime_seconds

log = logging.getLogger(__name__)

HISTORY_POINTS = 120


@dataclass
class MonitorSnapshot:
    timestamp: float = 0.0
    cpu_percent: float = 0.0
    cpu_per_core: list[float] = field(default_factory=list)
    cpu_freq_mhz: float = 0.0
    memory_percent: float = 0.0
    memory_used: int = 0
    memory_total: int = 0
    swap_percent: float = 0.0
    swap_used: int = 0
    swap_total: int = 0
    disks: list[dict[str, Any]] = field(default_factory=list)
    network_interfaces: list[dict[str, Any]] = field(default_factory=list)
    net_sent_rate: float = 0.0
    net_recv_rate: float = 0.0
    net_sent_total: int = 0
    net_recv_total: int = 0
    uptime: float = 0.0
    load_average: tuple[float, float, float] | None = None
    battery: dict[str, Any] | None = None


class SystemMonitor(QObject):
    sampled = Signal(object)  # MonitorSnapshot

    def __init__(
        self,
        backend,
        interval_ms: int = 1200,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.backend = backend
        self.interval_ms = max(400, int(interval_ms))
        self._timer = QTimer(self)
        self._timer.setInterval(self.interval_ms)
        self._timer.timeout.connect(self.sample)
        self._last_net: tuple[float, int, int] | None = None
        self._last_disks: list[dict[str, Any]] = []
        self._last_interfaces: list[dict[str, Any]] = []
        self._sample_count = 0
        self.cpu_history: deque[float] = deque(maxlen=HISTORY_POINTS)
        self.memory_history: deque[float] = deque(maxlen=HISTORY_POINTS)
        self.latest: MonitorSnapshot | None = None
        # Prime psutil so the first real reading is not 0%.
        psutil.cpu_percent(interval=None)

    # ------------------------------------------------------------- lifecycle
    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()
            self.sample()

    def stop(self) -> None:
        self._timer.stop()

    @property
    def running(self) -> bool:
        return self._timer.isActive()

    def set_interval(self, interval_ms: int) -> None:
        self.interval_ms = max(400, int(interval_ms))
        self._timer.setInterval(self.interval_ms)

    # ---------------------------------------------------------------- sample
    def sample(self) -> MonitorSnapshot:
        snapshot = MonitorSnapshot(timestamp=__import__("time").time())
        try:
            snapshot.cpu_percent = float(psutil.cpu_percent(interval=None))
            snapshot.cpu_per_core = [float(value) for value in psutil.cpu_percent(percpu=True)]
        except (OSError, RuntimeError):
            log.debug("cpu sampling failed", exc_info=True)

        try:
            frequency = psutil.cpu_freq()
            snapshot.cpu_freq_mhz = float(frequency.current) if frequency else 0.0
        except (AttributeError, OSError):
            snapshot.cpu_freq_mhz = 0.0

        try:
            memory = psutil.virtual_memory()
            snapshot.memory_percent = float(memory.percent)
            snapshot.memory_used = int(memory.used)
            snapshot.memory_total = int(memory.total)
            swap = psutil.swap_memory()
            snapshot.swap_percent = float(swap.percent)
            snapshot.swap_used = int(swap.used)
            snapshot.swap_total = int(swap.total)
        except (OSError, RuntimeError):
            log.debug("memory sampling failed", exc_info=True)

        # Disk and network enumeration is comparatively expensive; refresh it
        # every fifth sample (about once every six seconds by default).
        self._sample_count += 1
        if self._last_disks and self._sample_count % 5 != 1:
            snapshot.disks = self._last_disks
            snapshot.network_interfaces = self._last_interfaces
        else:
            self._last_disks = disk_usage()
            self._last_interfaces = network_summary(self.backend)
            snapshot.disks = self._last_disks
            snapshot.network_interfaces = self._last_interfaces

        try:
            counters = psutil.net_io_counters()
            now = snapshot.timestamp
            sent, received = int(counters.bytes_sent), int(counters.bytes_recv)
            snapshot.net_sent_total = sent
            snapshot.net_recv_total = received
            if self._last_net is not None:
                previous_time, previous_sent, previous_received = self._last_net
                elapsed = max(0.001, now - previous_time)
                snapshot.net_sent_rate = max(0.0, (sent - previous_sent) / elapsed)
                snapshot.net_recv_rate = max(0.0, (received - previous_received) / elapsed)
            self._last_net = (now, sent, received)
        except (OSError, RuntimeError):
            log.debug("network sampling failed", exc_info=True)

        snapshot.uptime = uptime_seconds()
        try:
            load = psutil.getloadavg()
            snapshot.load_average = (float(load[0]), float(load[1]), float(load[2]))
        except (AttributeError, OSError):
            snapshot.load_average = None

        try:
            snapshot.battery = self.backend.system.battery()
        except Exception:
            snapshot.battery = None

        self.cpu_history.append(snapshot.cpu_percent)
        self.memory_history.append(snapshot.memory_percent)
        self.latest = snapshot
        self.sampled.emit(snapshot)
        return snapshot
