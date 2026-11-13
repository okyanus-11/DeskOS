"""Widget registry: built-in widgets and plugin-provided widgets."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from deskos.widgets.base import DeskWidget, WidgetContext

log = logging.getLogger(__name__)

WidgetFactory = Callable[[WidgetContext], DeskWidget]


@dataclass
class WidgetSpec:
    type: str
    title: str
    description: str
    icon: str
    factory: WidgetFactory
    default_span: int = 1
    default_settings: dict[str, Any] = field(default_factory=dict)
    source: str = "builtin"  # builtin | plugin
    plugin_id: str = ""


class WidgetRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, WidgetSpec] = {}

    def register(self, spec: WidgetSpec) -> None:
        if not spec.type:
            raise ValueError("widget type must not be empty")
        self._specs[spec.type] = spec
        log.debug("registered widget type %s (%s)", spec.type, spec.source)

    def unregister(self, widget_type: str) -> None:
        self._specs.pop(widget_type, None)

    def register_plugin_widget(self, plugin_id: str, spec: WidgetSpec) -> None:
        spec.source = "plugin"
        spec.plugin_id = plugin_id
        self.register(spec)

    def unregister_plugin(self, plugin_id: str) -> None:
        for widget_type in [key for key, spec in self._specs.items() if spec.plugin_id == plugin_id]:
            del self._specs[widget_type]

    def get(self, widget_type: str) -> WidgetSpec | None:
        return self._specs.get(widget_type)

    def specs(self) -> list[WidgetSpec]:
        return sorted(self._specs.values(), key=lambda spec: spec.title.lower())

    def types(self) -> list[str]:
        return list(self._specs)

    def create(self, widget_type: str, context: WidgetContext) -> DeskWidget | None:
        spec = self._specs.get(widget_type)
        if spec is None:
            log.warning("unknown widget type requested: %s", widget_type)
            return None
        try:
            return spec.factory(context)
        except Exception:
            log.exception("widget %s failed to construct", widget_type)
            return None


def register_builtin_widgets(registry: WidgetRegistry) -> None:
    """Register every widget that ships with DeskOS."""
    from deskos.widgets.core_widgets import (
        CalendarWidget,
        ClockWidget,
        CpuWidget,
        MemoryWidget,
        NetworkWidget,
        StorageWidget,
        UptimeWidget,
    )
    from deskos.widgets.integration_widgets import GithubWidget, WeatherWidget

    for widget_class in (
        ClockWidget,
        CalendarWidget,
        CpuWidget,
        MemoryWidget,
        StorageWidget,
        NetworkWidget,
        UptimeWidget,
        WeatherWidget,
        GithubWidget,
    ):
        registry.register(
            WidgetSpec(
                type=widget_class.widget_type,
                title=widget_class.title,
                description=widget_class.description,
                icon=widget_class.icon,
                factory=widget_class,
                default_span=widget_class.default_span,
            )
        )
