from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Any

from ..cognitive.capabilities import Capability, CapabilityRegistry
from ..cognitive.types import RiskLevel
from ..core.api import CoreAPI
from ..database import CoreDatabase
from ..paths import module_source_dirs
from ..version import MODULE_RUNTIME_VERSION, SYSTEM_CORE_VERSION
from .base import ModuleContext, ModuleHealth, ModuleState, SayuriModule
from .dependencies import DependencyResolver, ResolutionResult
from .discovery import DiscoveryResult, discover_modules
from .loader import ModuleLoadError, instantiate_module, unload_module
from .manifest import ModuleManifest
from .migrations import MigrationError, ModuleMigrator
from .permissions import PermissionBroker, PermissionDecision

_RISK_BY_NAME = {
    "read_only": RiskLevel.READ_ONLY,
    "mutation": RiskLevel.MUTATION,
    "external": RiskLevel.EXTERNAL,
}


@dataclass
class ModuleRecord:
    """Полное состояние одного модуля в рантайме."""

    manifest: ModuleManifest
    state: ModuleState
    detail: str = ""
    permissions: tuple[str, ...] = ()
    denied_permissions: tuple[str, ...] = ()
    capabilities: list[str] = field(default_factory=list)
    applied_migrations: list[int] = field(default_factory=list)
    schema_version: int = 0
    instance: SayuriModule | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.manifest.id,
            "name": self.manifest.name,
            "version": self.manifest.version,
            "state": self.state.value,
            "detail": self.detail,
            "permissions": list(self.permissions),
            "denied_permissions": list(self.denied_permissions),
            "capabilities": list(self.capabilities),
            "applied_migrations": list(self.applied_migrations),
            "schema_version": self.schema_version,
            "source": None if self.manifest.source is None else str(self.manifest.source),
        }


class ModuleRuntime:
    """Слой модулей между системным и когнитивным ядром.

    Цикл одного модуля: discovery -> permissions -> load -> migrate -> start
    -> health -> stop. Способности запущенного модуля регистрируются в
    когнитивном CapabilityRegistry и снимаются при остановке.
    """

    VERSION = MODULE_RUNTIME_VERSION

    def __init__(
        self,
        core_api: CoreAPI,
        db: CoreDatabase,
        *,
        capabilities: CapabilityRegistry | None = None,
        module_dirs: list[Path] | None = None,
        core_version: str = SYSTEM_CORE_VERSION,
        strict_startup: bool = False,
    ) -> None:
        self.core_api = core_api
        self.db = db
        self.capabilities = capabilities
        self.module_dirs = list(module_dirs) if module_dirs is not None else module_source_dirs()
        self.core_version = core_version
        self.strict_startup = strict_startup
        self.permissions = PermissionBroker()
        self.resolver = DependencyResolver()
        self._records: dict[str, ModuleRecord] = {}
        self._started: list[str] = []
        self._discovery = DiscoveryResult()
        self._resolution = ResolutionResult()
        self._running = False
        self._lock = RLock()

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._records = {}
            self._started = []

        self._discovery = discover_modules(self.module_dirs)
        self._resolution = self.resolver.resolve(
            self._discovery.manifests,
            core_version=self.core_version,
        )

        catalog = self._discovery.by_id()
        for module_id in self._resolution.disabled:
            self._record(catalog[module_id], ModuleState.DISABLED, "disabled by manifest")
        for issue in self._resolution.issues:
            self._record(
                catalog[issue.module_id],
                ModuleState.REJECTED,
                f"{issue.reason}: {issue.detail}",
            )

        with self._lock:
            self._running = True

        skipped: set[str] = set()
        for module_id in self._resolution.order:
            manifest = catalog[module_id]
            blocking = [
                dependency.module_id
                for dependency in manifest.dependencies
                if dependency.module_id in skipped
            ]
            if blocking:
                self._record(
                    manifest,
                    ModuleState.BLOCKED,
                    f"dependency_failed: {', '.join(sorted(blocking))}",
                )
                skipped.add(module_id)
                continue

            try:
                self._start_module(manifest)
            except Exception as exc:
                self._handle_start_failure(manifest, exc)
                if self.strict_startup:
                    self.stop()
                    raise
                skipped.add(module_id)

        self._publish(
            "modules.runtime.started",
            {
                "version": self.VERSION,
                "started": list(self._started),
                "rejected": len(self._resolution.issues),
                "discovery_rejected": len(self._discovery.rejected),
            },
        )

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            order = list(reversed(self._started))
            self._started = []
            self._running = False

        for module_id in order:
            record = self._records.get(module_id)
            if record is None or record.instance is None:
                continue
            self._release_capabilities(record)
            try:
                record.instance.on_stop()
                record.state = ModuleState.STOPPED
                record.detail = ""
            except Exception as exc:
                record.state = ModuleState.FAILED
                record.detail = f"stop_failed: {exc}"
            finally:
                record.instance = None
                unload_module(record.manifest)
                self._persist(record)

        self._publish("modules.runtime.stopped", {"version": self.VERSION})

    def get(self, module_id: str) -> ModuleRecord | None:
        return self._records.get(module_id)

    def instance(self, module_id: str) -> SayuriModule | None:
        record = self._records.get(module_id)
        return None if record is None else record.instance

    def health(self) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for module_id in sorted(self._records):
            record = self._records[module_id]
            items.append(self._module_health(record).to_dict())

        running = [item for item in items if item["state"] == ModuleState.RUNNING.value]
        failed = [item for item in items if item["state"] == ModuleState.FAILED.value]
        unhealthy = [item for item in running if not item["healthy"]]
        blocked = [
            item
            for item in items
            if item["state"] in (ModuleState.BLOCKED.value, ModuleState.REJECTED.value)
        ]

        if failed:
            overall = "failed"
        elif unhealthy or blocked:
            overall = "degraded"
        else:
            overall = "healthy"

        return {
            "overall": overall,
            "module_count": len(items),
            "running_count": len(running),
            "healthy_count": len(running) - len(unhealthy),
            "failed_count": len(failed),
            "blocked_count": len(blocked),
            "modules": items,
        }

    def status(self) -> dict[str, Any]:
        return {
            "version": self.VERSION,
            "running": self.running,
            "core_version": self.core_version,
            "strict_startup": self.strict_startup,
            "module_dirs": [str(path) for path in self.module_dirs],
            "discovery": self._discovery.to_dict(),
            "resolution": self._resolution.to_dict(),
            "modules": [self._records[key].to_dict() for key in sorted(self._records)],
            "health": self.health(),
            "capability_boundary": {
                "read_only": "executable_after_permission_grant",
                "mutation": "requires_action_broker",
                "external": "requires_action_broker",
            },
        }

    def _start_module(self, manifest: ModuleManifest) -> None:
        decision = self.permissions.evaluate(manifest)
        if not decision.allowed:
            self._record(
                manifest,
                ModuleState.BLOCKED,
                f"permission_denied: {decision.denial_detail()}",
                permissions=decision,
            )
            self._publish(
                "modules.module.blocked",
                {
                    "module_id": manifest.id,
                    "denied_permissions": list(decision.denied),
                },
            )
            return

        record = self._record(
            manifest,
            ModuleState.LOADED,
            "",
            permissions=decision,
        )

        context = ModuleContext(manifest, self.core_api, decision.granted)
        instance = instantiate_module(manifest, context)
        record.instance = instance

        migrator = ModuleMigrator(manifest.id)
        record.applied_migrations = migrator.apply(instance.migrations())
        record.schema_version = migrator.current_version()
        if manifest.schema_version and record.schema_version != manifest.schema_version:
            raise MigrationError(
                f"Module {manifest.id} declares schema_version {manifest.schema_version}, "
                f"database is at {record.schema_version}"
            )
        record.state = ModuleState.MIGRATED
        self._persist(record)

        self.db.register_module(manifest.id, manifest.name, manifest.version)
        instance.on_start()

        record.capabilities = self._register_capabilities(record, decision)
        record.state = ModuleState.RUNNING
        record.detail = ""
        self._persist(record)
        self.db.set_module_status(manifest.id, "active")

        with self._lock:
            self._started.append(manifest.id)

        self._publish(
            "modules.module.started",
            {
                "module_id": manifest.id,
                "version": manifest.version,
                "capabilities": list(record.capabilities),
                "schema_version": record.schema_version,
            },
        )

    def _handle_start_failure(self, manifest: ModuleManifest, exc: Exception) -> None:
        reason = "load_failed" if isinstance(exc, ModuleLoadError) else type(exc).__name__
        record = self._records.get(manifest.id)
        if record is None:
            record = self._record(manifest, ModuleState.FAILED, f"{reason}: {exc}")
        else:
            record.state = ModuleState.FAILED
            record.detail = f"{reason}: {exc}"

        if record.instance is not None:
            self._release_capabilities(record)
            try:
                record.instance.on_stop()
            except Exception:
                pass
            record.instance = None
        unload_module(manifest)
        self._persist(record)
        self.db.set_module_status(manifest.id, "failed")

        try:
            self.core_api.save_checkpoint(
                f"module:{manifest.id}",
                {
                    "module_id": manifest.id,
                    "version": manifest.version,
                    "error": str(exc),
                    "reason": reason,
                },
                f"fix module {manifest.id} ({reason}) and restart the module runtime",
            )
        except Exception:
            pass

        self._publish(
            "modules.module.failed",
            {"module_id": manifest.id, "reason": reason, "error": str(exc)},
        )

    def _register_capabilities(
        self,
        record: ModuleRecord,
        decision: PermissionDecision,
    ) -> list[str]:
        if self.capabilities is None or record.instance is None:
            return []

        registered: list[str] = []
        for declaration in record.manifest.capabilities:
            handler = getattr(record.instance, declaration.handler, None)
            if not callable(handler):
                raise ModuleLoadError(
                    f"Capability {declaration.name!r} handler "
                    f"{declaration.handler!r} is not callable"
                )

            name = f"module.{record.manifest.id}.{declaration.name}"
            risk = _RISK_BY_NAME[declaration.risk]
            self.capabilities.unregister(name)
            self.capabilities.register(
                Capability(
                    name=name,
                    risk=risk,
                    handler=handler if risk == RiskLevel.READ_ONLY else None,
                    description=declaration.description,
                    module_id=record.manifest.id,
                    required_permissions=tuple(decision.granted),
                    permissions_granted=True,
                )
            )
            registered.append(name)
        return registered

    def _release_capabilities(self, record: ModuleRecord) -> None:
        if self.capabilities is not None:
            self.capabilities.unregister_module(record.manifest.id)
        record.capabilities = []

    def _module_health(self, record: ModuleRecord) -> ModuleHealth:
        if record.state != ModuleState.RUNNING or record.instance is None:
            return ModuleHealth(
                module_id=record.manifest.id,
                state=record.state.value,
                healthy=False,
                detail=record.detail,
            )
        try:
            health = record.instance.health()
        except Exception as exc:
            return ModuleHealth(
                module_id=record.manifest.id,
                state=record.state.value,
                healthy=False,
                detail=f"health_check_failed: {exc}",
            )
        return ModuleHealth(
            module_id=record.manifest.id,
            state=record.state.value,
            healthy=bool(health.healthy),
            detail=health.detail,
        )

    def _record(
        self,
        manifest: ModuleManifest,
        state: ModuleState,
        detail: str,
        *,
        permissions: PermissionDecision | None = None,
    ) -> ModuleRecord:
        record = self._records.get(manifest.id)
        if record is None:
            record = ModuleRecord(manifest=manifest, state=state, detail=detail)
            self._records[manifest.id] = record
        else:
            record.state = state
            record.detail = detail
        if permissions is not None:
            record.permissions = permissions.granted
            record.denied_permissions = permissions.denied
        self._persist(record)
        return record

    def _persist(self, record: ModuleRecord) -> None:
        try:
            self.db.upsert_module_state(
                record.manifest.id,
                record.state.value,
                record.manifest.version,
                detail=record.detail,
                permissions=list(record.permissions),
                capabilities=list(record.capabilities),
                schema_version=record.schema_version,
            )
        except Exception:
            pass

    def _publish(self, event_type: str, payload: dict[str, Any]) -> None:
        try:
            self.core_api.publish(event_type, payload, source="modules")
        except Exception:
            pass
