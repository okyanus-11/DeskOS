"""Configuration management: defaults, validation, recovery, backup."""

from __future__ import annotations

import json
import zipfile

import pytest

from deskos.core.config import DEFAULT_CONFIG, ConfigManager


def test_creates_defaults_when_missing(tmp_path):
    path = tmp_path / "config.json"
    config = ConfigManager(path)
    data = config.load()
    assert path.is_file()
    assert data["appearance"]["theme"] == "catppuccin-mocha"
    assert data["dock"]["position"] == "bottom"
    assert data["version"] == DEFAULT_CONFIG["version"]


def test_nested_get_set_and_persistence(tmp_path):
    path = tmp_path / "config.json"
    config = ConfigManager(path)
    config.load()
    config.set("appearance.accent", "mauve")
    config.set("dock.size", 72)
    assert config.get("appearance.accent") == "mauve"
    reloaded = ConfigManager(path)
    reloaded.load()
    assert reloaded.get("appearance.accent") == "mauve"
    assert reloaded.get("dock.size") == 72


def test_invalid_values_are_coerced_and_clamped(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "appearance": {
                    "theme": "not-a-theme",
                    "accent": "chartreuse",
                    "transparency": 5.0,
                    "ui_scale": "1.25",
                },
                "dock": {"size": 1000, "autohide": "yes"},
                "general": {"language": "de"},
                "ai": {"provider": "wat"},
            }
        ),
        encoding="utf-8",
    )
    config = ConfigManager(path)
    config.load()
    assert config.get("appearance.theme") == "catppuccin-mocha"
    assert config.get("appearance.accent") == "blue"
    assert config.get("appearance.transparency") == 1.0
    assert config.get("appearance.ui_scale") == 1.25
    assert config.get("dock.size") == 96
    assert config.get("dock.autohide") is True
    assert config.get("general.language") == "en"
    assert config.get("ai.provider") == "openai"
    assert config.issues  # validation notes were recorded


def test_unknown_keys_are_dropped(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"mystery": 1, "appearance": {"nope": True}}), encoding="utf-8")
    config = ConfigManager(path)
    data = config.load()
    assert "mystery" not in data
    assert "nope" not in data["appearance"]
    assert any("Unknown setting" in issue for issue in config.issues)


def test_corrupt_config_is_preserved_and_recovered(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{ this is not json", encoding="utf-8")
    config = ConfigManager(path)
    data = config.load()
    corrupt_files = list(tmp_path.glob("config.json.corrupt-*"))
    assert corrupt_files, "the unreadable file should be preserved"
    assert corrupt_files[0].read_text(encoding="utf-8") == "{ this is not json"
    assert data["appearance"]["theme"] == "catppuccin-mocha"
    assert any("unreadable" in issue for issue in config.issues)


def test_recovers_from_backup_file(tmp_path):
    path = tmp_path / "config.json"
    backup = tmp_path / "config.json.bak"
    backup.write_text(json.dumps({"appearance": {"accent": "teal"}}), encoding="utf-8")
    path.write_text("broken", encoding="utf-8")
    config = ConfigManager(path)
    config.load()
    assert config.get("appearance.accent") == "teal"
    assert any("Recovered" in issue for issue in config.issues)


def test_atomic_save_keeps_backup(tmp_path):
    path = tmp_path / "config.json"
    config = ConfigManager(path)
    config.load()
    config.set("appearance.accent", "peach")
    backup = path.with_suffix(".json.bak")
    assert backup.is_file()
    assert json.loads(path.read_text(encoding="utf-8"))["appearance"]["accent"] == "peach"


def test_backup_export_and_restore_roundtrip(tmp_path):
    config = ConfigManager(tmp_path / "config.json")
    config.load()
    config.set("appearance.accent", "sapphire")
    archive = tmp_path / "backup.zip"
    config.backup_to(archive)
    assert archive.is_file()
    with zipfile.ZipFile(archive) as handle:
        names = set(handle.namelist())
    assert {"manifest.json", "config.json"} <= names

    target = ConfigManager(tmp_path / "restored.json")
    target.load()
    target.restore_from(archive)
    assert target.get("appearance.accent") == "sapphire"


def test_restore_rejects_archive_without_config(tmp_path):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("manifest.json", "{}")
    config = ConfigManager(tmp_path / "config.json")
    config.load()
    with pytest.raises(ValueError):
        config.restore_from(archive)


def test_toggle_theme_and_reset(tmp_path):
    config = ConfigManager(tmp_path / "config.json")
    config.load()
    assert config.toggle_theme() == "catppuccin-latte"
    assert config.toggle_theme() == "catppuccin-mocha"
    config.set("dock.size", 80)
    config.reset()
    assert config.get("dock.size") == 56


def test_listeners_are_notified(tmp_path):
    config = ConfigManager(tmp_path / "config.json")
    config.load()
    seen: list[str] = []
    config.add_listener(seen.append)
    config.set("appearance.accent", "pink")
    assert seen == ["appearance.accent"]


def test_invalid_custom_commands_are_filtered(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"palette": {"custom_commands": ["nope", {"title": "ok", "command": "echo hi"}]}}),
        encoding="utf-8",
    )
    config = ConfigManager(path)
    config.load()
    commands = config.get("palette.custom_commands")
    assert len(commands) == 1
    assert commands[0]["title"] == "ok"
