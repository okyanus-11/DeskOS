# DeskOS architecture

DeskOS is a PySide6 desktop application with a deliberately boring structure:
one application controller builds every service, services talk through a small
event bus and dependency container, and Qt only appears in the UI layer.

```
main.py  ──►  DeskOSApplication (app.py)
                 │
                 ├── core/      config, database, commands, theme, paths, events, logging
                 ├── platform/  Windows and Linux backends behind one ABC
                 ├── services/  application registry, launcher, workspaces, system monitor
                 ├── plugins/   manifest validation, API, loader, manager
                 ├── widgets/   dashboard widget framework + core widgets
                 ├── ui/        shell window, dock, launcher, palette, chrome, components
                 ├── applications/  DeskFiles, DeskTerminal, DeskMonitor, …
                 ├── control_center/ settings pages
                 └── ai/        providers, credentials, service, chat window
```

## Layers and why they exist

| Layer | May import Qt? | Responsibility |
|---|---|---|
| `core/` | No | Configuration, SQLite access, command registry, theme tokens/QSS, paths, event bus, logging |
| `data/` | No | Repositories over the SQLite connection |
| `platform/` | Only for hotkeys | OS-specific behaviour behind abstract base classes |
| `services/` | Only `QObject`/signals | Long-lived application services and async registry |
| `plugins/` | No (API itself) | Manifest contract, permission gate, loader and lifecycle |
| `ui/`, `applications/`, `control_center/`, `widgets/`, `ai/view.py` | Yes | Everything the user sees |

The Qt-free core is not decoration: it is what lets the test suite validate
configuration, migrations, repositories, command matching, theme generation and
plugin manifests without starting a `QApplication`. The few core modules that
need a monitor snapshot import the dataclass only, not Qt widgets.

## Application startup

`main.py` parses the CLI, sets up logging and the exception hook, creates the
`QApplication`, and hands control to `DeskOSApplication`:

1. Load `config.json` (validating and repairing it).
2. Open `deskos.db` and run pending migrations.
3. Create the event bus, repositories, theme manager, icon provider.
4. Pick the platform backend (`WindowsBackend` or `LinuxBackend`).
5. Build services: system monitor, application registry, workspace manager,
   launcher service, command registry (including built-in commands).
6. Build the UI: main window (sidebar + dashboard + apps + workspaces), dock,
   tray icon.
7. Load plugins unless `--safe-mode` was passed.
8. Install shortcuts and (on Windows) global hotkeys, start the monitor timer,
   begin asynchronous application discovery, show the window.

`--self-test` runs steps 1–8 and then checks the window, dock, database
integrity, theme stylesheet, command count and plugin count before exiting.
`shutdown()` stops timers, waits for background work, saves the configuration,
closes the database and quits.

## Dependency container and events

`DeskOSContext` (`core/context.py`) is the one object passed to widgets, pages
and apps. It exposes the config, database, repositories, bus, theme, icons,
monitor, launcher-facing services (`ctx.services`), workspace manager, widget
registry, command registry and plugin manager.

The shell registers its `notify()` method as the `notifier` service, which is
what `DeskOSContext.toast()` and plugin notifications call. The shell decides
between an in-window toast (respecting the notifications and animations
settings) and a tray balloon when the window is hidden.

`EventBus` is a tiny synchronous publish/subscribe helper for cross-cutting
notifications (`theme.changed`, `workspace.changed`, `dock.changed`,
`config.changed`, `plugin.changed`). It is deliberately not a general message
broker: long-lived state lives in services and the database, not in events.

## Threading model

The GUI thread owns every Qt widget. Work that can block goes through
`deskos.utils.workers.run_async`, a thin wrapper around `QThreadPool` and
`QRunnable`:

```python
run_async(discover_apps, on_done, on_error, argument)
```

Results are delivered through Qt signals, so slots run on the GUI thread. The
application registry, recursive file search, directory sizes, system
information queries, the AI request and plugin HTTP fetching all use this path.
`wait_for_all()` is called during shutdown so background work cannot touch a
closed database.

Widgets that make HTTP requests keep the `QNetworkAccessManager` parented to
themselves, track in-flight replies, and check `shiboken6.isValid(self)` before
touching labels — a reply can arrive after the widget was removed from the
dashboard.

## Persistence

### Configuration

`config.json` lives next to the database. `ConfigManager` holds a deep copy of
`DEFAULT_CONFIG` and validates the loaded document section by section:

- missing keys are filled from defaults and reported in `issues`,
- unknown keys are dropped with a message,
- scalars are coerced and clamped to their allowed range,
- list-of-record settings (dashboard widgets, shortcuts) are cleaned,
- custom palette commands must be objects with a non-empty `title` and
  `command`,
- a parse failure moves the file to `config.json.corrupt-<timestamp>` and
  starts from defaults instead of crashing.

Saves are atomic (temporary file + replace). A timestamped ZIP backup of the
configuration and database can be created from Control Centre → General.

### SQLite

`core/database.py` owns the connection and a `schema_version` user version.
Migrations are numbered functions applied inside a transaction; adding a column
means appending a new migration, never editing an old one.

Tables:

| Table | Purpose |
|---|---|
| `notes` | notes with body, tags (JSON), pin state and timestamps |
| `tasks` | title, notes, due date, priority, category, completion |
| `workspaces` | name, icon, pinned commands (JSON), widget layout (JSON) |
| `app_usage` | launch counts and last launch time per application |
| `plugin_state` | enabled flag and namespaced settings (JSON) per plugin |
| `ai_conversations`, `ai_messages` | DeskAI history |
| `settings` | small key/value store for UI state |

Repositories in `data/repositories.py` are the only code that writes SQL;
services and widgets use repository methods. Rows are returned as
`sqlite3.Row`-backed dictionaries.

## Platform abstraction

`platform/base.py` defines `AppDiscovery`/`AppLauncher`, `SystemBackend`,
`TerminalBackend`, `FileOperations` and `AutostartBackend`. `platform/registry.py`
returns the backend for the current OS.

The Windows backend (`platform/windows/`) combines three discovery sources:
App Paths in the registry, Start Menu `.lnk` files resolved in a single
PowerShell `WScript.Shell` pass, and `Get-StartApps` for packaged apps. Results
are cached in the local cache directory and refreshed on demand. File deletion
uses `SHFileOperation` with the recycle flag; autostart writes the
`HKCU\…\Run` value; global hotkeys use `RegisterHotKey` plus a Qt native event
filter.

The Linux backend reads `.desktop` files, launches with `subprocess`, moves
files to the trash with `gio trash` (falling back to a warning rather than a
recursive delete), and writes an XDG autostart `.desktop` file.

Both backends expose the same `AvailableShell` list so DeskTerminal can offer
PowerShell 7, PowerShell 5 and Command Prompt on Windows, and `bash`/`sh` on
Linux.

## UI composition

- `ui/chrome.py` provides the frameless themed window base (custom title bar,
  `startSystemMove`, size grip, rounded corners).
- `ui/main_window.py` composes the sidebar, a `QStackedWidget` with the
  dashboard/apps/workspaces views, and the status footer.
- `ui/dashboard.py` renders `WidgetSpec`s from the registry into a responsive
  grid, handles drag reordering, per-widget settings and the wallpaper paint.
- `ui/dock.py` is a separate always-on-top tool window with pins, running
  indicators, status and an auto-hide reveal strip.
- `ui/launcher.py` and `ui/palette.py` are full-screen overlays; both are
  keyboard-first.
- `ui/apps_view.py` and the launcher share `AppTile`.
- `ui/components.py` contains the small reusable widgets (`Card`, `Muted`,
  `SectionTitle`, `SearchField`, `IconButton`, `StatBlock`, `RingGauge`,
  `ProgressStat`, `EmptyState`).

### Theming

`core/theme.py` defines two Catppuccin palettes and eleven accents as tokens,
then generates one application-wide stylesheet from those tokens. The theme
manager emits `theme.changed`; the controller re-applies the stylesheet and the
shell rebuilds themed content (icons, gauges, dashboard cards). There is no
per-widget colour literal outside the token file, with the exception of
chart series, which take their colours from the accent map.

## Widgets

`widgets/base.py` defines `DeskWidget` (header, menu, body layout, drag
signals, settings hooks) and `WidgetContext` (theme, icons, per-widget
settings, save callback, monitor access). `widgets/registry.py` holds
`WidgetSpec`s and their factories, including plugin-provided widgets.
`widgets/builtin.py` registers the core set; `widgets/core_widgets.py` and
`widgets/integration_widgets.py` implement them.

A widget receives `refresh(snapshot)` on every monitor tick (once per second by
default) and must not start its own timer for system data. Adding a widget is a
`WidgetSpec` plus a subclass; it automatically appears in the "Add widget"
menu.

## Commands and launcher

`core/commands.py` defines `Command` (id, title, category, keywords, icon,
callback, optional confirmation) and a registry with fuzzy search. Built-in
commands are registered in `core/builtin_commands.py`; workspace-specific and
custom shell commands are added at startup. The launcher service owns window
instances: opening an app that is already running raises the existing window
instead of creating a second one.

## Plugins

`plugins/api.py` validates `plugin.json`, defines the permission set and the
`PluginAPI` handed to plugins. `plugins/loader.py` discovers folders, checks
API version and dependencies, imports the entry module under a namespaced module
name, calls `register(api)` and records any failure without breaking other
plugins. `plugins/manager.py` persists the enabled state, unregisters widgets
and commands on disable, and exposes the list used by Control Centre.

Plugins are in-process Python. Permission checks guard the plugin API surface
only; they are not a sandbox. This is stated in the README, the plugin guide and
the Control Centre.

## DeskAI

`ai/providers.py` contains three small providers over `urllib.request`:
OpenAI-compatible chat completions, Anthropic messages and Ollama chat. All
raise `AIProviderError` with a human-readable message on failure.
`ai/credentials.py` stores keys in `keyring` and falls back to a user-only JSON
file when no backend exists. `ai/service.py` builds the system prompt from real
context (OS, hardware snapshot, workspace, recent log tail), persists messages
and runs the request in the background. `ai/view.py` renders the chat and turns
suggested commands into approval buttons; the service never executes a command
itself.

## Error handling and logging

`core/logging_setup.py` configures a rotating file handler in `logs/deskos.log`
and a console handler, and installs a `sys.excepthook` that logs uncaught
exceptions, records the traceback for DeskAI's "Explain last error" action and
shows a dialog when a GUI is available. Plugin import and registration errors
are captured per plugin, shown in the manager and never stop the shell from
starting. `--self-test` reports the first failing check.

## Testing strategy

- Pure logic (config, database, fuzzy, theme, formatting, plugin manifests,
  widget parsing) is tested without Qt.
- Platform backends are tested through fakes for `winreg`, `subprocess` and Qt
  network replies; the Linux `.desktop` parser is tested with real files.
- GUI tests construct every window, page, dock, overlay and widget on the
  offscreen platform and drive real interactions (terminal round-trip, notes
  autosave, palette filtering).
- `tests/test_startup.py` boots the whole `DeskOSApplication`, runs the self
  test, switches theme and workspace, and shuts down, which catches wiring bugs
  that unit tests miss.

Windows-only paths cannot execute on the Linux CI used for this release; they
are covered by fakes and explicitly listed as unverified on Windows.
