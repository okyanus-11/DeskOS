"""Windows-only logic that can be exercised on any host with fakes.

The real registry/hotkey/Recycle-Bin calls cannot run on Linux or macOS, so these
tests pin down the parsing and registry bookkeeping that the Windows backend
relies on.
"""

from __future__ import annotations

import json
import time

import pytest

from deskos.platform.windows import autostart as windows_autostart
from deskos.platform.windows.hotkey import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_NOREPEAT,
    MOD_WIN,
    parse_shortcut,
)


class FakeKey:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeWinreg:
    HKEY_CURRENT_USER = 1
    REG_SZ = 1

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def OpenKey(self, hive, path):  # noqa: N802
        if not self.values:
            raise OSError("value not present")
        return FakeKey(self.values)

    def CreateKey(self, hive, path):  # noqa: N802
        return FakeKey(self.values)

    def QueryValueEx(self, key, name):  # noqa: N802
        if name not in self.values:
            raise OSError("value not present")
        return self.values[name], 1

    def SetValueEx(self, key, name, reserved, kind, value):  # noqa: N802
        key.values[name] = value

    def DeleteValue(self, key, name):  # noqa: N802
        if name not in key.values:
            raise FileNotFoundError(name)
        del key.values[name]


class TestHotkeyParsing:
    def test_ctrl_alt_space(self):
        modifiers, key = parse_shortcut("Ctrl+Alt+Space")
        assert modifiers == MOD_NOREPEAT | MOD_CONTROL | MOD_ALT
        assert key == 0x20

    def test_win_super_meta_are_equivalent(self):
        assert parse_shortcut("Super+A") == parse_shortcut("Meta+A") == parse_shortcut("Win+A")
        assert parse_shortcut("Win+A")[0] & MOD_WIN

    def test_letters_digits_and_named_keys(self):
        assert parse_shortcut("Alt+F")[1] == ord("F")
        assert parse_shortcut("Alt+7")[1] == ord("7")
        assert parse_shortcut("Alt+Enter")[1] == 0x0D
        assert parse_shortcut("Alt+Tab")[1] == 0x09

    @pytest.mark.parametrize("sequence", ["", "Hyper+Space", "Ctrl+F13", "Ctrl+Alt"])
    def test_invalid_sequences_raise(self, sequence):
        with pytest.raises(ValueError):
            parse_shortcut(sequence)


class TestWindowsAutostart:
    def test_enable_and_disable(self, monkeypatch):
        fake = FakeWinreg()
        monkeypatch.setattr(windows_autostart, "winreg", fake)
        manager = windows_autostart.WindowsAutostart()

        assert manager.is_enabled() is False
        assert manager.set_enabled(True) is True
        assert fake.values["DeskOS"] == windows_autostart.launch_command()
        assert "deskos" in fake.values["DeskOS"]
        assert manager.is_enabled() is True

        assert manager.set_enabled(False) is False
        assert "DeskOS" not in fake.values
        assert manager.is_enabled() is False

    def test_without_winreg_is_a_graceful_noop(self, monkeypatch):
        monkeypatch.setattr(windows_autostart, "winreg", None)
        manager = windows_autostart.WindowsAutostart()
        assert manager.is_enabled() is False
        assert manager.set_enabled(True) is False

    def test_mechanism_is_explicit(self):
        assert "Run" in windows_autostart.WindowsAutostart().mechanism()


class TestWindowsBackend:
    def test_cache_hours_are_forwarded(self):
        from deskos.platform.windows import WindowsBackend

        backend = WindowsBackend(cache_hours=24)
        assert backend.apps.cache_hours == 24
        assert backend.supports_global_hotkeys is True


class TestWindowsAppDiscoveryCache:
    def test_invalid_cache_timestamps_are_ignored(self, tmp_path):
        from deskos.platform.windows.apps import WindowsAppDiscovery

        cache = tmp_path / "apps.json"
        discovery = WindowsAppDiscovery(cache_path=cache)
        for created in ("not-a-timestamp", float("nan"), float("inf"), time.time() + 3600):
            cache.write_text(
                json.dumps({"created": created, "entries": []}),
                encoding="utf-8",
            )
            assert discovery._load_cache() is None

    def test_malformed_entries_do_not_discard_valid_cache_entries(self, tmp_path):
        from deskos.platform.windows.apps import WindowsAppDiscovery

        cache = tmp_path / "apps.json"
        cache.write_text(
            json.dumps({
                "created": time.time(),
                "entries": [
                    {"id": "broken", "name": "Broken", "args": 42},
                    {"id": "valid", "name": "Calculator", "args": []},
                    "not-an-entry",
                ],
            }),
            encoding="utf-8",
        )
        entries = WindowsAppDiscovery(cache_path=cache)._load_cache()
        assert entries is not None
        assert [(entry.id, entry.name) for entry in entries] == [("valid", "Calculator")]
