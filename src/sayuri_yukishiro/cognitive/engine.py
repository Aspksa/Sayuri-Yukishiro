from __future__ import annotations

from threading import RLock
from typing import Any
from uuid import uuid4

from ..core.api import CoreAPI
from ..database import CoreDatabase
from ..version import COGNITIVE_CORE_VERSION
from .assessment import CognitiveAssessment
from .capabilities import (
    CapabilityRegistry,
    ExecutionGate,
    build_default_capabilities,
)
from .evidence import ExecutionReceipt, make_receipt
from .goals import GoalManager
from .intent import IntentAnalyzer
from .planner import CognitivePlanner
from .provider import NullReasoningProvider, ReasoningProvider
from .types import (
    CognitiveContext,
    CognitiveSession,
    PlanStep,
    StepState,
)
from .verification import ResultVerifier


class CognitiveCore:
    VERSION = COGNITIVE_CORE_VERSION

    def __init__(
        self,
        core_api: CoreAPI,
        db: CoreDatabase,
        *,
        provider: ReasoningProvider | None = None,
        capabilities: CapabilityRegistry | None = None,
    ) -> None:
        self.core_api = core_api
        self.db = db
        self.provider = provider or NullReasoningProvider()
        self.capabilities = capabilities or build_default_capabilities()
        self.gate = ExecutionGate()
        self.intent_analyzer = IntentAnalyzer()
        self.goal_manager = GoalManager()
        self.planner = CognitivePlanner()
        self.verifier = ResultVerifier()
        self.assessment = CognitiveAssessment()
        self._sessions: dict[str, CognitiveSession] = {}
        self._running = False
        self._lock = RLock()

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
        self.core_api.publish(
            "cognitive.started",
            {"version": self.VERSION, "provider": self.provider.name},
            source="cognitive",
        )

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False
        self.core_api.publish(
            "cognitive.stopped",
            {"version": self.VERSION},
            source="cognitive",
        )

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    def create_session(
        self,
        text: str,
        *,
        context: CognitiveContext | dict[str, Any] | None = None,
    ) -> CognitiveSession:
        if not self.running:
            raise RuntimeError("Cognitive core is not running")
        if not text.strip():
            raise ValueError("Input text must not be empty")

        if context is None:
            cognitive_context = CognitiveContext()
        elif isinstance(context, CognitiveContext):
            cognitive_context = context
        else:
            cognitive_context = CognitiveContext.from_dict(context)

        intent = self.intent_analyzer.analyze(text)
        goal = self.goal_manager.create(text, intent, cognitive_context)
        plan = self.planner.build(intent, goal)
        contradictions = self.assessment.contradictions(cognitive_context)
        base_confidence = self.assessment.confidence(
            intent,
            cognitive_context,
            plan,
            contradictions,
        )

        provider_notes: list[str] = []
        confidence_delta = 0.0
        try:
            advice = self.provider.advise(
                text=text,
                intent=intent,
                goal=goal,
                context=cognitive_context,
            )
            provider_notes = list(advice.notes)
            confidence_delta = max(-0.2, min(0.2, float(advice.confidence_delta)))
        except Exception as exc:
            provider_notes = [f"provider_error:{type(exc).__name__}"]

        confidence = round(
            max(0.0, min(1.0, base_confidence + confidence_delta)),
            4,
        )
        verification = self.verifier.verify(plan)
        session = CognitiveSession(
            id=str(uuid4()),
            input_text=text,
            context=cognitive_context,
            intent=intent,
            goal=goal,
            plan=plan,
            status="in_progress",
            confidence=confidence,
            contradictions=contradictions,
            verification=verification,
            provider=self.provider.name,
            provider_notes=provider_notes,
        )
        with self._lock:
            self._sessions[session.id] = session
        self._persist(session)
        self.core_api.publish(
            "cognitive.session.created",
            {
                "session_id": session.id,
                "intent": intent.kind.value,
                "confidence": session.confidence,
            },
            source="cognitive",
        )
        return session

    def execute_step(self, session_id: str, step_id: str) -> ExecutionReceipt:
        session = self.get_session(session_id)
        step = self._find_step(session, step_id)

        if step.state in (StepState.COMPLETED, StepState.SKIPPED):
            receipt = make_receipt(
                session_id=session.id,
                step_id=step.id,
                capability=step.capability,
                status="skipped",
                evidence={"reason": "already_completed"},
            )
            self.db.append_cognitive_receipt(receipt.to_dict())
            return receipt

        unmet = [
            dependency
            for dependency in step.depends_on
            if self._find_step(session, dependency).state
            not in (StepState.COMPLETED, StepState.SKIPPED)
        ]
        if unmet:
            receipt = make_receipt(
                session_id=session.id,
                step_id=step.id,
                capability=step.capability,
                status="blocked",
                evidence={"reason": "dependency_not_completed", "dependencies": unmet},
            )
            self.db.append_cognitive_receipt(receipt.to_dict())
            return receipt

        capability = self.capabilities.get(step.capability)
        decision = self.gate.decide(capability)
        if not decision.allowed:
            step.state = StepState.BLOCKED
            step.error = decision.reason
            receipt = make_receipt(
                session_id=session.id,
                step_id=step.id,
                capability=step.capability,
                status="blocked",
                evidence={
                    "reason": decision.reason,
                    "risk": step.risk.value,
                },
            )
            self.db.append_cognitive_receipt(receipt.to_dict())
            self._after_step(session)
            return receipt

        assert capability is not None and capability.handler is not None
        step.state = StepState.RUNNING
        self._persist(session)
        payload = self._execution_payload(session, step)
        try:
            result = capability.handler(payload)
        except Exception as exc:
            step.state = StepState.FAILED
            step.error = str(exc)
            receipt = make_receipt(
                session_id=session.id,
                step_id=step.id,
                capability=step.capability,
                status="failed",
                evidence={"error": str(exc)},
            )
            self.db.append_cognitive_receipt(receipt.to_dict())
            self._after_step(session)
            return receipt

        step.state = StepState.COMPLETED
        step.result = result
        step.error = None
        evidence = result if isinstance(result, dict) else {"result": result}
        receipt = make_receipt(
            session_id=session.id,
            step_id=step.id,
            capability=step.capability,
            status="completed",
            evidence=evidence,
        )
        self.db.append_cognitive_receipt(receipt.to_dict())
        self._after_step(session)
        return receipt

    def run_safe(self, session_id: str) -> CognitiveSession:
        session = self.get_session(session_id)
        for step in session.plan.steps:
            if step.state != StepState.PENDING:
                continue
            receipt = self.execute_step(session.id, step.id)
            if receipt.status in {"blocked", "failed"}:
                break
        return self.get_session(session.id)

    def get_session(self, session_id: str) -> CognitiveSession:
        with self._lock:
            cached = self._sessions.get(session_id)
        if cached is not None:
            return cached
        stored = self.db.get_cognitive_session(session_id)
        if stored is None:
            raise KeyError(session_id)
        session = CognitiveSession.from_dict(stored)
        with self._lock:
            self._sessions[session.id] = session
        return session

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.db.list_cognitive_sessions(limit=limit)

    def receipts(self, session_id: str) -> list[dict[str, Any]]:
        return self.db.list_cognitive_receipts(session_id)

    def status(self) -> dict[str, Any]:
        return {
            "version": self.VERSION,
            "running": self.running,
            "provider": self.provider.name,
            "sessions": self.db.count_cognitive_sessions(),
            "loaded_sessions": len(self._sessions),
            "capabilities": self.capabilities.snapshot(),
            "safety_boundary": {
                "read_only_execution": True,
                "mutations": "requires_action_broker",
                "external_actions": "requires_action_broker",
            },
        }

    def _after_step(self, session: CognitiveSession) -> None:
        session.verification = self.verifier.verify(session.plan)
        if session.verification.complete:
            session.status = "completed"
        elif session.verification.failed_steps:
            session.status = "failed"
        elif session.verification.blocked_steps:
            session.status = "blocked"
        else:
            session.status = "in_progress"
        self._persist(session)
        self.core_api.publish(
            "cognitive.step.updated",
            {
                "session_id": session.id,
                "status": session.status,
                "verification_score": session.verification.score,
            },
            source="cognitive",
        )

    def _persist(self, session: CognitiveSession) -> None:
        data = session.to_dict()
        self.db.save_cognitive_session(data)
        if session.status == "completed":
            try:
                self.core_api.complete_checkpoint(
                    f"cognitive:{session.id}",
                    {"cognitive_session": data},
                )
            except KeyError:
                pass
            return

        next_step = self._next_unfinished_step(session)
        next_action = (
            f"continue cognitive session at {next_step.id}: {next_step.title}"
            if next_step is not None
            else "review cognitive session state"
        )
        self.core_api.save_checkpoint(
            f"cognitive:{session.id}",
            {"cognitive_session": data},
            next_action,
        )

    @staticmethod
    def _next_unfinished_step(session: CognitiveSession) -> PlanStep | None:
        for step in session.plan.steps:
            if step.state not in (StepState.COMPLETED, StepState.SKIPPED):
                return step
        return None

    @staticmethod
    def _find_step(session: CognitiveSession, step_id: str) -> PlanStep:
        for step in session.plan.steps:
            if step.id == step_id:
                return step
        raise KeyError(step_id)

    @staticmethod
    def _execution_payload(
        session: CognitiveSession,
        step: PlanStep,
    ) -> dict[str, Any]:
        return {
            "session_id": session.id,
            "step_id": step.id,
            "input_text": session.input_text,
            "intent": session.intent.kind.value,
            "objective": session.goal.objective,
            "context": session.context.to_dict(),
            "constraints": list(session.goal.constraints),
            "previous_results": {
                item.id: item.result
                for item in session.plan.steps
                if item.result is not None
            },
        }
