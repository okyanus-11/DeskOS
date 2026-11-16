# Plugin development

Plugins are the supported way to extend DeskOS. A plugin is a folder with a
JSON manifest and a Python entry module that registers widgets, commands or both.
This guide describes API version 1, which is what DeskOS 1.0 implements.

## Where plugins live

- Bundled: `<repository>/plugins/<plugin-id>/`
- User: `<data dir>/plugins/<plugin-id>/`
  (`%APPDATA%\DeskOS\plugins` on Windows, `~/.local/share/DeskOS/plugins` on Linux)

Both locations are scanned at startup and on demand from Control Centre →
Plugins. If two folders use the same `id`, the first one found wins and the
duplicate is ignored.

## Manifest

`plugin.json`:

```json
{
  "id": "my_plugin",
  "name": "My plugin",
  "version": "1.0.0",
  "api_version": 1,
  "entry": "main.py",
  "author": "Your Name",
  "description": "What the plugin adds and why.",
  "permissions": ["widget", "settings", "network"],
  "dependencies": ["PySide6"],
  "widget": { "type": "my_widget", "title": "My widget", "icon": "plugins", "span": 2 },
  "homepage": "https://example.com"
}
```

| Field | Required | Notes |
|---|---|---|
| `id` | yes | Lowercase letters, digits, `_`, `.`, `-`; 2–49 characters; must match the folder name by convention |
| `name` | yes | Shown in the plugin manager |
| `version` | yes | Free-form string, shown in the UI |
| `api_version` | yes | Must be `1` for this release |
| `entry` | yes | Python file inside the plugin folder, normally `main.py` |
| `author`, `description`, `homepage` | no | Metadata for the manager |
| `permissions` | no | Every API capability the plugin uses; unknown values reject the manifest |
| `dependencies` | no | Importable module names checked before loading (`PySide6` is always available) |
| `widget` | no | Optional metadata used by the manager listing |

A manifest with a missing required field, an unsupported API version, a
nonexistent entry file, an invalid id or an unknown permission is rejected and
reported in Control Centre → Plugins. Other plugins still load.

### Permissions

| Permission | Grants |
|---|---|
| `widget` | `api.register_widget` / `api.unregister_widget` |
| `commands` | `api.register_command` |
| `system` | `api.system_snapshot()` |
| `network` | `api.fetch_json()` |
| `settings` | `api.get_setting`, `api.set_setting`, `api.all_settings` |
| `notifications` | `api.notify()` |

Permissions are an **API contract, not a sandbox**. A plugin without `network`
cannot use the provided HTTP helper, but it can still `import urllib` and make a
request itself. DeskOS runs plugins in-process and cannot restrict arbitrary
Python. Install only plugins you trust.

New plugins discovered in the user plugin directory are **disabled by default**.
Enabling one from Control Centre → Plugins displays an explicit warning because
its Python code runs with the same operating-system permissions as DeskOS. This
reduces accidental execution, but it does not sandbox a plugin after you enable
it. Previously enabled plugins retain their saved enablement choice.

## Entry module and lifecycle

```python
# plugins/my_plugin/main.py
from PySide6.QtWidgets import QLabel

from deskos.widgets.base import DeskWidget


class MyWidget(DeskWidget):
    widget_type = "my_widget"
    title = "My widget"
    icon = "plugins"
    description = "Shows something useful."
    default_span = 1

    def build(self) -> None:
        self.label = QLabel("Waiting for the first sample…")
        self.body_layout.addWidget(self.label)

    def refresh(self, snapshot) -> None:
        if snapshot is None:
            return
        self.label.setText(f"CPU {snapshot.cpu_percent:.0f}%")


def register(api) -> None:
    api.register_widget(
        "my_widget",
        "My widget",
        MyWidget,
        description="Shows something useful.",
        icon="plugins",
        default_span=1,
        default_settings={"mode": "cpu"},
    )
    api.log("info", "my_plugin registered")
```

This example would need `"permissions": ["widget"]`. Loading sequence:

1. DeskOS reads the manifest and validates it.
2. Declared `dependencies` are imported; a missing one disables the plugin with
   a readable error.
3. The entry file is imported under a namespaced module name.
4. `register(api)` is called once.
5. Registrations appear in the dashboard's "Add widget" list and in the command
   palette.
6. Disabling the plugin (or restarting without it) calls `api.cleanup()`, which
   removes every widget and command the plugin registered.

Exceptions during import or registration are caught per plugin. The plugin is
marked as failed with the traceback in the manager; the rest of DeskOS keeps
running.

## Plugin API v1

```python
api.id                     # "my_plugin"
api.name                   # "My plugin"
api.version                # "1.0.0"
api.permissions            # ["widget", ...]
api.has_permission("widget")

# Widgets (permission: widget)
api.register_widget(widget_type, title, factory, *, icon="plugins",
                    description="", default_span=1, default_settings=None)
api.unregister_widget(widget_type)

# Commands (permission: commands)
api.register_command(command_id, title, callback, *, description="",
                     keywords=(), requires_confirmation=False)

# Settings (permission: settings) — stored per plugin id in SQLite
api.get_setting(key, default=None)
api.set_setting(key, value)
api.all_settings()

# System (permission: system)
api.system_snapshot()      # MonitorSnapshot or None before the first sample

# Network (permission: network)
api.fetch_json(url, on_success, on_error=None, headers=None)

# Notifications (permission: notifications)
api.notify("Message shown as a DeskOS toast")

# Logging (always)
api.log("info", "message")   # logger name: deskos.plugin.my_plugin

# Introspection / cleanup
api.registered_widgets()
api.registered_commands()
api.cleanup()
```

Command ids are automatically namespaced: passing `"ping"` registers
`plugin.my_plugin.ping`, which is stable and collision-free. A command
registered with `requires_confirmation=True` shows a confirmation dialog before
its callback runs — use it for anything that changes filesystem state or starts
a process.

`fetch_json` is asynchronous. Callbacks run on the GUI thread; keep them short.
Requests time out after 15 seconds and errors are delivered as strings.

## Writing a widget

`DeskWidget` provides the card chrome, drag handle, context menu and a body
layout. Override:

- `build()` — construct the content inside `self.body_layout`.
- `refresh(snapshot)` — called on every monitor tick (about once per second).
  `snapshot` is a `MonitorSnapshot`; it may be `None` during startup.
- `apply_settings(settings)` — react to per-widget settings (call `super()`
  first); keep the values in `self.context.settings`.
- `build_settings_form()` / `collect_settings()` — optional per-widget options;
  DeskOS opens the form from the widget's ⋯ menu and persists what you return.

Available helpers on the widget: `self.theme` (palette tokens), `self.icons`
(`IconProvider`), `self.ctx` (the full `DeskOSContext`), `self.body_layout`.
Use `deskos.ui.components` (`Muted`, `StatBlock`, `ProgressStat`, `RingGauge`)
to match the rest of the dashboard.

A widget must not create its own `QTimer` for system data, must not block the
GUI thread, and must tolerate being deleted while a network request is in
flight (see `integration_widgets.py` for the `shiboken6.isValid` guard).

## Writing a command

```python
def register(api):
    def open_projects():
        api.notify("Opening the projects folder")
        # call a launcher/app API or the platform through your own code

    api.register_command(
        "open_projects",
        "Open the projects folder",
        open_projects,
        description="Opens your projects directory.",
        keywords=("projects", "folder"),
    )
```

Keep command callbacks fast. If the work is slow, schedule it with
`deskos.utils.workers.run_async` and report the result with `api.notify`.

## Settings

`api.set_setting("city", "Ankara")` stores JSON in the `plugin_state` table,
namespaced by plugin id. Settings survive restarts and disabling the plugin;
they are removed only if the user deletes the plugin's row in the database (the
manager does not do that automatically). Use flat JSON-serialisable values.

## Debugging

- Enable `--debug` to see plugin discovery and registration in the log and on
  the console.
- `DeskOS → Control Centre → Plugins` shows load errors and the declared
  permissions.
- Start with `--safe-mode` to confirm that a problem is caused by a plugin.
- Plugin log records use the `deskos.plugin.<id>` logger, so they appear with
  the rest of the application log in `logs/deskos.log`.

## Testing a plugin

Add a pytest test that builds a `PluginManager` against a temporary folder, as in
`tests/test_plugins.py`:

```python
manager = PluginManager(context)
manager.directories = [tmp_path]
manager.discover_and_load()
record = manager.get("my_plugin")
assert record is not None and record.loaded
```

The fixtures in `tests/conftest.py` give you a fully wired `DeskOSContext` with
an offscreen Qt application, a temporary database and a fake platform backend.

## Bundled examples

- [`plugins/weather`](../plugins/weather/main.py) — a widget with settings,
  asynchronous HTTP and graceful failure.
- [`plugins/system_monitor`](../plugins/system_monitor/main.py) — a widget plus
  a palette command reading the shared system snapshot.

Both are small enough to copy as a starting point, and neither needs an API key.
