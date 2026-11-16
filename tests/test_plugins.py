"""Plugin discovery, manifest validation, permissions and error isolation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deskos.plugins.api import PluginContext, PluginError, PluginMetadata
from deskos.plugins.loader import PluginLoader, PluginRecord
from deskos.plugins.manager import PluginManager

WIDGET_PLUGIN = """
from deskos.widgets.base import DeskWidget

class DemoWidget(DeskWidget):
    widget_type = "demo_widget"
    title = "Demo"
    icon = "plugins"
    def build(self):
        from PySide6.QtWidgets import QLabel
        self.body_layout.addWidget(QLabel("demo"))

def register(api):
    api.register_widget("demo_widget", "Demo", DemoWidget, description="demo widget")
    api.register_command("ping", "Plugin ping", lambda: api.log("info", "pong"))
    api.log("info", "demo registered")
"""


def write_plugin(
    root: Path,
    plugin_id: str,
    *,
    main: str = WIDGET_PLUGIN,
    permissions: list[str] | None = None,
    dependencies: list[str] | None = None,
    api_version: int = 1,
    name: str = "Demo plugin",
) -> Path:
    folder = root / plugin_id
    folder.mkdir(parents=True)
    manifest = {
        "id": plugin_id,
        "name": name,
        "version": "1.0.0",
        "api_version": api_version,
        "entry": "main.py",
        "author": "tests",
        "description": "Test plugin",
        "permissions": permissions if permissions is not None else ["widget", "commands", "settings"],
        "dependencies": dependencies or ["PySide6"],
    }
    (folder / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    (folder / "main.py").write_text(main, encoding="utf-8")
    return folder


class TestManifestValidation:
    def test_valid_manifest(self, tmp_path):
        folder = write_plugin(tmp_path, "demo")
        metadata = PluginMetadata.load_manifest(folder)
        assert metadata.id == "demo"
        assert metadata.permissions == ["widget", "commands", "settings"]

    @pytest.mark.parametrize(
        "mutation,expected",
        [
            ({"api_version": 99}, "supports v1"),
            ({"entry": "missing.py"}, "does not exist"),
            ({"permissions": ["root"]}, "unknown permission"),
            ({"id": "Bad Id"}, "invalid plugin id"),
        ],
    )
    def test_invalid_manifests(self, tmp_path, mutation, expected):
        folder = write_plugin(tmp_path, "demo")
        manifest_path = folder / "plugin.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload.update(mutation)
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(PluginError) as excinfo:
            PluginMetadata.load_manifest(folder)
        assert expected in str(excinfo.value)

    def test_missing_required_field(self, tmp_path):
        folder = write_plugin(tmp_path, "demo")
        manifest_path = folder / "plugin.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        del payload["name"]
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(PluginError):
            PluginMetadata.load_manifest(folder)

    def test_invalid_json(self, tmp_path):
        folder = tmp_path / "broken"
        folder.mkdir()
        (folder / "plugin.json").write_text("{nope", encoding="utf-8")
        with pytest.raises(PluginError):
            PluginMetadata.load_manifest(folder)


class TestDiscoveryAndLoading:
    def test_discovery_records_manifest_errors(self, tmp_path):
        write_plugin(tmp_path, "good")
        bad = tmp_path / "bad"
        bad.mkdir()
        (bad / "plugin.json").write_text("{}", encoding="utf-8")
        loader = PluginLoader()
        records = loader.discover(tmp_path)
        ids = {record.metadata.id for record in records}
        assert "good" in ids and "bad" in ids
        assert loader.records["bad"].error

    def test_missing_dependency_disables_plugin(self, tmp_path):
        write_plugin(tmp_path, "needs_dep", dependencies=["definitely_not_installed_module"])
        loader = PluginLoader()
        records = loader.discover(tmp_path)
        record = next(item for item in records if item.metadata.id == "needs_dep")
        assert record.enabled is False
        assert "missing dependency" in record.error

    def test_manager_loads_widget_and_command(self, context, tmp_path, qapp):
        write_plugin(tmp_path, "demo")
        manager = PluginManager(context)
        manager.directories = [tmp_path]
        manager.discover_and_load()
        record = manager.get("demo")
        assert record is not None and record.loaded and not record.error
        assert context.widget_registry.get("demo_widget") is not None
        assert context.commands.get("plugin.demo.ping") is not None
        command = context.commands.get("plugin.demo.ping")
        assert command is not None
        result = context.commands.execute(command.id)
        assert result.ok

    def test_permission_violation_is_isolated(self, context, tmp_path, qapp):
        write_plugin(
            tmp_path,
            "sneaky",
            permissions=["commands"],
            main="\n".join(
                [
                    "def register(api):",
                    "    api.register_widget('sneaky_widget', 'Sneaky', lambda ctx: None)",
                ]
            ),
        )
        manager = PluginManager(context)
        manager.directories = [tmp_path]
        manager.discover_and_load()
        record = manager.get("sneaky")
        assert record is not None
        assert record.loaded is False
        assert "widget" in record.error
        assert context.widget_registry.get("sneaky_widget") is None

    def test_broken_plugin_does_not_block_others(self, context, tmp_path, qapp):
        write_plugin(tmp_path, "broken", main="raise RuntimeError('kaboom')\n")
        write_plugin(tmp_path, "healthy")
        manager = PluginManager(context)
        manager.directories = [tmp_path]
        manager.discover_and_load()
        assert manager.get("broken").error
        assert manager.get("healthy").loaded
        assert context.widget_registry.get("demo_widget") is not None

    def test_enable_disable_persists(self, context, tmp_path, qapp):
        write_plugin(tmp_path, "demo")
        manager = PluginManager(context)
        manager.directories = [tmp_path]
        manager.discover_and_load()
        manager.set_enabled("demo", False)
        assert context.widget_registry.get("demo_widget") is None
        assert context.plugin_state.is_enabled("demo") is False

        reloaded = PluginManager(context)
        reloaded.directories = [tmp_path]
        reloaded.discover_and_load()
        assert reloaded.get("demo").enabled is False

        reloaded.set_enabled("demo", True)
        assert context.widget_registry.get("demo_widget") is not None

    def test_duplicate_plugin_ids_are_ignored(self, tmp_path):
        write_plugin(tmp_path, "dup")
        second_root = tmp_path / "second"
        write_plugin(second_root, "dup", name="Duplicate")
        loader = PluginLoader()
        loader.discover(tmp_path)
        loader.discover(second_root)
        assert loader.records["dup"].metadata.name == "Demo plugin"

    def test_settings_are_namespaced(self, context, tmp_path, qapp):
        write_plugin(tmp_path, "demo")
        manager = PluginManager(context)
        manager.directories = [tmp_path]
        manager.discover_and_load()
        record = manager.get("demo")
        assert record.context is not None
        record.context.set_setting("greeting", "hello")
        assert context.plugin_state.get_settings("demo") == {"greeting": "hello"}

    def test_unload_removes_registrations(self, context, tmp_path, qapp):
        write_plugin(tmp_path, "demo")
        manager = PluginManager(context)
        manager.directories = [tmp_path]
        manager.discover_and_load()
        manager.set_enabled("demo", False)
        assert context.commands.get("plugin.demo.ping") is None


def test_user_plugins_are_disabled_until_explicitly_enabled(
    monkeypatch, context, tmp_path, qapp
):
    """New user-installed code must not execute automatically at startup."""
    monkeypatch.setattr(
        "deskos.plugins.manager.user_plugins_dir", lambda: tmp_path
    )
    write_plugin(tmp_path, "untrusted_user_plugin")

    manager = PluginManager(context)
    manager.directories = [tmp_path]
    manager.discover_and_load()

    record = manager.get("untrusted_user_plugin")
    assert record is not None
    assert record.enabled is False
    assert record.loaded is False
    assert context.widget_registry.get("demo_widget") is None

    manager.set_enabled("untrusted_user_plugin", True)
    assert record.enabled is True
    assert record.loaded is True
    assert context.widget_registry.get("demo_widget") is not None
