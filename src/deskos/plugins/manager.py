"""Plugin manager: wires discovery, enablement, state persistence and errors."""

from __future__ import annotations

import logging
from pathlib import Path

from deskos.core.context import DeskOSContext
from deskos.core.paths import bundled_plugins_dir, data_dir, user_plugins_dir
from deskos.plugins.api import PluginContext, PluginHttp
from deskos.plugins.loader import PluginLoader, PluginRecord

log = logging.getLogger(__name__)


class PluginManager:
    def __init__(self, context: DeskOSContext) -> None:
        self.ctx = context
        self.loader = PluginLoader()
        self.http = PluginHttp()
        self.errors: dict[str, str] = {}
        self.directories: list[Path] = [bundled_plugins_dir(), user_plugins_dir()]

    # ------------------------------------------------------------------ load
    def discover_and_load(self) -> list[PluginRecord]:
        for directory in self.directories:
            try:
                self.loader.discover(directory)
            except OSError:
                log.exception("could not scan plugin directory %s", directory)

        user_root = user_plugins_dir().absolute()
        for record in list(self.loader.records.values()):
            plugin_path = record.metadata.path
            is_user_plugin = (
                plugin_path is not None
                and plugin_path.absolute().parent == user_root
            )
            # Bundled plugins are trusted with the application. Newly discovered
            # user plugins stay disabled until the user explicitly enables them.
            default_enabled = record.enabled and not is_user_plugin
            enabled = self.ctx.plugin_state.is_enabled(
                record.metadata.id, default=default_enabled
            ) and not record.error
            record.enabled = enabled
            if not enabled:
                continue
            self._load_record(record)
        self.ctx.bus.emit("plugins.changed")
        return self.plugins

    def _load_record(self, record: PluginRecord) -> None:
        context = PluginContext(
            record.metadata,
            state=self.ctx.plugin_state,
            widget_registry=self.ctx.widget_registry,
            command_registry=self.ctx.commands,
            monitor=self.ctx.monitor,
            notify=self.ctx.toast,
            http=self.http,
            data_dir=data_dir() / "plugin-data" / record.metadata.id,
        )
        try:
            context.data_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            log.debug("could not create plugin data directory", exc_info=True)
        self.loader.load(record, context)
        if record.error:
            self.errors[record.metadata.id] = record.error

    # ---------------------------------------------------------------- queries
    @property
    def plugins(self) -> list[PluginRecord]:
        return sorted(self.loader.records.values(), key=lambda item: item.metadata.name.lower())

    def get(self, plugin_id: str) -> PluginRecord | None:
        return self.loader.records.get(plugin_id)

    # -------------------------------------------------------------- mutations
    def set_enabled(self, plugin_id: str, enabled: bool) -> None:
        record = self.loader.records.get(plugin_id)
        if record is None:
            return
        self.ctx.plugin_state.set_enabled(plugin_id, enabled)
        record.enabled = enabled
        if enabled:
            if not record.loaded:
                self._load_record(record)
        else:
            self.loader.unload(record)
        self.ctx.bus.emit("plugins.changed")
        log.info("plugin %s %s", plugin_id, "enabled" if enabled else "disabled")

    def reload_all(self) -> None:
        for record in list(self.loader.records.values()):
            if record.loaded:
                self.loader.unload(record)
            record.error = ""
        self.loader.records.clear()
        self.errors.clear()
        self.discover_and_load()

    def open_folder(self) -> bool:
        return self.ctx.platform.files.open_path(str(user_plugins_dir()))
