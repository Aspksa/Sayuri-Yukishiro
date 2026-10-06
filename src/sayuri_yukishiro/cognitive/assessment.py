from __future__ import annotations

from .types import CognitiveContext, Intent, Plan


class CognitiveAssessment:
    def contradictions(self, context: CognitiveContext) -> list[str]:
        normalized = {
            " ".join(item.strip().lower().split())
            for item in context.constraints
            if item.strip()
        }
        contradictions: list[str] = []
        for item in sorted(normalized):
            inverse_candidates = []
            if item.startswith("не "):
                inverse_candidates.append(item[3:])
            else:
                inverse_candidates.append(f"не {item}")
            if item.startswith("not "):
                inverse_candidates.append(item[4:])
            else:
                inverse_candidates.append(f"not {item}")
            if any(candidate in normalized for candidate in inverse_candidates):
                contradictions.append(f"conflicting_constraint:{item}")
        return contradictions

    def confidence(
        self,
        intent: Intent,
        context: CognitiveContext,
        plan: Plan,
        contradictions: list[str],
    ) -> float:
        score = intent.confidence
        if context.facts:
            score += 0.05
        if context.constraints:
            score += 0.03
        if plan.steps:
            score += 0.05
        score -= min(0.35, 0.12 * len(contradictions))
        return round(max(0.0, min(1.0, score)), 4)
