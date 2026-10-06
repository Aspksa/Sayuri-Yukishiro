from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sayuri_yukishiro.core.events import EventBus
from sayuri_yukishiro.core.runtime import SystemCore
from sayuri_yukishiro.database import CoreDatabase


class SystemCoreTests(unittest.TestCase):
    def make_core(self, root: Path) -> SystemCore:
        return SystemCore(
            db=CoreDatabase(root / "core.db"),
            config_path=root / "system.json",
            log_dir=root / "logs",
        )

    def test_system_core_starts_healthy_and_stops(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            core = self.make_core(Path(tmp))
            core.start()
            status = core.status()
            self.assertTrue(status["running"])
            self.assertEqual(status["health"]["overall"], "healthy")
            self.assertEqual(
                status["health"]["healthy_count"],
                status["health"]["service_count"],
            )
            core.stop()
            self.assertFalse(core.running)

    def test_event_bus_delivers_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = CoreDatabase(Path(tmp) / "events.db")
            db.initialize()
            bus = EventBus(db)
            bus.start()
            received: list[str] = []
            bus.subscribe("demo.event", lambda event: received.append(event.id))
            event = bus.publish("demo.event", {"value": 1})
            self.assertEqual(received, [event.id])
            bus.stop()

    def test_job_manager_executes_background_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            core = self.make_core(Path(tmp))
            core.start()
            job_id = core.api.submit_job("sum", lambda a, b: a + b, 2, 3)
            self.assertEqual(core.jobs.wait(job_id, timeout=5), 5)
            self.assertEqual(core.jobs.get(job_id)["status"], "completed")
            core.stop()

    def test_checkpoint_is_recovered_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            core = self.make_core(root)
            core.start()
            core.api.save_checkpoint(
                "task-001",
                {"step": 2},
                "continue from step 3",
            )
            core.stop()

            restored = self.make_core(root)
            restored.start()
            tasks = restored.api.recoverable_tasks()
            self.assertEqual(len(tasks), 1)
            self.assertEqual(tasks[0]["task_id"], "task-001")
            self.assertEqual(tasks[0]["next_action"], "continue from step 3")
            restored.api.complete_checkpoint("task-001")
            self.assertEqual(restored.api.recoverable_tasks(), [])
            restored.stop()

    def test_database_schema_tracks_system_core_migration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = CoreDatabase(Path(tmp) / "schema.db")
            db.initialize()
            with db.session() as conn:
                versions = [
                    row[0]
                    for row in conn.execute(
                        "SELECT version FROM schema_migrations ORDER BY version"
                    ).fetchall()
                ]
            self.assertEqual(versions, [1, 2])


if __name__ == "__main__":
    unittest.main()
