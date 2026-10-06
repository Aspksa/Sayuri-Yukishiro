from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from sayuri_yukishiro.cognitive.engine import CognitiveCore
from sayuri_yukishiro.core.jobs import JobManager
from sayuri_yukishiro.core.runtime import SystemCore
from sayuri_yukishiro.database import CoreDatabase
from sayuri_yukishiro.paths import PROJECT_ROOT
from sayuri_yukishiro.process_utils import process_alive
from sayuri_yukishiro.server import SayuriHandler, serve
from sayuri_yukishiro.storage_policy import sqlite_journal_mode
from sayuri_yukishiro.updater import inspect_update
from sayuri_yukishiro.version import (
    COGNITIVE_CORE_VERSION,
    SERVER_PRODUCT,
    SYSTEM_CORE_VERSION,
)


class StabilityRegressionTests(unittest.TestCase):
    def test_process_alive_is_read_only_and_detects_exit(self) -> None:
        self.assertTrue(process_alive(os.getpid()))
        child = subprocess.Popen(
            [sys.executable, "-c", "pass"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        pid = child.pid
        child.wait(timeout=5)
        self.assertFalse(process_alive(pid))

    def test_bind_failure_stops_both_cores(self) -> None:
        system = MagicMock()
        system.api = object()
        system.db = object()
        cognitive = MagicMock()

        with (
            patch("sayuri_yukishiro.server.SystemCore", return_value=system),
            patch("sayuri_yukishiro.server.CognitiveCore", return_value=cognitive),
            patch(
                "sayuri_yukishiro.server.SayuriHTTPServer",
                side_effect=OSError("address already in use"),
            ),
        ):
            with self.assertRaises(OSError):
                serve(port=8765)

        system.start.assert_called_once()
        cognitive.start.assert_called_once()
        cognitive.stop.assert_called_once()
        system.stop.assert_called_once()

    def test_lightweight_core_status_does_not_run_quick_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = CoreDatabase(root / "core.db")
            core = SystemCore(
                db=db,
                config_path=root / "system.json",
                log_dir=root / "logs",
                update_dir=root / "update",
            )
            core.start()
            try:
                with patch.object(
                    db,
                    "quick_check",
                    side_effect=AssertionError("quick_check must not run"),
                ):
                    status = core.status()
                    self.assertEqual(status["database_check"], "not_checked")
            finally:
                core.stop()

    def test_deep_core_status_runs_quick_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = CoreDatabase(root / "core.db")
            core = SystemCore(
                db=db,
                config_path=root / "system.json",
                log_dir=root / "logs",
                update_dir=root / "update",
            )
            core.start()
            try:
                with patch.object(db, "quick_check", return_value="ok") as check:
                    status = core.status(deep=True)
                    self.assertEqual(status["database_check"], "ok")
                    check.assert_called_once()
            finally:
                core.stop()

    def test_job_manager_bounds_in_memory_history_and_releases_futures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = CoreDatabase(Path(tmp) / "jobs.db")
            db.initialize()
            manager = JobManager(db, max_workers=2, max_history=2)
            manager.start()
            try:
                for value in range(6):
                    job_id = manager.submit("echo", lambda item=value: item)
                    self.assertEqual(manager.wait(job_id, timeout=5), value)
                time.sleep(0.05)
                self.assertLessEqual(len(manager.snapshot()), 2)
                self.assertEqual(manager._futures, {})
            finally:
                manager.stop()

    def test_onedrive_storage_uses_delete_journal_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "OneDrive" / "Sayuri" / "core.db"
            with patch.dict(
                os.environ,
                {"OneDrive": str(root / "OneDrive")},
                clear=False,
            ):
                self.assertEqual(sqlite_journal_mode(db_path), "DELETE")

    def test_sqlite_journal_mode_can_be_explicitly_overridden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "core.db"
            with patch.dict(
                os.environ,
                {"SAYURI_SQLITE_JOURNAL_MODE": "DELETE"},
                clear=False,
            ):
                db = CoreDatabase(db_path)
                db.initialize()
                with db.session() as conn:
                    mode = str(conn.execute("PRAGMA journal_mode").fetchone()[0])
                self.assertEqual(mode.lower(), "delete")

    def test_update_inspection_refreshes_tracking_ref_without_merging(self) -> None:
        calls: list[tuple[str, ...]] = []

        def completed(args: tuple[str, ...], stdout: str = "", code: int = 0):
            return subprocess.CompletedProcess(
                ["git", *args],
                code,
                stdout=stdout,
                stderr="",
            )

        def fake_git(*args: str, timeout: int = 30, root: Path = PROJECT_ROOT):
            calls.append(tuple(args))
            key = tuple(args)
            if key == ("rev-parse", "--is-inside-work-tree"):
                return completed(key, "true\n")
            if key == ("symbolic-ref", "--quiet", "--short", "HEAD"):
                return completed(key, "release/test\n")
            if key == (
                "rev-parse",
                "--abbrev-ref",
                "--symbolic-full-name",
                "@{upstream}",
            ):
                return completed(key, "origin/release/test\n")
            if key == ("remote", "get-url", "origin"):
                return completed(key, "https://example.invalid/repo.git\n")
            if key == ("status", "--porcelain"):
                return completed(key, "")
            if key == ("rev-parse", "HEAD"):
                return completed(key, "aaa\n")
            if key == (
                "fetch",
                "--quiet",
                "origin",
                "+refs/heads/release/test:refs/remotes/origin/release/test",
            ):
                return completed(key)
            if key == ("rev-parse", "origin/release/test"):
                return completed(key, "bbb\n")
            if key == ("show", "aaa:VERSION"):
                return completed(key, "0.3.1\n")
            if key == ("show", "bbb:VERSION"):
                return completed(key, "0.4.0\n")
            if key == ("merge-base", "--is-ancestor", "aaa", "bbb"):
                return completed(key)
            if key == (
                "log",
                "--reverse",
                "--format=%h %s",
                "aaa..bbb",
            ):
                return completed(key, "bbb feature: update service\n")
            raise AssertionError(f"Unexpected git call: {key}")

        with (
            patch("sayuri_yukishiro.updater.shutil.which", return_value="git"),
            patch("sayuri_yukishiro.updater.run_git", side_effect=fake_git),
        ):
            result = inspect_update(fetch=True)

        self.assertEqual(result.status, "available")
        self.assertTrue(result.can_apply)
        self.assertEqual(result.available_version, "0.4.0")
        self.assertEqual(result.upstream.upstream_ref, "origin/release/test")
        self.assertIn(
            (
                "fetch",
                "--quiet",
                "origin",
                "+refs/heads/release/test:refs/remotes/origin/release/test",
            ),
            calls,
        )
        self.assertFalse(any(call and call[0] == "merge" for call in calls))

    def test_version_metadata_has_single_python_source(self) -> None:
        self.assertEqual(SystemCore.CORE_VERSION, SYSTEM_CORE_VERSION)
        self.assertEqual(CognitiveCore.VERSION, COGNITIVE_CORE_VERSION)
        self.assertEqual(SayuriHandler.server_version, SERVER_PRODUCT)

        with tempfile.TemporaryDirectory() as tmp:
            db = CoreDatabase(Path(tmp) / "version.db")
            db.initialize()
            core_module = next(
                item for item in db.list_modules() if item["id"] == "core"
            )
            self.assertEqual(core_module["version"], SYSTEM_CORE_VERSION)

    def test_windows_launchers_do_not_contain_regressed_constructs(self) -> None:
        batch = (PROJECT_ROOT / "Sayuri-Yukishiro.bat").read_text(
            encoding="utf-8"
        )
        launcher = (PROJECT_ROOT / "scripts" / "launcher.ps1").read_text(
            encoding="utf-8"
        )
        self.assertNotIn('-Root "%~dp0"', batch)
        self.assertNotIn("v0.1.0", batch)
        self.assertNotIn("v0.1.0", launcher)
        self.assertNotIn("$args =", launcher.lower())
        self.assertIn("/api/shutdown", launcher)
        self.assertIn("Обновления проекта", launcher)
        self.assertIn('health.project -ne "Sayuri Yukishiro"', launcher)


if __name__ == "__main__":
    unittest.main()
