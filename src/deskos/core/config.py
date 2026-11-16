"""Preference storage: JSON config with defaults, validation and recovery.

Design notes
------------
* A single ``config.json`` holds every user preference.  Persistent records
  (notes, tasks, workspaces, AI history) live in SQLite instead.
* Writes are atomic (temporary file + ``os.replace``) and the previous file is
  kept as ``config.json.bak``.
* A corrupt file is never silently deleted: it is renamed to
  ``config.json.corrupt-<timestamp>`` and the backup/defaults are loaded.
* Unknown keys are dropped with a warning so downgrades cannot crash the app.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import shutil
import tempfile
import time
import zipfile
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from deskos.core.events import EventBus
from deskos.core.paths import backups_dir, config_path, database_path

log = logging.getLogger(__name__)

CONFIG_VERSION = 1

DEFAULT_CONFIG: dict[str, Any] = {
    "version": CONFIG_VERSION,
    "appearance": {
        "theme": "graphite",
        "accent": "blue",
        "custom_accent": "#68a9ff",
        "use_custom_accent": False,
        "wallpaper": "",
        "animations": True,
        "ui_scale": 1.0,
    },
    "general": {
        "language": "en",
        "notifications": True,
        "start_minimized": False,
        "start_with_dashboard": True,
        "show_dock": True,
        "close_to_tray": True,
        "confirm_commands": True,
    },
    "window": {"width": 1280, "height": 820, "x": None, "y": None, "maximized": False},
    "dock": {
        "position": "bottom",
        "size": 56,
        "opacity": 0.92,
        "autohide": False,
        "always_on_top": False,
        "show_clock": True,
        "show_system_status": True,
        "show_workspace": True,
        "pinned": [
            "app.launcher",
            "app.files",
            "app.terminal",
            "app.monitor",
            "app.notes",
            "app.clock",
            "app.tasks",
            "app.ai",
            "app.settings",
        ],
    },
    "launcher": {"columns": 6, "show_recent": True, "recent_count": 6},
    "palette": {
        "shortcut": "Meta+Space",
        "fallback_shortcut": "Ctrl+Alt+Space",
        "custom_commands": [],
    },
    "dashboard": {
        "columns": 4,
        "show_shortcuts": True,
        "widgets": [
            {"type": "clock", "enabled": True},
            {"type": "cpu", "enabled": True},
            {"type": "memory", "enabled": True},
            {"type": "calendar", "enabled": True},
            {"type": "storage", "enabled": True},
            {"type": "network", "enabled": True},
            {"type": "uptime", "enabled": True},
            {"type": "weather", "enabled": True},
            {"type": "github", "enabled": False},
        ],
        "shortcuts": [
            {"label": "Files", "command": "app.files"},
            {"label": "Terminal", "command": "app.terminal"},
            {"label": "Monitor", "command": "app.monitor"},
            {"label": "Notes", "command": "app.notes"},
        ],
    },
    "workspaces": {"active": "default", "seeded": False},
    "plugins": {"enabled": {}, "settings": {}},
    "ai": {
        "enabled": False,
        "provider": "openai",
        "model": "gpt-4o-mini",
        "base_url": "https://api.openai.com/v1",
        "temperature": 0.4,
        "max_context_messages": 20,
        "system_prompt": (
            "You are DeskAI, the assistant built into DeskOS. Be concise and "
            "practical. You never claim to have executed a command; you may "
            "suggest one for the user to approve."
        ),
    },
    "advanced": {
        "log_level": "INFO",
        "monitor_interval_ms": 1200,
        "discovery_cache_hours": 6,
        "safe_mode": False,
    },
}

# (minimum, maximum) for numeric settings, applied after type coercion.
RANGES: dict[str, tuple[float, float]] = {
    "appearance.ui_scale": (0.8, 1.6),
    "dock.size": (36, 96),
    "dock.opacity": (0.4, 1.0),
    "launcher.columns": (3, 10),
    "launcher.recent_count": (3, 12),
    "dashboard.columns": (2, 6),
    "window.width": (800, 10000),
    "window.height": (520, 10000),
    "ai.temperature": (0.0, 1.5),
    "ai.max_context_messages": (2, 100),
    "advanced.monitor_interval_ms": (400, 10000),
    "advanced.discovery_cache_hours": (1, 168),
}

ALLOWED_THEMES = ("graphite", "catppuccin-mocha", "catppuccin-latte")
ALLOWED_ACCENTS = (
    "blue",
    "lavender",
    "sapphire",
    "sky",
    "teal",
    "green",
    "yellow",
    "peach",
    "maroon",
    "red",
    "mauve",
    "pink",
)
ALLOWED_DOCK_POSITIONS = ("top", "bottom")
ALLOWED_LANGUAGES = ("en", "tr")
ALLOWED_PROVIDERS = ("openai", "anthropic", "ollama", "custom")


def _coerce(value: Any, reference: Any) -> Any:
    """Coerce ``value`` to the type of the default ``reference``."""
    if reference is None:
        return value
    if isinstance(reference, bool):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)
    if isinstance(reference, int) and not isinstance(reference, bool):
        try:
            return int(value)
        except (TypeError, ValueError):
            return reference
    if isinstance(reference, float):
        try:
            return float(value)
        except (TypeError, ValueError):
            return reference
    if isinstance(reference, str):
        return value if isinstance(value, str) else str(value)
    if isinstance(reference, list):
        return value if isinstance(value, list) else list(reference)
    if isinstance(reference, dict):
        return value if isinstance(value, dict) else dict(reference)
    return value


class ConfigManager:
    """Load, validate, mutate and persist user preferences."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        bus: EventBus | None = None,
        defaults: Mapping[str, Any] | None = None,
        autosave: bool = True,
    ) -> None:
        self.path = Path(path) if path else config_path()
        self.bus = bus
        self.defaults = copy.deepcopy(dict(defaults or DEFAULT_CONFIG))
        self.autosave = autosave
        self.issues: list[str] = []
        self._data: dict[str, Any] = copy.deepcopy(self.defaults)
        self._listeners: list[Callable[[str], None]] = []
        self._loading = False

    # ------------------------------------------------------------------ load
    def load(self) -> dict[str, Any]:
        self.issues.clear()
        raw: dict[str, Any] | None = None

        if self.path.is_file():
            raw = self._read_file(self.path)
            if raw is None:
                raw = self._recover_from_backup()
        else:
            log.info("config not found, creating defaults at %s", self.path)

        data = self._validate(raw or {})
        self._data = data
        if self.autosave:
            self.save(emit=False)
        self._emit("config.loaded")
        return self._data

    def _read_file(self, path: Path) -> dict[str, Any] | None:
        try:
            text = path.read_text(encoding="utf-8")
            parsed = json.loads(text)
        except (OSError, json.JSONDecodeError) as exc:
            stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
            corrupt = path.with_name(f"{path.name}.corrupt-{stamp}")
            try:
                shutil.move(str(path), str(corrupt))
                msg = f"Configuration was unreadable ({exc}); moved to {corrupt.name}"
            except OSError:
                msg = f"Configuration was unreadable ({exc})"
            self.issues.append(msg)
            log.warning(msg)
            return None
        if not isinstance(parsed, dict):
            self.issues.append("Configuration root must be a JSON object; using defaults")
            return {}
        return parsed

    def _recover_from_backup(self) -> dict[str, Any] | None:
        backup = self.path.with_suffix(self.path.suffix + ".bak")
        if not backup.is_file():
            return None
        log.warning("attempting recovery from %s", backup.name)
        try:
            parsed = json.loads(backup.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if isinstance(parsed, dict):
            self.issues.append(f"Recovered configuration from {backup.name}")
            return parsed
        return None

    # -------------------------------------------------------------- validate
    def _validate(self, data: Mapping[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, reference in self.defaults.items():
            if key not in data:
                self.issues.append(f"Missing setting '{key}', using default")
                result[key] = copy.deepcopy(reference)
                continue
            value = data[key]
            if isinstance(reference, dict):
                if not isinstance(value, dict):
                    self.issues.append(f"Setting '{key}' must be an object; using defaults")
                    result[key] = copy.deepcopy(reference)
                    continue
                result[key] = self._validate_section(key, value, reference)
            else:
                result[key] = self._coerce_key(key, value, reference)

        unknown = set(data) - set(self.defaults)
        for key in sorted(unknown):
            self.issues.append(f"Unknown setting '{key}' ignored")

        self._enforce_choices(result)
        return result

    def _validate_section(
        self, prefix: str, data: Mapping[str, Any], defaults: Mapping[str, Any]
    ) -> dict[str, Any]:
        section: dict[str, Any] = {}
        for key, reference in defaults.items():
            path = f"{prefix}.{key}"
            if key not in data:
                self.issues.append(f"Missing setting '{path}', using default")
                section[key] = copy.deepcopy(reference)
                continue
            value = data[key]
            if isinstance(reference, dict):
                section[key] = (
                    self._validate_section(path, value, reference)
                    if isinstance(value, dict)
                    else copy.deepcopy(reference)
                )
            elif path == "palette.custom_commands":
                section[key] = self._validate_custom_commands(value)
            elif isinstance(reference, list) and reference and isinstance(reference[0], dict):
                section[key] = self._validate_record_list(path, value, reference[0])
            else:
                section[key] = self._coerce_key(path, value, reference)
        unknown = set(data) - set(defaults)
        for key in sorted(unknown):
            self.issues.append(f"Unknown setting '{prefix}.{key}' ignored")
        return section

    def _validate_custom_commands(self, value: Any) -> list[dict[str, Any]]:
        """Custom palette commands must be objects with a title and a command."""
        if not isinstance(value, list):
            self.issues.append("Setting 'palette.custom_commands' must be a list; using default")
            return []
        cleaned: list[dict[str, Any]] = []
        for index, record in enumerate(value):
            if not isinstance(record, dict):
                self.issues.append(f"Custom command {index + 1} is not an object; ignored")
                continue
            title = str(record.get("title", "")).strip()
            command = str(record.get("command", "")).strip()
            if not title or not command:
                self.issues.append(f"Custom command {index + 1} needs a title and command; ignored")
                continue
            item: dict[str, Any] = {"title": title, "command": command}
            description = str(record.get("description", "")).strip()
            if description:
                item["description"] = description
            cleaned.append(item)
        return cleaned

    def _validate_record_list(
        self, path: str, value: Any, template: Mapping[str, Any]
    ) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            self.issues.append(f"Setting '{path}' must be a list; using default")
            return []
        cleaned: list[dict[str, Any]] = []
        for index, record in enumerate(value):
            if not isinstance(record, dict):
                self.issues.append(f"Entry {index} of '{path}' is not an object; ignored")
                continue
            item = {}
            for key, reference in template.items():
                item[key] = _coerce(record.get(key, reference), reference)
            # Custom commands and shortcuts may carry extra scalar fields.
            for key, extra in record.items():
                if key not in item and isinstance(extra, (str, int, float, bool)):
                    item[key] = extra
            cleaned.append(item)
        return cleaned

    def _coerce_key(self, path: str, value: Any, reference: Any) -> Any:
        coerced = _coerce(value, reference)
        if isinstance(coerced, (int, float)) and not isinstance(coerced, bool):
            bounds = RANGES.get(path)
            if bounds:
                low, high = bounds
                if coerced < low or coerced > high:
                    self.issues.append(
                        f"Setting '{path}' was {coerced}, clamped to [{low}, {high}]"
                    )
                    coerced = type(coerced)(min(max(coerced, low), high))
        return coerced

    def _enforce_choices(self, data: dict[str, Any]) -> None:
        appearance = data.get("appearance", {})
        if appearance.get("theme") not in ALLOWED_THEMES:
            self.issues.append(
                f"Unknown theme '{appearance.get('theme')}', falling back to Catppuccin Mocha"
            )
            appearance["theme"] = "catppuccin-mocha"
        if appearance.get("accent") not in ALLOWED_ACCENTS:
            self.issues.append(f"Unknown accent '{appearance.get('accent')}', using blue")
            appearance["accent"] = "blue"
        if data.get("dock", {}).get("position") not in ALLOWED_DOCK_POSITIONS:
            data["dock"]["position"] = "bottom"
        if data.get("general", {}).get("language") not in ALLOWED_LANGUAGES:
            data["general"]["language"] = "en"
        if data.get("ai", {}).get("provider") not in ALLOWED_PROVIDERS:
            data["ai"]["provider"] = "openai"

    # ------------------------------------------------------------------ save
    def save(self, *, emit: bool = True) -> None:
        if self._loading:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._data, indent=2, ensure_ascii=False)
        backup = self.path.with_suffix(self.path.suffix + ".bak")
        if self.path.is_file():
            try:
                shutil.copy2(self.path, backup)
            except OSError:
                log.debug("could not refresh config backup", exc_info=True)
        fd, tmp_name = tempfile.mkstemp(prefix=".config-", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.path)
        except OSError:
            log.exception("failed to save configuration")
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            return
        if emit:
            self._emit("config.saved")

    # --------------------------------------------------------------- get/set
    def get(self, path: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, path: str, value: Any, *, save: bool = True) -> None:
        parts = path.split(".")
        node = self._data
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                child = {}
                node[part] = child
            node = child
        if node.get(parts[-1]) == value:
            return
        node[parts[-1]] = value
        if save and self.autosave:
            self.save()
        self._emit("config.changed", key=path)

    def update(self, values: Mapping[str, Any], *, save: bool = True) -> None:
        for path, value in values.items():
            self.set(path, value, save=False)
        if save and self.autosave:
            self.save()
        self._emit("config.changed", key="*")

    def as_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self._data)

    def reset(self) -> None:
        self._data = copy.deepcopy(self.defaults)
        self.issues.clear()
        self.save()
        self._emit("config.changed", key="*")

    def toggle_theme(self) -> str:
        current = self.get("appearance.theme")
        new = "catppuccin-latte" if current == "catppuccin-mocha" else "catppuccin-mocha"
        self.set("appearance.theme", new)
        return new

    # ------------------------------------------------------------- observers
    def add_listener(self, callback: Callable[[str], None]) -> Callable[[], None]:
        self._listeners.append(callback)

        def remove() -> None:
            if callback in self._listeners:
                self._listeners.remove(callback)

        return remove

    def _emit(self, topic: str, **payload: Any) -> None:
        if self.bus is not None:
            self.bus.emit(topic, **payload)
        if topic == "config.changed":
            for listener in list(self._listeners):
                try:
                    listener(payload.get("key", "*"))
                except Exception:
                    log.exception("config listener failed")

    # ------------------------------------------------------ backup & restore
    def backup_to(self, destination: Path, *, include_database: bool = False) -> Path:
        """Export configuration (and optionally the database) as a zip archive."""
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        manifest = {
            "application": "DeskOS",
            "format": 1,
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
            "includes_database": include_database,
            "config_version": CONFIG_VERSION,
        }
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
            archive.writestr("config.json", json.dumps(self._data, indent=2, ensure_ascii=False))
            db = database_path()
            if include_database and db.is_file():
                archive.write(db, "deskos.db")
        log.info("configuration exported to %s", destination)
        return destination

    def restore_from(self, archive_path: Path) -> list[str]:
        """Import a backup archive; returns validation notes."""
        archive_path = Path(archive_path)
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            if "config.json" not in names:
                raise ValueError("Archive does not contain config.json")
            payload = json.loads(archive.read("config.json").decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("config.json in archive is not an object")
            db_target = database_path()
            if "deskos.db" in names:
                db_target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open("deskos.db") as src, open(db_target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                log.info("database replaced from backup archive")
        self.issues.clear()
        self._data = self._validate(payload)
        self.save(emit=False)
        self._emit("config.changed", key="*")
        return list(self.issues)

    def create_backup(self) -> Path:
        stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
        target = backups_dir() / f"deskos-config-{stamp}.json"
        target.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")
        return target


def utc_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
