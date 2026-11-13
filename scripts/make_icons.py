"""Render the DeskOS logo into the PNG/ICO icon sizes used by the app and PyInstaller.

Usage:  python scripts/make_icons.py
Requires PySide6 (part of the runtime dependencies).
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]
LOGO = ROOT / "assets" / "images" / "deskos-logo.svg"
OUT_DIR = ROOT / "assets" / "images"
SIZES = (16, 24, 32, 48, 64, 128, 256, 512, 1024)


def render_svg(path: Path, size: int) -> QImage:
    renderer = QSvgRenderer(str(path))
    image = QImage(QSize(size, size), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    return image


def main() -> int:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])  # noqa: F841
    if not LOGO.is_file():
        print(f"logo not found: {LOGO}", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        image = render_svg(LOGO, size)
        target = OUT_DIR / f"deskos-{size}.png"
        image.save(str(target))
        print(f"wrote {target.relative_to(ROOT)}")

    # Multi-resolution .ico for Windows shortcuts, window icons and PyInstaller.
    ico_path = OUT_DIR / "deskos.ico"
    icons = [render_svg(LOGO, size) for size in (16, 32, 48, 64, 128, 256)]
    biggest = icons[-1]
    if not biggest.save(str(ico_path), "ICO"):
        print("failed to write .ico", file=sys.stderr)
        return 1
    print(f"wrote {ico_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
