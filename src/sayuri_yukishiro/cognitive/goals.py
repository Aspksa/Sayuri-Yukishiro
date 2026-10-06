from __future__ import annotations

import re
from uuid import uuid4

from .types import CognitiveContext, Goal, Intent, IntentKind


class GoalManager:
    def create(self, text: str, intent: Intent, context: CognitiveContext) -> Goal:
        objective = re.sub(r"\s+", " ", text.strip())
        criteria = self._criteria(intent.kind)
        constraints = list(dict.fromkeys([
            *context.constraints,
            "no_unapproved_mutations",
            "preserve_evidence",
        ]))
        return Goal(
            id=str(uuid4()),
            objective=objective,
            success_criteria=criteria,
            constraints=constraints,
        )

    @staticmethod
    def _criteria(kind: IntentKind) -> list[str]:
        mapping = {
            IntentKind.QUESTION: [
                "ответ соответствует вопросу",
                "существенные утверждения можно обосновать",
            ],
            IntentKind.ANALYSIS: [
                "выводы опираются на проверяемые данные",
                "противоречия отмечены",
                "результат проверен",
            ],
            IntentKind.CREATION: [
                "результат соответствует запросу",
                "ограничения пользователя соблюдены",
                "результат проверен перед выдачей",
            ],
            IntentKind.ACTION: [
                "действие явно определено",
                "риск определён до выполнения",
                "мутация не выполняется без брокера действий",
            ],
            IntentKind.NAVIGATION: [
                "целевая сущность определена",
                "навигация не выполняет побочных изменений",
            ],
            IntentKind.CONVERSATION: ["намерение пользователя не искажено"],
            IntentKind.UNKNOWN: ["цель сохранена без домысливания"],
        }
        return list(mapping[kind])
