"""Minimal internationalisation.

Only the shell-level strings are translated today (navigation, window titles,
common actions).  App-internal copy remains English; this is documented in the
README rather than implied to be complete.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

LANGUAGES = {"en": "English", "tr": "Türkçe"}

CATALOGS: dict[str, dict[str, str]] = {
    "en": {
        "app.name": "DeskOS",
        "nav.dashboard": "Dashboard",
        "nav.workspaces": "Workspaces",
        "nav.apps": "Applications",
        "nav.monitor": "System",
        "nav.settings": "Control Center",
        "nav.ai": "DeskAI",
        "action.launcher": "Applications",
        "action.palette": "Command palette",
        "action.settings": "Control Center",
        "action.ai": "Ask DeskAI",
        "action.quit": "Quit DeskOS",
        "action.minimize": "Minimize",
        "action.close": "Close",
        "action.toggle_theme": "Toggle light / dark theme",
        "section.recent": "Recently used",
        "section.pinned": "Pinned",
        "section.widgets": "Widgets",
        "section.shortcuts": "Shortcuts",
        "dock.launcher": "Open the application launcher",
        "search.placeholder": "Search applications and commands…",
        "palette.placeholder": "Type a command…",
        "widget.add": "Add widget",
        "widget.remove": "Remove widget",
        "widget.settings": "Widget settings",
        "workspace.active": "Active workspace",
        "settings.appearance": "Appearance",
        "settings.system": "System",
        "settings.network": "Network",
        "settings.applications": "Applications",
        "settings.general": "General",
        "settings.plugins": "Plugins",
    },
    "tr": {
        "app.name": "DeskOS",
        "nav.dashboard": "Panel",
        "nav.workspaces": "Çalışma Alanları",
        "nav.apps": "Uygulamalar",
        "nav.monitor": "Sistem",
        "nav.settings": "Denetim Merkezi",
        "nav.ai": "DeskAI",
        "action.launcher": "Uygulamalar",
        "action.palette": "Komut paleti",
        "action.settings": "Denetim Merkezi",
        "action.ai": "DeskAI'ye sor",
        "action.quit": "DeskOS'tan çık",
        "action.minimize": "Küçült",
        "action.close": "Kapat",
        "action.toggle_theme": "Açık / koyu temayı değiştir",
        "section.recent": "Son kullanılanlar",
        "section.pinned": "Sabitlenenler",
        "section.widgets": "Araçlar",
        "section.shortcuts": "Kısayollar",
        "dock.launcher": "Uygulama başlatıcıyı aç",
        "search.placeholder": "Uygulama ve komut ara…",
        "palette.placeholder": "Bir komut yazın…",
        "widget.add": "Araç ekle",
        "widget.remove": "Aracı kaldır",
        "widget.settings": "Araç ayarları",
        "workspace.active": "Etkin çalışma alanı",
        "settings.appearance": "Görünüm",
        "settings.system": "Sistem",
        "settings.network": "Ağ",
        "settings.applications": "Uygulamalar",
        "settings.general": "Genel",
        "settings.plugins": "Eklentiler",
    },
}


class Translator:
    def __init__(self, language: str = "en") -> None:
        self._language = language if language in CATALOGS else "en"

    @property
    def language(self) -> str:
        return self._language

    def set_language(self, language: str) -> None:
        self._language = language if language in CATALOGS else "en"

    def t(self, key: str, default: str | None = None, **values: object) -> str:
        text = CATALOGS.get(self._language, {}).get(key)
        if text is None:
            text = CATALOGS["en"].get(key, default if default is not None else key)
        if values:
            try:
                text = text.format(**values)
            except (KeyError, IndexError):
                log.debug("translation placeholder mismatch for %r", key)
        return text


translator = Translator()


def set_language(language: str) -> None:
    translator.set_language(language)


def tr(key: str, default: str | None = None, **values: object) -> str:
    return translator.t(key, default, **values)
