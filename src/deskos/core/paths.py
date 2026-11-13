"""Filesystem locations used by DeskOS.

User data never lives inside the source tree.  On Windows everything is kept in
``%APPDATA%\\DeskOS`` so that roaming profiles and backup tools pick it up; on
Linux the XDG data directory is used.  ``DESKOS_HOME`` overrides the root, which
is what the test-suite and the screenshot renderer rely on.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "DeskOS"
APP_SLUG = "deskos"


def _platform_data_root() -> Path:
    override = os.environ.get("DESKOS_HOME")
    if override:
        return Path(override).expanduser()

    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_NAME


def data_dir() -> Path:
    """Root of all persistent DeskOS state (config, database, logs, plugins)."""
    path = _platform_data_root()
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return data_dir() / "config.json"


def database_path() -> Path:
    return data_dir() / "deskos.db"


def logs_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        path = Path(base) / APP_NAME / "cache"
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Caches" / APP_NAME
    else:
        base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
        path = Path(base) / APP_SLUG
    path.mkdir(parents=True, exist_ok=True)
    return path


def backups_dir() -> Path:
    path = data_dir() / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_plugins_dir() -> Path:
    """Directory scanned in addition to the bundled ``plugins/`` folder."""
    path = data_dir() / "plugins"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resource_root() -> Path:
    """Directory that holds ``assets/`` and bundled ``plugins/``.

    When frozen by PyInstaller the resources are unpacked into ``sys._MEIPASS``;
    when installed as a wheel we fall back to the project root that contains the
    ``src`` and ``assets`` folders.
    """
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    # src/deskos/core/paths.py -> project root
    return Path(__file__).resolve().parents[3]


def assets_dir() -> Path:
    return resource_root() / "assets"


def icons_dir() -> Path:
    return assets_dir() / "icons"


def images_dir() -> Path:
    return assets_dir() / "images"


def bundled_plugins_dir() -> Path:
    return resource_root() / "plugins"


def icon_file(name: str) -> Path:
    """Path of a bundled SVG icon, falling back to a generic document icon."""
    candidate = icons_dir() / f"{name}.svg"
    return candidate if candidate.is_file() else icons_dir() / "file.svg"


def logo_path() -> Path:
    png = images_dir() / "deskos-256.png"
    return png if png.is_file() else images_dir() / "deskos-logo.svg"


def app_icon_path() -> Path:
    ico = images_dir() / "deskos.ico"
    return ico if ico.is_file() else logo_path()


def is_windows() -> bool:
    return sys.platform == "win32"


def is_linux() -> bool:
    return sys.platform.startswith("linux")
