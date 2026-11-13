"""Windows file manager integration used by DeskFiles."""

from __future__ import annotations

import logging
import os
import subprocess  # noqa: S404 - opening explorer is the feature
from pathlib import Path

import psutil

from deskos.platform.base import FileIntegration

log = logging.getLogger(__name__)


class WindowsFiles(FileIntegration):
    def open_path(self, path: str) -> bool:
        try:
            os.startfile(path)  # type: ignore[attr-defined]  # noqa: S606
            return True
        except OSError:
            log.exception("could not open %s", path)
            return False

    def reveal_path(self, path: str) -> bool:
        try:
            if Path(path).is_dir():
                os.startfile(path)  # type: ignore[attr-defined]  # noqa: S606
            else:
                subprocess.Popen(["explorer.exe", f"/select,{path}"], close_fds=True)  # noqa: S603
            return True
        except OSError:
            log.exception("could not reveal %s", path)
            return False

    def trash(self, path: str) -> bool:
        """Move a file to the Recycle Bin using the shell's SHFileOperation."""
        try:
            import ctypes
            from ctypes import wintypes

            class SHFILEOPSTRUCTW(ctypes.Structure):
                _fields_ = [
                    ("hwnd", wintypes.HWND),
                    ("wFunc", wintypes.UINT),
                    ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR),
                    ("fFlags", ctypes.c_uint),
                    ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p),
                    ("lpszProgressTitle", wintypes.LPCWSTR),
                ]

            FO_DELETE = 3
            FOF_ALLOWUNDO = 0x0040
            FOF_NOCONFIRMATION = 0x0010
            FOF_SILENT = 0x0004
            operation = SHFILEOPSTRUCTW()
            operation.wFunc = FO_DELETE
            operation.pFrom = path + "\0\0"
            operation.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT
            result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))  # type: ignore[attr-defined]
            if result != 0:
                log.warning("SHFileOperationW returned %s for %s", result, path)
                return False
            return True
        except Exception:
            log.exception("could not move %s to the Recycle Bin", path)
            return False

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
            if "cdrom" in partition.opts or not partition.fstype:
                continue
            drives.append((partition.device.rstrip("\\"), partition.device))
        return drives

    def default_path(self) -> str:
        return str(Path.home())
