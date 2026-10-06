from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sayuri_yukishiro.database import CoreDatabase
from sayuri_yukishiro.paths import project_version


class FoundationSmokeTests(unittest.TestCase):
    def test_project_version_is_defined(self) -> None:
        self.assertNotEqual(project_version(), "0.0.0-unknown")

    def test_core_database_initializes_and_is_healthy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = CoreDatabase(Path(tmp) / "core.db")
            db.initialize()
            self.assertEqual(db.quick_check().lower(), "ok")
            modules = db.list_modules()
            self.assertTrue(any(module["id"] == "core" for module in modules))


if __name__ == "__main__":
    unittest.main()
