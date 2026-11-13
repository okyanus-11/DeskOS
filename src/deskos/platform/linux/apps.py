"""Linux application discovery through freedesktop ``.desktop`` entries.

This is the basis of the future Arch Linux support: it reads the same files that
application menus use, resolves ``Exec`` lines with field-code stripping, and
launches entries with ``gio launch`` or by executing the resolved command.
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess  # noqa: S404 - launching applications is the feature
from pathlib import Path

from deskos.platform.base import AppEntry, AppLauncher, LaunchError

log = logging.getLogger(__name__)
_SKIP_TERMINALS = {"true", "false"}


def app_id_for(name: str, path: str = "") -> str:
    import hashlib

    digest = hashlib.sha1(f"{name.lower()}|{path.lower()}".encode()).hexdigest()[:12]
    return f"ext:{digest}"


def _data_dirs() -> list[Path]:
    dirs: list[Path] = []
    home = Path.home()
    for entry in (os.environ.get("XDG_DATA_HOME"), str(home / ".local" / "share")):
        if entry:
            dirs.append(Path(entry) / "applications")
    for entry in (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":"):
        if entry:
            dirs.append(Path(entry) / "applications")
    return dirs


def parse_desktop_entry(text: str) -> dict[str, str]:
    """Parse the ``[Desktop Entry]`` group of a .desktop file."""
    result: dict[str, str] = {}
    in_group = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_group = line == "[Desktop Entry]"
            continue
        if not in_group or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in ("Name", "Exec", "Icon", "Comment", "Type", "Terminal", "NoDisplay", "Hidden",
                   "Categories", "GenericName"):
            result[key] = value.strip()
    return result


def split_exec(command: str) -> list[str]:
    """Split an ``Exec`` value, dropping deprecated field codes."""
    try:
        parts = shlex.split(command)
    except ValueError:
        return []
    cleaned: list[str] = []
    for part in parts:
        if part.startswith("%"):
            continue
        cleaned.append(part)
    return cleaned


class DesktopEntryDiscovery(AppLauncher):
    def __init__(self, roots: list[Path] | None = None) -> None:
        self.roots = roots or _data_dirs()

    def discover(self, force: bool = False) -> list[AppEntry]:
        entries: dict[str, AppEntry] = {}
        for root in self.roots:
            if not root.is_dir():
                continue
            for path in sorted(root.glob("*.desktop")):
                entry = self._load_entry(path)
                if entry and entry.name not in entries:
                    entries[entry.name] = entry
        return sorted(entries.values(), key=lambda item: item.name.lower())

    def _load_entry(self, path: Path) -> AppEntry | None:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        data = parse_desktop_entry(text)
        if data.get("Type") != "Application":
            return None
        if data.get("NoDisplay", "").lower() in _SKIP_TERMINALS:
            return None
        if data.get("Hidden", "").lower() in _SKIP_TERMINALS:
            return None
        name = data.get("Name", "").strip()
        command = split_exec(data.get("Exec", ""))
        if not name or not command:
            return None
        return AppEntry(
            id=app_id_for(name, str(path)),
            name=name,
            path=str(path),
            args=command,
            source="desktop-entry",
            icon_path=data.get("Icon", ""),
            comment=data.get("Comment", ""),
            target=str(path),
            kind="desktop-entry",
        )

    def launch(self, entry: AppEntry) -> None:
        command = entry.args or [entry.path]
        try:
            subprocess.Popen(  # noqa: S603 - command comes from a desktop entry
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                start_new_session=True,
            )
        except OSError as exc:
            raise LaunchError(f"Could not launch {entry.name}: {exc}") from exc
