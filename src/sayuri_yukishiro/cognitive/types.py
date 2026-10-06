from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class IntentKind(str, Enum):
    QUESTION = "question"
    ACTION = "action"
    ANALYSIS = "analysis"
    CREATION = "creation"
    NAVIGATION = "navigation"
    CONVERSATION = "conversation"
    UNKNOWN = "unknown"


class RiskLevel(str, Enum):
    READ_ONLY = "read_only"
    MUTATION = "mutation"
    EXTERNAL = "external"


class StepState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class CognitiveContext:
    conversation_id: str | None = None
    project: str | None = None
    active_module: str | None = None
    facts: dict[str, Any] = field(default_factory=dict)
    constraints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CognitiveContext":
        return cls(
            conversation_id=data.get("conversation_id"),
            project=data.get("project"),
            active_module=data.get("active_module"),
            facts=dict(data.get("facts", {})),
            constraints=list(data.get("constraints", [])),
        )


@dataclass
class Intent:
    kind: IntentKind
    confidence: float
    signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["kind"] = self.kind.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Intent":
        return cls(
            kind=IntentKind(str(data["kind"])),
            confidence=float(data["confidence"]),
            signals=list(data.get("signals", [])),
        )


@dataclass
class Goal:
    id: str
    objective: str
    success_criteria: list[str]
    constraints: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Goal":
        return cls(
            id=str(data["id"]),
            objective=str(data["objective"]),
            success_criteria=list(data.get("success_criteria", [])),
            constraints=list(data.get("constraints", [])),
        )


@dataclass
class PlanStep:
    id: str
    title: str
    description: str
    capability: str
    risk: RiskLevel
    depends_on: list[str] = field(default_factory=list)
    state: StepState = StepState.PENDING
    result: Any = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["risk"] = self.risk.value
        data["state"] = self.state.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlanStep":
        return cls(
            id=str(data["id"]),
            title=str(data["title"]),
            description=str(data["description"]),
            capability=str(data["capability"]),
            risk=RiskLevel(str(data["risk"])),
            depends_on=list(data.get("depends_on", [])),
            state=StepState(str(data.get("state", "pending"))),
            result=data.get("result"),
            error=data.get("error"),
        )


@dataclass
class Plan:
    id: str
    goal_id: str
    steps: list[PlanStep]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "goal_id": self.goal_id,
            "steps": [step.to_dict() for step in self.steps],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Plan":
        return cls(
            id=str(data["id"]),
            goal_id=str(data["goal_id"]),
            steps=[PlanStep.from_dict(item) for item in data.get("steps", [])],
        )


@dataclass
class Verification:
    complete: bool
    score: float
    missing_steps: list[str] = field(default_factory=list)
    blocked_steps: list[str] = field(default_factory=list)
    failed_steps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Verification":
        return cls(
            complete=bool(data.get("complete", False)),
            score=float(data.get("score", 0.0)),
            missing_steps=list(data.get("missing_steps", [])),
            blocked_steps=list(data.get("blocked_steps", [])),
            failed_steps=list(data.get("failed_steps", [])),
        )


@dataclass
class CognitiveSession:
    id: str
    input_text: str
    context: CognitiveContext
    intent: Intent
    goal: Goal
    plan: Plan
    status: str
    confidence: float
    contradictions: list[str]
    verification: Verification
    provider: str = "none"
    provider_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "input_text": self.input_text,
            "context": self.context.to_dict(),
            "intent": self.intent.to_dict(),
            "goal": self.goal.to_dict(),
            "plan": self.plan.to_dict(),
            "status": self.status,
            "confidence": self.confidence,
            "contradictions": list(self.contradictions),
            "verification": self.verification.to_dict(),
            "provider": self.provider,
            "provider_notes": list(self.provider_notes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CognitiveSession":
        return cls(
            id=str(data["id"]),
            input_text=str(data["input_text"]),
            context=CognitiveContext.from_dict(dict(data.get("context", {}))),
            intent=Intent.from_dict(dict(data["intent"])),
            goal=Goal.from_dict(dict(data["goal"])),
            plan=Plan.from_dict(dict(data["plan"])),
            status=str(data.get("status", "in_progress")),
            confidence=float(data.get("confidence", 0.0)),
            contradictions=list(data.get("contradictions", [])),
            verification=Verification.from_dict(dict(data.get("verification", {}))),
            provider=str(data.get("provider", "none")),
            provider_notes=list(data.get("provider_notes", [])),
        )
