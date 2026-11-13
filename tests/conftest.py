"""Shared fixtures and platform fakes for the DeskOS test-suite.

Tests run headless (``QT_QPA_PLATFORM=offscreen``) and against a temporary data
directory, so nothing touches the developer's real DeskOS state.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from deskos.core.commands import CommandRegistry  # noqa: E402
from deskos.core.config import ConfigManager  # noqa: E402
from deskos.core.context import DeskOSContext  # noqa: E402
from deskos.core.database import Database  # noqa: E402
from deskos.core.events import EventBus  # noqa: E402
from deskos.core.theme import ThemeManager  # noqa: E402
from deskos.data.repositories import (  # noqa: E402
    AIHistoryRepository,
    NotesRepository,
    PluginStateRepository,
    TasksRepository,
    UsageRepository,
    WorkspaceRepository,
)
from deskos.platform.base import (  # noqa: E402
    AppEntry,
    AppLauncher,
    AutostartManager,
    FileIntegration,
    LaunchError,
    PlatformBackend,
    ShellSpec,
    SystemBackend,
    TerminalBackend,
)
from deskos.services.app_registry import ApplicationRegistry  # noqa: E402
from deskos.services.workspace_manager import WorkspaceManager  # noqa: E402
from deskos.system.monitor import SystemMonitor  # noqa: E402
from deskos.ui.icons import IconProvider  # noqa: E402
from deskos.widgets.registry import WidgetRegistry, register_builtin_widgets  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def temp_home(tmp_path, monkeypatch):
    home = tmp_path / "deskos-home"
    home.mkdir()
    monkeypatch.setenv("DESKOS_HOME", str(home))
    return home


class FakeLauncher(AppLauncher):
    def __init__(self) -> None:
        self.entries = [
            AppEntry(id="ext:one", name="Alpha Editor", path="/usr/bin/alpha", source="test"),
            AppEntry(id="ext:two", name="Beta Browser", path="/usr/bin/beta", source="test"),
        ]
        self.launched: list[AppEntry] = []
        self.fail_next = False
        self.discover_calls = 0

    def discover(self, force: bool = False) -> list[AppEntry]:
        self.discover_calls += 1
        return list(self.entries)

    def launch(self, entry: AppEntry) -> None:
        if self.fail_next:
            raise LaunchError("simulated launch failure")
        self.launched.append(entry)


class FakeTerminal(TerminalBackend):
    def __init__(self) -> None:
        self.external_calls: list[tuple[str, str | None]] = []

    def available_shells(self) -> list[ShellSpec]:
        shells = []
        bash = shutil.which("bash")
        if bash:
            shells.append(ShellSpec(id="bash", label="Bash", executable=bash, repl_args=["--noprofile"]))
        return shells

    def launch_external(self, shell: ShellSpec, cwd: str | None = None) -> None:
        self.external_calls.append((shell.id, cwd))


class FakeFiles(FileIntegration):
    def __init__(self, root: Path) -> None:
        self.root = root
        self.opened: list[str] = []
        self.trashed: list[str] = []
        self.revealed: list[str] = []

    def open_path(self, path: str) -> bool:
        self.opened.append(path)
        return True

    def reveal_path(self, path: str) -> bool:
        self.revealed.append(path)
        return True

    def trash(self, path: str) -> bool:
        self.trashed.append(path)
        return True

    def locations(self) -> list[tuple[str, str]]:
        return [("Home", str(self.root))]

    def drives(self) -> list[tuple[str, str]]:
        return [("/", "/")]

    def default_path(self) -> str:
        return str(self.root)


class FakeSystem(SystemBackend):
    def os_info(self) -> dict[str, str]:
        return {
            "name": "TestOS",
            "version": "1.0",
            "release": "1.0-test",
            "build": "42",
            "architecture": "x86_64",
            "hostname": "test-host",
            "user": "tester",
        }

    def hardware_info(self) -> dict[str, str]:
        return {
            "processor": "Test CPU",
            "cores_physical": "4",
            "cores_logical": "8",
            "cpu_mhz": "3200",
            "memory_total": str(8 * 1024**3),
            "machine": "x86_64",
        }

    def network_interfaces(self) -> list[dict]:
        return [
            {
                "name": "test0",
                "ipv4": "192.0.2.10",
                "mac": "00:11:22:33:44:55",
                "is_up": True,
                "speed_mbps": 1000,
                "bytes_sent": 1024,
                "bytes_recv": 2048,
            }
        ]

    def battery(self) -> dict | None:
        return {"percent": 80, "plugged": True, "seconds_left": None}


class FakeAutostart(AutostartManager):
    def __init__(self) -> None:
        self.enabled = False
        self.set_calls: list[bool] = []

    def is_enabled(self) -> bool:
        return self.enabled

    def set_enabled(self, enabled: bool) -> bool:
        self.set_calls.append(enabled)
        self.enabled = enabled
        return self.enabled

    def mechanism(self) -> str:
        return "test mechanism"


def make_platform(root: Path) -> PlatformBackend:
    return PlatformBackend(
        name="test",
        display_name="Test platform",
        apps=FakeLauncher(),
        terminal=FakeTerminal(),
        files=FakeFiles(root),
        system=FakeSystem(),
        autostart=FakeAutostart(),
    )


def make_context(tmp_path: Path, qapp) -> DeskOSContext:
    bus = EventBus()
    config = ConfigManager(tmp_path / "config.json", bus=bus)
    config.load()
    db = Database(tmp_path / "deskos.db")
    db.connect()
    theme = ThemeManager(config, bus)
    icons = IconProvider(theme)
    commands = CommandRegistry()
    platform = make_platform(tmp_path)
    monitor = SystemMonitor(platform, 1000)
    usage = UsageRepository(db)
    app_registry = ApplicationRegistry(platform.apps, usage)
    workspace_repo = WorkspaceRepository(db)
    workspaces = WorkspaceManager(workspace_repo, config, bus)
    widget_registry = WidgetRegistry()
    register_builtin_widgets(widget_registry)
    context = DeskOSContext(
        config=config,
        bus=bus,
        db=db,
        theme=theme,
        icons=icons,
        platform=platform,
        commands=commands,
        monitor=monitor,
        app_registry=app_registry,
        workspaces=workspaces,
        notes=NotesRepository(db),
        tasks=TasksRepository(db),
        workspace_repo=workspace_repo,
        usage=usage,
        ai_history=AIHistoryRepository(db),
        plugin_state=PluginStateRepository(db),
        widget_registry=widget_registry,
    )
    return context


@pytest.fixture()
def context(tmp_path, qapp, temp_home):
    ctx = make_context(tmp_path, qapp)
    yield ctx
    ctx.db.close()


@pytest.fixture()
def notes(context):
    return context.notes


@pytest.fixture()
def tasks(context):
    return context.tasks


@pytest.fixture()
def sample_snapshot():
    from deskos.system.monitor import MonitorSnapshot

    return MonitorSnapshot(
        timestamp=1_700_000_000.0,
        cpu_percent=37.5,
        cpu_per_core=[10.0, 20.0, 30.0, 40.0],
        cpu_freq_mhz=3200.0,
        memory_percent=62.0,
        memory_used=4 * 1024**3,
        memory_total=8 * 1024**3,
        swap_percent=12.0,
        swap_used=256 * 1024**2,
        swap_total=2 * 1024**3,
        disks=[
            {
                "device": "/dev/test",
                "mountpoint": "/",
                "fstype": "ext4",
                "total": 100 * 1024**3,
                "used": 40 * 1024**3,
                "free": 60 * 1024**3,
                "percent": 40.0,
            }
        ],
        network_interfaces=[
            {
                "name": "test0",
                "ipv4": "192.0.2.10",
                "mac": "00:11:22:33:44:55",
                "is_up": True,
                "speed_mbps": 1000,
                "bytes_sent": 1024,
                "bytes_recv": 2048,
            }
        ],
        net_sent_rate=1024.0,
        net_recv_rate=2048.0,
        net_sent_total=10_000,
        net_recv_total=20_000,
        uptime=3600.0 * 30,
        load_average=(0.4, 0.5, 0.6),
        battery={"percent": 80, "plugged": True, "seconds_left": None},
    )
