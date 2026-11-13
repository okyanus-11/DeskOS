"""DeskOS workspace persistence and switching."""

from __future__ import annotations


def test_default_and_seeded_workspaces(context):
    workspaces = context.workspaces.list()
    names = {workspace.name for workspace in workspaces}
    assert "Default" in names
    assert {"Development", "School", "Personal", "Monitoring"} <= names
    assert context.workspaces.active_id == "default"


def test_switch_updates_config_and_emits(context):
    events = []
    context.bus.subscribe("workspace.changed", lambda workspace: events.append(workspace.name))
    target = next(ws for ws in context.workspaces.list() if ws.name == "Development")
    switched = context.workspaces.switch(target.id)
    assert switched.name == "Development"
    assert context.workspaces.active_id == target.id
    assert context.config.get("workspaces.active") == target.id
    assert events == ["Development"]


def test_switch_unknown_workspace_raises(context):
    try:
        context.workspaces.switch("nope")
    except KeyError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected KeyError")


def test_pinned_commands_and_widget_layout(context):
    context.workspaces.set_pinned(["app.files", "app.notes"])
    assert context.workspaces.pinned_commands() == ["app.files", "app.notes"]

    widgets = [{"type": "cpu", "enabled": True}, {"type": "clock", "enabled": False}]
    context.workspaces.set_widgets(widgets)
    assert context.workspaces.widget_layout() == widgets

    context.workspaces.set_layout({"columns": 3})
    assert context.workspaces.columns() == 3
    assert context.workspaces.active().layout["columns"] == 3


def test_widget_layout_falls_back_to_config(context):
    workspace = context.workspaces.active()
    context.workspace_repo.update(workspace.id, widgets=[])
    layout = context.workspaces.widget_layout()
    assert layout[0]["type"] == "clock"


def test_create_inherits_current_widgets(context):
    created = context.workspaces.create("Focus mode", icon="notes")
    assert created.name == "Focus mode"
    assert created.widgets  # inherited from the default dashboard template
    assert 2 <= context.workspaces.columns() <= 6


def test_active_workspace_cannot_be_deleted(context):
    active = context.workspaces.active_id
    assert context.workspaces.delete(active) is False
    other = next(ws for ws in context.workspaces.list() if ws.id != active)
    assert context.workspaces.delete(other.id) is True


def test_workspaces_survive_restart(context):
    from deskos.services.workspace_manager import WorkspaceManager

    context.workspaces.set_pinned(["app.terminal"])
    restarted = WorkspaceManager(context.workspace_repo, context.config, context.bus)
    assert restarted.pinned_commands() == ["app.terminal"]
