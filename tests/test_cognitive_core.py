from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sayuri_yukishiro.cognitive.engine import CognitiveCore
from sayuri_yukishiro.cognitive.provider import ProviderAdvice
from sayuri_yukishiro.cognitive.types import IntentKind
from sayuri_yukishiro.core.runtime import SystemCore
from sayuri_yukishiro.database import CoreDatabase


class BoostProvider:
    name = "test-provider"

    def advise(self, *, text, intent, goal, context):
        return ProviderAdvice(
            confidence_delta=0.1,
            notes=["test-provider-used"],
            metadata={"test": True},
        )


class CognitiveCoreTests(unittest.TestCase):
    def make_system(self, root: Path) -> tuple[CoreDatabase, SystemCore]:
        db = CoreDatabase(root / "core.db")
        system = SystemCore(
            db=db,
            config_path=root / "system.json",
            log_dir=root / "logs",
        )
        return db, system

    def test_analysis_request_completes_safe_plan_with_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db, system = self.make_system(Path(tmp))
            system.start()
            cognitive = CognitiveCore(system.api, db)
            cognitive.start()
            try:
                session = cognitive.create_session("Проверь архитектуру ядра")
                completed = cognitive.run_safe(session.id)
                receipts = cognitive.receipts(session.id)

                self.assertEqual(completed.intent.kind, IntentKind.ANALYSIS)
                self.assertEqual(completed.status, "completed")
                self.assertTrue(completed.verification.complete)
                self.assertEqual(len(receipts), len(completed.plan.steps))
                self.assertTrue(
                    all(receipt["status"] == "completed" for receipt in receipts)
                )
            finally:
                cognitive.stop()
                system.stop()

    def test_mutation_step_is_blocked_without_action_broker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db, system = self.make_system(Path(tmp))
            system.start()
            cognitive = CognitiveCore(system.api, db)
            cognitive.start()
            try:
                session = cognitive.create_session("Удалить тестовый файл")
                result = cognitive.run_safe(session.id)
                receipts = cognitive.receipts(session.id)

                self.assertEqual(result.intent.kind, IntentKind.ACTION)
                self.assertEqual(result.status, "blocked")
                self.assertFalse(result.verification.complete)
                self.assertEqual(receipts[-1]["status"], "blocked")
                self.assertEqual(
                    receipts[-1]["evidence"]["reason"],
                    "requires_action_broker",
                )
            finally:
                cognitive.stop()
                system.stop()

    def test_session_persists_and_restores_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db, system = self.make_system(root)
            system.start()
            cognitive = CognitiveCore(system.api, db)
            cognitive.start()
            try:
                session = cognitive.create_session("Что умеет ядро?")
                cognitive.run_safe(session.id)
                session_id = session.id
            finally:
                cognitive.stop()
                system.stop()

            restored_db, restored_system = self.make_system(root)
            restored_system.start()
            restored = CognitiveCore(restored_system.api, restored_db)
            restored.start()
            try:
                recovered = restored.get_session(session_id)
                self.assertEqual(recovered.id, session_id)
                self.assertEqual(recovered.status, "completed")
                self.assertTrue(recovered.verification.complete)
            finally:
                restored.stop()
                restored_system.stop()

    def test_provider_can_adjust_confidence_without_owning_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db, system = self.make_system(Path(tmp))
            system.start()
            baseline = CognitiveCore(system.api, db)
            baseline.start()
            try:
                base = baseline.create_session("Что такое системное ядро?")
                baseline_confidence = base.confidence
            finally:
                baseline.stop()

            enhanced = CognitiveCore(
                system.api,
                db,
                provider=BoostProvider(),
            )
            enhanced.start()
            try:
                session = enhanced.create_session("Что такое системное ядро?")
                self.assertEqual(session.provider, "test-provider")
                self.assertIn("test-provider-used", session.provider_notes)
                self.assertGreater(session.confidence, baseline_confidence)
            finally:
                enhanced.stop()
                system.stop()

    def test_conflicting_constraints_are_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db, system = self.make_system(Path(tmp))
            system.start()
            cognitive = CognitiveCore(system.api, db)
            cognitive.start()
            try:
                session = cognitive.create_session(
                    "Проверь ограничения",
                    context={
                        "constraints": [
                            "не изменять файл",
                            "изменять файл",
                        ]
                    },
                )
                self.assertTrue(session.contradictions)
                self.assertTrue(
                    all(
                        item.startswith("conflicting_constraint:")
                        for item in session.contradictions
                    )
                )
            finally:
                cognitive.stop()
                system.stop()


if __name__ == "__main__":
    unittest.main()
