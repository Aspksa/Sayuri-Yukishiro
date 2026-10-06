from __future__ import annotations

import re

from .types import Intent, IntentKind


class IntentAnalyzer:
    _RULES: tuple[tuple[IntentKind, tuple[str, ...]], ...] = (
        (
            IntentKind.ACTION,
            (
                "удали",
                "измени",
                "отправ",
                "опубли",
                "запусти",
                "останов",
                "установ",
                "delete",
                "update",
                "send",
                "publish",
                "start",
                "stop",
                "install",
            ),
        ),
        (
            IntentKind.ANALYSIS,
            (
                "анализ",
                "проанализ",
                "сравни",
                "проверь",
                "исслед",
                "audit",
                "analy",
                "compare",
                "review",
            ),
        ),
        (
            IntentKind.CREATION,
            (
                "создай",
                "сделай",
                "напиши",
                "подготов",
                "сгенер",
                "create",
                "write",
                "build",
                "generate",
            ),
        ),
        (
            IntentKind.NAVIGATION,
            (
                "открой",
                "перейди",
                "найди файл",
                "open",
                "navigate",
                "go to",
            ),
        ),
    )

    def analyze(self, text: str) -> Intent:
        normalized = re.sub(r"\s+", " ", text.strip().lower())
        if not normalized:
            return Intent(IntentKind.UNKNOWN, 0.0, ["empty_input"])

        for kind, keywords in self._RULES:
            signals = [keyword for keyword in keywords if keyword in normalized]
            if signals:
                confidence = min(0.98, 0.72 + 0.06 * len(signals))
                return Intent(kind, confidence, signals)

        if "?" in text or normalized.startswith(
            (
                "что ",
                "как ",
                "почему ",
                "зачем ",
                "когда ",
                "где ",
                "кто ",
                "which ",
                "what ",
                "how ",
                "why ",
            )
        ):
            return Intent(IntentKind.QUESTION, 0.82, ["question_form"])

        if len(normalized.split()) <= 4:
            return Intent(
                IntentKind.CONVERSATION,
                0.58,
                ["short_conversational_input"],
            )

        return Intent(IntentKind.UNKNOWN, 0.45, ["no_strong_rule"])
