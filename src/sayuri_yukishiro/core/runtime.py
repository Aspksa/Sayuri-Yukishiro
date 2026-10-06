from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any

from ..database import CoreDatabase
from ..paths import LOG_DIR, PROJECT_ROOT, project_version
from ..version import SYSTEM_CORE_VERSION
from .api import CoreAPI
from .checkpoints import CheckpointService
from .config import ConfigurationService
from .events import EventBus
from .health import HealthMonitor
from .jobs import JobManager
from .logging_service import LoggingService
from .recovery import RecoveryService
from .service import ServiceRegistry


class SystemCore:
    CORE_VERSION = SYSTEM_CORE_VERSION

    def __init__(
        self,
        *,
        db: CoreDatabase | None = None,
        config_path: Path | None = None,
        log_dir: Path | None = None,
    ) -> None:
        self.db = db or CoreDatabase()
        self.db.initialize()

        config_file = config_path or (PROJECT_ROOT / "config" / "system.json")
        self.config = ConfigurationService(config_file)
        self.config.start()

        self.logging = LoggingService(
            log_dir or LOG_DIR,
            level=str(self.config.get("logging.level", "INFO")),
            max_bytes=int(self.config.get("logging.max_bytes", 2000000)),
            backup_count=int(self.config.get("logging.backup_count", 3)),
        )
        self.events = EventBus(self.db)
        self.jobs = JobManager(
            self.db,
            max_workers=int(self.config.get("core.max_workers", 4)),
            max_history=int(self.config.get("core.job_history_limit", 500)),
        )
        self.checkpoints = CheckpointService(self.db)
        self.recovery = RecoveryService(
            self.checkpoints,
            self.events,
            enabled=bool(self.config.get("core.recovery_enabled", True)),
        )

        self.registry = ServiceRegistry(self.db)
        self.registry.register(self.config)
        self.registry.register(self.logging)
        self.registry.register(self.events)
        self.registry.register(self.jobs)
        self.registry.register(self.checkpoints)
        self.registry.register(self.recovery)

        self.health = HealthMonitor(self.registry)
        self.api = CoreAPI(self)
        self._running = False
        self._lock = RLock()

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self.registry.start_all()
            self._running = True
        self.events.publish(
            "core.started",
            {
                "project_version": project_version(),
                "core_version": self.CORE_VERSION,
            },
            source="core",
        )
        self.logging.logger.info("system core started")

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self.events.publish("core.stopping", {}, source="core")
            self.logging.logger.info("system core stopping")
            try:
                self.registry.stop_all()
            finally:
                self._running = False

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    def status(self, *, deep: bool = False) -> dict[str, Any]:
        health = self.health.snapshot()
        return {
            "project": "Sayuri Yukishiro",
            "project_version": project_version(),
            "core_version": self.CORE_VERSION,
            "running": self.running,
            "health": health,
            "recoverable_tasks": len(self.recovery.pending()),
            "database_check": self.db.quick_check() if deep else "not_checked",
        }
