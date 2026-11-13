"""Filesystem helpers used by DeskFiles.

Every operation reports failures instead of swallowing them so the UI can show a
clear message (permissions, locked files and long paths are common on Windows).
"""

from __future__ import annotations

import logging
import os
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class OperationResult:
    ok: bool
    message: str = ""
    affected: list[str] | None = None


def search_files(root: str, query: str, limit: int = 300, max_depth: int = 8) -> list[str]:
    """Recursively search file names (case-insensitive) below ``root``."""
    needle = query.strip().lower()
    if not needle:
        return []
    results: list[str] = []
    base = Path(root)
    if not base.is_dir():
        return results
    base_depth = len(base.parts)
    for current, directories, files in os.walk(base, onerror=lambda _err: None):
        depth = len(Path(current).parts) - base_depth
        if depth >= max_depth:
            directories[:] = []
        for name in list(directories) + list(files):
            if needle in name.lower():
                results.append(str(Path(current) / name))
                if len(results) >= limit:
                    return results
    return results


def unique_destination(directory: Path, name: str) -> Path:
    """Return a non-existing path such as ``report (2).txt``."""
    candidate = directory / name
    if not candidate.exists():
        return candidate
    stem = Path(name).stem
    suffix = Path(name).suffix
    index = 2
    while True:
        candidate = directory / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def copy_items(paths: Iterable[str], destination: str, *, move: bool = False) -> OperationResult:
    target = Path(destination)
    if not target.is_dir():
        return OperationResult(False, "The destination is not a folder")
    affected: list[str] = []
    for raw in paths:
        source = Path(raw)
        try:
            if source.resolve() == target.resolve():
                affected.append(str(source))
                continue  # copying a file into its own folder is a no-op
            destination_path = unique_destination(target, source.name)
            if source.is_dir():
                shutil.copytree(source, destination_path)
            else:
                shutil.copy2(source, destination_path)
            if move:
                if source.is_dir():
                    shutil.rmtree(source)
                else:
                    source.unlink()
            affected.append(str(destination_path))
        except (OSError, shutil.Error) as exc:
            log.warning("could not %s %s: %s", "move" if move else "copy", source, exc)
            return OperationResult(False, f"{source.name}: {exc}", affected)
    return OperationResult(True, "", affected)


def directory_size(path: str) -> int:
    total = 0
    for current, _directories, files in os.walk(path, onerror=lambda _err: None):
        for name in files:
            try:
                total += (Path(current) / name).stat().st_size
            except OSError:
                continue
    return total


def delete_permanently(paths: Iterable[str]) -> OperationResult:
    for raw in paths:
        target = Path(raw)
        try:
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()
        except OSError as exc:
            log.warning("could not delete %s: %s", target, exc)
            return OperationResult(False, f"{target.name}: {exc}")
    return OperationResult(True)


def create_folder(parent: str, name: str) -> OperationResult:
    target = Path(parent) / name
    try:
        target.mkdir(parents=False, exist_ok=False)
    except FileExistsError:
        return OperationResult(False, "An item with that name already exists")
    except OSError as exc:
        return OperationResult(False, str(exc))
    return OperationResult(True, affected=[str(target)])


def rename_item(path: str, new_name: str) -> OperationResult:
    source = Path(path)
    target = source.with_name(new_name)
    try:
        source.rename(target)
    except OSError as exc:
        return OperationResult(False, str(exc))
    return OperationResult(True, affected=[str(target)])


def humanize_mode(path: str) -> str:
    try:
        mode = os.stat(path).st_mode
    except OSError:
        return "—"
    return oct(mode & 0o777)
