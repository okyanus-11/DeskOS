"""XDG file integration (xdg-open / gio trash)."""

from __future__ import annotations

import logging
import shutil
import subprocess  # noqa: S404 - opening files is the feature
from pathlib import Path

import psutil

from deskos.platform.base import FileIntegration

log = logging.getLogger(__name__)


class LinuxFiles(FileIntegration):
    def open_path(self, path: str) -> bool:
        opener = shutil.which("xdg-open")
        if not opener:
            return False
        try:
            subprocess.Popen(  # noqa: S603
                [opener, path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True
            )
            return True
        except OSError:
            log.exception("xdg-open failed for %s", path)
            return False

    def reveal_path(self, path: str) -> bool:
        target = path if Path(path).is_dir() else str(Path(path).parent)
        return self.open_path(target)

    def trash(self, path: str) -> bool:
        gio = shutil.which("gio")
        if not gio:
            log.warning("gio not available; cannot move %s to trash", path)
            return False
        try:
            completed = subprocess.run(  # noqa: S603
                [gio, "trash", path], capture_output=True, text=True, timeout=60
            )
        except (OSError, subprocess.SubprocessError):
            log.exception("gio trash failed for %s", path)
            return False
        if completed.returncode != 0:
            log.warning("gio trash: %s", completed.stderr.strip()[:300])
            return False
        return True

    def locations(self) -> list[tuple[str, str]]:
        home = Path.home()
        candidates = [
            ("Home", home),
            ("Desktop", home / "Desktop"),
            ("Documents", home / "Documents"),
            ("Downloads", home / "Downloads"),
            ("Pictures", home / "Pictures"),
            ("Music", home / "Music"),
            ("Videos", home / "Videos"),
        ]
        return [(label, str(path)) for label, path in candidates if path.is_dir()]

    def drives(self) -> list[tuple[str, str]]:
        drives: list[tuple[str, str]] = []
        for partition in psutil.disk_partitions(all=False):
            drives.append((partition.mountpoint, partition.mountpoint))
        return drives

    def default_path(self) -> str:
        return str(Path.home())
