"""Plugin discovery and loading.

Discovery validates manifests and dependencies before anything is imported.  A
plugin that fails to import is recorded with its error and never retried
implicitly, so one broken plugin cannot prevent the shell from starting.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from deskos.plugins.api import PluginContext, PluginError, PluginMetadata

log = logging.getLogger(__name__)


@dataclass
class PluginRecord:
    metadata: PluginMetadata
    enabled: bool = True
    loaded: bool = False
    error: str = ""
    context: PluginContext | None = None
    module: ModuleType | None = None
    missing_dependencies: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.error:
            return "error"
        if not self.enabled:
            return "disabled"
        return "active" if self.loaded else "not loaded"


def dependency_available(name: str) -> bool:
    """Check an import name without importing it."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError, AttributeError):
        return False


class PluginLoader:
    def __init__(self) -> None:
        self.records: dict[str, PluginRecord] = {}

    # ------------------------------------------------------------- discovery
    def discover(self, root: Path) -> list[PluginRecord]:
        """Scan a directory of plugin folders and read their manifests."""
        found: list[PluginRecord] = []
        if not root.is_dir():
            return found
        for child in sorted(root.iterdir()):
            if not child.is_dir() or child.name.startswith((".", "_")):
                continue
            manifest = child / "plugin.json"
            if not manifest.is_file():
                log.debug("skipping %s (no plugin.json)", child)
                continue
            try:
                metadata = PluginMetadata.load_manifest(child)
            except PluginError as exc:
                log.warning("invalid plugin at %s: %s", child, exc)
                record = PluginRecord(
                    metadata=PluginMetadata(
                        id=child.name,
                        name=child.name,
                        version="0.0.0",
                        api_version=0,
                        entry="",
                        path=child,
                    ),
                    error=str(exc),
                    enabled=False,
                )
                self.records.setdefault(record.metadata.id, record)
                found.append(record)
                continue
            missing = [dep for dep in metadata.dependencies if not dependency_available(dep)]
            record = PluginRecord(
                metadata=metadata,
                missing_dependencies=missing,
                error=(
                    f"missing dependency: {', '.join(missing)}" if missing else ""
                ),
                enabled=not missing,
            )
            if metadata.id in self.records:
                log.warning(
                    "plugin id collision: %s at %s ignored (already loaded from %s)",
                    metadata.id,
                    child,
                    self.records[metadata.id].metadata.path,
                )
                continue
            self.records[metadata.id] = record
            found.append(record)
        return found

    # ---------------------------------------------------------------- loading
    def load(self, record: PluginRecord, context: PluginContext) -> PluginRecord:
        if record.error:
            return record
        metadata = record.metadata
        if metadata.path is None:
            record.error = "plugin path is missing"
            return record
        if not record.enabled:
            return record
        module_name = f"deskos_plugin_{metadata.id.replace('.', '_').replace('-', '_')}"
        entry_path = metadata.path / metadata.entry
        try:
            spec = importlib.util.spec_from_file_location(module_name, entry_path)
            if spec is None or spec.loader is None:
                raise PluginError("could not create an import spec")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            register = getattr(module, "register", None)
            if not callable(register):
                raise PluginError("plugin entry does not define register(api)")
            register(context)
        except Exception as exc:
            record.error = f"{type(exc).__name__}: {exc}"
            record.loaded = False
            log.exception("plugin %s failed to load", metadata.id)
            try:
                context.cleanup()
            except Exception:
                log.debug("plugin cleanup after failure raised", exc_info=True)
            return record
        record.module = module
        record.context = context
        record.loaded = True
        record.error = ""
        log.info("plugin %s v%s loaded", metadata.name, metadata.version)
        return record

    def unload(self, record: PluginRecord) -> None:
        context = record.context
        if context is not None:
            try:
                unload = getattr(record.module, "unload", None)
                if callable(unload):
                    unload(context)
            except Exception:
                log.exception("plugin %s unload hook failed", record.metadata.id)
            try:
                context.cleanup()
            except Exception:
                log.exception("plugin %s cleanup failed", record.metadata.id)
        module = record.module
        module_name = getattr(module, "__name__", None)
        if module_name and module_name in sys.modules:
            del sys.modules[module_name]
        record.module = None
        record.context = None
        record.loaded = False

    def remove(self, plugin_id: str) -> None:
        record = self.records.pop(plugin_id, None)
        if record is not None:
            self.unload(record)
