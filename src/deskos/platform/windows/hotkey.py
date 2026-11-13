"""Global hotkeys on Windows via ``RegisterHotKey``.

``Super+Space`` is reserved by Windows for the input-language switcher, so
``RegisterHotKey`` may refuse it.  DeskOS reports that failure and falls back to
a configurable alternative (``Ctrl+Alt+Space`` by default), which is also
registered globally.  On other platforms the UI falls back to an application
shortcut that only fires while a DeskOS window has focus.
"""

from __future__ import annotations

import ctypes
import logging
from collections.abc import Callable

from PySide6.QtCore import QAbstractNativeEventFilter

log = logging.getLogger(__name__)

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312

_VK_SPACE = 0x20
_VK_F1 = 0x70
_KEY_NAMES = {
    "space": _VK_SPACE,
    "enter": 0x0D,
    "escape": 0x1B,
    "tab": 0x09,
    "`": 0xC0,
}
for _letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    _KEY_NAMES[_letter.lower()] = ord(_letter)
for _digit in "0123456789":
    _KEY_NAMES[_digit] = ord(_digit)

_MODIFIERS = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "meta": MOD_WIN,
    "win": MOD_WIN,
    "super": MOD_WIN,
}


def parse_shortcut(sequence: str) -> tuple[int, int]:
    """Parse ``Ctrl+Alt+Space`` into ``(modifiers, virtual_key)``."""
    parts = [part.strip().lower() for part in sequence.split("+") if part.strip()]
    if not parts:
        raise ValueError("empty shortcut")
    key = parts[-1]
    if key not in _KEY_NAMES:
        raise ValueError(f"unsupported key: {key}")
    modifiers = 0
    for part in parts[:-1]:
        if part not in _MODIFIERS:
            raise ValueError(f"unsupported modifier: {part}")
        modifiers |= _MODIFIERS[part]
    return modifiers | MOD_NOREPEAT, _KEY_NAMES[key]


class GlobalHotkeyManager(QAbstractNativeEventFilter):
    """Register multiple global hotkeys and dispatch them to callbacks."""

    def __init__(self) -> None:
        super().__init__()
        self._callbacks: dict[int, Callable[[], None]] = {}
        self._next_id = 0xA100
        self._registered: set[int] = set()

    def register(self, sequence: str, callback: Callable[[], None]) -> bool:
        try:
            modifiers, key = parse_shortcut(sequence)
        except ValueError as exc:
            log.warning("invalid hotkey %r: %s", sequence, exc)
            return False
        hotkey_id = self._next_id
        self._next_id += 1
        try:
            success = ctypes.windll.user32.RegisterHotKey(None, hotkey_id, modifiers, key)  # type: ignore[attr-defined]
        except Exception:
            log.exception("RegisterHotKey failed for %s", sequence)
            return False
        if not success:
            log.warning("global shortcut %s is already reserved by another program", sequence)
            return False
        self._callbacks[hotkey_id] = callback
        self._registered.add(hotkey_id)
        log.info("registered global shortcut %s", sequence)
        return True

    def unregister_all(self) -> None:
        for hotkey_id in list(self._registered):
            try:
                ctypes.windll.user32.UnregisterHotKey(None, hotkey_id)  # type: ignore[attr-defined]
            except Exception:
                log.debug("could not unregister hotkey %s", hotkey_id, exc_info=True)
        self._registered.clear()
        self._callbacks.clear()

    def nativeEventFilter(self, event_type, message):  # noqa: N802 - Qt API
        try:
            if event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
                msg = ctypes.cast(int(message), ctypes.POINTER(ctypes.c_uint))  # type: ignore[arg-type]
                if msg and msg[1] == WM_HOTKEY:
                    hotkey_id = int(msg[2])
                    callback = self._callbacks.get(hotkey_id)
                    if callback is not None:
                        callback()
                        return True, 0
        except Exception:
            log.debug("hotkey event filter error", exc_info=True)
        return False, 0
