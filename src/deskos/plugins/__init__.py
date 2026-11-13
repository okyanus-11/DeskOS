"""DeskOS plugin framework.

Plugins are plain Python packages with a ``plugin.json`` manifest.  They receive
a :class:`~deskos.plugins.api.PluginContext` that exposes widget/command
registration, namespaced settings, logging, notifications and (when declared and
permitted) a JSON HTTP helper plus read-only monitor snapshots.

Plugins run **in-process**; the manifest's permission list is an explicit,
documented contract and a set of guard rails, not a sandbox.  Only install
plugins you trust.
"""

from deskos.plugins.api import (
    ALLOWED_PERMISSIONS,
    API_VERSION,
    PluginContext,
    PluginError,
    PluginMetadata,
)
from deskos.plugins.manager import PluginManager, PluginRecord

__all__ = [
    "ALLOWED_PERMISSIONS",
    "API_VERSION",
    "PluginContext",
    "PluginError",
    "PluginManager",
    "PluginMetadata",
    "PluginRecord",
]
