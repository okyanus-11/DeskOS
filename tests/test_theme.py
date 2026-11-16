"""Theme tokens and generated style sheets."""

from __future__ import annotations

import pytest

from deskos.core.config import ConfigManager
from deskos.core.theme import LATTE, MOCHA, PALETTES, ThemeManager


@pytest.fixture()
def manager(tmp_path):
    config = ConfigManager(tmp_path / "config.json")
    config.load()
    return ThemeManager(config)


def test_default_palette_is_mocha(manager):
    assert manager.palette.key == "catppuccin-mocha"
    assert manager.palette.is_dark
    assert {"catppuccin-mocha", "catppuccin-latte"} <= set(PALETTES)


def test_theme_switch_updates_config_and_qss(manager):
    manager.set_theme("catppuccin-latte")
    assert manager.palette.key == LATTE.key
    assert manager.config.get("appearance.theme") == LATTE.key
    qss = manager.qss()
    assert LATTE.base in qss
    assert MOCHA.base not in qss


def test_accent_switch(manager):
    manager.set_accent("mauve")
    assert manager.accent_name == "mauve"
    assert manager.accent == MOCHA.accents["mauve"]
    assert manager.config.get("appearance.accent") == "mauve"
    assert MOCHA.accents["mauve"] in manager.qss()


def test_unknown_theme_is_ignored(manager):
    manager.set_theme("nonsense")
    assert manager.palette.key == MOCHA.key
    manager.set_accent("ultraviolet")
    assert manager.accent_name == "blue"


def test_scale_changes_sizes(manager):
    assert manager.px(10) == 10
    manager.config.set("appearance.ui_scale", 1.5)
    assert manager.px(10) == 15
    assert manager.font_px(13) == 20


def test_alpha_helper(manager):
    assert manager.alpha("#89b4fa", 0.5) == "rgba(137, 180, 250, 0.500)"
    assert "rgba(0, 0, 0" in manager.alpha("#000", 2.0)


def test_toggle_returns_new_key(manager):
    assert manager.toggle() == LATTE.key
    assert manager.toggle() == MOCHA.key


def test_tokens_expose_painting_colours(manager):
    tokens = manager.tokens()
    assert tokens["accent"] == manager.accent
    assert tokens["dark"] is True
    assert tokens["radius"] > 0


def test_apply_config_reloads_theme(manager):
    manager.config.set("appearance.theme", "catppuccin-latte")
    manager.config.set("appearance.accent", "teal")
    manager.apply_config()
    assert manager.palette.key == LATTE.key
    assert manager.accent_name == "teal"



def test_custom_accent_is_validated_and_persisted(manager):
    manager.set_custom_accent("#12abef")
    assert manager.accent == "#12abef"
    assert manager.config.get("appearance.custom_accent") == "#12abef"
    assert manager.config.get("appearance.use_custom_accent") is True
    assert "#12abef" in manager.qss()


def test_preset_accent_disables_custom_accent(manager):
    manager.set_custom_accent("#12abef")
    manager.set_accent("teal")
    assert manager.accent == MOCHA.accents["teal"]
    assert manager.config.get("appearance.use_custom_accent") is False


def test_invalid_custom_accent_is_ignored(manager):
    original = manager.accent
    manager.set_custom_accent("not-a-colour")
    assert manager.accent == original
