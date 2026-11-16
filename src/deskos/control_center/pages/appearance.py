"""Appearance: theme, accent, wallpaper, transparency, animations and scaling."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QColorDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from deskos.core.config import ALLOWED_ACCENTS
from deskos.core.context import DeskOSContext
from deskos.core.theme import ACCENT_LABELS, PALETTES
from deskos.ui.components import Card, Muted, SectionTitle, scrollable

log = logging.getLogger(__name__)


class AppearancePage(QWidget):
    def __init__(self, context: DeskOSContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = context
        self.theme = context.theme

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 10, 24, 20)
        layout.setSpacing(16)

        title = QLabel("Appearance")
        title.setObjectName("Heading")
        layout.addWidget(title)
        layout.addWidget(Muted("Themes and accents apply immediately — no restart needed."))

        theme_card = Card()
        theme_card.layout.addWidget(SectionTitle("Theme"))
        theme_row = QHBoxLayout()
        self._theme_buttons = QButtonGroup(self)
        self._theme_buttons.setExclusive(True)
        for index, (key, palette) in enumerate(PALETTES.items()):
            button = QPushButton(f"{palette.label}\n{'Dark' if palette.is_dark else 'Light'}")
            button.setCheckable(True)
            button.setMinimumHeight(58)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(
                f"QPushButton {{ background: {palette.mantle}; color: {palette.text};"
                f" border: 1px solid {palette.surface1}; border-radius: 10px; padding: 8px 14px; }}"
                f"QPushButton:checked {{ border: 2px solid {palette.accents['blue']}; }}"
            )
            button.clicked.connect(lambda _checked=False, name=key: self._set_theme(name))
            self._theme_buttons.addButton(button, index)
            theme_row.addWidget(button, 1)
        theme_card.layout.addLayout(theme_row)
        layout.addWidget(theme_card)

        accent_card = Card()
        accent_card.layout.addWidget(SectionTitle("Accent colour"))
        swatches = QHBoxLayout()
        swatches.setSpacing(8)
        self._accent_group = QButtonGroup(self)
        self._accent_group.setExclusive(True)
        for index, accent in enumerate(ALLOWED_ACCENTS):
            button = QPushButton()
            button.setObjectName("AccentSwatch")
            button.setCheckable(True)
            button.setToolTip(ACCENT_LABELS[accent])
            color = self.theme.palette.accents.get(accent, "#89b4fa")
            button.setStyleSheet(
                f"QPushButton {{ background: {color}; border-radius: 12px;"
                f" min-width: 24px; max-width: 24px; min-height: 24px; max-height: 24px;"
                f" border: 2px solid transparent; }}"
                f"QPushButton:checked {{ border: 2px solid {self.theme.palette.text}; }}"
            )
            button.clicked.connect(lambda _checked=False, name=accent: self._set_accent(name))
            self._accent_group.addButton(button, index)
            swatches.addWidget(button)
        swatches.addStretch(1)
        accent_card.layout.addLayout(swatches)
        custom_row = QHBoxLayout()
        self.custom_accent_button = QPushButton("Choose custom colour…")
        self.custom_accent_button.clicked.connect(self._choose_custom_accent)
        custom_row.addWidget(self.custom_accent_button)
        custom_row.addStretch(1)
        accent_card.layout.addLayout(custom_row)
        self.accent_label = Muted("")
        accent_card.layout.addWidget(self.accent_label)
        layout.addWidget(accent_card)

        wallpaper_card = Card()
        wallpaper_card.layout.addWidget(SectionTitle("Wallpaper"))
        wallpaper_row = QHBoxLayout()
        self.wallpaper_label = Muted("No custom wallpaper")
        wallpaper_row.addWidget(self.wallpaper_label, 1)
        choose = QPushButton("Choose image…")
        choose.clicked.connect(self._choose_wallpaper)
        wallpaper_row.addWidget(choose)
        clear = QPushButton("Clear")
        clear.clicked.connect(self._clear_wallpaper)
        wallpaper_row.addWidget(clear)
        wallpaper_card.layout.addLayout(wallpaper_row)
        wallpaper_card.layout.addWidget(
            Muted("Images (PNG, JPG, WebP) are drawn behind the dashboard widgets.")
        )
        layout.addWidget(wallpaper_card)

        effects_card = Card()
        effects_card.layout.addWidget(SectionTitle("Effects & scaling"))
        transparency_row = QHBoxLayout()
        transparency_row.addWidget(QLabel("Dock transparency"))
        self.transparency = QSlider(Qt.Orientation.Horizontal)
        self.transparency.setRange(40, 100)
        self.transparency.valueChanged.connect(self._on_transparency)
        transparency_row.addWidget(self.transparency, 1)
        self.transparency_value = Muted("")
        transparency_row.addWidget(self.transparency_value)
        effects_card.layout.addLayout(transparency_row)

        scale_row = QHBoxLayout()
        scale_row.addWidget(QLabel("Interface scale"))
        self.scale_slider = QSlider(Qt.Orientation.Horizontal)
        self.scale_slider.setRange(80, 160)
        self.scale_slider.setSingleStep(5)
        self.scale_slider.valueChanged.connect(self._on_scale)
        scale_row.addWidget(self.scale_slider, 1)
        self.scale_value = Muted("")
        scale_row.addWidget(self.scale_value)
        effects_card.layout.addLayout(scale_row)

        self.animations_button = QPushButton("Disable animations")
        self.animations_button.setCheckable(True)
        self.animations_button.clicked.connect(self._toggle_animations)
        effects_card.layout.addWidget(self.animations_button)
        layout.addWidget(effects_card)
        layout.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scrollable(container))
        self.refresh()

    # ------------------------------------------------------------------ state
    def refresh(self) -> None:
        current_theme = self.ctx.config.get("appearance.theme")
        for index, key in enumerate(PALETTES):
            button = self._theme_buttons.button(index)
            if button is not None:
                button.setChecked(key == current_theme)
        accent = self.ctx.config.get("appearance.accent")
        use_custom = bool(self.ctx.config.get("appearance.use_custom_accent", False))
        for index, key in enumerate(ALLOWED_ACCENTS):
            button = self._accent_group.button(index)
            if button is not None:
                button.setChecked(key == accent and not use_custom)
        if use_custom:
            custom = str(self.ctx.config.get("appearance.custom_accent", "#89b4fa"))
            self.accent_label.setText(f"Custom accent: {custom.upper()}")
            self.custom_accent_button.setStyleSheet(
                f"QPushButton {{ background: {custom}; color: #11111b; "
                "border: 1px solid transparent; border-radius: 9px; padding: 7px 12px; }"
            )
        else:
            self.accent_label.setText(f"Accent: {ACCENT_LABELS.get(str(accent), accent)}")
            self.custom_accent_button.setStyleSheet("")

        wallpaper = str(self.ctx.config.get("appearance.wallpaper", ""))
        self.wallpaper_label.setText(wallpaper or "No custom wallpaper")
        self.transparency.setValue(int(float(self.ctx.config.get("dock.opacity", 0.92)) * 100))
        self.scale_slider.setValue(int(float(self.ctx.config.get("appearance.ui_scale", 1.0)) * 100))
        animations = bool(self.ctx.config.get("appearance.animations", True))
        self.animations_button.setChecked(not animations)
        self.animations_button.setText("Disable animations" if animations else "Animations disabled")

    def _set_theme(self, key: str) -> None:
        self.theme.set_theme(key)
        self._apply_globals()

    def _set_accent(self, key: str) -> None:
        self.theme.set_accent(key)
        self.accent_label.setText(f"Accent: {ACCENT_LABELS.get(key, key)}")
        self._apply_globals()

    def _choose_custom_accent(self) -> None:
        current = self.theme.accent
        color = QColorDialog.getColor(QColor(current), self, "Choose custom accent")
        if color.isValid():
            self.theme.set_custom_accent(color.name())
            self._apply_globals()

    def _on_transparency(self, value: int) -> None:
        self.transparency_value.setText(f"{value}%")
        self.ctx.config.set("dock.opacity", max(0.4, value / 100.0))
        dock = self.ctx.services.get("dock")
        if dock is not None:
            dock.apply_config()

    def _on_scale(self, value: int) -> None:
        self.scale_value.setText(f"{value}%")
        self.ctx.config.set("appearance.ui_scale", value / 100.0)
        self._apply_globals()

    def _toggle_animations(self) -> None:
        enabled = not self.animations_button.isChecked()
        self.ctx.config.set("appearance.animations", enabled)
        self.animations_button.setText(
            "Disable animations" if enabled else "Animations disabled"
        )

    def _apply_globals(self) -> None:
        apply_theme = self.ctx.services.get("apply_theme")
        if callable(apply_theme):
            apply_theme()
        self.refresh()

    def _choose_wallpaper(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self, "Choose wallpaper", "", "Images (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if path:
            self.ctx.config.set("appearance.wallpaper", path)
            self.wallpaper_label.setText(path)
            self.ctx.bus.emit("wallpaper.changed")
            self.ctx.toast("Wallpaper updated")

    def _clear_wallpaper(self) -> None:
        self.ctx.config.set("appearance.wallpaper", "")
        self.wallpaper_label.setText("No custom wallpaper")
        self.ctx.bus.emit("wallpaper.changed")
