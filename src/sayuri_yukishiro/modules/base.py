from __future__ import annotations

from abc import ABC
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from enum import Enum
from sqlite3 import Connection
from typing import Any, Callable, Iterator

from ..core.api import CoreAPI
from ..database import module_connection
from .manifest import ModuleManifest
from .migrations import Migration


class ModuleState(str, Enum):
    DISCOVERED = "discovered"
    DISABLED = "disabled"
    REJECTED = "rejected"
    BLOCKED = "blocked"
    LOADED = "loaded"
    MIGRATED = "migrated"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True)
class ModuleHealth:
    module_id: str
    state: str
    healthy: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ModuleContext:
    """Всё, что модуль получает от платформы.

    Модуль не обращается к системному ядру напрямую: доступны только
    ограниченный CoreAPI, собственная БД и выданные разрешения.
    """

    def __init__(
        self,
        manifest: ModuleManifest,
        core_api: CoreAPI,
        granted_permissions: tuple[str, ...] = (),
    ) -> None:
        self.manifest = manifest
        self.core_api = core_api
        self.granted_permissions = tuple(granted_permissions)

    @property
    def module_id(self) -> str:
        return self.manifest.id

    def has_permission(self, permission: str) -> bool:
        return permission in self.granted_permissions

    def require_permission(self, permission: str) -> None:
        if not self.has_permission(permission):
            raise PermissionError(
                f"Module {self.module_id!r} has no granted permission {permission!r}"
            )

    @contextmanager
    def database(self) -> Iterator[Connection]:
        self.require_permission("module.database")
        with module_connection(self.manifest.id) as conn:
            yield conn

    def publish(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        self.require_permission("core.events.publish")
        self.core_api.publish(event_type, payload, source=f"module:{self.module_id}")

    def config_get(self, path: str, default: Any = None) -> Any:
        self.require_permission("core.config.read")
        return self.core_api.config_get(path, default)

    def submit_job(self, name: str, func: Callable[..., Any], *args: Any, **kwargs: Any) -> str:
        self.require_permission("core.jobs.submit")
        return self.core_api.submit_job(f"{self.module_id}:{name}", func, *args, **kwargs)

    def save_checkpoint(
        self,
        task_id: str,
        payload: dict[str, Any],
        next_action: str,
    ) -> None:
        self.require_permission("core.checkpoints.write")
        self.core_api.save_checkpoint(f"module:{self.module_id}:{task_id}", payload, next_action)


class SayuriModule(ABC):
    """Базовый контракт модуля Sayuri.

    Жизненный цикл, которым управляет Module Runtime:
    __init__ -> migrations() -> on_start() -> health() -> on_stop().
    Модуль не управляет собственным запуском и не трогает чужие БД.
    """

    def __init__(self, context: ModuleContext) -> None:
        self.context = context

    @property
    def manifest(self) -> ModuleManifest:
        return self.context.manifest

    @property
    def module_id(self) -> str:
        return self.context.module_id

    def migrations(self) -> tuple[Migration, ...]:
        return ()

    def on_start(self) -> None:
        return

    def on_stop(self) -> None:
        return

    def health(self) -> ModuleHealth:
        return ModuleHealth(
            module_id=self.module_id,
            state=ModuleState.RUNNING.value,
            healthy=True,
        )
