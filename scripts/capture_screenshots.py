"""Render real DeskOS screenshots from the running application.

The script boots the full shell on Qt's offscreen platform, uses a temporary
data directory (so no personal state is touched), populates a little demo content
and saves PNGs into ``docs/screenshots``.  Every image is a genuine grab of the
Qt widget tree — nothing is mocked or drawn by hand.

Usage:
    QT_QPA_PLATFORM=offscreen python scripts/capture_screenshots.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HOME = tempfile.mkdtemp(prefix="deskos-shots-")
os.environ["DESKOS_HOME"] = HOME

from PySide6.QtCore import QPoint, QTimer  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QPainter  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

OUTPUT = ROOT / "docs" / "screenshots"
WIDTH, HEIGHT = 1440, 900


def settle(milliseconds: int = 220) -> None:
    QTest.qWait(milliseconds)


def grab(widget, name: str, *, width: int | None = None, height: int | None = None) -> None:
    if width and height:
        widget.resize(width, height)
    widget.show()
    settle(320)
    QApplication.processEvents()
    pixmap = widget.grab()
    target = OUTPUT / name
    pixmap.save(str(target))
    print(f"captured {target.relative_to(ROOT)} ({pixmap.width()}x{pixmap.height()})", flush=True)


def grab_overlay(overlay, window, name: str) -> None:
    """Composite the translucent overlay panel over the dimmed shell."""
    settle(250)
    base = window.grab()
    panel = overlay.panel.grab()
    position = QPoint(
        max(0, (base.width() - panel.width()) // 2),
        max(0, (base.height() - panel.height()) // 2),
    )
    painter = QPainter(base)
    painter.fillRect(base.rect(), QColor(10, 10, 16, 135))
    painter.drawPixmap(position, panel)
    painter.end()
    target = OUTPUT / name
    base.save(str(target))
    print(f"captured {target.relative_to(ROOT)} ({base.width()}x{base.height()})", flush=True)


def seed_content(controller) -> None:
    notes = controller.notes_repo
    if notes.count() == 0:
        notes.create(
            "DeskOS 1.0 release checklist",
            "Sign the build, regenerate the docs screenshots and tag the release.\n"
            "The changelog is generated from the commit history.",
            "Work",
            ["release", "docs"],
        )
        notes.create(
            "Plugin ideas",
            "A clipboard-history widget and a music transport widget would both fit the "
            "existing widget API without new permissions.",
            "Ideas",
            ["plugins"],
        )
    tasks = controller.tasks_repo
    if tasks.counts()[0] == 0:
        tasks.create("Review the theme tokens", priority=1, category="Design")
        tasks.create("Write the plugin guide", due_date="2026-12-01", priority=2, category="Docs")
        finished = tasks.create("Publish the repository", priority=3, category="Release")
        tasks.set_completed(finished, True)


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication.instance() or QApplication(sys.argv[:1])

    from deskos.app import DeskOSApplication

    controller = DeskOSApplication(app)
    seed_content(controller)
    for _ in range(60):
        controller.monitor.sample()
        QTest.qWait(12)

    window = controller.main_window
    window.resize(WIDTH, HEIGHT)
    window.show()
    settle(900)
    controller.monitor.sample()
    settle(500)

    grab(window, "01-dashboard.png")

    # Applications + workspaces pages
    window.select_page("applications")
    settle(700)
    grab(window, "02-applications.png")

    window.select_page("workspaces")
    settle(300)
    grab(window, "03-workspaces.png")

    # Light theme dashboard
    controller.theme.set_theme("catppuccin-latte")
    controller.apply_theme()
    window.select_page("dashboard")
    settle(600)
    grab(window, "04-dashboard-light.png")
    controller.theme.set_theme("catppuccin-mocha")
    controller.apply_theme()
    settle(400)

    # Overlays
    window.show_launcher()
    settle(500)
    launcher_overlay = window._launcher
    if launcher_overlay is not None:
        launcher_overlay.setGeometry(0, 0, WIDTH, HEIGHT)
        grab_overlay(launcher_overlay, window, "05-launcher.png")
        launcher_overlay.hide()

    window.show_palette()
    settle(450)
    palette = window._palette
    if palette is not None:
        palette.setGeometry(0, 0, WIDTH, HEIGHT)
        palette.search.setText("")
        grab_overlay(palette, window, "06-command-palette.png")
        palette.hide()

    # Control center pages
    control = controller.launcher.open_settings("appearance")
    settle(500)
    control.resize(1100, 760)
    grab(control, "07-control-center-appearance.png")
    control.select_page("system")
    settle(500)
    grab(control, "08-control-center-system.png")
    control.select_page("plugins")
    settle(300)
    grab(control, "09-control-center-plugins.png")
    control.close()

    # Built-in applications
    monitor_window = controller.launcher.open_builtin("app.monitor")
    settle(1200)
    controller.monitor.sample()
    settle(900)
    grab(monitor_window, "10-deskmonitor.png")
    monitor_window.close()

    notes_window = controller.launcher.open_builtin("app.notes")
    settle(500)
    grab(notes_window, "11-desknotes.png")
    notes_window.close()

    tasks_window = controller.launcher.open_builtin("app.tasks")
    settle(400)
    grab(tasks_window, "12-desktasks.png")
    tasks_window.close()

    clock_window = controller.launcher.open_builtin("app.clock")
    settle(400)
    grab(clock_window, "13-deskclock.png")
    clock_window.close()

    files_window = controller.launcher.open_builtin("app.files")
    settle(700)
    grab(files_window, "14-deskfiles.png")
    files_window.close()

    terminal_window = controller.launcher.open_builtin("app.terminal")
    settle(700)
    page = getattr(terminal_window, "page", None)
    if page is not None:
        page.send_command("echo DeskOS terminal — real shell process")
        page.send_command("uname -a" if os.name != "nt" else "ver")
        settle(900)
    grab(terminal_window, "15-deskterminal.png")
    terminal_window.close()

    ai_window = controller.launcher.open_ai()
    settle(500)
    grab(ai_window, "16-deskai.png")
    ai_window.close()

    grab(controller.dock, "17-dock.png")

    controller.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
