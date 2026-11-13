"""Platform abstraction: discovery, parsing and launch behaviour."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from deskos.platform.base import AppEntry, LaunchError
from deskos.platform.linux.apps import (
    DesktopEntryDiscovery,
    app_id_for,
    parse_desktop_entry,
    split_exec,
)
from deskos.platform.windows import apps as windows_apps


class TestDesktopEntries:
    def _write(self, root: Path, name: str, content: str) -> Path:
        path = root / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_parse_entry(self):
        data = parse_desktop_entry(
            "[Desktop Entry]\nType=Application\nName=Editor\nExec=editor %f\nIcon=editor\n"
        )
        assert data["Name"] == "Editor"
        assert data["Exec"] == "editor %f"

    def test_field_codes_are_stripped(self):
        assert split_exec("firefox %u --new-window %F") == ["firefox", "--new-window"]

    def test_discovery_filters_hidden_and_links(self, tmp_path):
        self._write(
            tmp_path,
            "editor.desktop",
            "[Desktop Entry]\nType=Application\nName=Editor\nExec=editor\nComment=Edit text\n",
        )
        self._write(
            tmp_path,
            "hidden.desktop",
            "[Desktop Entry]\nType=Application\nName=Hidden\nExec=hidden\nNoDisplay=true\n",
        )
        self._write(
            tmp_path,
            "link.desktop",
            "[Desktop Entry]\nType=Link\nName=Link\nURL=https://example.com\n",
        )
        entries = DesktopEntryDiscovery(roots=[tmp_path]).discover()
        assert [entry.name for entry in entries] == ["Editor"]
        assert entries[0].args == ["editor"]
        assert entries[0].kind == "desktop-entry"

    def test_launch_spawns_command(self, tmp_path, monkeypatch):
        self._write(
            tmp_path,
            "editor.desktop",
            "[Desktop Entry]\nType=Application\nName=Editor\nExec=editor\n",
        )
        entry = DesktopEntryDiscovery(roots=[tmp_path]).discover()[0]
        called: list[list[str]] = []
        monkeypatch.setattr(
            subprocess, "Popen", lambda command, **kwargs: called.append(command)
        )
        DesktopEntryDiscovery(roots=[tmp_path]).launch(entry)
        assert called == [["editor"]]

    def test_missing_executable_reports_launch_error(self, tmp_path, monkeypatch):
        entry = AppEntry(id="x", name="Missing", args=["definitely-not-a-real-binary-xyz"])

        def boom(*args, **kwargs):
            raise OSError("not found")

        monkeypatch.setattr(subprocess, "Popen", boom)
        with pytest.raises(LaunchError):
            DesktopEntryDiscovery(roots=[tmp_path]).launch(entry)


class TestWindowsDiscoveryHelpers:
    def test_ids_are_stable_and_distinct(self):
        assert app_id_for("Editor", "C:/Editor.exe") == app_id_for("Editor", "C:/Editor.exe")
        assert app_id_for("Editor", "C:/Editor.exe") != app_id_for("Editor", "D:/Editor.exe")
        assert app_id_for("Editor").startswith("ext:")

    def test_json_payload_parsing(self):
        assert windows_apps._parse_json_array('{"Name": "One"}') == [{"Name": "One"}]
        assert windows_apps._parse_json_array('[{"Name": "One"}, 3]') == [{"Name": "One"}]
        assert windows_apps._parse_json_array("not json") == []
        assert windows_apps._parse_json_array("") == []

    def test_deduplicate_prefers_start_menu_over_store(self):
        store = AppEntry(id="ext:1", name="Terminal", kind="store", target="Terminal!App")
        shortcut = AppEntry(id="ext:2", name="Terminal", kind="shortcut", path="C:/term.exe")
        result = windows_apps.WindowsAppDiscovery._deduplicate([store, shortcut])
        assert len(result) == 1
        assert result[0].kind == "shortcut"

    def test_cache_roundtrip(self, tmp_path):
        discovery = windows_apps.WindowsAppDiscovery(cache_path=tmp_path / "cache.json")
        entries = [AppEntry(id="ext:x", name="Cached", path="/bin/cached")]
        discovery._save_cache(entries)
        loaded = discovery._load_cache()
        assert loaded is not None and loaded[0].name == "Cached"

    def test_cache_expiry(self, tmp_path):
        discovery = windows_apps.WindowsAppDiscovery(
            cache_path=tmp_path / "cache.json", cache_hours=0
        )
        discovery._save_cache([AppEntry(id="ext:x", name="Old")])
        assert discovery._load_cache() is None

    def test_store_launch_uses_appsfolder(self, monkeypatch):
        entry = AppEntry(id="ext:s", name="Store app", kind="store", target="Store!App")
        calls: list[list[str]] = []
        monkeypatch.setattr(
            windows_apps.subprocess, "Popen", lambda args, **kwargs: calls.append(args)
        )
        windows_apps.WindowsAppDiscovery().launch(entry)
        assert calls and "shell:AppsFolder\\Store!App" in calls[0]

    def test_unlaunchable_entry_raises(self):
        with pytest.raises(LaunchError):
            windows_apps.WindowsAppDiscovery().launch(
                AppEntry(id="ext:none", name="Nothing", kind="app")
            )

    def test_registry_discovery_with_fake_winreg(self, tmp_path, monkeypatch):
        executable = tmp_path / "alpha.exe"
        executable.write_text("stub", encoding="utf-8")

        class Key:
            def __init__(self, values, subkeys):
                self.values = values
                self.subkeys = subkeys

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        class FakeWinreg:
            HKEY_CURRENT_USER = 1
            HKEY_LOCAL_MACHINE = 2

            def __init__(self):
                self.root = {
                    1: {
                        "Software\\Microsoft\\Windows\\CurrentVersion\\App Paths": Key(
                            {}, {"alpha.exe": Key({"": str(executable)}, {})}
                        )
                    }
                }

            def OpenKey(self, hive, path):  # noqa: N802
                if isinstance(hive, Key):
                    node = hive.subkeys.get(path)
                else:
                    node = self.root.get(hive, {}).get(path)
                if node is None:
                    raise OSError("missing")
                return node

            def QueryInfoKey(self, node):  # noqa: N802
                return (len(node.subkeys), 0, 0)

            def EnumKey(self, node, index):  # noqa: N802
                return list(node.subkeys)[index]

            def QueryValueEx(self, node, name):  # noqa: N802
                if name not in node.values:
                    raise OSError("no value")
                return node.values[name], 1

        monkeypatch.setattr(windows_apps, "winreg", FakeWinreg())
        entries = windows_apps.WindowsAppDiscovery()._from_registry()
        assert len(entries) == 1
        assert entries[0].name == "alpha"
        assert entries[0].source == "registry"

    def test_registry_discovery_without_winreg(self, monkeypatch):
        monkeypatch.setattr(windows_apps, "winreg", None)
        assert windows_apps.WindowsAppDiscovery()._from_registry() == []
