"""Plugin manifest model and the context object handed to plugins."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PySide6.QtCore import QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from deskos.data.repositories import PluginStateRepository

log = logging.getLogger(__name__)

API_VERSION = 1
ALLOWED_PERMISSIONS = {
    "widget": "Add widgets to the dashboard",
    "commands": "Add entries to the command palette",
    "system": "Read CPU/memory/network snapshots",
    "network": "Make outbound HTTP requests through the plugin helper",
    "settings": "Store namespaced plugin settings",
    "notifications": "Show toast notifications",
}
_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]{1,48}$")
_REQUIRED_FIELDS = ("id", "name", "version", "api_version", "entry")


class PluginError(RuntimeError):
    """Raised for invalid manifests and failed plugin operations."""


@dataclass
class PluginMetadata:
    id: str
    name: str
    version: str
    api_version: int
    entry: str
    author: str = ""
    description: str = ""
    permissions: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    widget: dict[str, Any] = field(default_factory=dict)
    homepage: str = ""
    path: Path | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any], path: Path) -> PluginMetadata:
        for key in _REQUIRED_FIELDS:
            if key not in payload:
                raise PluginError(f"plugin.json is missing required field '{key}'")
        plugin_id = str(payload["id"])
        if not _ID_PATTERN.match(plugin_id):
            raise PluginError(
                f"invalid plugin id '{plugin_id}' (lowercase letters, digits, '.', '_', '-')"
            )
        try:
            api_version = int(payload["api_version"])
        except (TypeError, ValueError) as exc:
            raise PluginError("api_version must be an integer") from exc
        if api_version != API_VERSION:
            raise PluginError(
                f"plugin targets API v{api_version}, this DeskOS build supports v{API_VERSION}"
            )
        permissions = payload.get("permissions", [])
        if not isinstance(permissions, list):
            raise PluginError("permissions must be a list")
        unknown = [item for item in permissions if item not in ALLOWED_PERMISSIONS]
        if unknown:
            raise PluginError(f"unknown permission(s): {', '.join(map(str, unknown))}")
        dependencies = payload.get("dependencies", [])
        if not isinstance(dependencies, list):
            raise PluginError("dependencies must be a list")
        widget = payload.get("widget", {})
        if widget and not isinstance(widget, dict):
            raise PluginError("widget must be an object")

        entry_path = path / str(payload["entry"])
        if not entry_path.is_file():
            raise PluginError(f"entry file '{payload['entry']}' does not exist")

        return cls(
            id=plugin_id,
            name=str(payload["name"]),
            version=str(payload["version"]),
            api_version=api_version,
            entry=str(payload["entry"]),
            author=str(payload.get("author", "")),
            description=str(payload.get("description", "")),
            permissions=[str(item) for item in permissions],
            dependencies=[str(item) for item in dependencies],
            widget=dict(widget),
            homepage=str(payload.get("homepage", "")),
            path=path,
        )

    @classmethod
    def load_manifest(cls, path: Path) -> PluginMetadata:
        manifest = path / "plugin.json"
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PluginError(f"could not read plugin.json: {exc}") from exc
        if not isinstance(payload, dict):
            raise PluginError("plugin.json must contain a JSON object")
        return cls.from_dict(payload, path)


class PluginHttp:
    """Single shared network manager for plugin HTTP fetches."""

    def __init__(self) -> None:
        self._manager = QNetworkAccessManager()

    def get_json(
        self,
        url: str,
        on_success: Callable[[Any], None],
        on_error: Callable[[str], None] | None = None,
        headers: dict[str, str] | None = None,
        timeout_ms: int = 12000,
    ) -> None:
        request = QNetworkRequest(QUrl(url))
        request.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, "DeskOS-plugin/1.0")
        request.setTransferTimeout(timeout_ms)
        for key, value in (headers or {}).items():
            request.setRawHeader(key.encode(), value.encode())
        reply = self._manager.get(request)

        def finish() -> None:
            try:
                if reply.error() != QNetworkReply.NetworkError.NoError:
                    if on_error is not None:
                        on_error(reply.errorString())
                    return
                raw = bytes(reply.readAll().data()).decode("utf-8", errors="replace")
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError as exc:
                    if on_error is not None:
                        on_error(f"invalid JSON: {exc}")
                    return
                on_success(payload)
            finally:
                reply.deleteLater()

        reply.finished.connect(finish)


class PluginContext:
    """The API surface available to a plugin during registration and at runtime."""

    def __init__(
        self,
        metadata: PluginMetadata,
        *,
        state: PluginStateRepository,
        widget_registry,
        command_registry,
        monitor,
        notify: Callable[[str], None],
        http: PluginHttp,
        data_dir: Path,
    ) -> None:
        self.metadata = metadata
        self._state = state
        self._widgets = widget_registry
        self._commands = command_registry
        self._monitor = monitor
        self._notify = notify
        self._http = http
        self.data_dir = data_dir
        self._settings = state.get_settings(metadata.id)
        self._widget_types: list[str] = []
        self._command_ids: list[str] = []

    # -------------------------------------------------------------- metadata
    @property
    def id(self) -> str:
        return self.metadata.id

    @property
    def name(self) -> str:
        return self.metadata.name

    @property
    def permissions(self) -> list[str]:
        return list(self.metadata.permissions)

    def has_permission(self, permission: str) -> bool:
        return permission in self.metadata.permissions

    def _require(self, permission: str) -> None:
        if permission not in self.metadata.permissions:
            raise PermissionError(
                f"plugin '{self.id}' did not declare the '{permission}' permission"
            )

    # -------------------------------------------------------------- settings
    def get_setting(self, key: str, default: Any = None) -> Any:
        return self._settings.get(key, default)

    def set_setting(self, key: str, value: Any) -> None:
        self._require("settings")
        self._settings[str(key)] = value
        self._state.save_settings(self.id, self._settings)

    def all_settings(self) -> dict[str, Any]:
        return dict(self._settings)

    # --------------------------------------------------------------- widgets
    def register_widget(
        self,
        widget_type: str,
        title: str,
        factory: Callable[[Any], Any],
        *,
        icon: str = "plugins",
        description: str = "",
        default_span: int = 1,
        default_settings: dict[str, Any] | None = None,
    ) -> None:
        self._require("widget")
        from deskos.widgets.registry import WidgetSpec

        if not widget_type:
            raise PluginError("widget type must not be empty")
        self._widgets.register_plugin_widget(
            self.id,
            WidgetSpec(
                type=widget_type,
                title=title,
                description=description or f"Provided by the {self.name} plugin",
                icon=icon,
                factory=factory,
                default_span=max(1, min(4, default_span)),
                default_settings=dict(default_settings or {}),
            ),
        )
        self._widget_types.append(widget_type)

    def unregister_widget(self, widget_type: str) -> None:
        self._widgets.unregister(widget_type)
        if widget_type in self._widget_types:
            self._widget_types.remove(widget_type)

    # -------------------------------------------------------------- commands
    def register_command(
        self,
        command_id: str,
        title: str,
        callback: Callable[..., Any],
        *,
        description: str = "",
        keywords: tuple[str, ...] = (),
        requires_confirmation: bool = False,
    ) -> None:
        self._require("commands")
        from deskos.core.commands import CATEGORY_CUSTOM, Command

        full_id = command_id if command_id.startswith(f"plugin.{self.id}.") else f"plugin.{self.id}.{command_id}"
        self._commands.register(
            Command(
                id=full_id,
                title=title,
                category=CATEGORY_CUSTOM,
                description=description,
                keywords=tuple(keywords) + (self.name,),
                icon="plugins",
                callback=callback,
                requires_confirmation=requires_confirmation,
            )
        )
        self._command_ids.append(full_id)

    # ----------------------------------------------------------------- system
    def system_snapshot(self):
        self._require("system")
        return self._monitor.latest

    def notify(self, message: str) -> None:
        self._require("notifications")
        self._notify(message)

    def fetch_json(
        self,
        url: str,
        on_success: Callable[[Any], None],
        on_error: Callable[[str], None] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._require("network")
        self._http.get_json(url, on_success, on_error, headers)

    # ------------------------------------------------------------------- log
    def log(self, level: str, message: str) -> None:
        logger = logging.getLogger(f"deskos.plugin.{self.id}")
        numeric = getattr(logging, str(level).upper(), logging.INFO)
        logger.log(numeric, "%s", message)

    # --------------------------------------------------------------- cleanup
    def registered_widgets(self) -> list[str]:
        return list(self._widget_types)

    def registered_commands(self) -> list[str]:
        return list(self._command_ids)

    def cleanup(self) -> None:
        for widget_type in list(self._widget_types):
            self._widgets.unregister(widget_type)
        self._widget_types.clear()
        for command_id in list(self._command_ids):
            self._commands.unregister(command_id)
        self._command_ids.clear()
