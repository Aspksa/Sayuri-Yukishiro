from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .paths import CORE_DATA_DIR, MODULE_DATA_DIR, ensure_runtime_dirs
from .storage_policy import sqlite_journal_mode
from .version import SYSTEM_CORE_VERSION

CORE_DB_PATH = CORE_DATA_DIR / "sayuri_yukishiro.db"
_SAFE_MODULE_ID = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=repr)


class CoreDatabase:
    def __init__(self, path: Path = CORE_DB_PATH) -> None:
        ensure_runtime_dirs()
        self.path = path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        mode = sqlite_journal_mode(self.path)
        conn.execute(f"PRAGMA journal_mode = {mode}")
        conn.execute("PRAGMA synchronous = FULL" if mode == "DELETE" else "PRAGMA synchronous = NORMAL")
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
            self._apply_system_core_schema(conn)
            self._apply_cognitive_schema(conn)
            self._apply_module_runtime_schema(conn)

            now = utc_now()
            conn.execute(
                """
                INSERT INTO modules(id, name, version, status, db_path, created_at, updated_at)
                VALUES('core', 'Sayuri Yukishiro Core', ?, 'active', ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    version=excluded.version,
                    status=excluded.status,
                    db_path=excluded.db_path,
                    updated_at=excluded.updated_at
                """,
                (SYSTEM_CORE_VERSION, str(self.path), now, now),
            )

    def _apply_system_core_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS core_services (
                name TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                detail TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS core_jobs (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_core_jobs_status
                ON core_jobs(status, updated_at);

            CREATE TABLE IF NOT EXISTS checkpoints (
                task_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                next_action TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_checkpoints_status
                ON checkpoints(status, updated_at);
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(2, ?)",
            (utc_now(),),
        )


    def _apply_cognitive_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS cognitive_sessions (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                intent TEXT NOT NULL,
                confidence REAL NOT NULL,
                state_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_cognitive_sessions_status
                ON cognitive_sessions(status, updated_at);

            CREATE TABLE IF NOT EXISTS cognitive_receipts (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                step_id TEXT NOT NULL,
                capability TEXT NOT NULL,
                status TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES cognitive_sessions(id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_cognitive_receipts_session
                ON cognitive_receipts(session_id, created_at);
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(3, ?)",
            (utc_now(),),
        )

    def _apply_module_runtime_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS module_states (
                module_id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                version TEXT NOT NULL,
                detail TEXT NOT NULL,
                permissions_json TEXT NOT NULL,
                capabilities_json TEXT NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_module_states_state
                ON module_states(state, updated_at);
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(4, ?)",
            (utc_now(),),
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
                (module_id, event_type, _json_text(payload), utc_now()),
            )

    def audit(
        self,
        actor: str,
        action: str,
        target: str | None = None,
        details: dict | None = None,
    ) -> None:
        with self.session() as conn:
            conn.execute(
                "INSERT INTO audit_log(actor, action, target, details_json, created_at) VALUES(?, ?, ?, ?, ?)",
                (actor, action, target, _json_text(details or {}), utc_now()),
            )

    def upsert_service_state(self, name: str, state: str, detail: str = "") -> None:
        with self.session() as conn:
            conn.execute(
                """
                INSERT INTO core_services(name, state, detail, updated_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    state=excluded.state,
                    detail=excluded.detail,
                    updated_at=excluded.updated_at
                """,
                (name, state, detail, utc_now()),
            )

    def list_service_states(self) -> list[dict[str, Any]]:
        with self.session() as conn:
            rows = conn.execute(
                "SELECT name, state, detail, updated_at FROM core_services ORDER BY name"
            ).fetchall()
            return [dict(row) for row in rows]

    def create_core_job(self, job_id: str, name: str, status: str) -> None:
        now = utc_now()
        with self.session() as conn:
            conn.execute(
                """
                INSERT INTO core_jobs(id, name, status, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?)
                """,
                (job_id, name, status, now, now),
            )

    def update_core_job(
        self,
        job_id: str,
        status: str,
        *,
        result: Any = None,
        error: str | None = None,
    ) -> None:
        with self.session() as conn:
            conn.execute(
                """
                UPDATE core_jobs
                SET status=?, result_json=?, error=?, updated_at=?
                WHERE id=?
                """,
                (status, _json_text(result) if result is not None else None, error, utc_now(), job_id),
            )

    def mark_unfinished_jobs_interrupted(self) -> int:
        with self.session() as conn:
            cursor = conn.execute(
                """
                UPDATE core_jobs
                SET status='interrupted', updated_at=?
                WHERE status IN ('pending', 'running')
                """,
                (utc_now(),),
            )
            return int(cursor.rowcount)

    def save_checkpoint(
        self,
        task_id: str,
        status: str,
        payload: dict[str, Any],
        next_action: str,
    ) -> None:
        now = utc_now()
        with self.session() as conn:
            conn.execute(
                """
                INSERT INTO checkpoints(
                    task_id, status, payload_json, next_action, created_at, updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    status=excluded.status,
                    payload_json=excluded.payload_json,
                    next_action=excluded.next_action,
                    updated_at=excluded.updated_at
                """,
                (task_id, status, _json_text(payload), next_action, now, now),
            )

    def get_checkpoint(self, task_id: str) -> dict[str, Any] | None:
        with self.session() as conn:
            row = conn.execute(
                """
                SELECT task_id, status, payload_json, next_action, created_at, updated_at
                FROM checkpoints
                WHERE task_id=?
                """,
                (task_id,),
            ).fetchone()
            if row is None:
                return None
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json"))
            return item

    def list_recoverable_checkpoints(self) -> list[dict[str, Any]]:
        with self.session() as conn:
            rows = conn.execute(
                """
                SELECT task_id, status, payload_json, next_action, created_at, updated_at
                FROM checkpoints
                WHERE status != 'completed'
                ORDER BY updated_at DESC
                """
            ).fetchall()
            result: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                item["payload"] = json.loads(item.pop("payload_json"))
                result.append(item)
            return result



    def save_cognitive_session(self, state: dict[str, Any]) -> None:
        now = utc_now()
        session_id = str(state["id"])
        intent = str(dict(state.get("intent", {})).get("kind", "unknown"))
        status = str(state.get("status", "in_progress"))
        confidence = float(state.get("confidence", 0.0))
        with self.session() as conn:
            conn.execute(
                """
                INSERT INTO cognitive_sessions(
                    id, status, intent, confidence, state_json, created_at, updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    intent=excluded.intent,
                    confidence=excluded.confidence,
                    state_json=excluded.state_json,
                    updated_at=excluded.updated_at
                """,
                (
                    session_id,
                    status,
                    intent,
                    confidence,
                    _json_text(state),
                    now,
                    now,
                ),
            )

    def get_cognitive_session(self, session_id: str) -> dict[str, Any] | None:
        with self.session() as conn:
            row = conn.execute(
                "SELECT state_json FROM cognitive_sessions WHERE id=?",
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            return dict(json.loads(str(row["state_json"])))

    def list_cognitive_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        safe_limit = max(1, min(200, int(limit)))
        with self.session() as conn:
            rows = conn.execute(
                """
                SELECT id, status, intent, confidence, created_at, updated_at
                FROM cognitive_sessions
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def count_cognitive_sessions(self) -> int:
        with self.session() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM cognitive_sessions"
            ).fetchone()
            return int(row["count"]) if row is not None else 0

    def append_cognitive_receipt(self, receipt: dict[str, Any]) -> None:
        with self.session() as conn:
            conn.execute(
                """
                INSERT INTO cognitive_receipts(
                    id, session_id, step_id, capability, status,
                    evidence_json, created_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(receipt["id"]),
                    str(receipt["session_id"]),
                    str(receipt["step_id"]),
                    str(receipt["capability"]),
                    str(receipt["status"]),
                    _json_text(receipt.get("evidence", {})),
                    str(receipt["created_at"]),
                ),
            )

    def list_cognitive_receipts(self, session_id: str) -> list[dict[str, Any]]:
        with self.session() as conn:
            rows = conn.execute(
                """
                SELECT id, session_id, step_id, capability, status,
                       evidence_json, created_at
                FROM cognitive_receipts
                WHERE session_id=?
                ORDER BY rowid
                """,
                (session_id,),
            ).fetchall()
            result: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                item["evidence"] = json.loads(item.pop("evidence_json"))
                result.append(item)
            return result


    def upsert_module_state(
        self,
        module_id: str,
        state: str,
        version: str,
        *,
        detail: str = "",
        permissions: list[str] | None = None,
        capabilities: list[str] | None = None,
        schema_version: int = 0,
    ) -> None:
        with self.session() as conn:
            conn.execute(
                """
                INSERT INTO module_states(
                    module_id, state, version, detail,
                    permissions_json, capabilities_json, schema_version, updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(module_id) DO UPDATE SET
                    state=excluded.state,
                    version=excluded.version,
                    detail=excluded.detail,
                    permissions_json=excluded.permissions_json,
                    capabilities_json=excluded.capabilities_json,
                    schema_version=excluded.schema_version,
                    updated_at=excluded.updated_at
                """,
                (
                    module_id,
                    state,
                    version,
                    detail,
                    _json_text(list(permissions or [])),
                    _json_text(list(capabilities or [])),
                    int(schema_version),
                    utc_now(),
                ),
            )

    def list_module_states(self) -> list[dict[str, Any]]:
        with self.session() as conn:
            rows = conn.execute(
                """
                SELECT module_id, state, version, detail,
                       permissions_json, capabilities_json, schema_version, updated_at
                FROM module_states
                ORDER BY module_id
                """
            ).fetchall()
            result: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                item["permissions"] = json.loads(item.pop("permissions_json"))
                item["capabilities"] = json.loads(item.pop("capabilities_json"))
                result.append(item)
            return result

    def set_module_status(self, module_id: str, status: str) -> None:
        with self.session() as conn:
            conn.execute(
                "UPDATE modules SET status=?, updated_at=? WHERE id=?",
                (status, utc_now(), module_id),
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
    mode = sqlite_journal_mode(path)
    conn.execute(f"PRAGMA journal_mode = {mode}")
    conn.execute("PRAGMA synchronous = FULL" if mode == "DELETE" else "PRAGMA synchronous = NORMAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
