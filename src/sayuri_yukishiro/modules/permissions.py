from __future__ import annotations

from dataclasses import dataclass, field

from .manifest import AUTO_GRANTED_PERMISSIONS, ModuleManifest


@dataclass(frozen=True)
class PermissionGrant:
    permission: str
    granted: bool
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "permission": self.permission,
            "granted": self.granted,
            "reason": self.reason,
        }


@dataclass
class PermissionDecision:
    module_id: str
    grants: list[PermissionGrant] = field(default_factory=list)

    @property
    def granted(self) -> tuple[str, ...]:
        return tuple(item.permission for item in self.grants if item.granted)

    @property
    def denied(self) -> tuple[str, ...]:
        return tuple(item.permission for item in self.grants if not item.granted)

    @property
    def allowed(self) -> bool:
        return not self.denied

    def denial_detail(self) -> str:
        return "; ".join(
            f"{item.permission}:{item.reason}" for item in self.grants if not item.granted
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "module_id": self.module_id,
            "granted": list(self.granted),
            "denied": list(self.denied),
            "grants": [item.to_dict() for item in self.grants],
        }


class PermissionBroker:
    """Решает, какие разрешения модуля можно выдать без Action Broker.

    Разрешения уровня чтения и работы с собственной БД выдаются автоматически.
    Всё, что меняет внешнее состояние — процессы, сеть, файловая система вне
    собственной БД модуля, — остаётся заблокированным до появления отдельного
    брокера действий и системы подтверждений.
    """

    AUTO_GRANTED = frozenset(AUTO_GRANTED_PERMISSIONS)

    def evaluate(self, manifest: ModuleManifest) -> PermissionDecision:
        decision = PermissionDecision(module_id=manifest.id)
        for permission in manifest.permissions:
            if permission in self.AUTO_GRANTED:
                decision.grants.append(
                    PermissionGrant(permission, True, "auto_granted_read_only")
                )
            else:
                decision.grants.append(
                    PermissionGrant(permission, False, "requires_action_broker")
                )
        return decision
