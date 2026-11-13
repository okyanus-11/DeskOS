"""Full application startup, wiring and shutdown."""

from __future__ import annotations

import json

import pytest

from deskos.core.config import ConfigManager
from deskos.main import parse_args


def test_parse_args_defaults():
    args = parse_args([])
    assert args.safe_mode is False
    assert args.self_test is False


def test_parse_args_flags():
    args = parse_args(["--safe-mode", "--debug", "--self-test"])
    assert args.safe_mode and args.debug and args.self_test


def test_application_boots_and_shuts_down(tmp_path, monkeypatch, qapp):
    from deskos.app import DeskOSApplication

    home = tmp_path / "home"
    monkeypatch.setenv("DESKOS_HOME", str(home))
    controller = DeskOSApplication(qapp, safe_mode=False)
    try:
        assert controller.self_test() is True
        assert controller.platform.name
        assert len(controller.commands.all()) > 10
        assert controller.main_window is not None
        assert controller.dock is not None
        assert controller.config.path.is_file()
        assert controller.db.integrity_check()
        assert controller.context.services["notifier"] == controller.notify

        providers = {plugin.metadata.id for plugin in controller.plugins.plugins}
        assert {"weather", "system_monitor"} <= providers
        assert controller.widget_registry.get("weather_forecast") is not None
        assert controller.widget_registry.get("system_load") is not None

        # Theme switching at runtime updates the stored preference and the QSS.
        controller.theme.set_theme("catppuccin-latte")
        controller.apply_theme()
        assert "catppuccin-latte" == controller.config.get("appearance.theme")
        assert controller.theme.palette.is_dark is False

        # Workspace switch affects the dashboard and dock.
        workspace = next(
            item for item in controller.workspaces.list() if item.id != controller.workspaces.active_id
        )
        controller.workspaces.switch(workspace.id)
        assert controller.workspaces.active_id == workspace.id

        actions = [command.id for command in controller.commands.all()]
        assert "app.terminal" in actions
        assert "system.status" in actions
    finally:
        controller.shutdown()

    # Graceful shutdown persists configuration.
    config_file = home / "config.json"
    assert config_file.is_file()
    stored = json.loads(config_file.read_text(encoding="utf-8"))
    assert stored["appearance"]["theme"] == "catppuccin-latte"
    assert not (home / "config.json.corrupt-anything").exists()


def test_safe_mode_skips_plugins(tmp_path, monkeypatch, qapp):
    from deskos.app import DeskOSApplication

    monkeypatch.setenv("DESKOS_HOME", str(tmp_path / "safe"))
    controller = DeskOSApplication(qapp, safe_mode=True)
    try:
        assert controller.plugins is None
        assert controller.self_test() is True
    finally:
        controller.shutdown()


def test_corrupted_config_is_recovered_on_startup(tmp_path, monkeypatch, qapp):
    from deskos.app import DeskOSApplication

    home = tmp_path / "home"
    home.mkdir()
    (home / "config.json").write_text("{broken", encoding="utf-8")
    monkeypatch.setenv("DESKOS_HOME", str(home))
    controller = DeskOSApplication(qapp, safe_mode=True)
    try:
        assert controller.config.get("appearance.theme") == "catppuccin-mocha"
        assert list(home.glob("config.json.corrupt-*"))
    finally:
        controller.shutdown()


def test_config_manager_defaults_without_file(tmp_path):
    config = ConfigManager(tmp_path / "missing" / "config.json")
    data = config.load()
    assert data["dock"]["pinned"]
    assert config.path.is_file()
