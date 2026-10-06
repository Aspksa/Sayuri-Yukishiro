from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch

from sayuri_yukishiro.cognitive.engine import CognitiveCore
from sayuri_yukishiro.core.events import EventBus
from sayuri_yukishiro.core.jobs import JobManager
from sayuri_yukishiro.core.runtime import SystemCore
from sayuri_yukishiro.core.update_service import UpdateService
from sayuri_yukishiro.database import CoreDatabase
from sayuri_yukishiro.server import SayuriHTTPServer
from sayuri_yukishiro.update_helper import UpdateHelper
from sayuri_yukishiro.update_state import (
    default_update_state,
    load_update_state,
    save_update_state,
)
from sayuri_yukishiro.updater import UpdateInspection, UpstreamInfo


class UpdateServiceTests(unittest.TestCase):
    def make_services(self, root: Path):
        db = CoreDatabase(root / "core.db")
        db.initialize()
        events = EventBus(db)
        jobs = JobManager(db, max_workers=1)
        events.start()
        jobs.start()
        service = UpdateService(
            jobs,
            events,
            root=root,
            update_dir=root / "update",
            data_dir=root / "runtime-data",
        )
        service.start()
        return db, events, jobs, service

    def test_async_check_persists_available_version_and_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, events, jobs, service = self.make_services(root)
            inspection = UpdateInspection(
                status="available",
                message="Update is available.",
                current_sha="a" * 40,
                target_sha="b" * 40,
                current_version="0.3.1",
                available_version="0.4.0",
                upstream=UpstreamInfo(
                    branch="main",
                    remote_name="origin",
                    remote_branch="main",
                    upstream_ref="origin/main",
                    remote_url="https://example.invalid/repo.git",
                ),
                changes=("abc change one", "def change two"),
            )
            try:
                with patch(
                    "sayuri_yukishiro.core.update_service.inspect_update",
                    return_value=inspection,
                ):
                    job_id = service.request_check()
                    jobs.wait(job_id, timeout=5)

                state = service.status()
                self.assertEqual(state["phase"], "available")
                self.assertEqual(state["available_version"], "0.4.0")
                self.assertEqual(state["target_sha"], "b" * 40)
                self.assertTrue(state["can_apply"])
                self.assertEqual(len(state["changes"]), 2)
            finally:
                service.stop()
                jobs.stop()
                events.stop()

    def test_prepare_apply_writes_exact_checked_target_to_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, events, jobs, service = self.make_services(root)
            inspection = UpdateInspection(
                status="available",
                message="Update is available.",
                current_sha="a" * 40,
                target_sha="b" * 40,
                current_version="0.3.1",
                available_version="0.4.0",
                upstream=UpstreamInfo(
                    branch="main",
                    remote_name="origin",
                    remote_branch="main",
                    upstream_ref="origin/main",
                    remote_url="https://example.invalid/repo.git",
                ),
                changes=("abc change",),
            )
            state = default_update_state()
            state.update(
                {
                    "phase": "available",
                    "can_apply": True,
                    "update_available": True,
                    "current_sha": inspection.current_sha,
                    "target_sha": inspection.target_sha,
                    "available_version": "0.4.0",
                }
            )
            save_update_state(state, root / "update" / "status.json")
            fake_helper = MagicMock()
            fake_helper.pid = 4242
            try:
                with (
                    patch(
                        "sayuri_yukishiro.core.update_service.inspect_update",
                        return_value=inspection,
                    ),
                    patch.object(
                        service,
                        "_spawn_helper",
                        return_value=fake_helper,
                    ),
                ):
                    result = service.prepare_apply()

                plan = json.loads(
                    (root / "update" / "apply-plan.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(plan["before_sha"], "a" * 40)
                self.assertEqual(plan["target_sha"], "b" * 40)
                self.assertEqual(plan["upstream"], "origin/main")
                self.assertEqual(
                    Path(plan["data_dir"]),
                    root / "runtime-data",
                )
                self.assertIn("db_backup_dir", plan)
                self.assertEqual(result["phase"], "waiting_for_shutdown")
                self.assertEqual(result["helper_pid"], 4242)
            finally:
                service.stop()
                jobs.stop()
                events.stop()

    def test_update_api_rejects_missing_control_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = CoreDatabase(root / "core.db")
            core = SystemCore(
                db=db,
                config_path=root / "system.json",
                log_dir=root / "logs",
                update_dir=root / "update",
                port=0,
            )
            core.start()
            cognitive = CognitiveCore(core.api, db)
            cognitive.start()
            server = SayuriHTTPServer(
                ("127.0.0.1", 0),
                core,
                cognitive,
                shutdown_token="test-secret",
            )
            thread = threading.Thread(
                target=server.serve_forever,
                daemon=True,
            )
            thread.start()
            host, port = server.server_address
            try:
                with urllib.request.urlopen(
                    f"http://{host}:{port}/api/session/control-token",
                    timeout=2,
                ) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                self.assertTrue(payload["token"])
                self.assertNotEqual(payload["token"], "test-secret")

                bad_host = urllib.request.Request(
                    f"http://{host}:{port}/api/session/control-token",
                    headers={"Host": "evil.example"},
                )
                with self.assertRaises(urllib.error.HTTPError) as host_ctx:
                    urllib.request.urlopen(bad_host, timeout=2)
                self.assertEqual(host_ctx.exception.code, 403)

                request = urllib.request.Request(
                    f"http://{host}:{port}/api/update/check",
                    method="POST",
                )
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(request, timeout=2)
                self.assertEqual(ctx.exception.code, 403)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)
                cognitive.stop()
                core.stop()

    def _git(self, root: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            self.fail(
                f"git {' '.join(args)} failed: {result.stderr}"
            )
        return result.stdout.strip()

    def test_helper_creates_backup_applies_exact_sha_and_can_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "repo"
            root.mkdir()
            self._git(root, "init")
            self._git(root, "config", "user.email", "test@example.invalid")
            self._git(root, "config", "user.name", "Sayuri Test")

            (root / "VERSION").write_text("0.3.1\n", encoding="utf-8")
            (root / "payload.txt").write_text("old\n", encoding="utf-8")
            self._git(root, "add", "VERSION", "payload.txt")
            self._git(root, "commit", "-m", "old")
            before = self._git(root, "rev-parse", "HEAD")

            (root / "VERSION").write_text("0.4.0\n", encoding="utf-8")
            (root / "payload.txt").write_text("new\n", encoding="utf-8")
            self._git(root, "add", "VERSION", "payload.txt")
            self._git(root, "commit", "-m", "new")
            target = self._git(root, "rev-parse", "HEAD")
            self._git(root, "reset", "--hard", before)

            control = base / "update"
            control.mkdir()
            state_file = control / "status.json"
            save_update_state(default_update_state(), state_file)
            plan_file = control / "plan.json"
            plan = {
                "schema_version": 1,
                "root": str(root),
                "data_dir": str(base / "runtime-data"),
                "state_path": str(state_file),
                "backup_path": str(control / "backup.zip"),
                "db_backup_dir": str(control / "db-backup"),
                "parent_pid": 0,
                "python_executable": sys.executable,
                "port": 8765,
                "shutdown_token": "test-token",
                "before_sha": before,
                "target_sha": target,
                "upstream": "origin/main",
                "current_version": "0.3.1",
                "available_version": "0.4.0",
            }
            plan_file.write_text(
                json.dumps(plan),
                encoding="utf-8",
            )

            runtime_data = base / "runtime-data"
            runtime_data.mkdir()
            db_path = runtime_data / "state.db"
            import sqlite3
            conn = sqlite3.connect(db_path)
            try:
                conn.execute("CREATE TABLE sample(value TEXT NOT NULL)")
                conn.execute("INSERT INTO sample(value) VALUES('old')")
                conn.commit()
            finally:
                conn.close()

            helper = UpdateHelper(plan_file)
            helper.backup()
            helper.apply()

            conn = sqlite3.connect(db_path)
            try:
                conn.execute("UPDATE sample SET value='new'")
                conn.commit()
            finally:
                conn.close()
            self.assertTrue((control / "backup.zip").is_file())
            self.assertEqual(
                (root / "payload.txt").read_text(encoding="utf-8"),
                "new\n",
            )
            self.assertEqual(self._git(root, "rev-parse", "HEAD"), target)

            fake_process = MagicMock()
            fake_process.pid = 9876
            with (
                patch.object(
                    helper,
                    "_start_core",
                    return_value=fake_process,
                ),
                patch.object(
                    helper,
                    "_wait_health",
                    return_value={
                        "status": "ok",
                        "version": "0.3.1",
                    },
                ),
            ):
                restarted = helper.rollback("forced test rollback")

            self.assertIs(restarted, fake_process)
            self.assertEqual(self._git(root, "rev-parse", "HEAD"), before)
            self.assertEqual(
                (root / "payload.txt").read_text(encoding="utf-8"),
                "old\n",
            )
            state = load_update_state(state_file)
            self.assertEqual(state["phase"], "rolled_back")
            self.assertEqual(
                state["rollback"]["databases_restored"],
                1,
            )
            conn = sqlite3.connect(db_path)
            try:
                value = conn.execute(
                    "SELECT value FROM sample"
                ).fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(value, "old")

    def test_helper_refuses_destructive_rollback_if_worktree_changed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "repo"
            root.mkdir()
            self._git(root, "init")
            self._git(root, "config", "user.email", "test@example.invalid")
            self._git(root, "config", "user.name", "Sayuri Test")

            (root / "VERSION").write_text("0.3.1\n", encoding="utf-8")
            (root / "payload.txt").write_text("old\n", encoding="utf-8")
            self._git(root, "add", "VERSION", "payload.txt")
            self._git(root, "commit", "-m", "old")
            before = self._git(root, "rev-parse", "HEAD")

            (root / "VERSION").write_text("0.4.0\n", encoding="utf-8")
            (root / "payload.txt").write_text("new\n", encoding="utf-8")
            self._git(root, "add", "VERSION", "payload.txt")
            self._git(root, "commit", "-m", "new")
            target = self._git(root, "rev-parse", "HEAD")
            self._git(root, "reset", "--hard", before)

            control = base / "update"
            control.mkdir()
            state_file = control / "status.json"
            save_update_state(default_update_state(), state_file)
            plan_file = control / "plan.json"
            plan_file.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "root": str(root),
                        "state_path": str(state_file),
                        "backup_path": str(control / "backup.zip"),
                        "parent_pid": 0,
                        "python_executable": sys.executable,
                        "port": 8765,
                        "shutdown_token": "test-token",
                        "before_sha": before,
                        "target_sha": target,
                        "upstream": "origin/main",
                        "current_version": "0.3.1",
                        "available_version": "0.4.0",
                    }
                ),
                encoding="utf-8",
            )

            helper = UpdateHelper(plan_file)
            helper.backup()
            helper.apply()
            (root / "local-note.txt").write_text(
                "must survive\n",
                encoding="utf-8",
            )

            restarted = helper.rollback("forced test failure")
            state = load_update_state(state_file)

            self.assertIsNone(restarted)
            self.assertEqual(
                state["rollback"]["status"],
                "blocked_local_changes",
            )
            self.assertEqual(self._git(root, "rev-parse", "HEAD"), target)
            self.assertTrue((root / "local-note.txt").is_file())
            self.assertTrue((control / "backup.zip").is_file())

    def test_stale_busy_state_recovers_to_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            update_dir = root / "update"
            state = default_update_state()
            state.update(
                {
                    "phase": "applying",
                    "helper_pid": 424242,
                    "can_apply": False,
                }
            )
            save_update_state(state, update_dir / "status.json")

            db = CoreDatabase(root / "core.db")
            db.initialize()
            events = EventBus(db)
            jobs = JobManager(db, max_workers=1)
            events.start()
            jobs.start()
            service = UpdateService(
                jobs,
                events,
                root=root,
                update_dir=update_dir,
                data_dir=root / "runtime-data",
            )
            try:
                with patch(
                    "sayuri_yukishiro.core.update_service._process_alive",
                    return_value=False,
                ):
                    service.start()
                restored = service.status()
                self.assertEqual(restored["phase"], "failed")
                self.assertEqual(
                    restored["rollback"]["status"],
                    "interrupted",
                )
            finally:
                service.stop()
                jobs.stop()
                events.stop()

    def test_restart_terminates_unhealthy_new_process_before_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "repo"
            root.mkdir()
            control = base / "update"
            control.mkdir()
            state_file = control / "status.json"
            save_update_state(default_update_state(), state_file)
            plan_file = control / "plan.json"
            plan_file.write_text(
                json.dumps(
                    {
                        "root": str(root),
                        "data_dir": str(base / "runtime-data"),
                        "state_path": str(state_file),
                        "backup_path": str(control / "backup.zip"),
                        "db_backup_dir": str(control / "db-backup"),
                        "parent_pid": 0,
                        "python_executable": sys.executable,
                        "port": 8765,
                        "shutdown_token": "shutdown-secret",
                        "before_sha": "a" * 40,
                        "target_sha": "b" * 40,
                    }
                ),
                encoding="utf-8",
            )
            helper = UpdateHelper(plan_file)
            process = MagicMock()
            process.pid = 4444
            with (
                patch.object(helper, "_start_core", return_value=process),
                patch.object(
                    helper,
                    "_wait_health",
                    side_effect=TimeoutError("not healthy"),
                ),
                patch.object(helper, "_terminate_process") as terminate,
            ):
                with self.assertRaises(TimeoutError):
                    helper.restart()
            terminate.assert_called_once_with(process)

    def test_verification_uses_isolated_runtime_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "repo"
            root.mkdir()
            (root / "scripts").mkdir()
            state_file = base / "update" / "status.json"
            state_file.parent.mkdir()
            save_update_state(default_update_state(), state_file)
            plan_file = state_file.parent / "plan.json"
            production = base / "production-data"
            plan_file.write_text(
                json.dumps(
                    {
                        "root": str(root),
                        "data_dir": str(production),
                        "state_path": str(state_file),
                        "backup_path": str(base / "backup.zip"),
                        "db_backup_dir": str(base / "db-backup"),
                        "parent_pid": 0,
                        "python_executable": sys.executable,
                        "port": 8765,
                        "shutdown_token": "shutdown-secret",
                        "before_sha": "a" * 40,
                        "target_sha": "b" * 40,
                    }
                ),
                encoding="utf-8",
            )
            helper = UpdateHelper(plan_file)
            calls = []

            def fake_run(command, **kwargs):
                calls.append(kwargs["env"].copy())
                return subprocess.CompletedProcess(command, 0)

            with patch(
                "sayuri_yukishiro.update_helper.subprocess.run",
                side_effect=fake_run,
            ):
                helper.verify()

            self.assertTrue(calls)
            for env in calls:
                self.assertNotEqual(
                    Path(env["SAYURI_DATA_DIR"]),
                    production,
                )
                self.assertEqual(
                    Path(env["SAYURI_DATA_DIR"]),
                    helper.verify_data_dir,
                )

    def test_update_ui_is_part_of_system_shell(self) -> None:
        from sayuri_yukishiro.paths import PROJECT_ROOT

        html = (PROJECT_ROOT / "web" / "index.html").read_text(
            encoding="utf-8"
        )
        main_py = (
            PROJECT_ROOT
            / "src"
            / "sayuri_yukishiro"
            / "main.py"
        ).read_text(encoding="utf-8")

        self.assertIn("Обновления проекта", html)
        self.assertIn("/api/update/check", html)
        self.assertIn("/api/update/apply", html)
        self.assertIn("if (response.status === 403)", html)
        self.assertIn("if (reconnectedAfterApply) controlToken = '';", html)
        self.assertNotIn("safe_update", main_py)


if __name__ == "__main__":
    unittest.main()
