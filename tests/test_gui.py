"""Off-screen GUI tests for the shell, dashboard, apps and overlays."""

from __future__ import annotations

import time

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from deskos.applications.catalog import BuiltinCatalog
from deskos.core.builtin_commands import register_builtin_commands
from deskos.services.launcher_service import LauncherService


def build_services(context, qapp):
    """Attach the runtime services the UI expects and return them."""
    context.services["catalog"] = BuiltinCatalog()
    context.services["launcher"] = LauncherService(context, context.services["catalog"])
    register_builtin_commands(context)
    return context.services["launcher"]


def test_dashboard_builds_configured_widgets(context, qapp):
    build_services(context, qapp)
    from deskos.ui.dashboard import DashboardView

    view = DashboardView(context)
    view.resize(1200, 800)
    view.show()
    assert view._widgets, "the default dashboard should create widgets"
    assert "clock" in view._widgets
    view.add_widget("github")
    assert "github" in view._widgets
    assert any(entry.get("type") == "github" for entry in context.workspaces.widget_layout())
    view.move_widget("github", -1)
    view.remove_widget("github")
    assert "github" not in view._widgets
    view.close()


def test_dashboard_widget_settings_persist(context, qapp):
    build_services(context, qapp)
    from deskos.ui.dashboard import DashboardView

    view = DashboardView(context)
    view._save_widget_settings("weather", {"city": "Ankara"})
    stored = next(
        entry for entry in context.workspaces.widget_layout() if entry.get("type") == "weather"
    )
    assert stored["settings"] == {"city": "Ankara"}
    view.close()


def test_dock_and_main_window(context, qapp):
    launcher = build_services(context, qapp)
    from deskos.ui.dock import Dock
    from deskos.ui.main_window import MainWindow

    window = MainWindow(context)
    context.services["shell"] = window
    dock = Dock(context)
    context.services["dock"] = dock
    assert window.stack.count() == 3
    assert dock._items, "pinned built-in apps should appear in the dock"
    window.select_page("applications")
    assert window.stack.currentIndex() == 1
    window.select_page("workspaces")
    assert window.stack.currentIndex() == 2
    launcher.close_all()
    dock.close()
    window.close()


def test_launcher_overlay_filters(context, qapp):
    build_services(context, qapp)
    context.app_registry._on_discovered(list(context.platform.apps.entries))
    from deskos.ui.launcher import LauncherOverlay

    overlay = LauncherOverlay(context)
    overlay.resize(1200, 800)
    overlay.open_overlay()
    QTest.qWait(60)
    total = len(overlay._tiles)
    assert total >= 8
    overlay.search.setText("DeskFiles")
    QTest.qWait(30)
    visible = [tile for tile in overlay._tiles if not tile.isHidden()]
    assert any("DeskFiles" in tile.text() for tile in visible)
    overlay.hide()


def test_command_palette_filters_and_runs(context, qapp):
    build_services(context, qapp)
    from deskos.ui.palette import CommandPaletteOverlay

    overlay = CommandPaletteOverlay(context)
    overlay.open_overlay()
    QTest.qWait(30)
    overlay.search.setText("cpu")
    QTest.qWait(30)
    assert overlay.list.count() >= 1
    overlay.search.setText("definitely-no-command")
    QTest.qWait(30)
    assert overlay.list.count() == 0
    overlay.hide()


def test_notes_page_saves(context, qapp):
    build_services(context, qapp)
    from deskos.applications.notes.view import NotesPage

    note_id = context.notes.create("Seed", "content", "Work", ["a"])
    page = NotesPage(context)
    page._select_note(note_id)
    page.title_field.setText("Renamed note")
    page.body_field.setPlainText("Updated body")
    page._save_current()
    saved = context.notes.get(note_id)
    assert saved.title == "Renamed note"
    assert saved.body == "Updated body"
    page.deleteLater()


def test_tasks_page_lists_tasks(context, qapp):
    build_services(context, qapp)
    from deskos.applications.tasks.view import TasksPage

    context.tasks.create("First task", priority=1)
    context.tasks.create("Second task", priority=3)
    page = TasksPage(context)
    assert page.list_layout.count() >= 2
    assert page.counts.text().startswith("2 active")
    page.deleteLater()


def test_files_page_navigates(context, qapp, tmp_path):
    build_services(context, qapp)
    from deskos.applications.files.view import FilesPage
    from deskos.applications.files.ops import search_files

    (tmp_path / "alpha.txt").write_text("a")
    (tmp_path / "folder").mkdir()
    page = FilesPage(context)
    page.navigate(str(tmp_path))
    assert page.current_path() == str(tmp_path)
    assert search_files(str(tmp_path), "alpha") == [str(tmp_path / "alpha.txt")]
    page.deleteLater()


def test_terminal_runs_real_shell(context, qapp):
    build_services(context, qapp)
    from deskos.applications.terminal.view import TerminalPage

    shells = context.platform.terminal.available_shells()
    if not shells:
        pytest.skip("no POSIX shell on this machine")
    page = TerminalPage(context)
    page.show()
    assert page.current_shell() is not None
    page.send_command("echo deskos-$((6*7))")
    deadline = time.time() + 8
    while time.time() < deadline:
        QTest.qWait(100)
        if "deskos-42" in page.output.toPlainText():
            break
    assert "deskos-42" in page.output.toPlainText(), page.output.toPlainText()
    page.on_closing()
    page.deleteLater()


def test_monitor_page_and_control_center(context, qapp, sample_snapshot):
    build_services(context, qapp)
    from deskos.applications.monitor.view import MonitorPage
    from deskos.control_center.window import ControlCenterWindow

    monitor_page = MonitorPage(context)
    monitor_page._on_snapshot(sample_snapshot)
    monitor_page._apply_hardware(context.platform.system.hardware_info())
    monitor_page._apply_os(context.platform.system.os_info())
    assert monitor_page.process_table.columnCount() == 4

    window = ControlCenterWindow(context)
    window.resize(1000, 720)
    for key in ("appearance", "system", "network", "applications", "general", "plugins"):
        window.select_page(key)
        QTest.qWait(10)
    window.close()
    monitor_page.deleteLater()


def test_clock_and_ai_windows_construct(context, qapp):
    build_services(context, qapp)
    from deskos.ai.view import DeskAIWindow
    from deskos.applications.clock.view import ClockPage

    clock = ClockPage(context)
    clock._stopwatch_start()
    QTest.qWait(30)
    clock._stopwatch_lap()
    assert clock.laps.count() == 1
    clock._stopwatch_reset()
    clock._timer_toggle()
    clock._timer_reset()
    clock.deleteLater()

    ai = DeskAIWindow(context)
    assert ai.provider_label.text()
    ai.close()


def test_theme_switch_repaints_shell(context, qapp):
    build_services(context, qapp)
    from deskos.ui.main_window import MainWindow

    window = MainWindow(context)
    context.services["shell"] = window
    context.theme.set_theme("catppuccin-latte")
    assert context.theme.palette.is_dark is False
    context.theme.set_theme("catppuccin-mocha")
    window.close()


def test_launcher_service_open_builtin(context, qapp):
    launcher = build_services(context, qapp)
    window = launcher.open_builtin("app.notes")
    assert window is not None and window.isVisible()
    assert launcher.is_running("app.notes")
    launcher.close_all()
    assert not launcher.is_running("app.notes")


def test_plugin_widget_render(context, qapp):
    build_services(context, qapp)
    from deskos.widgets.base import WidgetContext

    spec = context.widget_registry.get("cpu")
    assert spec is not None
    widget_context = WidgetContext(ctx=context, icons=context.icons)
    widget = context.widget_registry.create("cpu", widget_context)
    assert widget is not None
    widget.refresh(None)
    widget.show()
    QTest.qWait(10)
    assert widget.grab().width() > 0
    widget.deleteLater()
