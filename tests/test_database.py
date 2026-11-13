"""Persistence layer: migrations, repositories and transactions."""

from __future__ import annotations

import pytest

from deskos.core.database import SCHEMA_VERSION, Database
from deskos.data.repositories import (
    AIHistoryRepository,
    NotesRepository,
    PluginStateRepository,
    TasksRepository,
    UsageRepository,
    WorkspaceRepository,
)


@pytest.fixture()
def database(tmp_path):
    db = Database(tmp_path / "deskos.db")
    db.connect()
    yield db
    db.close()


def test_migrations_create_schema(database):
    tables = set(database.table_names())
    assert {
        "notes",
        "tasks",
        "workspaces",
        "app_usage",
        "ai_conversations",
        "ai_messages",
        "plugin_state",
        "launch_history",
    } <= tables
    assert database.integrity_check()
    version = database.scalar("PRAGMA user_version")
    assert int(version) == SCHEMA_VERSION


def test_reconnecting_is_idempotent(database):
    database.connect()
    database.connect()
    assert database.query_one("SELECT 1 AS ok")["ok"] == 1


def test_transaction_rolls_back(database):
    repo = NotesRepository(database)
    before = repo.count()
    with pytest.raises(RuntimeError):
        with database.transaction() as connection:
            connection.execute(
                "INSERT INTO notes (title, body, category, tags, pinned, created_at, updated_at)"
                " VALUES ('x', '', 'General', '', 0, 'now', 'now')"
            )
            raise RuntimeError("boom")
    assert repo.count() == before


class TestNotes:
    def test_create_update_search_and_delete(self, database):
        repo = NotesRepository(database)
        note_id = repo.create("Groceries", "Milk and bread", "Personal", ["home", "food"])
        note = repo.get(note_id)
        assert note is not None
        assert note.display_title == "Groceries"
        assert note.tags == ["home", "food"]

        repo.update(note_id, body="Milk, bread, coffee", tags=["home"])
        note = repo.get(note_id)
        assert "coffee" in note.body
        assert note.tags == ["home"]

        assert [item.id for item in repo.list("coffee")] == [note_id]
        assert repo.list("nothing-matches") == []
        repo.delete(note_id)
        assert repo.get(note_id) is None

    def test_pin_sorting_and_categories(self, database):
        repo = NotesRepository(database)
        first = repo.create("First", "a", "Work")
        second = repo.create("Second", "b", "School")
        repo.update(second, pinned=True)
        ordered = repo.list()
        assert ordered[0].id == second
        assert set(repo.categories()) == {"Work", "School"}
        assert repo.toggle_pin(first) is True
        assert repo.list()[0].pinned

    def test_empty_title_has_placeholder(self, database):
        repo = NotesRepository(database)
        note_id = repo.create("", "body")
        assert repo.get(note_id).display_title == "Untitled note"


class TestTasks:
    def test_crud_and_filters(self, database):
        repo = TasksRepository(database)
        high = repo.create("Ship release", due_date="2026-01-01", priority=1)
        low = repo.create("Tidy desk", priority=3)
        repo.set_completed(low, True)

        assert [task.id for task in repo.list("active")] == [high]
        assert [task.id for task in repo.list("completed")] == [low]
        assert len(repo.list()) == 2
        assert repo.counts() == (2, 1)

        repo.update(high, title="Ship 1.0", priority=3)
        assert repo.get(high).title == "Ship 1.0"
        assert repo.get(high).priority == 3

        assert repo.clear_completed() == 1
        assert repo.counts() == (1, 0)

    def test_priority_is_clamped(self, database):
        repo = TasksRepository(database)
        task_id = repo.create("weird", priority=99)
        assert repo.get(task_id).priority == 3

    def test_search(self, database):
        repo = TasksRepository(database)
        repo.create("Write docs", notes="README and architecture")
        target = repo.create("Fix bug", notes="crash in options")
        assert [task.id for task in repo.list(search="crash")] == [target]


class TestWorkspaces:
    def test_default_workspace(self, database):
        repo = WorkspaceRepository(database)
        workspace = repo.ensure_default()
        assert workspace.id == "default"
        assert repo.ensure_default().id == workspace.id
        assert repo.count() == 1

    def test_create_update_delete(self, database):
        repo = WorkspaceRepository(database)
        repo.ensure_default()
        workspace_id = repo.create("Dev", "terminal", apps=[{"command": "app.terminal"}])
        workspace = repo.get(workspace_id)
        assert workspace.name == "Dev"
        assert workspace.apps == [{"command": "app.terminal"}]

        repo.update(workspace_id, name="Development", widgets=[{"type": "cpu"}], layout={"columns": 3})
        updated = repo.get(workspace_id)
        assert updated.name == "Development"
        assert updated.widgets == [{"type": "cpu"}]
        assert updated.layout == {"columns": 3}

        assert repo.delete(workspace_id) is True
        assert repo.delete("default") is False
        assert repo.get("default") is not None

    def test_corrupt_json_column_falls_back(self, database):
        repo = WorkspaceRepository(database)
        repo.ensure_default()
        workspace_id = repo.create("Broken")
        database.execute("UPDATE workspaces SET apps = 'not json' WHERE id = ?", (workspace_id,))
        assert repo.get(workspace_id).apps == []


class TestUsageEtc:
    def test_usage_recording_and_recent(self, database):
        usage = UsageRepository(database)
        usage.record_launch("app.files", "DeskFiles")
        usage.record_launch("app.files", "DeskFiles")
        usage.record_launch("app.notes", "DeskNotes")
        assert usage.launch_count("app.files") == 2
        recent = usage.recent(5)
        assert recent[0]["app_id"] == "app.notes"
        assert usage.most_used(1)[0]["app_id"] == "app.files"
        usage.clear()
        assert usage.recent() == []

    def test_ai_history(self, database):
        history = AIHistoryRepository(database)
        conversation = history.create_conversation("Test", "openai", "gpt-4o-mini")
        history.add_message(conversation, "user", "hello")
        history.add_message(conversation, "assistant", "hi")
        messages = history.messages(conversation)
        assert [message["role"] for message in messages] == ["user", "assistant"]
        assert history.messages(conversation, limit=1)[0]["content"] == "hi"
        history.rename_conversation(conversation, "Renamed")
        assert history.conversations()[0]["title"] == "Renamed"
        history.delete_conversation(conversation)
        assert history.messages(conversation) == []

    def test_plugin_state(self, database):
        state = PluginStateRepository(database)
        assert state.is_enabled("demo") is True
        state.set_enabled("demo", False)
        assert state.is_enabled("demo") is False
        state.save_settings("demo", {"city": "Ankara"})
        assert state.get_settings("demo") == {"city": "Ankara"}
        assert state.all_states() == {"demo": False}
