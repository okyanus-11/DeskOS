"""Widgets that talk to public APIs (weather and GitHub activity).

Both degrade gracefully: while loading they show a neutral message, and on
failure they display the reason rather than fabricated data.  No API keys are
required; the GitHub widget follows the unauthenticated rate limit.
"""

from __future__ import annotations

import json
import logging

import shiboken6
import urllib.parse
from datetime import datetime, timezone
from typing import Any

from PySide6.QtCore import QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from deskos.ui.components import Muted
from deskos.utils.formatting import relative_time
from deskos.widgets.base import DeskWidget

log = logging.getLogger(__name__)

WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Dense drizzle",
    56: "Freezing drizzle",
    57: "Freezing drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Freezing rain",
    67: "Freezing rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Rain showers",
    81: "Rain showers",
    82: "Violent rain showers",
    85: "Snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Thunderstorm with heavy hail",
}


def describe_weather_code(code: int | None) -> str:
    if code is None:
        return "Unknown"
    return WEATHER_CODES.get(int(code), f"Weather code {code}")


def parse_weather(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalise an Open-Meteo response (pure function, unit tested)."""
    current = payload.get("current") or {}
    return {
        "temperature": current.get("temperature_2m"),
        "apparent": current.get("apparent_temperature"),
        "humidity": current.get("relative_humidity_2m"),
        "wind": current.get("wind_speed_10m"),
        "code": current.get("weather_code"),
        "description": describe_weather_code(current.get("weather_code")),
        "units": (payload.get("current_units") or {}).get("temperature_2m", "°C"),
    }


class _NetworkWidget(DeskWidget):
    """Shared helper: JSON GET with graceful error handling."""

    def __init__(self, context, parent=None) -> None:
        self._manager: QNetworkAccessManager | None = None
        self._replies: set[QNetworkReply] = set()
        super().__init__(context, parent)
        if self._manager is None:
            self._manager = QNetworkAccessManager(self)

    def _get_json(self, url: str, on_success, *, headers: dict[str, str] | None = None) -> None:
        request = QNetworkRequest(QUrl(url))
        request.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, "DeskOS/1.0")
        request.setTransferTimeout(12000)
        for key, value in (headers or {}).items():
            request.setRawHeader(key.encode(), value.encode())
        if self._manager is None:
            # apply_settings() can run during base construction; create lazily.
            self._manager = QNetworkAccessManager(self)
        reply = self._manager.get(request)
        self._replies.add(reply)
        reply.finished.connect(lambda: self._replies.discard(reply))
        reply.finished.connect(lambda: self._handle_reply(reply, on_success))

    def _handle_reply(self, reply: QNetworkReply, on_success) -> None:
        if not shiboken6.isValid(self):
            # The widget was removed while the request was in flight.
            reply.deleteLater()
            return
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self._on_network_error(reply.errorString())
                return
            raw = bytes(reply.readAll().data())
            payload = json.loads(raw.decode("utf-8", errors="replace"))
            on_success(payload)
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._on_network_error("Invalid response from the server")
        except Exception:
            log.exception("widget network request failed")
            self._on_network_error("Request failed")
        finally:
            reply.deleteLater()

    def _on_network_error(self, message: str) -> None:
        log.info("widget network error: %s", message)


class WeatherWidget(_NetworkWidget):
    widget_type = "weather"
    title = "Weather"
    icon = "weather"
    description = "Current conditions from Open-Meteo (no API key required)."
    default_span = 2
    minimum_body_height = 90

    def build(self) -> None:
        row = QHBoxLayout()
        left = QVBoxLayout()
        left.setSpacing(0)
        self.temperature = QLabel("—")
        self.temperature.setObjectName("StatValue")
        self.description = Muted("Fetching forecast…")
        left.addWidget(self.temperature)
        left.addWidget(self.description)
        row.addLayout(left)
        row.addStretch(1)
        self.body_layout.addLayout(row)

        self.details = Muted("")
        self.body_layout.addWidget(self.details)

        self.attribution = QLabel("Data: Open-Meteo")
        self.attribution.setObjectName("Muted")
        self.body_layout.addWidget(self.attribution)
        self.body_layout.addStretch(1)

        self._city = ""
        self._refresh_timer = None

    def apply_settings(self, settings: dict[str, Any]) -> None:
        super().apply_settings(settings)
        city = str(self.context.settings.get("city") or "Istanbul")
        if city != self._city:
            self._city = city
            self._fetch()

    def _fetch(self) -> None:
        query = urllib.parse.urlencode(
            {"name": self._city, "count": 1, "language": "en", "format": "json"}
        )
        self.description.setText(f"Locating {self._city}…")
        self._get_json(
            f"https://geocoding-api.open-meteo.com/v1/search?{query}", self._on_geocode
        )

    def _on_geocode(self, payload: dict[str, Any]) -> None:
        results = payload.get("results") or []
        if not results:
            self._on_network_error(f"Location '{self._city}' was not found")
            self.description.setText(f"Location '{self._city}' not found")
            return
        place = results[0]
        self._place_name = f"{place.get('name')}, {place.get('country_code', '').upper()}"
        params = urllib.parse.urlencode(
            {
                "latitude": place.get("latitude"),
                "longitude": place.get("longitude"),
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
                "timezone": "auto",
            }
        )
        self._get_json(f"https://api.open-meteo.com/v1/forecast?{params}", self._on_forecast)

    def _on_forecast(self, payload: dict[str, Any]) -> None:
        data = parse_weather(payload)
        unit = data["units"] or "°C"
        if data["temperature"] is None:
            self._on_network_error("Forecast response was incomplete")
            self.description.setText("No forecast data returned")
            return
        self.temperature.setText(f"{data['temperature']:.0f}{unit}")
        self.description.setText(f"{data['description']} · {getattr(self, '_place_name', self._city)}")
        parts = []
        if data["apparent"] is not None:
            parts.append(f"Feels like {data['apparent']:.0f}{unit}")
        if data["humidity"] is not None:
            parts.append(f"Humidity {data['humidity']:.0f}%")
        if data["wind"] is not None:
            parts.append(f"Wind {data['wind']:.0f} km/h")
        self.details.setText(" · ".join(parts))

    def _on_network_error(self, message: str) -> None:
        super()._on_network_error(message)
        if hasattr(self, "description"):
            self.description.setText("Weather unavailable")
            if not self.details.text():
                self.details.setText("Check the connection or city name in widget settings.")

    def build_settings_form(self) -> QWidget | None:
        form = QWidget()
        layout = QVBoxLayout(form)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("City"))
        self._city_field = QLineEdit(str(self.context.settings.get("city", "Istanbul")))
        self._city_field.setPlaceholderText("e.g. Istanbul")
        layout.addWidget(self._city_field)
        layout.addWidget(Muted("Geocoded with Open-Meteo; no API key needed."))
        return form

    def collect_settings(self) -> dict[str, Any]:
        return {"city": self._city_field.text().strip() or "Istanbul"}


class GithubWidget(_NetworkWidget):
    widget_type = "github"
    title = "GitHub activity"
    icon = "github"
    description = "Latest public events for a GitHub user or organisation."
    default_span = 2
    minimum_body_height = 90

    def build(self) -> None:
        self.heading = QLabel("—")
        self.heading.setObjectName("Subheading")
        self.body_layout.addWidget(self.heading)
        self.latest = Muted("")
        self.latest.setWordWrap(True)
        self.body_layout.addWidget(self.latest)
        self.summary = Muted("")
        self.body_layout.addWidget(self.summary)
        self.body_layout.addStretch(1)
        self._user = ""

    def apply_settings(self, settings: dict[str, Any]) -> None:
        super().apply_settings(settings)
        user = str(self.context.settings.get("username") or "").strip()
        if user != self._user:
            self._user = user
            if user:
                self._fetch()
            else:
                self.heading.setText("No username configured")
                self.latest.setText("Add a GitHub username in the widget settings.")
                self.summary.setText("")

    def _fetch(self) -> None:
        self.heading.setText(f"@{self._user}")
        self.latest.setText("Fetching public activity…")
        url = f"https://api.github.com/users/{urllib.parse.quote(self._user)}/events/public?per_page=20"
        self._get_json(
            url,
            self._on_events,
            headers={"Accept": "application/vnd.github+json"},
        )

    def _on_events(self, payload: Any) -> None:
        if not isinstance(payload, list):
            self._on_network_error("Unexpected GitHub response")
            return
        if not payload:
            self.latest.setText("No public events yet.")
            self.summary.setText("")
            return
        event = payload[0] if isinstance(payload[0], dict) else {}
        kind = str(event.get("type", "Event")).replace("Event", "")
        repo = (event.get("repo") or {}).get("name", "")
        created = str(event.get("created_at", ""))
        self.latest.setText(f"{kind} in {repo}" if repo else kind)
        self.summary.setText(f"{len(payload)} recent public events · latest {relative_time(created)}")

    def _on_network_error(self, message: str) -> None:
        super()._on_network_error(message)
        if hasattr(self, "latest"):
            self.latest.setText("Could not load GitHub activity")
            self.summary.setText("The API may be rate limited; try again later.")

    def build_settings_form(self) -> QWidget | None:
        form = QWidget()
        layout = QVBoxLayout(form)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("GitHub username"))
        self._user_field = QLineEdit(str(self.context.settings.get("username", "")))
        self._user_field.setPlaceholderText("e.g. okyanus-11")
        layout.addWidget(self._user_field)
        layout.addWidget(
            Muted("Uses the public GitHub API without authentication (60 requests/hour).")
        )
        return form

    def collect_settings(self) -> dict[str, Any]:
        return {"username": self._user_field.text().strip()}
