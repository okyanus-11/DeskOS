"""The DeskOS design system: Catppuccin palettes, accents and generated QSS.

Every colour used by the UI comes from a :class:`Palette`.  The theme manager
builds one global style sheet from those tokens, so switching between
Catppuccin Mocha and Latte (or changing the accent) updates the whole
application at runtime without a restart.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from PySide6.QtGui import QColor

from deskos.core.config import ALLOWED_ACCENTS, ConfigManager
from deskos.core.events import EventBus

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Palette:
    key: str
    label: str
    appearance: str  # "dark" | "light"
    base: str
    mantle: str
    crust: str
    surface0: str
    surface1: str
    surface2: str
    overlay0: str
    overlay1: str
    text: str
    subtext0: str
    subtext1: str
    accents: dict[str, str] = field(default_factory=dict)

    def color(self, role: str) -> str:
        if role in self.accents:
            return self.accents[role]
        return getattr(self, role, self.text)

    @property
    def is_dark(self) -> bool:
        return self.appearance == "dark"


MOCHA = Palette(
    key="catppuccin-mocha",
    label="Catppuccin Mocha",
    appearance="dark",
    base="#1e1e2e",
    mantle="#181825",
    crust="#11111b",
    surface0="#313244",
    surface1="#45475a",
    surface2="#585b70",
    overlay0="#6c7086",
    overlay1="#7f849c",
    text="#cdd6f4",
    subtext0="#a6adc8",
    subtext1="#bac2de",
    accents={
        "rosewater": "#f5e0dc",
        "flamingo": "#f2cdcd",
        "pink": "#f5c2e7",
        "mauve": "#cba6f7",
        "red": "#f38ba8",
        "maroon": "#eba0ac",
        "peach": "#fab387",
        "yellow": "#f9e2af",
        "green": "#a6e3a1",
        "teal": "#94e2d5",
        "sky": "#89dceb",
        "sapphire": "#74c7ec",
        "blue": "#89b4fa",
        "lavender": "#b4befe",
    },
)

LATTE = Palette(
    key="catppuccin-latte",
    label="Catppuccin Latte",
    appearance="light",
    base="#eff1f5",
    mantle="#e6e9ef",
    crust="#dce0e8",
    surface0="#ccd0da",
    surface1="#bcc0cc",
    surface2="#acb0be",
    overlay0="#9ca0b0",
    overlay1="#8c8fa1",
    text="#4c4f69",
    subtext0="#6c6f85",
    subtext1="#5c5f77",
    accents={
        "rosewater": "#dc8a78",
        "flamingo": "#dd7878",
        "pink": "#ea76cb",
        "mauve": "#8839ef",
        "red": "#d20f39",
        "maroon": "#e64553",
        "peach": "#fe640b",
        "yellow": "#df8e1d",
        "green": "#40a02b",
        "teal": "#179299",
        "sky": "#04a5e5",
        "sapphire": "#209fb5",
        "blue": "#1e66f5",
        "lavender": "#7287fd",
    },
)

PALETTES: dict[str, Palette] = {palette.key: palette for palette in (MOCHA, LATTE)}
ACCENT_KEYS = tuple(ALLOWED_ACCENTS)
ACCENT_LABELS = {key: key.replace("-", " ").title() for key in ACCENT_KEYS}

FONT_STACK = (
    '"Segoe UI Variable Text", "Segoe UI", "Inter", "Noto Sans", "Cantarell", '
    '"DejaVu Sans", sans-serif'
)
MONO_STACK = (
    '"Cascadia Code", "JetBrains Mono", "Fira Code", "Consolas", "Menlo", "DejaVu Sans Mono", '
    "monospace"
)

# Spacing/radius scale (px at 100% UI scale).
RADIUS_SM = 6
RADIUS_MD = 10
RADIUS_LG = 14
RADIUS_XL = 20
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 18
SPACE_XL = 26


class ThemeManager:
    """Current palette plus QSS generation, persisted through the config."""

    def __init__(self, config: ConfigManager, bus: EventBus | None = None) -> None:
        self.config = config
        self.bus = bus
        self._palette = PALETTES.get(
            str(config.get("appearance.theme", MOCHA.key)), MOCHA
        )
        accent = str(config.get("appearance.accent", "blue"))
        self._accent = accent if accent in self._palette.accents else "blue"
        self._use_custom_accent = bool(config.get("appearance.use_custom_accent", False))
        self._custom_accent = self._validated_custom_accent(
            config.get("appearance.custom_accent", "#89b4fa")
        )

    # -------------------------------------------------------------- state
    @property
    def palette(self) -> Palette:
        return self._palette

    @property
    def accent_name(self) -> str:
        return self._accent

    @property
    def accent(self) -> str:
        if self._use_custom_accent:
            return self._custom_accent
        return self._palette.accents.get(self._accent, self._palette.text)

    @staticmethod
    def _validated_custom_accent(value: Any) -> str:
        color = QColor(str(value or ""))
        return color.name() if color.isValid() else "#89b4fa"

    @property
    def scale(self) -> float:
        try:
            return float(self.config.get("appearance.ui_scale", 1.0))
        except (TypeError, ValueError):
            return 1.0

    def px(self, value: int | float) -> int:
        return max(1, int(round(float(value) * self.scale)))

    def font_px(self, base: int = 13) -> int:
        return max(9, int(round(base * self.scale)))

    def alpha(self, hex_color: str, opacity: float) -> str:
        """Return ``rgba(...)`` for the given #rrggbb colour and alpha 0..1."""
        color = hex_color.lstrip("#")
        if len(color) == 3:
            color = "".join(ch * 2 for ch in color)
        try:
            red, green, blue = (int(color[i : i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            red, green, blue = (30, 30, 46)
        return f"rgba({red}, {green}, {blue}, {max(0.0, min(1.0, opacity)):.3f})"

    def set_theme(self, key: str, *, save: bool = True) -> None:
        palette = PALETTES.get(key)
        if palette is None:
            log.warning("unknown theme %r requested", key)
            return
        if palette.key == self._palette.key:
            return
        self._palette = palette
        self.config.set("appearance.theme", palette.key, save=save)
        self._announce()

    def set_accent(self, key: str, *, save: bool = True) -> None:
        if key not in ACCENT_KEYS:
            log.warning("unknown accent %r requested", key)
            return
        if key == self._accent and not self._use_custom_accent:
            return
        self._accent = key
        self._use_custom_accent = False
        self.config.update(
            {"appearance.accent": key, "appearance.use_custom_accent": False},
            save=save,
        )
        self._announce()

    def set_custom_accent(self, value: str, *, save: bool = True) -> None:
        color = QColor(str(value))
        if not color.isValid():
            log.warning("invalid custom accent %r ignored", value)
            return
        self._custom_accent = color.name()
        self._use_custom_accent = True
        self.config.update(
            {
                "appearance.custom_accent": self._custom_accent,
                "appearance.use_custom_accent": True,
            },
            save=save,
        )
        self._announce()

    def toggle(self) -> str:
        target = LATTE if self._palette.is_dark else MOCHA
        self.set_theme(target.key)
        return target.key

    def apply_config(self) -> None:
        """Re-read theme/accent/scale from config (used after restore)."""
        theme_key = str(self.config.get("appearance.theme", MOCHA.key))
        self._palette = PALETTES.get(theme_key, MOCHA)
        accent = str(self.config.get("appearance.accent", "blue"))
        self._accent = accent if accent in self._palette.accents else "blue"
        self._use_custom_accent = bool(self.config.get("appearance.use_custom_accent", False))
        self._custom_accent = self._validated_custom_accent(
            self.config.get("appearance.custom_accent", "#89b4fa")
        )
        self._announce()

    def _announce(self) -> None:
        if self.bus is not None:
            self.bus.emit("theme.changed", theme=self._palette.key, accent=self._accent)

    # ------------------------------------------------------------- QPalette
    def palette_spec(self) -> dict[str, str]:
        """Roles consumed by the UI layer to build a QPalette."""
        p = self._palette
        return {
            "window": p.base,
            "window_text": p.text,
            "base": p.mantle,
            "alternate_base": p.crust,
            "text": p.text,
            "button": p.surface0,
            "button_text": p.text,
            "highlight": self.accent,
            "highlighted_text": p.crust,
            "tooltip_base": p.surface0,
            "tooltip_text": p.text,
            "placeholder": p.overlay1,
            "disabled_text": p.overlay0,
            "link": self.accent,
            "mid": p.surface1,
        }

    # ----------------------------------------------------------------- QSS
    def qss(self) -> str:
        p = self._palette
        accent = self.accent
        accent_hover = self._mix(accent, p.text, 0.22)
        accent_pressed = self._mix(accent, p.crust, 0.25)
        scale = self.scale
        r_sm = self.px(RADIUS_SM)
        r_md = self.px(RADIUS_MD)
        r_lg = self.px(RADIUS_LG)
        r_xl = self.px(RADIUS_XL)
        font = self.font_px(13)
        font_small = self.font_px(12)
        font_title = self.font_px(15)
        font_heading = self.font_px(22)
        pad = self.px(SPACE_MD)
        pad_sm = self.px(SPACE_SM)
        pad_lg = self.px(SPACE_LG)
        border = f"1px solid {p.surface0}"
        subtle_border = f"1px solid {p.surface1}"

        return f"""
* {{
    font-family: {FONT_STACK};
    font-size: {font}px;
    color: {p.text};
    outline: none;
}}
QWidget#Root, QMainWindow, QDialog {{
    background: {p.base};
}}
QWidget#Shell {{
    background: {p.base};
    border-radius: {r_lg}px;
    border: 1px solid {p.surface1};
}}
QWidget#TitleBar {{
    background: transparent;
    border-top-left-radius: {r_lg}px;
    border-top-right-radius: {r_lg}px;
}}
QLabel#TitleLabel {{
    font-size: {font_title}px;
    font-weight: 600;
    color: {p.text};
}}
QLabel#AppTitle {{
    font-size: {font_heading}px;
    font-weight: 700;
    color: {p.text};
}}
QLabel#Heading {{
    font-size: {font_heading}px;
    font-weight: 700;
    color: {p.text};
}}
QLabel#Subheading {{
    font-size: {font_title}px;
    font-weight: 600;
    color: {p.text};
}}
QLabel#Muted, QLabel[muted="true"] {{
    color: {p.subtext0};
    font-size: {font_small}px;
}}
QLabel#SectionTitle {{
    color: {p.subtext1};
    font-size: {font_small}px;
    font-weight: 700;
    letter-spacing: 1px;
    text-transform: uppercase;
}}
QLabel#StatValue {{
    font-size: {self.font_px(26)}px;
    font-weight: 700;
    color: {p.text};
}}
QLabel#StatLabel {{
    color: {p.subtext0};
    font-size: {font_small}px;
}}
QLabel#Accent {{
    color: {accent};
}}
QLabel#Badge {{
    background: {self.alpha(accent, 0.16)};
    color: {accent};
    border-radius: {self.px(9)}px;
    padding: {self.px(2)}px {pad_sm}px;
    font-size: {font_small}px;
    font-weight: 600;
}}
QLabel#Pill {{
    background: {p.surface0};
    color: {p.subtext1};
    border-radius: {self.px(9)}px;
    padding: {self.px(2)}px {pad_sm}px;
    font-size: {font_small}px;
}}
QFrame#Card, QWidget#Card {{
    background: {self.alpha(p.mantle, 0.92)};
    border: {subtle_border};
    border-radius: {r_lg}px;
}}
QFrame#WidgetCard {{
    background: {self.alpha(p.mantle, 0.86)};
    border: {subtle_border};
    border-radius: {r_lg}px;
}}
QFrame#WidgetCard:hover {{
    border: 1px solid {self.alpha(accent, 0.55)};
}}
QFrame#Panel {{
    background: {p.mantle};
    border: {subtle_border};
    border-radius: {r_xl}px;
}}
QFrame#Divider {{
    background: {p.surface0};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}
QFrame#VDivider {{
    background: {p.surface0};
    max-width: 1px;
    min-width: 1px;
    border: none;
}}
QWidget#NavRail {{
    background: {self.alpha(p.crust, 0.55)};
    border-right: {subtle_border};
    border-top-left-radius: {r_lg}px;
    border-bottom-left-radius: {r_lg}px;
}}
QWidget#Sidebar {{
    background: {self.alpha(p.mantle, 0.55)};
    border-right: {subtle_border};
}}
QPushButton {{
    background: {p.surface0};
    color: {p.text};
    border: {border};
    border-radius: {r_md}px;
    padding: {self.px(7)}px {pad}px;
    font-weight: 500;
}}
QPushButton:hover {{
    background: {p.surface1};
    border-color: {p.surface2};
}}
QPushButton:pressed {{
    background: {p.surface2};
}}
QPushButton:disabled {{
    color: {p.overlay0};
    background: {self.alpha(p.surface0, 0.6)};
}}
QPushButton#PrimaryButton {{
    background: {accent};
    color: {p.crust};
    border: 1px solid {accent};
    font-weight: 600;
}}
QPushButton#PrimaryButton:hover {{
    background: {accent_hover};
    border-color: {accent_hover};
}}
QPushButton#PrimaryButton:pressed {{
    background: {accent_pressed};
}}
QPushButton#DangerButton {{
    background: transparent;
    color: {p.accents['red']};
    border: 1px solid {self.alpha(p.accents['red'], 0.5)};
}}
QPushButton#DangerButton:hover {{
    background: {self.alpha(p.accents['red'], 0.16)};
}}
QPushButton#GhostButton, QPushButton[variant="ghost"] {{
    background: transparent;
    border: 1px solid transparent;
    color: {p.subtext1};
}}
QPushButton#GhostButton:hover, QPushButton[variant="ghost"]:hover {{
    background: {p.surface0};
    color: {p.text};
}}
QPushButton#IconButton {{
    background: transparent;
    border: none;
    border-radius: {r_md}px;
    padding: {self.px(5)}px;
}}
QPushButton#IconButton:hover {{
    background: {p.surface0};
}}
QPushButton#IconButton:checked {{
    background: {self.alpha(accent, 0.18)};
}}
QPushButton#WindowButton {{
    background: transparent;
    border: none;
    border-radius: {r_sm}px;
    padding: {self.px(5)}px {self.px(8)}px;
    color: {p.subtext1};
}}
QPushButton#WindowButton:hover {{
    background: {p.surface0};
    color: {p.text};
}}
QPushButton#WindowButtonClose:hover {{
    background: {p.accents['red']};
    color: {p.crust};
}}
QPushButton#NavButton {{
    background: transparent;
    border: none;
    border-radius: {r_md}px;
    padding: {self.px(9)}px {pad}px;
    color: {p.subtext0};
    text-align: left;
    font-weight: 500;
}}
QPushButton#NavButton:hover {{
    background: {p.surface0};
    color: {p.text};
}}
QPushButton#NavButton:checked {{
    background: {self.alpha(accent, 0.16)};
    color: {accent};
    font-weight: 600;
}}
QPushButton#DockButton {{
    background: transparent;
    border: none;
    border-radius: {r_md}px;
    padding: {self.px(4)}px;
}}
QPushButton#DockButton:hover {{
    background: {self.alpha(p.text, 0.10)};
}}
QPushButton#AccentSwatch {{
    border-radius: {self.px(12)}px;
    border: 2px solid transparent;
    min-width: {self.px(24)}px;
    max-width: {self.px(24)}px;
    min-height: {self.px(24)}px;
    max-height: {self.px(24)}px;
}}
QPushButton#AccentSwatch:checked {{
    border: 2px solid {p.text};
}}
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox,
QDateEdit, QTimeEdit, QDateTimeEdit {{
    background: {p.crust};
    border: {border};
    border-radius: {r_md}px;
    padding: {self.px(6)}px {pad_sm}px;
    selection-background-color: {self.alpha(accent, 0.4)};
    selection-color: {p.text};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QComboBox:focus, QDateEdit:focus, QTimeEdit:focus {{
    border: 1px solid {accent};
}}
QLineEdit#SearchField {{
    background: {p.surface0};
    border: {border};
    border-radius: {r_lg}px;
    padding: {self.px(8)}px {pad}px;
    font-size: {font_title}px;
}}
QLineEdit#SearchField:focus {{
    border: 1px solid {self.alpha(accent, 0.8)};
    background: {p.mantle};
}}
QComboBox::drop-down {{
    border: none;
    width: {self.px(22)}px;
}}
QComboBox QAbstractItemView {{
    background: {p.mantle};
    border: {subtle_border};
    border-radius: {r_md}px;
    padding: {self.px(4)}px;
    selection-background-color: {self.alpha(accent, 0.25)};
}}
QCheckBox, QRadioButton {{
    spacing: {pad_sm}px;
    color: {p.subtext1};
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: {self.px(16)}px;
    height: {self.px(16)}px;
    border-radius: {self.px(5)}px;
    border: 1px solid {p.surface2};
    background: {p.crust};
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {accent};
    border-color: {accent};
}}
QRadioButton::indicator {{
    border-radius: {self.px(8)}px;
}}
QSlider::groove:horizontal {{
    height: {self.px(4)}px;
    background: {p.surface1};
    border-radius: {self.px(2)}px;
}}
QSlider::sub-page:horizontal {{
    background: {accent};
    border-radius: {self.px(2)}px;
}}
QSlider::handle:horizontal {{
    background: {p.text};
    border: 2px solid {p.base};
    width: {self.px(14)}px;
    height: {self.px(14)}px;
    margin: -{self.px(6)}px 0;
    border-radius: {self.px(9)}px;
}}
QProgressBar {{
    background: {p.surface0};
    border: none;
    border-radius: {self.px(5)}px;
    height: {self.px(9)}px;
    text-align: center;
    color: {p.subtext1};
    font-size: {font_small}px;
}}
QProgressBar::chunk {{
    background: {accent};
    border-radius: {self.px(5)}px;
}}
QTabWidget::pane {{
    border: none;
    background: transparent;
}}
QTabBar::tab {{
    background: transparent;
    color: {p.subtext0};
    padding: {self.px(7)}px {pad}px;
    margin-right: {self.px(4)}px;
    border-radius: {r_md}px;
    font-weight: 500;
}}
QTabBar::tab:hover {{
    background: {p.surface0};
    color: {p.text};
}}
QTabBar::tab:selected {{
    background: {self.alpha(accent, 0.16)};
    color: {accent};
    font-weight: 600;
}}
QTreeView, QListView, QTableView, QListWidget, QTreeWidget, QTableWidget {{
    background: {p.mantle};
    border: {subtle_border};
    border-radius: {r_md}px;
    padding: {self.px(4)}px;
    alternate-background-color: {self.alpha(p.surface0, 0.35)};
}}
QTreeView::item, QListView::item, QTableView::item, QListWidget::item {{
    padding: {self.px(6)}px;
    border-radius: {r_sm}px;
}}
QTreeView::item:selected, QListView::item:selected, QTableView::item:selected,
QListWidget::item:selected {{
    background: {self.alpha(accent, 0.2)};
    color: {p.text};
}}
QTreeView::item:hover, QListView::item:hover, QListWidget::item:hover {{
    background: {p.surface0};
}}
QHeaderView::section {{
    background: {p.mantle};
    color: {p.subtext0};
    border: none;
    border-bottom: {subtle_border};
    padding: {self.px(6)}px {pad_sm}px;
    font-size: {font_small}px;
    font-weight: 600;
}}
QMenu {{
    background: {p.mantle};
    border: {subtle_border};
    border-radius: {r_md}px;
    padding: {self.px(6)}px;
}}
QMenu::item {{
    padding: {self.px(7)}px {pad_lg}px;
    border-radius: {r_sm}px;
    color: {p.subtext1};
}}
QMenu::item:selected {{
    background: {self.alpha(accent, 0.2)};
    color: {p.text};
}}
QMenu::separator {{
    height: 1px;
    background: {p.surface0};
    margin: {self.px(5)}px {pad_sm}px;
}}
QToolTip {{
    background: {p.surface0};
    color: {p.text};
    border: {subtle_border};
    border-radius: {r_sm}px;
    padding: {self.px(5)}px {pad_sm}px;
}}
QScrollBar:vertical {{
    background: transparent;
    width: {self.px(11)}px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {p.surface2};
    border-radius: {self.px(5)}px;
    min-height: {self.px(28)}px;
}}
QScrollBar::handle:vertical:hover {{
    background: {p.overlay0};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: {self.px(11)}px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {p.surface2};
    border-radius: {self.px(5)}px;
    min-width: {self.px(28)}px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0;
    height: 0;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}
QSplitter::handle {{
    background: {p.surface0};
}}
QSplitter::handle:horizontal {{
    width: {self.px(2)}px;
}}
QSplitter::handle:vertical {{
    height: {self.px(2)}px;
}}
QGroupBox {{
    border: {subtle_border};
    border-radius: {r_md}px;
    margin-top: {self.px(14)}px;
    padding-top: {self.px(10)}px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: {pad}px;
    padding: 0 {self.px(4)}px;
    color: {p.subtext1};
}}
QCalendarWidget QWidget {{
    alternate-background-color: {p.mantle};
    background: {p.mantle};
}}
QCalendarWidget QAbstractItemView:enabled {{
    background: {p.mantle};
    color: {p.text};
    selection-background-color: {self.alpha(accent, 0.35)};
    selection-color: {p.text};
}}
QCalendarWidget QAbstractItemView:disabled {{
    color: {p.overlay0};
}}
QCalendarWidget QToolButton {{
    background: transparent;
    color: {p.text};
    border: none;
    border-radius: {r_sm}px;
    padding: {self.px(4)}px;
}}
QCalendarWidget QToolButton:hover {{
    background: {p.surface0};
}}
QCalendarWidget QSpinBox {{
    background: {p.mantle};
}}
QWidget#Dock {{
    background: {self.alpha(p.mantle, 0.96)};
    border: {subtle_border};
    border-radius: {r_xl}px;
}}
QWidget#LauncherPanel, QWidget#PalettePanel {{
    background: {self.alpha(p.base, 0.98)};
    border: {subtle_border};
    border-radius: {r_xl}px;
}}
QWidget#Overlay {{
    background: {self.alpha(p.crust, 0.55)};
}}
QPushButton#LauncherTile {{
    background: {self.alpha(p.surface0, 0.7)};
    border: {border};
    border-radius: {r_lg}px;
    padding: {pad}px;
    text-align: center;
    font-weight: 500;
}}
QPushButton#LauncherTile:hover {{
    background: {self.alpha(accent, 0.16)};
    border: 1px solid {self.alpha(accent, 0.6)};
}}
QPushButton#LauncherTile:focus {{
    border: 1px solid {accent};
}}
QPushButton#PaletteItem {{
    background: transparent;
    border: none;
    border-radius: {r_md}px;
    padding: {self.px(9)}px {pad}px;
    text-align: left;
}}
QPushButton#PaletteItem:hover {{
    background: {p.surface0};
}}
QPushButton#PaletteItem[active="true"] {{
    background: {self.alpha(accent, 0.2)};
}}
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QWidget#BubbleUser {{
    background: {self.alpha(accent, 0.22)};
    border: 1px solid {self.alpha(accent, 0.4)};
    border-radius: {r_lg}px;
}}
QWidget#BubbleAssistant {{
    background: {p.surface0};
    border: {subtle_border};
    border-radius: {r_lg}px;
}}
QWidget#BubbleSystem {{
    background: {self.alpha(p.accents['yellow'], 0.12)};
    border: 1px solid {self.alpha(p.accents['yellow'], 0.35)};
    border-radius: {r_md}px;
}}
QWidget#Toast {{
    background: {p.surface0};
    border: {subtle_border};
    border-radius: {r_md}px;
}}
QWidget#DropIndicator {{
    background: {accent};
    border-radius: {self.px(2)}px;
}}
QToolBar {{
    background: transparent;
    border: none;
    spacing: {self.px(4)}px;
}}
QStatusBar {{
    background: {p.mantle};
    color: {p.subtext0};
}}
QPlainTextEdit#TerminalOutput {{
    background: {p.crust};
    color: {p.text};
    font-family: {MONO_STACK};
    font-size: {font}px;
    border-radius: {r_md}px;
}}
QPushButton#LauncherTile[active="true"] {{
    background: {self.alpha(accent, 0.22)};
    border: 2px solid {accent};
}}
QListWidget#PaletteList {{
    background: transparent;
    border: none;
    padding: 0;
}}
QListWidget#PaletteList::item {{
    padding: {self.px(8)}px {pad}px;
    border-radius: {r_md}px;
    color: {p.subtext1};
}}
QListWidget#PaletteList::item:selected {{
    background: {self.alpha(accent, 0.2)};
    color: {p.text};
}}
QListWidget#SettingsNav {{
    background: transparent;
    border: none;
    padding: 0;
}}
QListWidget#SettingsNav::item {{
    padding: {self.px(9)}px {pad}px;
    border-radius: {r_md}px;
    color: {p.subtext0};
}}
QListWidget#SettingsNav::item:hover {{
    background: {p.surface0};
    color: {p.text};
}}
QListWidget#SettingsNav::item:selected {{
    background: {self.alpha(accent, 0.16)};
    color: {accent};
}}
QWidget#Body, QWidget#PageStack {{
    background: transparent;
}}
"""
    @staticmethod
    def _mix(first: str, second: str, amount: float) -> str:
        """Blend two hex colours, ``amount`` 0..1 towards ``second``."""
        def parts(value: str) -> tuple[int, int, int]:
            value = value.lstrip("#")
            return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)

        r1, g1, b1 = parts(first)
        r2, g2, b2 = parts(second)
        amount = max(0.0, min(1.0, amount))
        blended = (
            int(round(r1 + (r2 - r1) * amount)),
            int(round(g1 + (g2 - g1) * amount)),
            int(round(b1 + (b2 - b1) * amount)),
        )
        return "#{:02x}{:02x}{:02x}".format(*blended)

    def tokens(self) -> dict[str, Any]:
        """Expose design tokens to Python painting code (graphs, dock, etc.)."""
        p = self._palette
        return {
            "base": p.base,
            "mantle": p.mantle,
            "crust": p.crust,
            "surface0": p.surface0,
            "surface1": p.surface1,
            "surface2": p.surface2,
            "overlay0": p.overlay0,
            "overlay1": p.overlay1,
            "text": p.text,
            "subtext0": p.subtext0,
            "subtext1": p.subtext1,
            "accent": self.accent,
            "accent_name": self._accent,
            "green": p.accents["green"],
            "yellow": p.accents["yellow"],
            "red": p.accents["red"],
            "peach": p.accents["peach"],
            "teal": p.accents["teal"],
            "mauve": p.accents["mauve"],
            "blue": p.accents["blue"],
            "radius": self.px(RADIUS_MD),
            "scale": self.scale,
            "dark": p.is_dark,
        }
