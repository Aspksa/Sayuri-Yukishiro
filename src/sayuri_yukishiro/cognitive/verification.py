from __future__ import annotations

from .types import Plan, StepState, Verification


class ResultVerifier:
    def verify(self, plan: Plan) -> Verification:
        total = len(plan.steps)
        completed = [
            step.id
            for step in plan.steps
            if step.state in (StepState.COMPLETED, StepState.SKIPPED)
        ]
        missing = [
            step.id
            for step in plan.steps
            if step.state in (StepState.PENDING, StepState.RUNNING)
        ]
        blocked = [step.id for step in plan.steps if step.state == StepState.BLOCKED]
        failed = [step.id for step in plan.steps if step.state == StepState.FAILED]
        score = 1.0 if total == 0 else len(completed) / total
        return Verification(
            complete=not missing and not blocked and not failed,
            score=round(score, 4),
            missing_steps=missing,
            blocked_steps=blocked,
            failed_steps=failed,
        )
