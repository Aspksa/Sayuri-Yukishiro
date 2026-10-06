from __future__ import annotations

from typing import Any

from .service import ServiceRegistry


class HealthMonitor:
    def __init__(self, registry: ServiceRegistry) -> None:
        self._registry = registry

    def snapshot(self) -> dict[str, Any]:
        services = self._registry.snapshot()
        failed = [item for item in services if item["state"] == "failed"]
        unhealthy = [item for item in services if not item["healthy"]]
        if failed:
            overall = "failed"
        elif unhealthy:
            overall = "degraded"
        else:
            overall = "healthy"
        return {
            "overall": overall,
            "service_count": len(services),
            "healthy_count": len(services) - len(unhealthy),
            "services": services,
        }
