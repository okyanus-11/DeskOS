"""DeskClock: digital clock, calendar, stopwatch, countdown timer, world clocks."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from PySide6.QtCore import QElapsedTimer, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCalendarWidget,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from deskos.applications.base import AppPage
from deskos.ui.components import Card, IconButton, Muted, SectionTitle
from deskos.utils.formatting import format_stopwatch, format_timer

log = logging.getLogger(__name__)

WORLD_ZONES = (
    "UTC",
    "Europe/London",
    "Europe/Berlin",
    "Europe/Istanbul",
    "Europe/Paris",
    "America/New_York",
    "America/Chicago",
    "America/Los_Angeles",
    "America/Sao_Paulo",
    "Asia/Dubai",
    "Asia/Kolkata",
    "Asia/Shanghai",
    "Asia/Tokyo",
    "Asia/Seoul",
    "Australia/Sydney",
)


class ClockPage(AppPage):
    def __init__(self, context, parent: QWidget | None = None) -> None:
        super().__init__(context, parent)
        self._stopwatch_elapsed = 0
        self._stopwatch_running = False
        self._stopwatch_timer = QElapsedTimer()
        self._laps: list[int] = []
        self._timer_remaining = 0
        self._timer_running = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 8, 18, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Clock")
        title.setObjectName("Heading")
        header.addWidget(title)
        header.addStretch(1)
        self.header_clock = QLabel("")
        self.header_clock.setObjectName("Subheading")
        header.addWidget(self.header_clock)
        layout.addLayout(header)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_clock_tab(), "Clock")
        self.tabs.addTab(self._build_stopwatch_tab(), "Stopwatch")
        self.tabs.addTab(self._build_timer_tab(), "Timer")
        self.tabs.addTab(self._build_world_tab(), "World clocks")
        layout.addWidget(self.tabs, 1)

        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(250)
        self._clock_timer.timeout.connect(self._tick)
        self._clock_timer.start()
        self._tick()

    # ------------------------------------------------------------------ clock
    def _build_clock_tab(self) -> QWidget:
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(22)

        left = QVBoxLayout()
        left.setSpacing(4)
        self.time_label = QLabel("--:--:--")
        self.time_label.setObjectName("AppTitle")
        font = self.time_label.font()
        font.setPixelSize(self.theme.font_px(64))
        font.setBold(True)
        self.time_label.setFont(font)
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left.addWidget(self.time_label)

        self.date_label = QLabel("")
        self.date_label.setObjectName("Subheading")
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left.addWidget(self.date_label)

        self.tz_label = Muted("")
        self.tz_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left.addWidget(self.tz_label)
        left.addStretch(1)

        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(False)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.calendar.setHorizontalHeaderFormat(
            QCalendarWidget.HorizontalHeaderFormat.ShortDayNames
        )
        self.calendar.setMinimumSize(420, 280)
        left.addWidget(self.calendar)
        layout.addLayout(left, 1)
        return tab

    # --------------------------------------------------------------- stopwatch
    def _build_stopwatch_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(14)

        self.stopwatch_label = QLabel("00:00.00")
        self.stopwatch_label.setObjectName("AppTitle")
        font = self.stopwatch_label.font()
        font.setPixelSize(self.theme.font_px(60))
        font.setBold(True)
        self.stopwatch_label.setFont(font)
        self.stopwatch_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.stopwatch_label)

        buttons = QHBoxLayout()
        buttons.setAlignment(Qt.AlignmentFlag.AlignCenter)
        buttons.setSpacing(10)
        self.sw_start = QPushButton("Start")
        self.sw_start.setObjectName("PrimaryButton")
        self.sw_start.clicked.connect(self._stopwatch_start)
        self.sw_lap = QPushButton("Lap")
        self.sw_lap.clicked.connect(self._stopwatch_lap)
        self.sw_reset = QPushButton("Reset")
        self.sw_reset.clicked.connect(self._stopwatch_reset)
        for button in (self.sw_start, self.sw_lap, self.sw_reset):
            buttons.addWidget(button)
        layout.addLayout(buttons)

        self.laps = QListWidget()
        self.laps.setMaximumHeight(260)
        layout.addWidget(self.laps, 1)
        return tab

    def _stopwatch_start(self) -> None:
        if self._stopwatch_running:
            self._stopwatch_elapsed += self._stopwatch_timer.elapsed()
            self._stopwatch_running = False
            self.sw_start.setText("Start")
        else:
            self._stopwatch_timer.start()
            self._stopwatch_running = True
            self.sw_start.setText("Pause")

    def _stopwatch_lap(self) -> None:
        current = self._current_stopwatch_ms()
        previous = self._laps[-1] if self._laps else 0
        self._laps.append(current)
        item = QListWidgetItem(
            f"Lap {len(self._laps):02d}   {format_stopwatch(current - previous)}"
            f"   ·   total {format_stopwatch(current)}"
        )
        self.laps.insertItem(0, item)

    def _stopwatch_reset(self) -> None:
        self._stopwatch_running = False
        self._stopwatch_elapsed = 0
        self._laps.clear()
        self.laps.clear()
        self.sw_start.setText("Start")
        self.stopwatch_label.setText("00:00.00")

    def _current_stopwatch_ms(self) -> int:
        elapsed = self._stopwatch_elapsed
        if self._stopwatch_running:
            elapsed += self._stopwatch_timer.elapsed()
        return elapsed

    # ------------------------------------------------------------------- timer
    def _build_timer_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(14)

        self.timer_label = QLabel("05:00")
        self.timer_label.setObjectName("AppTitle")
        font = self.timer_label.font()
        font.setPixelSize(self.theme.font_px(60))
        font.setBold(True)
        self.timer_label.setFont(font)
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.timer_label)

        self.timer_progress = QProgressBar()
        self.timer_progress.setTextVisible(False)
        self.timer_progress.setRange(0, 100)
        self.timer_progress.setValue(100)
        layout.addWidget(self.timer_progress)

        form = QHBoxLayout()
        form.setAlignment(Qt.AlignmentFlag.AlignCenter)
        form.setSpacing(8)
        form.addWidget(QLabel("Minutes"))
        self.minutes_spin = QSpinBox()
        self.minutes_spin.setRange(0, 600)
        self.minutes_spin.setValue(5)
        form.addWidget(self.minutes_spin)
        form.addWidget(QLabel("Seconds"))
        self.seconds_spin = QSpinBox()
        self.seconds_spin.setRange(0, 59)
        form.addWidget(self.seconds_spin)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        buttons.setAlignment(Qt.AlignmentFlag.AlignCenter)
        buttons.setSpacing(10)
        self.timer_start = QPushButton("Start")
        self.timer_start.setObjectName("PrimaryButton")
        self.timer_start.clicked.connect(self._timer_toggle)
        self.timer_reset = QPushButton("Reset")
        self.timer_reset.clicked.connect(self._timer_reset)
        buttons.addWidget(self.timer_start)
        buttons.addWidget(self.timer_reset)
        layout.addLayout(buttons)
        layout.addStretch(1)
        return tab

    def _timer_total(self) -> int:
        return self.minutes_spin.value() * 60 + self.seconds_spin.value()

    def _timer_toggle(self) -> None:
        if self._timer_running:
            self._timer_running = False
            self.timer_start.setText("Resume")
            return
        if self._timer_remaining <= 0:
            self._timer_remaining = self._timer_total()
        if self._timer_remaining <= 0:
            self.ctx.toast("Choose a duration first")
            return
        self._timer_running = True
        self.timer_start.setText("Pause")

    def _timer_reset(self) -> None:
        self._timer_running = False
        self._timer_remaining = 0
        self.timer_start.setText("Start")
        self.timer_progress.setValue(100)
        self.timer_label.setText(format_timer(self._timer_total()))

    def _tick_timer(self) -> None:
        if not self._timer_running:
            if self._timer_remaining <= 0:
                self.timer_label.setText(format_timer(self._timer_total()))
                self.timer_progress.setValue(100)
            return
        self._timer_remaining -= 1
        self.timer_label.setText(format_timer(self._timer_remaining))
        total = max(1, self._timer_total())
        self.timer_progress.setValue(int(self._timer_remaining / total * 100))
        if self._timer_remaining <= 0:
            self._timer_running = False
            self.timer_start.setText("Start")
            QApplication.beep()
            self.ctx.toast("Timer finished", 6000)

    # ------------------------------------------------------------ world clocks
    def _build_world_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        add_row = QHBoxLayout()
        self.zone_combo = QComboBox()
        self.zone_combo.addItems(WORLD_ZONES)
        add_row.addWidget(self.zone_combo, 1)
        add_button = QPushButton("Add")
        add_button.setObjectName("PrimaryButton")
        add_button.clicked.connect(self._add_zone)
        add_row.addWidget(add_button)
        layout.addLayout(add_row)

        self.zone_list = QListWidget()
        layout.addWidget(self.zone_list, 1)

        self.zone_row = QHBoxLayout()
        remove_button = IconButton(self.icons, "trash", "Remove selected zone", 30, 16)
        remove_button.clicked.connect(self._remove_zone)
        self.zone_row.addWidget(remove_button)
        self.zone_row.addWidget(Muted("Times update every second from your system time zone database."))
        self.zone_row.addStretch(1)
        layout.addLayout(self.zone_row)

        for zone in self.ctx.config.get("clock.zones", ["Europe/Istanbul", "UTC"]):
            self._append_zone(str(zone))
        return tab

    def _append_zone(self, name: str) -> None:
        try:
            ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            self.ctx.toast(f"Unknown time zone: {name}")
            return
        for row in range(self.zone_list.count()):
            if self.zone_list.item(row).data(Qt.ItemDataRole.UserRole) == name:
                return
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, name)
        self.zone_list.addItem(item)
        self._update_zone_item(item)

    def _add_zone(self) -> None:
        self._append_zone(self.zone_combo.currentText())
        self._persist_zones()

    def _remove_zone(self) -> None:
        row = self.zone_list.currentRow()
        if row >= 0:
            self.zone_list.takeItem(row)
            self._persist_zones()

    def _persist_zones(self) -> None:
        zones = [
            str(self.zone_list.item(row).data(Qt.ItemDataRole.UserRole))
            for row in range(self.zone_list.count())
        ]
        self.ctx.config.set("clock.zones", zones)

    def _update_zone_item(self, item: QListWidgetItem) -> None:
        name = item.data(Qt.ItemDataRole.UserRole)
        try:
            zone = ZoneInfo(str(name))
            now = datetime.now(zone)
            item.setText(f"{name:<22} {now.strftime('%H:%M:%S')}   {now.strftime('%a %d %b')}")
        except (ZoneInfoNotFoundError, ValueError):
            item.setText(f"{name} — unavailable")

    # -------------------------------------------------------------------- tick
    def _tick(self) -> None:
        now = datetime.now()
        self.time_label.setText(now.strftime("%H:%M:%S"))
        self.date_label.setText(now.strftime("%A, %d %B %Y"))
        self.tz_label.setText(f"Time zone: {now.astimezone().tzname() or 'local'}")
        self.header_clock.setText(now.strftime("%H:%M"))

        if self._stopwatch_running:
            self.stopwatch_label.setText(format_stopwatch(self._current_stopwatch_ms()))
        elif self._stopwatch_elapsed:
            self.stopwatch_label.setText(format_stopwatch(self._stopwatch_elapsed))

        self._tick_timer()
        for row in range(self.zone_list.count()):
            self._update_zone_item(self.zone_list.item(row))
