"""Repositories encapsulating every SQL statement in DeskOS.

Keeping SQL here means the UI never builds queries and tests can exercise the
persistence layer directly against a temporary database.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from deskos.core.database import Database

log = logging.getLogger(__name__)


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def _split_tags(value: str) -> list[str]:
    return [tag.strip() for tag in value.split(",") if tag.strip()]


# --------------------------------------------------------------------- notes
@dataclass
class Note:
    id: int
    title: str
    body: str
    category: str
    tags: list[str] = field(default_factory=list)
    pinned: bool = False
    created_at: str = ""
    updated_at: str = ""

    @property
    def display_title(self) -> str:
        return self.title.strip() or "Untitled note"

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Note:
        return cls(
            id=int(row["id"]),
            title=row["title"],
            body=row["body"],
            category=row["category"],
            tags=_split_tags(row["tags"]),
            pinned=bool(row["pinned"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class NotesRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    def create(
        self,
        title: str = "",
        body: str = "",
        category: str = "General",
        tags: list[str] | None = None,
    ) -> int:
        stamp = now_iso()
        cursor = self.db.execute(
            "INSERT INTO notes (title, body, category, tags, pinned, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, 0, ?, ?)",
            (title, body, category, ",".join(tags or []), stamp, stamp),
        )
        return int(cursor.lastrowid or 0)

    def update(self, note_id: int, **fields: Any) -> None:
        allowed = {"title", "body", "category", "tags", "pinned"}
        payload = {key: value for key, value in fields.items() if key in allowed}
        if not payload:
            return
        if "tags" in payload and isinstance(payload["tags"], (list, tuple)):
            payload["tags"] = ",".join(str(tag) for tag in payload["tags"])
        if "pinned" in payload:
            payload["pinned"] = 1 if payload["pinned"] else 0
        payload["updated_at"] = now_iso()
        columns = ", ".join(f"{key} = ?" for key in payload)
        params = list(payload.values()) + [note_id]
        self.db.execute(f"UPDATE notes SET {columns} WHERE id = ?", params)

    def delete(self, note_id: int) -> None:
        self.db.execute("DELETE FROM notes WHERE id = ?", (note_id,))

    def get(self, note_id: int) -> Note | None:
        row = self.db.query_one("SELECT * FROM notes WHERE id = ?", (note_id,))
        return Note.from_row(row) if row else None

    def list(self, search: str = "", category: str | None = None) -> list[Note]:
        clauses: list[str] = []
        params: list[Any] = []
        if search.strip():
            clauses.append("(title LIKE ? OR body LIKE ? OR tags LIKE ?)")
            like = f"%{search.strip()}%"
            params.extend([like, like, like])
        if category and category != "All":
            clauses.append("category = ?")
            params.append(category)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.db.query(
            f"SELECT * FROM notes {where} ORDER BY pinned DESC, updated_at DESC", params
        )
        return [Note.from_row(row) for row in rows]

    def categories(self) -> list[str]:
        rows = self.db.query("SELECT DISTINCT category FROM notes ORDER BY category")
        return [row["category"] for row in rows if row["category"]]

    def count(self) -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM notes", default=0))

    def toggle_pin(self, note_id: int) -> bool:
        note = self.get(note_id)
        if note is None:
            return False
        self.update(note_id, pinned=not note.pinned)
        return not note.pinned


# --------------------------------------------------------------------- tasks
PRIORITY_LABELS = {1: "High", 2: "Normal", 3: "Low"}


@dataclass
class Task:
    id: int
    title: str
    notes: str = ""
    due_date: str | None = None
    priority: int = 2
    completed: bool = False
    category: str = "General"
    created_at: str = ""
    updated_at: str = ""
    completed_at: str | None = None

    @property
    def priority_label(self) -> str:
        return PRIORITY_LABELS.get(self.priority, "Normal")

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Task:
        return cls(
            id=int(row["id"]),
            title=row["title"],
            notes=row["notes"],
            due_date=row["due_date"],
            priority=int(row["priority"]),
            completed=bool(row["completed"]),
            category=row["category"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
        )


class TasksRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    def create(
        self,
        title: str,
        notes: str = "",
        due_date: str | None = None,
        priority: int = 2,
        category: str = "General",
    ) -> int:
        stamp = now_iso()
        cursor = self.db.execute(
            "INSERT INTO tasks (title, notes, due_date, priority, completed, category,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, 0, ?, ?, ?)",
            (title, notes, due_date, max(1, min(3, int(priority))), category, stamp, stamp),
        )
        return int(cursor.lastrowid or 0)

    def update(self, task_id: int, **fields: Any) -> None:
        allowed = {"title", "notes", "due_date", "priority", "completed", "category"}
        payload = {key: value for key, value in fields.items() if key in allowed}
        if not payload:
            return
        if "completed" in payload:
            payload["completed"] = 1 if payload["completed"] else 0
            payload["completed_at"] = now_iso() if payload["completed"] else None
        if "priority" in payload:
            payload["priority"] = max(1, min(3, int(payload["priority"])))
        payload["updated_at"] = now_iso()
        columns = ", ".join(f"{key} = ?" for key in payload)
        params = list(payload.values()) + [task_id]
        self.db.execute(f"UPDATE tasks SET {columns} WHERE id = ?", params)

    def set_completed(self, task_id: int, completed: bool) -> None:
        self.update(task_id, completed=completed)

    def delete(self, task_id: int) -> None:
        self.db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))

    def get(self, task_id: int) -> Task | None:
        row = self.db.query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
        return Task.from_row(row) if row else None

    def list(self, view: str = "all", search: str = "") -> list[Task]:
        clauses: list[str] = []
        params: list[Any] = []
        if view == "active":
            clauses.append("completed = 0")
        elif view == "completed":
            clauses.append("completed = 1")
        if search.strip():
            clauses.append("(title LIKE ? OR notes LIKE ?)")
            like = f"%{search.strip()}%"
            params.extend([like, like])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.db.query(
            "SELECT * FROM tasks "
            f"{where} ORDER BY completed ASC, priority ASC,"
            " COALESCE(due_date, '9999-12-31') ASC, created_at DESC",
            params,
        )
        return [Task.from_row(row) for row in rows]

    def counts(self) -> tuple[int, int]:
        total = int(self.db.scalar("SELECT COUNT(*) FROM tasks", default=0))
        done = int(self.db.scalar("SELECT COUNT(*) FROM tasks WHERE completed = 1", default=0))
        return total, done

    def clear_completed(self) -> int:
        cursor = self.db.execute("DELETE FROM tasks WHERE completed = 1")
        return cursor.rowcount


# ---------------------------------------------------------------- workspaces
@dataclass
class Workspace:
    id: str
    name: str
    icon: str = "workspace"
    apps: list[dict[str, Any]] = field(default_factory=list)
    widgets: list[dict[str, Any]] = field(default_factory=list)
    layout: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Workspace:
        def decode(value: str, fallback: Any) -> Any:
            try:
                parsed = json.loads(value)
            except (TypeError, json.JSONDecodeError):
                return fallback
            return parsed if isinstance(parsed, type(fallback)) else fallback

        return cls(
            id=row["id"],
            name=row["name"],
            icon=row["icon"],
            apps=decode(row["apps"], []),
            widgets=decode(row["widgets"], []),
            layout=decode(row["layout"], {}),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class WorkspaceRepository:
    DEFAULT_ID = "default"

    def __init__(self, database: Database) -> None:
        self.db = database

    def ensure_default(self) -> Workspace:
        existing = self.get(self.DEFAULT_ID)
        if existing:
            return existing
        self.create(
            name="Default",
            icon="workspace",
            workspace_id=self.DEFAULT_ID,
            apps=[
                {"command": "app.files", "label": "Files"},
                {"command": "app.terminal", "label": "Terminal"},
                {"command": "app.monitor", "label": "Monitor"},
            ],
            widgets=[],
        )
        workspace = self.get(self.DEFAULT_ID)
        assert workspace is not None
        return workspace

    def create(
        self,
        name: str,
        icon: str = "workspace",
        workspace_id: str | None = None,
        apps: list[dict[str, Any]] | None = None,
        widgets: list[dict[str, Any]] | None = None,
        layout: dict[str, Any] | None = None,
    ) -> str:
        identifier = workspace_id or uuid.uuid4().hex[:12]
        stamp = now_iso()
        self.db.execute(
            "INSERT INTO workspaces (id, name, icon, apps, widgets, layout, created_at,"
            " updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                identifier,
                name.strip() or "Workspace",
                icon,
                json.dumps(apps or []),
                json.dumps(widgets or []),
                json.dumps(layout or {}),
                stamp,
                stamp,
            ),
        )
        return identifier

    def update(self, workspace_id: str, **fields: Any) -> None:
        allowed = {"name", "icon", "apps", "widgets", "layout"}
        payload: dict[str, Any] = {}
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key in {"apps", "widgets", "layout"}:
                payload[key] = json.dumps(value)
            else:
                payload[key] = value
        if not payload:
            return
        payload["updated_at"] = now_iso()
        columns = ", ".join(f"{key} = ?" for key in payload)
        self.db.execute(
            f"UPDATE workspaces SET {columns} WHERE id = ?", [*payload.values(), workspace_id]
        )

    def delete(self, workspace_id: str) -> bool:
        if workspace_id == self.DEFAULT_ID:
            log.warning("refusing to delete the default workspace")
            return False
        self.db.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
        return True

    def get(self, workspace_id: str) -> Workspace | None:
        row = self.db.query_one("SELECT * FROM workspaces WHERE id = ?", (workspace_id,))
        return Workspace.from_row(row) if row else None

    def list(self) -> list[Workspace]:
        rows = self.db.query(
            "SELECT * FROM workspaces ORDER BY (id = 'default') DESC, name ASC"
        )
        return [Workspace.from_row(row) for row in rows]

    def count(self) -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM workspaces", default=0))


# -------------------------------------------------------------------- usage
class UsageRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    def record_launch(self, app_id: str, name: str, path: str = "") -> None:
        stamp = now_iso()
        self.db.execute(
            "INSERT INTO app_usage (app_id, name, path, launch_count, last_launched)"
            " VALUES (?, ?, ?, 1, ?)"
            " ON CONFLICT(app_id) DO UPDATE SET"
            " launch_count = app_usage.launch_count + 1,"
            " last_launched = excluded.last_launched,"
            " name = excluded.name,"
            " path = CASE WHEN excluded.path != '' THEN excluded.path ELSE app_usage.path END",
            (app_id, name, path, stamp),
        )
        self.db.execute(
            "INSERT INTO launch_history (app_id, launched_at) VALUES (?, ?)", (app_id, stamp)
        )

    def recent(self, limit: int = 8) -> list[dict[str, Any]]:
        rows = self.db.query(
            "SELECT app_id, name, path, launch_count, last_launched FROM app_usage"
            " ORDER BY last_launched DESC, rowid DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in rows]

    def most_used(self, limit: int = 8) -> list[dict[str, Any]]:
        rows = self.db.query(
            "SELECT app_id, name, path, launch_count, last_launched FROM app_usage"
            " ORDER BY launch_count DESC, last_launched DESC, rowid DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in rows]

    def launch_count(self, app_id: str) -> int:
        return int(
            self.db.scalar("SELECT launch_count FROM app_usage WHERE app_id = ?", (app_id,), 0)
            or 0
        )

    def clear(self) -> None:
        self.db.execute("DELETE FROM app_usage")
        self.db.execute("DELETE FROM launch_history")


# --------------------------------------------------------------- AI history
class AIHistoryRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    def create_conversation(
        self, title: str = "New conversation", provider: str = "", model: str = ""
    ) -> int:
        stamp = now_iso()
        cursor = self.db.execute(
            "INSERT INTO ai_conversations (title, provider, model, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (title, provider, model, stamp, stamp),
        )
        return int(cursor.lastrowid or 0)

    def add_message(self, conversation_id: int, role: str, content: str) -> int:
        stamp = now_iso()
        cursor = self.db.execute(
            "INSERT INTO ai_messages (conversation_id, role, content, created_at)"
            " VALUES (?, ?, ?, ?)",
            (conversation_id, role, content, stamp),
        )
        self.db.execute(
            "UPDATE ai_conversations SET updated_at = ? WHERE id = ?",
            (stamp, conversation_id),
        )
        return int(cursor.lastrowid or 0)

    def messages(self, conversation_id: int, limit: int | None = None) -> list[dict[str, Any]]:
        if limit:
            rows = self.db.query(
                "SELECT * FROM (SELECT * FROM ai_messages WHERE conversation_id = ?"
                " ORDER BY id DESC LIMIT ?) ORDER BY id ASC",
                (conversation_id, limit),
            )
        else:
            rows = self.db.query(
                "SELECT * FROM ai_messages WHERE conversation_id = ? ORDER BY id ASC",
                (conversation_id,),
            )
        return [dict(row) for row in rows]

    def conversations(self, limit: int = 30) -> list[dict[str, Any]]:
        rows = self.db.query(
            "SELECT c.*, (SELECT COUNT(*) FROM ai_messages m WHERE m.conversation_id = c.id)"
            " AS message_count FROM ai_conversations c ORDER BY c.updated_at DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in rows]

    def rename_conversation(self, conversation_id: int, title: str) -> None:
        self.db.execute(
            "UPDATE ai_conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title, now_iso(), conversation_id),
        )

    def delete_conversation(self, conversation_id: int) -> None:
        self.db.execute("DELETE FROM ai_messages WHERE conversation_id = ?", (conversation_id,))
        self.db.execute("DELETE FROM ai_conversations WHERE id = ?", (conversation_id,))


# ------------------------------------------------------------ plugin state
class PluginStateRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    def is_enabled(self, plugin_id: str, default: bool = True) -> bool:
        row = self.db.query_one("SELECT enabled FROM plugin_state WHERE plugin_id = ?", (plugin_id,))
        return default if row is None else bool(row["enabled"])

    def set_enabled(self, plugin_id: str, enabled: bool) -> None:
        self.db.execute(
            "INSERT INTO plugin_state (plugin_id, enabled) VALUES (?, ?)"
            " ON CONFLICT(plugin_id) DO UPDATE SET enabled = excluded.enabled",
            (plugin_id, 1 if enabled else 0),
        )

    def get_settings(self, plugin_id: str) -> dict[str, Any]:
        row = self.db.query_one("SELECT settings FROM plugin_state WHERE plugin_id = ?", (plugin_id,))
        if row is None:
            return {}
        try:
            parsed = json.loads(row["settings"])
        except (TypeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def save_settings(self, plugin_id: str, settings: dict[str, Any]) -> None:
        self.db.execute(
            "INSERT INTO plugin_state (plugin_id, settings) VALUES (?, ?)"
            " ON CONFLICT(plugin_id) DO UPDATE SET settings = excluded.settings",
            (plugin_id, json.dumps(settings)),
        )

    def all_states(self) -> dict[str, bool]:
        rows = self.db.query("SELECT plugin_id, enabled FROM plugin_state")
        return {row["plugin_id"]: bool(row["enabled"]) for row in rows}
