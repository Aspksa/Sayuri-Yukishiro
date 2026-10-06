"""Эталонный модуль Sayuri: безопасная read-only диагностика.

Модуль демонстрирует обязательный контракт:
манифест -> миграции собственной БД -> on_start -> способность -> health -> on_stop.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sayuri_yukishiro.modules.base import ModuleHealth, ModuleState, SayuriModule
from sayuri_yukishiro.modules.migrations import Migration

MODULE_VERSION = "0.1.0"


class SystemProbeModule(SayuriModule):
    def __init__(self, context) -> None:
        super().__init__(context)
        self._started_at: str | None = None

    def migrations(self) -> tuple[Migration, ...]:
        return (
            Migration(
                version=1,
                description="observations table",
                statements=(
                    """
                    CREATE TABLE IF NOT EXISTS observations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        kind TEXT NOT NULL,
                        detail TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """,
                ),
            ),
        )

    def on_start(self) -> None:
        self._started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._record("start", f"module {self.module_id} v{MODULE_VERSION} started")
        self.context.publish("module.system_probe.started", {"version": MODULE_VERSION})

    def on_stop(self) -> None:
        self._record("stop", f"module {self.module_id} stopped")

    def snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Read-only способность: не меняет внешнее состояние."""

        with self.context.database() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM observations").fetchone()
            observations = int(row["count"]) if row is not None else 0

        return {
            "module_id": self.module_id,
            "module_version": MODULE_VERSION,
            "started_at": self._started_at,
            "observations": observations,
            "requested_objective": payload.get("objective"),
            "log_level": self.context.config_get("logging.level", "INFO"),
        }

    def health(self) -> ModuleHealth:
        try:
            with self.context.database() as conn:
                conn.execute("SELECT 1 FROM observations LIMIT 1").fetchone()
        except Exception as exc:
            return ModuleHealth(
                module_id=self.module_id,
                state=ModuleState.RUNNING.value,
                healthy=False,
                detail=f"module_database_unavailable: {exc}",
            )
        return ModuleHealth(
            module_id=self.module_id,
            state=ModuleState.RUNNING.value,
            healthy=True,
            detail=f"started_at={self._started_at}",
        )

    def _record(self, kind: str, detail: str) -> None:
        with self.context.database() as conn:
            conn.execute(
                "INSERT INTO observations(kind, detail, created_at) VALUES(?, ?, ?)",
                (kind, detail, datetime.now(timezone.utc).isoformat(timespec="seconds")),
            )
