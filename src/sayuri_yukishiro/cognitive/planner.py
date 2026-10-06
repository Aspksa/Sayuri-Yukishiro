from __future__ import annotations

from uuid import uuid4

from .types import Goal, Intent, IntentKind, Plan, PlanStep, RiskLevel


class CognitivePlanner:
    def build(self, intent: Intent, goal: Goal) -> Plan:
        steps: list[PlanStep] = [
            PlanStep(
                id="step-001",
                title="Разобрать запрос",
                description="Зафиксировать намерение, цель, контекст и ограничения без изменения внешнего состояния.",
                capability="cognitive.inspect",
                risk=RiskLevel.READ_ONLY,
            )
        ]

        if intent.kind == IntentKind.ANALYSIS:
            steps.extend(
                [
                    PlanStep(
                        id="step-002",
                        title="Сформировать анализ",
                        description="Подготовить структурированный аналитический результат на основе доступного контекста.",
                        capability="cognitive.synthesize",
                        risk=RiskLevel.READ_ONLY,
                        depends_on=["step-001"],
                    ),
                    PlanStep(
                        id="step-003",
                        title="Проверить результат",
                        description="Проверить завершённость, доказательства и возможные противоречия.",
                        capability="cognitive.verify",
                        risk=RiskLevel.READ_ONLY,
                        depends_on=["step-002"],
                    ),
                ]
            )
        elif intent.kind == IntentKind.CREATION:
            steps.extend(
                [
                    PlanStep(
                        id="step-002",
                        title="Подготовить результат",
                        description="Сформировать проект результата без внешних изменений.",
                        capability="cognitive.compose",
                        risk=RiskLevel.READ_ONLY,
                        depends_on=["step-001"],
                    ),
                    PlanStep(
                        id="step-003",
                        title="Проверить результат",
                        description="Проверить соответствие результата цели и ограничениям.",
                        capability="cognitive.verify",
                        risk=RiskLevel.READ_ONLY,
                        depends_on=["step-002"],
                    ),
                ]
            )
        elif intent.kind in (IntentKind.ACTION, IntentKind.NAVIGATION):
            steps.extend(
                [
                    PlanStep(
                        id="step-002",
                        title="Подготовить действие",
                        description="Определить требуемое действие, целевой объект и риск.",
                        capability="cognitive.prepare_action",
                        risk=RiskLevel.READ_ONLY,
                        depends_on=["step-001"],
                    ),
                    PlanStep(
                        id="step-003",
                        title="Запросить выполнение действия",
                        description="Передать изменение внешнего состояния будущему брокеру действий.",
                        capability="action.execute",
                        risk=RiskLevel.MUTATION,
                        depends_on=["step-002"],
                    ),
                ]
            )
        else:
            steps.extend(
                [
                    PlanStep(
                        id="step-002",
                        title="Сформировать ответ",
                        description="Подготовить результат в рамках доступного контекста.",
                        capability="cognitive.synthesize",
                        risk=RiskLevel.READ_ONLY,
                        depends_on=["step-001"],
                    ),
                    PlanStep(
                        id="step-003",
                        title="Проверить результат",
                        description="Проверить завершённость плана перед выдачей результата.",
                        capability="cognitive.verify",
                        risk=RiskLevel.READ_ONLY,
                        depends_on=["step-002"],
                    ),
                ]
            )

        return Plan(id=str(uuid4()), goal_id=goal.id, steps=steps)
