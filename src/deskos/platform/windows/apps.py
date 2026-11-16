"""Real Windows application discovery.

Three mechanisms are combined, all of them documented Windows behaviour:

1. **App Paths** - ``HKCU``/``HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\
   App Paths`` holds executables that are registered as launchable.
2. **Start Menu shortcuts** - every ``*.lnk`` under the per-user and
   all-users Start Menu folders is enumerated and its target resolved through
   the ``WScript.Shell`` COM object (invoked once through PowerShell so no extra
   Python dependency is required).
3. **Packaged/Store apps** - ``Get-StartApps`` returns the AppUserModelIDs that
   ``explorer.exe shell:AppsFolder\\<id>`` can launch.

Results are cached in the user cache directory and refreshed on demand, because
enumerating the Start Menu costs a PowerShell round-trip.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import subprocess  # noqa: S404 - launching installed applications is the feature
import time
from pathlib import Path
from typing import Any

try:  # pragma: no cover - only importable on Windows
    import winreg
except ImportError:  # pragma: no cover - exercised on Linux test runners
    winreg = None  # type: ignore[assignment]

from deskos.platform.base import AppEntry, AppLauncher, LaunchError

log = logging.getLogger(__name__)

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_PS_TIMEOUT = 90


def app_id_for(name: str, path: str = "") -> str:
    digest = hashlib.sha1(f"{name.lower()}|{path.lower()}".encode("utf-8")).hexdigest()[:12]
    return f"ext:{digest}"


def _run_powershell(script: str, timeout: int = _PS_TIMEOUT) -> str:
    """Run a PowerShell snippet and return stdout (empty string on failure)."""
    executable = "powershell.exe"
    try:
        completed = subprocess.run(  # noqa: S603 - fixed executable, generated script
            [executable, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-Command", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        log.exception("PowerShell discovery step failed")
        return ""
    if completed.returncode != 0:
        log.warning(
            "PowerShell exited with %s: %s",
            completed.returncode,
            completed.stderr.strip()[:400],
        )
    return completed.stdout or ""


def _parse_json_array(raw: str) -> list[dict[str, Any]]:
    raw = raw.strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        log.debug("could not parse discovery payload: %s", raw[:300])
        return []
    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    return []


class WindowsAppDiscovery(AppLauncher):
    def __init__(self, cache_path: Path | None = None, cache_hours: float = 6.0) -> None:
        self.cache_path = cache_path
        self.cache_hours = cache_hours

    # ------------------------------------------------------------- discovery
    def discover(self, force: bool = False) -> list[AppEntry]:
        if not force:
            cached = self._load_cache()
            if cached:
                return cached

        entries: list[AppEntry] = []
        for step, loader in (
            ("App Paths registry", self._from_registry),
            ("Start Menu", self._from_start_menu),
            ("Store apps", self._from_start_apps),
        ):
            try:
                found = loader()
                log.info("%s discovery returned %d entries", step, len(found))
                entries.extend(found)
            except Exception:
                log.exception("%s discovery failed; continuing with other sources", step)

        merged = self._deduplicate(entries)
        self._save_cache(merged)
        return merged

    def _from_registry(self) -> list[AppEntry]:
        if winreg is None:
            return []
        entries: list[AppEntry] = []
        roots = [
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
        ]
        for hive, subkey in roots:
            try:
                with winreg.OpenKey(hive, subkey) as root:
                    count = winreg.QueryInfoKey(root)[0]
                    for index in range(count):
                        try:
                            exe_name = winreg.EnumKey(root, index)
                            with winreg.OpenKey(root, exe_name) as entry_key:
                                try:
                                    target, _ = winreg.QueryValueEx(entry_key, "")
                                except OSError:
                                    continue
                        except OSError:
                            continue
                        if not isinstance(target, str) or not target.lower().endswith(".exe"):
                            continue
                        if not os.path.isfile(target):
                            continue
                        name = Path(target).stem.replace("_", " ").strip()
                        entries.append(
                            AppEntry(
                                id=app_id_for(name, target),
                                name=name,
                                path=target,
                                source="registry",
                                icon_path=target,
                                kind="app",
                            )
                        )
            except OSError:
                log.debug("App Paths key unavailable: %s", subkey)
        return entries

    def _start_menu_roots(self) -> list[Path]:
        roots: list[Path] = []
        for env in ("ProgramData", "APPDATA"):
            base = os.environ.get(env)
            if not base:
                continue
            candidate = Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
            if candidate.is_dir():
                roots.append(candidate)
        return roots

    def _from_start_menu(self) -> list[AppEntry]:
        roots = self._start_menu_roots()
        if not roots:
            log.warning("no Start Menu folders found")
            return []

        directories = ";".join(str(root).replace("'", "''") for root in roots)
        script = (
            "$ErrorActionPreference = 'SilentlyContinue';"
            "$shell = New-Object -ComObject WScript.Shell;"
            "$items = @();"
            f"foreach ($dir in @('{directories}'.Split(';'))) {{"
            "  Get-ChildItem -LiteralPath $dir -Filter *.lnk -Recurse |"
            "  ForEach-Object {"
            "    try {"
            "      $s = $shell.CreateShortcut($_.FullName);"
            "      $items += [pscustomobject]@{"
            "        Shortcut = $_.FullName;"
            "        Name = $_.BaseName;"
            "        Target = $s.TargetPath;"
            "        Arguments = $s.Arguments;"
            "        WorkingDirectory = $s.WorkingDirectory;"
            "        Description = $s.Description"
            "      }"
            "    } catch {}"
            "  }"
            "};"
            "ConvertTo-Json -InputObject $items -Compress -Depth 3"
        )
        payload = _parse_json_array(_run_powershell(script))

        entries: list[AppEntry] = []
        for record in payload:
            name = str(record.get("Name") or "").strip()
            shortcut = str(record.get("Shortcut") or "")
            target = str(record.get("Target") or "")
            if not name:
                continue
            if target and target.lower().endswith((".url", ".website")):
                continue
            arguments = str(record.get("Arguments") or "").strip()
            entries.append(
                AppEntry(
                    id=app_id_for(name, shortcut or target),
                    name=name,
                    path=target,
                    args=arguments.split() if arguments else [],
                    source="start-menu",
                    icon_path=target or shortcut,
                    comment=str(record.get("Description") or ""),
                    target=shortcut,
                    kind="shortcut",
                )
            )
        return entries

    def _from_start_apps(self) -> list[AppEntry]:
        script = (
            "$ErrorActionPreference = 'SilentlyContinue';"
            "Get-StartApps | Select-Object Name, AppID |"
            " ConvertTo-Json -Compress -Depth 3"
        )
        payload = _parse_json_array(_run_powershell(script))
        entries: list[AppEntry] = []
        for record in payload:
            name = str(record.get("Name") or "").strip()
            app_id = str(record.get("AppID") or "").strip()
            if not name or not app_id:
                continue
            # App Paths/Start Menu already cover classic win32 programs; only
            # keep identifiers that cannot be launched as a plain file.
            if app_id.lower().endswith(".exe") and os.path.isfile(app_id):
                continue
            entries.append(
                AppEntry(
                    id=app_id_for(name, app_id),
                    name=name,
                    source="store",
                    target=app_id,
                    kind="store",
                )
            )
        return entries

    @staticmethod
    def _deduplicate(entries: list[AppEntry]) -> list[AppEntry]:
        seen: dict[str, AppEntry] = {}
        for entry in entries:
            key = entry.name.strip().lower()
            existing = seen.get(key)
            if existing is None:
                seen[key] = entry
                continue
            # Prefer a concrete executable target over a .lnk, and Start Menu
            # metadata over the terse registry name.
            if existing.kind == "store" and entry.kind != "store":
                seen[key] = entry
        result = sorted(seen.values(), key=lambda item: item.name.lower())
        return result

    # ---------------------------------------------------------------- launch
    def launch(self, entry: AppEntry) -> None:
        try:
            if entry.kind == "store" and entry.target:
                subprocess.Popen(  # noqa: S603 - opening a registered AppUserModelID
                    ["explorer.exe", f"shell:AppsFolder\\{entry.target}"], close_fds=True
                )
                return
            target = entry.target if entry.kind == "shortcut" else entry.path
            if target and os.path.isfile(target) and target.lower().endswith(".lnk"):
                os.startfile(target)  # type: ignore[attr-defined]  # noqa: S606
                return
            if entry.path and os.path.isfile(entry.path):
                os.startfile(entry.path)  # type: ignore[attr-defined]  # noqa: S606
                return
            if entry.target and os.path.isfile(entry.target):
                os.startfile(entry.target)  # type: ignore[attr-defined]  # noqa: S606
                return
        except OSError as exc:
            raise LaunchError(f"Could not launch {entry.name}: {exc}") from exc
        raise LaunchError(f"No launchable target found for {entry.name}")

    # ----------------------------------------------------------------- cache
    def _load_cache(self) -> list[AppEntry] | None:
        if not self.cache_path or not self.cache_path.is_file():
            return None
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        try:
            created = float(payload.get("created", 0))
        except (TypeError, ValueError):
            return None
        now = time.time()
        if not math.isfinite(created) or created <= 0 or created > now + 300:
            return None
        if now - created > self.cache_hours * 3600:
            return None
        raw_entries = payload.get("entries")
        if not isinstance(raw_entries, list):
            return None
        entries: list[AppEntry] = []
        for item in raw_entries:
            if not isinstance(item, dict):
                continue
            try:
                entry = AppEntry.from_dict(item)
            except (TypeError, ValueError):
                log.debug("ignoring malformed application cache entry")
                continue
            if entry.id and entry.name:
                entries.append(entry)
        return entries or None

    def _save_cache(self, entries: list[AppEntry]) -> None:
        if not self.cache_path:
            return
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps(
                    {"created": time.time(), "entries": [entry.to_dict() for entry in entries]},
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            log.debug("could not write application cache", exc_info=True)
