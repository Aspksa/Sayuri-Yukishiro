from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .types import RiskLevel

CapabilityHandler = Callable[[dict[str, Any]], Any]


@dataclass(frozen=True)
class Capability:
    name: str
    risk: RiskLevel
    handler: CapabilityHandler | None
    description: str = ""
    module_id: str | None = None
    required_permissions: tuple[str, ...] = field(default_factory=tuple)
    permissions_granted: bool = True


@dataclass(frozen=True)
class CapabilityDecision:
    allowed: bool
    reason: str
    capability: str
    risk: RiskLevel


class CapabilityRegistry:
    def __init__(self) -> None:
        self._items: dict[str, Capability] = {}

    def register(self, capability: Capability) -> None:
        if capability.name in self._items:
            raise ValueError(f"Capability already registered: {capability.name}")
        self._items[capability.name] = capability

    def unregister(self, name: str) -> bool:
        return self._items.pop(name, None) is not None

    def unregister_module(self, module_id: str) -> list[str]:
        """Снять все способности модуля при его остановке."""

        removed = [
            name
            for name, item in self._items.items()
            if item.module_id is not None and item.module_id == module_id
        ]
        for name in removed:
            del self._items[name]
        return sorted(removed)

    def names_for_module(self, module_id: str) -> list[str]:
        return sorted(
            name
            for name, item in self._items.items()
            if item.module_id is not None and item.module_id == module_id
        )

    def get(self, name: str) -> Capability | None:
        return self._items.get(name)

    def names(self) -> list[str]:
        return sorted(self._items)

    def snapshot(self) -> list[dict[str, Any]]:
        return [
            {
                "name": item.name,
                "risk": item.risk.value,
                "executable": item.handler is not None and item.permissions_granted,
                "description": item.description,
                "module_id": item.module_id,
                "required_permissions": list(item.required_permissions),
                "permissions_granted": item.permissions_granted,
            }
            for item in sorted(self._items.values(), key=lambda value: value.name)
        ]


class ExecutionGate:
    """Запрещает мутации, пока в проекте нет отдельного Action Broker."""

    def decide(self, capability: Capability | None) -> CapabilityDecision:
        if capability is None:
            return CapabilityDecision(
                allowed=False,
                reason="capability_not_registered",
                capability="unknown",
                risk=RiskLevel.EXTERNAL,
            )
        if capability.risk != RiskLevel.READ_ONLY:
            return CapabilityDecision(
                allowed=False,
                reason="requires_action_broker",
                capability=capability.name,
                risk=capability.risk,
            )
        if not capability.permissions_granted:
            return CapabilityDecision(
                allowed=False,
                reason="module_permission_denied",
                capability=capability.name,
                risk=capability.risk,
            )
        if capability.handler is None:
            return CapabilityDecision(
                allowed=False,
                reason="capability_has_no_handler",
                capability=capability.name,
                risk=capability.risk,
            )
        return CapabilityDecision(
            allowed=True,
            reason="read_only_allowed",
            capability=capability.name,
            risk=capability.risk,
        )


def build_default_capabilities() -> CapabilityRegistry:
    registry = CapabilityRegistry()

    def inspect(payload: dict[str, Any]) -> dict[str, Any]:
        text = str(payload.get("input_text", ""))
        return {
            "intent": payload.get("intent"),
            "objective": payload.get("objective"),
            "input_length": len(text),
            "context_keys": sorted(dict(payload.get("context", {})).keys()),
        }

    def synthesize(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "prepared": True,
            "objective": payload.get("objective"),
            "intent": payload.get("intent"),
            "note": "structured_result_ready_for_reasoning_provider",
        }

    def compose(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "prepared": True,
            "objective": payload.get("objective"),
            "note": "draft_generation_requires_reasoning_provider_for_semantic_content",
        }

    def verify(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "checked": True,
            "objective": payload.get("objective"),
        }

    def prepare_action(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "prepared": True,
            "objective": payload.get("objective"),
            "mutation_requires_action_broker": True,
        }

    registry.register(Capability("cognitive.inspect", RiskLevel.READ_ONLY, inspect))
    registry.register(Capability("cognitive.synthesize", RiskLevel.READ_ONLY, synthesize))
    registry.register(Capability("cognitive.compose", RiskLevel.READ_ONLY, compose))
    registry.register(Capability("cognitive.verify", RiskLevel.READ_ONLY, verify))
    registry.register(Capability("cognitive.prepare_action", RiskLevel.READ_ONLY, prepare_action))
    registry.register(
        Capability(
            "action.execute",
            RiskLevel.MUTATION,
            None,
            "Reserved mutation boundary. Execution requires future Action Broker.",
        )
    )
    return registry
