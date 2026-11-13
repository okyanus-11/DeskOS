"""SQLite persistence layer with migrations and safe access helpers.

All persistent application records live here.  The connection is opened with
``check_same_thread=False`` plus an internal lock because widgets and worker
threads (file search, AI requests) may touch the same database; every write goes
through an explicit transaction so a failed statement cannot leave half-written
state behind.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from deskos.core.paths import database_path

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1

MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS notes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT    NOT NULL DEFAULT '',
            body        TEXT    NOT NULL DEFAULT '',
            category    TEXT    NOT NULL DEFAULT 'General',
            tags        TEXT    NOT NULL DEFAULT '',
            pinned      INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT    NOT NULL,
            updated_at  TEXT    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_notes_updated ON notes(updated_at DESC);

        CREATE TABLE IF NOT EXISTS tasks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT    NOT NULL,
            notes       TEXT    NOT NULL DEFAULT '',
            due_date    TEXT,
            priority    INTEGER NOT NULL DEFAULT 2,
            completed   INTEGER NOT NULL DEFAULT 0,
            category    TEXT    NOT NULL DEFAULT 'General',
            created_at  TEXT    NOT NULL,
            updated_at  TEXT    NOT NULL,
            completed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_tasks_completed ON tasks(completed, due_date);

        CREATE TABLE IF NOT EXISTS workspaces (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            icon        TEXT NOT NULL DEFAULT 'workspace',
            apps        TEXT NOT NULL DEFAULT '[]',
            widgets     TEXT NOT NULL DEFAULT '[]',
            layout      TEXT NOT NULL DEFAULT '{}',
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS app_usage (
            app_id        TEXT PRIMARY KEY,
            name          TEXT NOT NULL,
            path          TEXT NOT NULL DEFAULT '',
            launch_count  INTEGER NOT NULL DEFAULT 1,
            last_launched TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS ai_conversations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL DEFAULT 'New conversation',
            provider    TEXT NOT NULL DEFAULT '',
            model       TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS ai_messages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL REFERENCES ai_conversations(id) ON DELETE CASCADE,
            role            TEXT NOT NULL,
            content         TEXT NOT NULL,
            created_at      TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ai_messages_conversation
            ON ai_messages(conversation_id, id);

        CREATE TABLE IF NOT EXISTS plugin_state (
            plugin_id TEXT PRIMARY KEY,
            enabled   INTEGER NOT NULL DEFAULT 1,
            settings  TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS launch_history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            app_id     TEXT NOT NULL,
            launched_at TEXT NOT NULL
        );
        """,
    ),
]


class Database:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else database_path()
        self._connection: sqlite3.Connection | None = None
        self._lock = threading.RLock()

    # ------------------------------------------------------------ lifecycle
    def connect(self) -> sqlite3.Connection:
        with self._lock:
            if self._connection is not None:
                return self._connection
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(
                str(self.path), timeout=15.0, check_same_thread=False
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
            self._connection = connection
            self._migrate()
            return connection

    @property
    def connection(self) -> sqlite3.Connection:
        return self.connect()

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                try:
                    self._connection.commit()
                finally:
                    self._connection.close()
                    self._connection = None
                    log.debug("database closed")

    def __enter__(self) -> Database:
        self.connect()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ----------------------------------------------------------- migrations
    def _migrate(self) -> None:
        assert self._connection is not None
        current = int(self._connection.execute("PRAGMA user_version").fetchone()[0])
        for version, script in MIGRATIONS:
            if version <= current:
                continue
            log.info("applying database migration %s", version)
            with self._connection:
                self._connection.executescript(script)
                self._connection.execute(f"PRAGMA user_version = {int(version)}")
            current = version

    # ----------------------------------------------------------- primitives
    def execute(self, sql: str, parameters: Sequence[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            connection = self.connect()
            cursor = connection.execute(sql, parameters)
            connection.commit()
            return cursor

    def executemany(self, sql: str, rows: Iterable[Sequence[Any]]) -> None:
        with self._lock:
            connection = self.connect()
            connection.executemany(sql, rows)
            connection.commit()

    def query(self, sql: str, parameters: Sequence[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self.connect().execute(sql, parameters).fetchall())

    def query_one(self, sql: str, parameters: Sequence[Any] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self.connect().execute(sql, parameters).fetchone()

    def scalar(self, sql: str, parameters: Sequence[Any] = (), default: Any = None) -> Any:
        row = self.query_one(sql, parameters)
        if row is None:
            return default
        value = row[0]
        return default if value is None else value

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Group several statements atomically; rolls back on any exception."""
        with self._lock:
            connection = self.connect()
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                log.exception("database transaction rolled back")
                raise

    # ------------------------------------------------------------- integrity
    def integrity_check(self) -> bool:
        try:
            result = self.scalar("PRAGMA integrity_check", default="ok")
        except sqlite3.DatabaseError:
            log.exception("integrity check failed")
            return False
        return str(result).lower() == "ok"

    def table_names(self) -> list[str]:
        rows = self.query("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        return [row["name"] for row in rows]

    def backup_to(self, destination: Path) -> Path:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            target = sqlite3.connect(str(destination))
            try:
                self.connect().backup(target)
            finally:
                target.close()
        return destination
