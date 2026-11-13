"""Dashboard widget framework and the built-in widgets."""

from __future__ import annotations

import pytest

from deskos.widgets.base import WidgetContext
from deskos.widgets.integration_widgets import describe_weather_code, parse_weather
from deskos.widgets.registry import WidgetSpec


@pytest.fixture()
def widget_context(context):
    return WidgetContext(
        ctx=context,
        icons=context.icons,
        settings={},
        save_settings=lambda settings: None,
    )


@pytest.mark.parametrize(
    "widget_type",
    ["clock", "calendar", "cpu", "memory", "storage", "network", "uptime", "weather", "github"],
)
def test_builtin_widgets_construct_and_refresh(context, widget_context, sample_snapshot, widget_type):
    spec = context.widget_registry.get(widget_type)
    assert spec is not None
    widget = context.widget_registry.create(widget_type, widget_context)
    assert widget is not None
    assert widget.widget_type == widget_type
    widget.refresh(sample_snapshot)
    widget.show()  # exercises layout/paint paths offscreen


def test_unknown_widget_type_returns_none(context, widget_context):
    assert context.widget_registry.create("not-a-widget", widget_context) is None


def test_factory_errors_are_isolated(context, widget_context):
    def broken_factory(_context):
        raise RuntimeError("factory exploded")

    context.widget_registry.register(
        WidgetSpec(type="broken", title="Broken", description="", icon="plugins", factory=broken_factory)
    )
    assert context.widget_registry.create("broken", widget_context) is None
    assert "broken" in context.widget_registry.types()


def test_widget_settings_roundtrip(context, widget_context):
    widget = context.widget_registry.create("weather", widget_context)
    assert widget is not None
    widget.apply_settings({"city": "Ankara"})
    assert widget.context.settings["city"] == "Ankara"
    form = widget.build_settings_form()
    assert form is not None
    widget._city_field.setText("Izmir")
    assert widget.collect_settings()["city"] == "Izmir"


def test_plugin_widget_spec_source(context, widget_context):
    from deskos.widgets.base import DeskWidget

    class Demo(DeskWidget):
        widget_type = "demo"
        title = "Demo"

    context.widget_registry.register_plugin_widget(
        "demo-plugin",
        WidgetSpec(type="demo", title="Demo", description="", icon="plugins", factory=Demo),
    )
    spec = context.widget_registry.get("demo")
    assert spec.source == "plugin"
    assert spec.plugin_id == "demo-plugin"
    context.widget_registry.unregister_plugin("demo-plugin")
    assert context.widget_registry.get("demo") is None


def test_weather_payload_parsing():
    payload = {
        "current": {
            "temperature_2m": 21.4,
            "apparent_temperature": 20.1,
            "relative_humidity_2m": 55,
            "wind_speed_10m": 8.0,
            "weather_code": 2,
        },
        "current_units": {"temperature_2m": "°C"},
    }
    parsed = parse_weather(payload)
    assert parsed["temperature"] == 21.4
    assert parsed["description"] == "Partly cloudy"
    assert parsed["units"] == "°C"
    assert describe_weather_code(9999) == "Weather code 9999"
    assert describe_weather_code(None) == "Unknown"


def test_widget_registry_specs_are_sorted(context):
    titles = [spec.title for spec in context.widget_registry.specs()]
    assert titles == sorted(titles, key=str.lower)
