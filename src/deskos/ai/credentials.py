"""API key storage.

Preferred backend: the OS credential store via ``keyring`` — on Windows that is
the Credential Locker (DPAPI-backed).  If ``keyring`` is missing or has no usable
backend, DeskOS falls back to a user-only readable JSON file in its data folder
and reports that clearly instead of pretending the key is protected.
"""

from __future__ import annotations

import json
import logging
import os
import stat
from pathlib import Path

from deskos.core.paths import data_dir

log = logging.getLogger(__name__)

SERVICE_NAME = "DeskOS"


class CredentialStore:
    def __init__(self, fallback_path: Path | None = None) -> None:
        self.fallback_path = fallback_path or (data_dir() / "secrets.json")
        self._keyring = None
        self._keyring_error = ""
        try:
            import keyring  # noqa: PLC0415 - optional dependency

            backend = keyring.get_keyring()
            if backend is not None and "fail" not in type(backend).__name__.lower():
                self._keyring = keyring
        except Exception as exc:  # keyring missing or misconfigured
            self._keyring_error = str(exc)
            log.info("keyring unavailable, using file fallback: %s", exc)

    # ------------------------------------------------------------------ state
    def backend_name(self) -> str:
        if self._keyring is not None:
            try:
                return f"System credential store ({self._keyring.get_keyring().__class__.__name__})"
            except Exception:
                return "System credential store"
        return "Local secrets file (not OS-protected)"

    @property
    def secure_backend(self) -> bool:
        return self._keyring is not None

    # ----------------------------------------------------------------- access
    def get(self, provider: str) -> str:
        if self._keyring is not None:
            try:
                value = self._keyring.get_password(SERVICE_NAME, f"ai:{provider}")
                if value:
                    return str(value)
            except Exception:
                log.debug("keyring read failed", exc_info=True)
        return str(self._read_file().get(provider, ""))

    def set(self, provider: str, key: str) -> bool:
        key = (key or "").strip()
        if self._keyring is not None:
            try:
                if key:
                    self._keyring.set_password(SERVICE_NAME, f"ai:{provider}", key)
                else:
                    try:
                        self._keyring.delete_password(SERVICE_NAME, f"ai:{provider}")
                    except Exception:
                        pass
                return True
            except Exception:
                log.warning("keyring write failed; falling back to file", exc_info=True)
        return self._write_file(provider, key)

    def delete(self, provider: str) -> None:
        self.set(provider, "")

    # ------------------------------------------------------------------- file
    def _read_file(self) -> dict[str, str]:
        if not self.fallback_path.is_file():
            return {}
        try:
            payload = json.loads(self.fallback_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            log.warning("could not read fallback secrets file")
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write_file(self, provider: str, key: str) -> bool:
        payload = self._read_file()
        if key:
            payload[provider] = key
        else:
            payload.pop(provider, None)
        try:
            self.fallback_path.parent.mkdir(parents=True, exist_ok=True)
            self.fallback_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            try:
                os.chmod(self.fallback_path, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass
        except OSError:
            log.exception("could not persist the API key")
            return False
        return True

    def has_key(self, provider: str) -> bool:
        return bool(self.get(provider))
