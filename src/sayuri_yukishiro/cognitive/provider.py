from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .types import CognitiveContext, Goal, Intent


@dataclass(frozen=True)
class ProviderAdvice:
    confidence_delta: float = 0.0
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class ReasoningProvider(Protocol):
    name: str

    def advise(
        self,
        *,
        text: str,
        intent: Intent,
        goal: Goal,
        context: CognitiveContext,
    ) -> ProviderAdvice:
        ...


class NullReasoningProvider:
    """Провайдер-заглушка: когнитивное ядро работоспособно без внешней LLM."""

    name = "none"

    def advise(
        self,
        *,
        text: str,
        intent: Intent,
        goal: Goal,
        context: CognitiveContext,
    ) -> ProviderAdvice:
        return ProviderAdvice(
            notes=["external_reasoning_provider_not_connected"],
            metadata={"semantic_generation": False},
        )
