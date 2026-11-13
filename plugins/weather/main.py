"""Weather forecast plugin — a complete, working example of the DeskOS plugin API.

It registers one dashboard widget that fetches a 3-day forecast from Open-Meteo
through the permission-gated ``api.fetch_json`` helper and remembers the chosen
city in namespaced plugin settings.

Install: this folder already lives in the bundled ``plugins/`` directory. Copy it
to ``%APPDATA%\\DeskOS\\plugins`` to load it as a user plugin instead.
"""

from __future__ import annotations

import urllib.parse
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from deskos.ui.components import Muted
from deskos.widgets.base import DeskWidget


class ForecastWidget(DeskWidget):
    widget_type = "weather_forecast"
    title = "3-day forecast"
    icon = "weather"
    description = "Daily min/max temperatures from Open-Meteo."
    default_span = 2
    minimum_body_height = 96

    def build(self) -> None:
        self.rows_layout = QVBoxLayout()
        self.rows_layout.setSpacing(6)
        self.body_layout.addLayout(self.rows_layout)
        self.status = Muted("Loading forecast…")
        self.body_layout.addWidget(self.status)
        self.body_layout.addStretch(1)
        self._place = None

    def apply_settings(self, settings: dict[str, Any]) -> None:
        super().apply_settings(settings)
        self._city = str(self.context.settings.get("city", "Istanbul"))
        if self.context.settings.get("_fetched_city") != self._city:
            self._fetch(self._city)

    def _fetch(self, city: str) -> None:
        self.status.setText(f"Locating {city}…")
        query = urllib.parse.urlencode(
            {"name": city, "count": 1, "language": "en", "format": "json"}
        )
        api = getattr(self.context, "api", None)
        if api is None:  # pragma: no cover - defensive
            self.status.setText("Plugin API unavailable")
            return
        api.fetch_json(
            f"https://geocoding-api.open-meteo.com/v1/search?{query}",
            self._on_geocode,
            self._on_error,
        )

    def _on_geocode(self, payload: dict[str, Any]) -> None:
        results = payload.get("results") or []
        if not results:
            self._on_error(f"Location '{self._city}' not found")
            return
        place = results[0]
        self._place = f"{place.get('name')}, {str(place.get('country_code', '')).upper()}"
        params = urllib.parse.urlencode(
            {
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "daily": "temperature_2m_max,temperature_2m_min,weather_code",
                "forecast_days": 3,
                "timezone": "auto",
            }
        )
        self.context.api.fetch_json(
            f"https://api.open-meteo.com/v1/forecast?{params}",
            self._on_forecast,
            self._on_error,
        )

    def _on_forecast(self, payload: dict[str, Any]) -> None:
        daily = payload.get("daily") or {}
        dates = daily.get("time") or []
        highs = daily.get("temperature_2m_max") or []
        lows = daily.get("temperature_2m_min") or []
        units = (payload.get("daily_units") or {}).get("temperature_2m_max", "°C")
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not dates:
            self.status.setText("No forecast returned")
            return
        for index, day in enumerate(dates[:3]):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            label = QLabel(str(day))
            label.setObjectName("StatLabel")
            row_layout.addWidget(label)
            row_layout.addStretch(1)
            try:
                low = float(lows[index])
                high = float(highs[index])
                value = f"{low:.0f}{units} / {high:.0f}{units}"
            except (IndexError, TypeError, ValueError):
                value = "—"
            amount = QLabel(value)
            amount.setObjectName("Subheading")
            amount.setAlignment(Qt.AlignmentFlag.AlignRight)
            row_layout.addWidget(amount)
            self.rows_layout.addWidget(row)

        self.status.setText(f"{self._place or self._city} · Open-Meteo")
        self.context.settings["_fetched_city"] = self._city

    def _on_error(self, message: str) -> None:
        self.status.setText(f"Forecast unavailable: {message}")

    def _api(self):
        return getattr(self.context, "api", None)

    def build_settings_form(self) -> QWidget | None:
        form = QWidget()
        layout = QVBoxLayout(form)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("City"))
        self._city_field = QLineEdit(str(self.context.settings.get("city", "Istanbul")))
        layout.addWidget(self._city_field)
        return form

    def collect_settings(self) -> dict[str, Any]:
        return {"city": self._city_field.text().strip() or "Istanbul"}


def register(api) -> None:
    """Called once when the plugin is loaded."""

    # The widget needs the plugin API for HTTP calls and settings persistence.
    def factory(widget_context):
        widget_context.api = api
        return ForecastWidget(widget_context)

    api.register_widget(
        "weather_forecast",
        "3-day forecast",
        factory,
        icon="weather",
        description="Daily low/high temperatures from Open-Meteo.",
        default_span=2,
    )
    api.log("info", "weather plugin registered")


def unload(api) -> None:
    api.log("info", "weather plugin unloaded")
