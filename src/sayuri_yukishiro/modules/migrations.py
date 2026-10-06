from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ..database import module_connection


class MigrationError(RuntimeError):
    """Миграции модуля нельзя применить безопасно."""


@dataclass(frozen=True)
class Migration:
    """Одна миграция БД модуля.

    version — строго возрастающий номер начиная с 1.
    statements — SQL-операторы, применяемые в одной транзакции.
    """

    version: int
    description: str
    statements: tuple[str, ...]


def validate_migrations(migrations: tuple[Migration, ...]) -> None:
    previous = 0
    for migration in migrations:
        if migration.version <= 0:
            raise MigrationError(f"Migration version must be positive: {migration.version}")
        if migration.version <= previous:
            raise MigrationError(
                "Migrations must be declared in strictly increasing order; "
                f"{migration.version} follows {previous}"
            )
        if not migration.statements:
            raise MigrationError(f"Migration {migration.version} has no statements")
        previous = migration.version


class ModuleMigrator:
    """Применяет миграции к БД модуля и ведёт реестр применённых версий."""

    REGISTRY_SQL = """
        CREATE TABLE IF NOT EXISTS module_migrations (
            version INTEGER PRIMARY KEY,
            description TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
    """

    def __init__(self, module_id: str) -> None:
        self.module_id = module_id

    def applied_versions(self) -> list[int]:
        with module_connection(self.module_id) as conn:
            conn.execute(self.REGISTRY_SQL)
            rows = conn.execute(
                "SELECT version FROM module_migrations ORDER BY version"
            ).fetchall()
            return [int(row[0]) for row in rows]

    def current_version(self) -> int:
        applied = self.applied_versions()
        return applied[-1] if applied else 0

    def apply(self, migrations: tuple[Migration, ...]) -> list[int]:
        validate_migrations(migrations)
        declared = {migration.version for migration in migrations}
        applied = set(self.applied_versions())

        unknown = sorted(applied - declared)
        if unknown:
            raise MigrationError(
                f"Module database is newer than the module code: applied {unknown} "
                "are not declared by this version"
            )

        newly_applied: list[int] = []
        for migration in migrations:
            if migration.version in applied:
                continue
            with module_connection(self.module_id) as conn:
                conn.execute(self.REGISTRY_SQL)
                for statement in migration.statements:
                    conn.execute(statement)
                conn.execute(
                    """
                    INSERT INTO module_migrations(version, description, applied_at)
                    VALUES(?, ?, ?)
                    """,
                    (
                        migration.version,
                        migration.description,
                        datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                    ),
                )
            newly_applied.append(migration.version)
        return newly_applied
