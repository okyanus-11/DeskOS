"""Extensible dashboard widget framework."""

from deskos.widgets.base import DeskWidget, WidgetContext
from deskos.widgets.registry import (
    WidgetRegistry,
    WidgetSpec,
    register_builtin_widgets,
)

__all__ = [
    "DeskWidget",
    "WidgetContext",
    "WidgetRegistry",
    "WidgetSpec",
    "register_builtin_widgets",
]
