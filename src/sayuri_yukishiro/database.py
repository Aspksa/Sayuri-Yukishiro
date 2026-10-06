from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .paths import CORE_DATA_DIR, MODULE_DATA_DIR, ensure_runtime_dirs

CORE_DB_PATH = CORE_DATA_DIR / "sayuri_yukishiro.db"
_SAFE_MODULE_ID = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class CoreDatabase:
    def __init__(self, path: Path = CORE_DB_PATH) -> None:
        ensure_runtime_dirs()
        self.path = path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.session() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS modules (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'registered',
                    db_path TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS settings (
                    scope TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (scope, key)
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    module_id TEXT,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (module_id) REFERENCES modules(id)
                );

                CREATE INDEX IF NOT EXISTS idx_events_module_created
                    ON events(module_id, created_at);

                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    module_id TEXT,
                    job_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (module_id) REFERENCES modules(id)
                );

                CREATE INDEX IF NOT EXISTS idx_jobs_status
                    ON jobs(status, updated_at);

                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target TEXT,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(1, ?)",
                (utc_now(),),
            )
            now = utc_now()
            conn.execute(
                """
                INSERT INTO modules(id, name, version, status, db_path, created_at, updated_at)
                VALUES('core', 'Sayuri Yukishiro Core', '0.1.0', 'active', ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    version=excluded.version,
                    status=excluded.status,
                    db_path=excluded.db_path,
                    updated_at=excluded.updated_at
                """,
                (str(self.path), now, now),
            )

    def quick_check(self) -> str:
        with self.session() as conn:
            row = conn.execute("PRAGMA quick_check").fetchone()
            return str(row[0]) if row else "unknown"

    def list_modules(self) -> list[dict]:
        with self.session() as conn:
            rows = conn.execute(
                "SELECT id, name, version, status, db_path, updated_at FROM modules ORDER BY id"
            ).fetchall()
            return [dict(row) for row in rows]

    def register_module(self, module_id: str, name: str, version: str) -> Path:
        module_path = module_database_path(module_id)
        now = utc_now()
        with self.session() as conn:
            conn.execute(
                """
                INSERT INTO modules(id, name, version, status, db_path, created_at, updated_at)
                VALUES(?, ?, ?, 'registered', ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    version=excluded.version,
                    db_path=excluded.db_path,
                    updated_at=excluded.updated_at
                """,
                (module_id, name, version, str(module_path), now, now),
            )
        return module_path

    def append_event(self, event_type: str, payload: dict, module_id: str | None = None) -> None:
        with self.session() as conn:
            conn.execute(
                "INSERT INTO events(module_id, event_type, payload_json, created_at) VALUES(?, ?, ?, ?)",
                (module_id, event_type, json.dumps(payload, ensure_ascii=False), utc_now()),
            )

    def audit(self, actor: str, action: str, target: str | None = None, details: dict | None = None) -> None:
        with self.session() as conn:
            conn.execute(
                "INSERT INTO audit_log(actor, action, target, details_json, created_at) VALUES(?, ?, ?, ?, ?)",
                (
                    actor,
                    action,
                    target,
                    json.dumps(details or {}, ensure_ascii=False),
                    utc_now(),
                ),
            )


def module_database_path(module_id: str) -> Path:
    if not _SAFE_MODULE_ID.fullmatch(module_id):
        raise ValueError("Invalid module id. Use lowercase letters, digits, dot, dash or underscore.")
    ensure_runtime_dirs()
    return MODULE_DATA_DIR / f"{module_id}.db"


@contextmanager
def module_connection(module_id: str) -> Iterator[sqlite3.Connection]:
    path = module_database_path(module_id)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
