"""Built-in command palette entries.

Every command performs a real action: opening a window, toggling a setting,
reading live system data or launching the user's browser.  Commands registered
from configuration (``palette.custom_commands``) run shell commands and are
always confirmed first.
"""

from __future__ import annotations

import logging
import webbrowser

from deskos.core.commands import (
    CATEGORY_APPS,
    CATEGORY_APPEARANCE,
    CATEGORY_CUSTOM,
    CATEGORY_FILES,
    CATEGORY_SYSTEM,
    Command,
    CommandRegistry,
    shell_command_action,
)
from deskos.core.context import DeskOSContext
from deskos.utils.formatting import format_bytes, format_duration, format_rate

log = logging.getLogger(__name__)


def _launcher(ctx: DeskOSContext):
    return ctx.services["launcher"]


def _shell(ctx: DeskOSContext):
    return ctx.services.get("shell")


def _open_app(ctx: DeskOSContext, app_id: str) -> None:
    _launcher(ctx).open_builtin(app_id)


def _system_status(ctx: DeskOSContext) -> None:
    snapshot = ctx.monitor.latest
    if snapshot is None:
        ctx.toast("No system sample collected yet")
        return
    ctx.toast(
        f"CPU {snapshot.cpu_percent:.0f}% · RAM {snapshot.memory_percent:.0f}% "
        f"({format_bytes(snapshot.memory_used)}/{format_bytes(snapshot.memory_total)}) · "
        f"uptime {format_duration(snapshot.uptime)}",
        6000,
    )


def _cpu_status(ctx: DeskOSContext) -> None:
    snapshot = ctx.monitor.latest
    if snapshot is None:
        ctx.toast("No CPU sample yet")
        return
    frequency = f" @ {snapshot.cpu_freq_mhz / 1000:.2f} GHz" if snapshot.cpu_freq_mhz else ""
    ctx.toast(
        f"CPU {snapshot.cpu_percent:.1f}%{frequency} · {len(snapshot.cpu_per_core)} threads",
        5000,
    )


def _memory_status(ctx: DeskOSContext) -> None:
    snapshot = ctx.monitor.latest
    if snapshot is None:
        ctx.toast("No memory sample yet")
        return
    ctx.toast(
        f"Memory {snapshot.memory_percent:.1f}% · {format_bytes(snapshot.memory_used)} used "
        f"of {format_bytes(snapshot.memory_total)}",
        5000,
    )


def _network_status(ctx: DeskOSContext) -> None:
    snapshot = ctx.monitor.latest
    interfaces = snapshot.network_interfaces if snapshot else []
    active = [item for item in interfaces if item["is_up"] and item["ipv4"]]
    if active:
        primary = active[0]
        ctx.toast(
            f"{primary['name']} · {primary['ipv4']} · ↓ {format_rate(snapshot.net_recv_rate)} "
            f"↑ {format_rate(snapshot.net_sent_rate)}",
            6000,
        )
    elif interfaces:
        ctx.toast("Network adapters present but no active IPv4 connection", 5000)
    else:
        ctx.toast("No network adapters detected", 5000)


def _open_browser(ctx: DeskOSContext) -> None:
    opened = webbrowser.open("https://github.com/okyanus-11/DeskOS")
    ctx.toast("Opening your default browser" if opened else "No default browser found")


def _search_files(ctx: DeskOSContext) -> None:
    window = _launcher(ctx).open_builtin("app.files")
    page = getattr(window, "page", None)
    if page is not None and hasattr(page, "search"):
        page.search.setFocus()


def _toggle_theme(ctx: DeskOSContext) -> None:
    ctx.theme.toggle()
    ctx.toast(f"Theme: {ctx.theme.palette.label}")


def _toggle_dock(ctx: DeskOSContext) -> None:
    dock = ctx.services.get("dock")
    show = not bool(ctx.config.get("general.show_dock", True))
    ctx.config.set("general.show_dock", show)
    if dock is not None:
        dock.setVisible(show)
    ctx.toast("Dock shown" if show else "Dock hidden")


def _toggle_autohide(ctx: DeskOSContext) -> None:
    enabled = not bool(ctx.config.get("dock.autohide", False))
    ctx.config.set("dock.autohide", enabled)
    dock = ctx.services.get("dock")
    if dock is not None:
        dock.apply_config()
    ctx.toast(f"Dock auto-hide {'enabled' if enabled else 'disabled'}")


def _quit(ctx: DeskOSContext) -> None:
    app = ctx.services.get("app")
    if app is not None:
        app.shutdown()


def _symbols(ctx: DeskOSContext) -> None:
    _open_app(ctx, "app.files")
    ctx.toast("Tip: use DeskFiles' search field to filter files")


def register_builtin_commands(ctx: DeskOSContext) -> CommandRegistry:
    registry = ctx.commands
    registry.register_many(
        [
            Command(
                id="app.launcher",
                title="Open application launcher",
                category=CATEGORY_APPS,
                description="Browse and search installed applications.",
                keywords=("launcher", "apps", "start"),
                icon="apps",
                shortcut="Meta+Space",
                callback=lambda: _shell(ctx).show_launcher() if _shell(ctx) else None,
            ),
            Command(
                id="app.terminal",
                title="Open terminal",
                category=CATEGORY_APPS,
                description="Start DeskTerminal with a real shell.",
                keywords=("terminal", "shell", "powershell", "cmd", "bash"),
                icon="terminal",
                callback=lambda: _open_app(ctx, "app.terminal"),
            ),
            Command(
                id="app.files",
                title="Open files",
                category=CATEGORY_FILES,
                description="Browse local files in DeskFiles.",
                keywords=("files", "explorer", "browse"),
                icon="files",
                callback=lambda: _open_app(ctx, "app.files"),
            ),
            Command(
                id="app.monitor",
                title="Show system monitor",
                category=CATEGORY_SYSTEM,
                description="CPU, memory, disk and process overview.",
                keywords=("monitor", "performance", "processes"),
                icon="monitor",
                callback=lambda: _open_app(ctx, "app.monitor"),
            ),
            Command(
                id="app.notes",
                title="Open notes",
                category=CATEGORY_APPS,
                description="Quick notes with autosave.",
                keywords=("notes", "write"),
                icon="notes",
                callback=lambda: _open_app(ctx, "app.notes"),
            ),
            Command(
                id="app.tasks",
                title="Open tasks",
                category=CATEGORY_APPS,
                description="Task list with priorities and due dates.",
                keywords=("tasks", "todo"),
                icon="tasks",
                callback=lambda: _open_app(ctx, "app.tasks"),
            ),
            Command(
                id="app.clock",
                title="Open clock",
                category=CATEGORY_APPS,
                description="Clock, stopwatch, timer and world clocks.",
                keywords=("clock", "timer", "stopwatch"),
                icon="clock",
                callback=lambda: _open_app(ctx, "app.clock"),
            ),
            Command(
                id="app.settings",
                title="Open control center",
                category=CATEGORY_APPS,
                description="Themes, system, network, apps, plugins.",
                keywords=("settings", "preferences", "control"),
                icon="settings",
                callback=lambda: _launcher(ctx).open_settings(),
            ),
            Command(
                id="app.ai",
                title="Ask DeskAI",
                category=CATEGORY_APPS,
                description="Optional assistant with provider configuration.",
                keywords=("ai", "assistant", "chat", "gpt", "claude"),
                icon="ai",
                callback=lambda: _launcher(ctx).open_ai(),
            ),
            Command(
                id="system.status",
                title="Show system status",
                category=CATEGORY_SYSTEM,
                description="Live CPU, memory and uptime summary.",
                keywords=("status", "system", "overview"),
                icon="dashboard",
                callback=lambda: _system_status(ctx),
            ),
            Command(
                id="system.cpu",
                title="Show CPU usage",
                category=CATEGORY_SYSTEM,
                description="Current processor utilisation and frequency.",
                keywords=("cpu", "processor", "load"),
                icon="cpu",
                callback=lambda: _cpu_status(ctx),
            ),
            Command(
                id="system.memory",
                title="Show memory usage",
                category=CATEGORY_SYSTEM,
                description="RAM used and available.",
                keywords=("memory", "ram"),
                icon="memory",
                callback=lambda: _memory_status(ctx),
            ),
            Command(
                id="system.network",
                title="Show network information",
                category=CATEGORY_SYSTEM,
                description="Active adapter, IP address and throughput.",
                keywords=("network", "ip", "wifi", "ethernet"),
                icon="network",
                callback=lambda: _network_status(ctx),
            ),
            Command(
                id="files.search",
                title="Search files",
                category=CATEGORY_FILES,
                description="Open DeskFiles and focus the search field.",
                keywords=("find", "search", "files"),
                icon="search",
                callback=lambda: _search_files(ctx),
            ),
            Command(
                id="appearance.toggle_theme",
                title="Toggle dark mode",
                category=CATEGORY_APPEARANCE,
                description="Switch between Catppuccin Mocha and Latte.",
                keywords=("theme", "dark", "light", "appearance"),
                icon="moon",
                callback=lambda: _toggle_theme(ctx),
            ),
            Command(
                id="appearance.toggle_dock",
                title="Show or hide the dock",
                category=CATEGORY_APPEARANCE,
                description="Toggle the DeskOS dock.",
                keywords=("dock", "taskbar", "hide"),
                icon="dock",
                callback=lambda: _toggle_dock(ctx),
            ),
            Command(
                id="appearance.dock_autohide",
                title="Toggle dock auto-hide",
                category=CATEGORY_APPEARANCE,
                description="Hide the dock until the pointer reaches the screen edge.",
                keywords=("dock", "autohide"),
                icon="dock",
                callback=lambda: _toggle_autohide(ctx),
            ),
            Command(
                id="system.open_browser",
                title="Open browser",
                category=CATEGORY_APPS,
                description="Open the default web browser.",
                keywords=("browser", "web", "internet"),
                icon="external",
                callback=lambda: _open_browser(ctx),
            ),
            Command(
                id="system.quit",
                title="Quit DeskOS",
                category=CATEGORY_SYSTEM,
                description="Close every DeskOS window and stop the shell.",
                keywords=("quit", "exit", "close"),
                icon="power",
                callback=lambda: _quit(ctx),
            ),
        ]
    )

    # Workspace switching commands
    for workspace in ctx.workspaces.list():
        registry.register(
            Command(
                id=f"workspace.switch.{workspace.id}",
                title=f"Switch to workspace: {workspace.name}",
                category=CATEGORY_APPS,
                description="Activate this DeskOS workspace.",
                keywords=("workspace", workspace.name.lower()),
                icon="workspace",
                callback=lambda workspace_id=workspace.id: ctx.workspaces.switch(workspace_id),
            )
        )

    # User-defined commands (always confirmed before running)
    for index, entry in enumerate(ctx.config.get("palette.custom_commands", [])):
        raw = str(entry.get("command", "")).strip()
        title = str(entry.get("title", "")).strip() or f"Custom command {index + 1}"
        if not raw:
            continue
        registry.register(
            Command(
                id=f"custom.{index}",
                title=title,
                category=CATEGORY_CUSTOM,
                description=str(entry.get("description", "")) or f"Runs: {raw}",
                keywords=("custom", "shell"),
                icon="terminal",
                callback=shell_command_action(raw, title),
                requires_confirmation=True,
                confirm_text=f"Run this shell command?\n\n{raw}",
            )
        )

    log.info("registered %d palette commands", len(registry.all()))
    return registry
