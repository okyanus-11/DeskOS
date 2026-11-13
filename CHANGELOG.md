# Changelog

All notable changes to DeskOS are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned

- Signed installer and auto-update channel.
- Optional AppBar behaviour for the dock.
- Pseudo-terminal backend for DeskTerminal.
- Clipboard history and media transport plugins.

## [1.0.0] — 2026-11-13

The first complete release: a working desktop companion rather than a mock-up.
Everything listed below is implemented and covered by the test suite or the
headless self-test.

### Added

- **Shell**: frameless, themed main window with sidebar navigation, dashboard,
  application browser and workspaces; state is restored between launches.
- **Dashboard**: widget grid with drag-to-reorder, per-widget settings, custom
  wallpaper, and nine widgets (clock, calendar, CPU, memory, storage, network,
  uptime, weather, GitHub activity).
- **Dock**: pinned applications, running indicators, workspace switcher, clock
  and live system status; top/bottom placement, opacity, auto-hide and
  always-on-top options.
- **Launcher**: full-screen searchable launcher combining DeskOS apps, Windows
  Start Menu shortcuts, App Paths registry entries and Microsoft Store apps
  (Linux: `.desktop` entries), with recent applications and right-click pinning.
- **Command palette**: fuzzy search over every command, keyboard navigation,
  global hotkey registration on Windows and in-app fallbacks everywhere.
- **Control Centre**: appearance (theme, accent, wallpaper, transparency,
  scaling, animations), system information, network adapters, application
  rescan, general behaviour, plugin management, configuration export/backup.
- **Applications**: DeskFiles (browse, search, copy/cut/paste, rename, trash,
  properties), DeskTerminal (real shell subprocess, history, native-terminal
  hand-off), DeskMonitor (live gauges, disks, processes), DeskNotes (autosave,
  tags, pinning, search), DeskClock (clock, calendar, stopwatch, timer, world
  clocks), DeskTasks (priorities, due dates, categories), DeskAI.
- **Workspaces**: seeded Development/School/Personal/Monitoring layouts plus
  user-created workspaces, each with pinned commands and a widget layout.
- **Themes**: Catppuccin Mocha and Latte palettes, eleven accents, generated
  Qt stylesheet, runtime switching without a restart.
- **Plugins**: manifest validation, API v1 with declared permissions, isolated
  loading and unload, namespaced settings, plugin manager UI, and two working
  examples (weather forecast, system load).
- **DeskAI**: provider abstraction for OpenAI-compatible endpoints, Anthropic
  and Ollama; API keys in the OS credential store with a documented fallback;
  system context, conversation history, error explanation and approval-gated
  command suggestions.
- **Data**: validated JSON configuration with corruption recovery and backups;
  SQLite database with versioned migrations and repositories for notes, tasks,
  workspaces, usage history, plugin state, AI conversations and settings.
- **Platform layer**: Windows and Linux backends for application discovery,
  launching, recycle bin/trash, autostart, global hotkeys, system information
  and terminal shell discovery.
- **Packaging and docs**: PyInstaller spec and build scripts, icon generation
  script, screenshot renderer, README, architecture, plugin and build guides,
  contributing guide and this changelog.
- **Quality gates**: 139 pytest tests, `--self-test` CLI check, compile check.

### Known limitations

See the "Known limitations" section of the README. In particular, the Windows
code paths could not be executed on a real Windows machine during this release
build; they are unit-tested with fakes and documented as such.

[Unreleased]: https://github.com/okyanus-11/DeskOS/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/okyanus-11/DeskOS/releases/tag/v1.0.0
