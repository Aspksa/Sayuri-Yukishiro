from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sayuri_yukishiro.cognitive.engine import CognitiveCore
from sayuri_yukishiro.core.runtime import SystemCore
from sayuri_yukishiro.database import CoreDatabase
from sayuri_yukishiro.modules.base import ModuleState
from sayuri_yukishiro.modules.dependencies import DependencyResolver
from sayuri_yukishiro.modules.discovery import discover_modules
from sayuri_yukishiro.modules.manifest import (
    ManifestError,
    VersionSpec,
    parse_manifest,
)
from sayuri_yukishiro.modules.migrations import Migration, MigrationError, ModuleMigrator
from sayuri_yukishiro.modules.permissions import PermissionBroker
from sayuri_yukishiro.modules.runtime import ModuleRuntime
from sayuri_yukishiro.paths import MODULES_DIR
from sayuri_yukishiro.version import MODULE_RUNTIME_VERSION, SYSTEM_CORE_VERSION

MINIMAL_MANIFEST = {
    "manifest_version": 1,
    "id": "demo",
    "name": "Demo",
    "version": "1.0.0",
    "entry_point": "module:DemoModule",
}

MODULE_SOURCE = '''
from sayuri_yukishiro.modules.base import ModuleHealth, ModuleState, SayuriModule
from sayuri_yukishiro.modules.migrations import Migration


class {class_name}(SayuriModule):
    def migrations(self):
        return (
            Migration(
                version=1,
                description="notes",
                statements=(
                    "CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, text TEXT NOT NULL)",
                ),
            ),
        )

    def on_start(self):
        {on_start}

    def ping(self, payload):
        return {{"module_id": self.module_id, "objective": payload.get("objective")}}

    def health(self):
        return ModuleHealth(
            module_id=self.module_id,
            state=ModuleState.RUNNING.value,
            healthy={healthy},
            detail="test",
        )
'''


def write_module(
    root: Path,
    module_id: str,
    *,
    version: str = "1.0.0",
    dependencies: list[dict[str, str]] | None = None,
    permissions: list[str] | None = None,
    capabilities: list[dict[str, str]] | None = None,
    enabled: bool = True,
    schema_version: int = 1,
    requires_core: str | None = None,
    fail_on_start: bool = False,
    healthy: bool = True,
    manifest_overrides: dict | None = None,
) -> Path:
    directory = root / module_id
    directory.mkdir(parents=True, exist_ok=True)
    class_name = "".join(part.capitalize() for part in module_id.split("_")) + "Module"

    manifest = {
        "manifest_version": 1,
        "id": module_id,
        "name": module_id.replace("_", " ").title(),
        "version": version,
        "entry_point": f"module:{class_name}",
        "enabled": enabled,
        "schema_version": schema_version,
        "dependencies": dependencies or [],
        "permissions": permissions if permissions is not None else ["module.database"],
        "capabilities": capabilities
        if capabilities is not None
        else [{"name": "ping", "risk": "read_only", "handler": "ping"}],
    }
    if requires_core is not None:
        manifest["requires_core"] = requires_core
    if manifest_overrides:
        manifest.update(manifest_overrides)

    (directory / "module.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (directory / "module.py").write_text(
        MODULE_SOURCE.format(
            class_name=class_name,
            on_start='raise RuntimeError("start boom")' if fail_on_start else "return None",
            healthy="True" if healthy else "False",
        ),
        encoding="utf-8",
    )
    return directory


class ManifestTests(unittest.TestCase):
    def test_minimal_manifest_is_accepted(self) -> None:
        manifest = parse_manifest(dict(MINIMAL_MANIFEST))
        self.assertEqual(manifest.id, "demo")
        self.assertTrue(manifest.enabled)
        self.assertEqual(manifest.dependencies, ())
        self.assertEqual(manifest.capabilities, ())

    def test_invalid_fields_are_rejected(self) -> None:
        cases = {
            "id": {"id": "Demo-Module"},
            "version": {"version": "1.0"},
            "manifest_version": {"manifest_version": 99},
            "permission": {"permissions": ["core.secrets.read"]},
            "risk": {"capabilities": [{"name": "x", "risk": "danger", "handler": "x"}]},
            "self_dependency": {"dependencies": [{"id": "demo", "version": ">=1.0.0"}]},
            "version_spec": {"dependencies": [{"id": "other", "version": "latest"}]},
            "enabled": {"enabled": "yes"},
        }
        for label, override in cases.items():
            with self.subTest(label):
                data = dict(MINIMAL_MANIFEST)
                data.update(override)
                with self.assertRaises(ManifestError):
                    parse_manifest(data)

    def test_version_spec_operators(self) -> None:
        self.assertTrue(VersionSpec.parse(">=1.2.0").matches("1.3.0"))
        self.assertFalse(VersionSpec.parse(">=1.2.0").matches("1.1.9"))
        self.assertTrue(VersionSpec.parse("==1.2.0").matches("1.2.0"))
        self.assertFalse(VersionSpec.parse("==1.2.0").matches("1.2.1"))
        self.assertTrue(VersionSpec.parse("~>1.2.0").matches("1.2.9"))
        self.assertFalse(VersionSpec.parse("~>1.2.0").matches("1.3.0"))
        self.assertTrue(VersionSpec.parse("1.0.0").matches("2.0.0"))


class DiscoveryTests(unittest.TestCase):
    def test_broken_manifest_does_not_hide_valid_modules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_module(root, "alpha")
            broken = root / "broken"
            broken.mkdir()
            (broken / "module.json").write_text("{not json", encoding="utf-8")
            (root / "no_manifest").mkdir()

            result = discover_modules([root])

            self.assertEqual([item.id for item in result.manifests], ["alpha"])
            self.assertEqual(len(result.rejected), 2)
            self.assertTrue(any("not valid JSON" in item.error for item in result.rejected))

    def test_manifest_id_must_match_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = write_module(root, "alpha")
            data = json.loads((directory / "module.json").read_text(encoding="utf-8"))
            data["id"] = "beta"
            (directory / "module.json").write_text(json.dumps(data), encoding="utf-8")

            result = discover_modules([root])

            self.assertEqual(result.manifests, [])
            self.assertIn("does not match", result.rejected[0].error)

    def test_duplicate_module_id_is_rejected_once(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            write_module(Path(first), "alpha")
            write_module(Path(second), "alpha", version="2.0.0")

            result = discover_modules([Path(first), Path(second)])

            self.assertEqual([item.id for item in result.manifests], ["alpha"])
            self.assertEqual(result.manifests[0].version, "1.0.0")
            self.assertIn("Duplicate module id", result.rejected[0].error)


class DependencyTests(unittest.TestCase):
    def resolve(self, root: Path, core_version: str = SYSTEM_CORE_VERSION):
        return DependencyResolver().resolve(
            discover_modules([root]).manifests,
            core_version=core_version,
        )

    def test_dependencies_define_start_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_module(root, "base")
            write_module(root, "middle", dependencies=[{"id": "base", "version": ">=1.0.0"}])
            write_module(root, "top", dependencies=[{"id": "middle", "version": ">=1.0.0"}])

            resolution = self.resolve(root)

            self.assertEqual(resolution.order, ["base", "middle", "top"])
            self.assertEqual(resolution.issues, [])

    def test_cycle_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_module(root, "left", dependencies=[{"id": "right", "version": ">=1.0.0"}])
            write_module(root, "right", dependencies=[{"id": "left", "version": ">=1.0.0"}])

            resolution = self.resolve(root)

            self.assertEqual(resolution.order, [])
            self.assertEqual(
                {issue.reason for issue in resolution.issues},
                {"dependency_cycle"},
            )

    def test_missing_incompatible_and_cascading_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_module(root, "base", version="1.0.0")
            write_module(root, "needs_missing", dependencies=[{"id": "ghost", "version": ">=1.0.0"}])
            write_module(root, "needs_newer", dependencies=[{"id": "base", "version": ">=2.0.0"}])
            write_module(root, "cascade", dependencies=[{"id": "needs_newer", "version": ">=1.0.0"}])
            write_module(root, "turned_off", enabled=False)
            write_module(root, "needs_disabled", dependencies=[{"id": "turned_off", "version": ">=1.0.0"}])

            resolution = self.resolve(root)

            reasons = {issue.module_id: issue.reason for issue in resolution.issues}
            self.assertEqual(resolution.order, ["base"])
            self.assertEqual(resolution.disabled, ["turned_off"])
            self.assertEqual(reasons["needs_missing"], "missing_dependency")
            self.assertEqual(reasons["needs_newer"], "incompatible_dependency")
            self.assertEqual(reasons["cascade"], "dependency_unresolved")
            self.assertEqual(reasons["needs_disabled"], "dependency_disabled")

    def test_incompatible_core_requirement_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_module(root, "future", requires_core=">=99.0.0")

            resolution = self.resolve(root)

            self.assertEqual(resolution.order, [])
            self.assertEqual(resolution.issues[0].reason, "incompatible_core")


class PermissionTests(unittest.TestCase):
    def test_read_only_permissions_are_auto_granted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_module(
                root,
                "reader",
                permissions=["core.config.read", "module.database", "core.events.publish"],
            )
            manifest = discover_modules([root]).manifests[0]

            decision = PermissionBroker().evaluate(manifest)

            self.assertTrue(decision.allowed)
            self.assertEqual(decision.denied, ())

    def test_state_changing_permissions_require_action_broker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_module(root, "writer", permissions=["module.database", "filesystem.write"])
            manifest = discover_modules([root]).manifests[0]

            decision = PermissionBroker().evaluate(manifest)

            self.assertFalse(decision.allowed)
            self.assertEqual(decision.denied, ("filesystem.write",))
            self.assertIn("requires_action_broker", decision.denial_detail())


class MigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        patcher = patch(
            "sayuri_yukishiro.database.MODULE_DATA_DIR",
            Path(self._tmp.name),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def test_migrations_apply_once_and_are_idempotent(self) -> None:
        migrations = (
            Migration(1, "first", ("CREATE TABLE a (id INTEGER PRIMARY KEY)",)),
            Migration(2, "second", ("CREATE TABLE b (id INTEGER PRIMARY KEY)",)),
        )
        migrator = ModuleMigrator("demo")

        self.assertEqual(migrator.apply(migrations), [1, 2])
        self.assertEqual(migrator.apply(migrations), [])
        self.assertEqual(migrator.current_version(), 2)

    def test_newer_database_than_module_code_is_refused(self) -> None:
        migrator = ModuleMigrator("demo")
        migrator.apply(
            (
                Migration(1, "first", ("CREATE TABLE a (id INTEGER PRIMARY KEY)",)),
                Migration(2, "second", ("CREATE TABLE b (id INTEGER PRIMARY KEY)",)),
            )
        )

        with self.assertRaises(MigrationError):
            migrator.apply((Migration(1, "first", ("SELECT 1",)),))

    def test_invalid_migration_order_is_refused(self) -> None:
        with self.assertRaises(MigrationError):
            ModuleMigrator("demo").apply(
                (
                    Migration(2, "second", ("SELECT 1",)),
                    Migration(1, "first", ("SELECT 1",)),
                )
            )


class ModuleRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._module_data = tempfile.TemporaryDirectory()
        patcher = patch(
            "sayuri_yukishiro.database.MODULE_DATA_DIR",
            Path(self._module_data.name),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._module_data.cleanup)

    def make_platform(self, root: Path) -> tuple[CoreDatabase, SystemCore, CognitiveCore]:
        db = CoreDatabase(root / "core.db")
        system = SystemCore(
            db=db,
            config_path=root / "system.json",
            log_dir=root / "logs",
        )
        system.start()
        cognitive = CognitiveCore(system.api, db)
        cognitive.start()
        return db, system, cognitive

    def test_module_lifecycle_registers_and_releases_capabilities(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as mod_root:
            root = Path(tmp)
            modules_dir = Path(mod_root)
            write_module(modules_dir, "alpha", permissions=["module.database"])
            db, system, cognitive = self.make_platform(root)
            runtime = ModuleRuntime(
                system.api,
                db,
                capabilities=cognitive.capabilities,
                module_dirs=[modules_dir],
            )
            try:
                runtime.start()

                record = runtime.get("alpha")
                self.assertIsNotNone(record)
                self.assertEqual(record.state, ModuleState.RUNNING)
                self.assertEqual(record.capabilities, ["module.alpha.ping"])
                self.assertEqual(record.applied_migrations, [1])
                self.assertEqual(runtime.health()["overall"], "healthy")

                capability = cognitive.capabilities.get("module.alpha.ping")
                self.assertIsNotNone(capability)
                self.assertEqual(capability.module_id, "alpha")
                decision = cognitive.gate.decide(capability)
                self.assertTrue(decision.allowed)
                self.assertEqual(
                    capability.handler({"objective": "проверка"})["module_id"],
                    "alpha",
                )

                states = {item["module_id"]: item for item in db.list_module_states()}
                self.assertEqual(states["alpha"]["state"], "running")
                self.assertEqual(
                    [item["status"] for item in db.list_modules() if item["id"] == "alpha"],
                    ["active"],
                )

                runtime.stop()

                self.assertIsNone(cognitive.capabilities.get("module.alpha.ping"))
                self.assertEqual(runtime.get("alpha").state, ModuleState.STOPPED)
            finally:
                runtime.stop()
                cognitive.stop()
                system.stop()

    def test_module_with_denied_permission_is_blocked_and_not_started(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as mod_root:
            root = Path(tmp)
            modules_dir = Path(mod_root)
            write_module(
                modules_dir,
                "escalating",
                permissions=["module.database", "network.outbound"],
            )
            db, system, cognitive = self.make_platform(root)
            runtime = ModuleRuntime(
                system.api,
                db,
                capabilities=cognitive.capabilities,
                module_dirs=[modules_dir],
            )
            try:
                runtime.start()

                record = runtime.get("escalating")
                self.assertEqual(record.state, ModuleState.BLOCKED)
                self.assertIn("permission_denied", record.detail)
                self.assertEqual(record.denied_permissions, ("network.outbound",))
                self.assertEqual(record.capabilities, [])
                self.assertIsNone(cognitive.capabilities.get("module.escalating.ping"))
                self.assertEqual(runtime.health()["overall"], "degraded")
            finally:
                runtime.stop()
                cognitive.stop()
                system.stop()

    def test_failed_module_is_isolated_and_dependents_are_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as mod_root:
            root = Path(tmp)
            modules_dir = Path(mod_root)
            write_module(modules_dir, "broken", fail_on_start=True)
            write_module(
                modules_dir,
                "dependent",
                dependencies=[{"id": "broken", "version": ">=1.0.0"}],
            )
            write_module(modules_dir, "independent")
            db, system, cognitive = self.make_platform(root)
            runtime = ModuleRuntime(
                system.api,
                db,
                capabilities=cognitive.capabilities,
                module_dirs=[modules_dir],
            )
            try:
                runtime.start()

                self.assertEqual(runtime.get("broken").state, ModuleState.FAILED)
                self.assertEqual(runtime.get("dependent").state, ModuleState.BLOCKED)
                self.assertIn("dependency_failed", runtime.get("dependent").detail)
                self.assertEqual(runtime.get("independent").state, ModuleState.RUNNING)
                self.assertEqual(runtime.health()["overall"], "failed")

                tasks = {item["task_id"]: item for item in system.api.recoverable_tasks()}
                self.assertIn("module:broken", tasks)
                self.assertIn("broken", tasks["module:broken"]["next_action"])
            finally:
                runtime.stop()
                cognitive.stop()
                system.stop()

    def test_strict_startup_rolls_back_started_modules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as mod_root:
            root = Path(tmp)
            modules_dir = Path(mod_root)
            write_module(modules_dir, "alpha")
            write_module(modules_dir, "zeta", fail_on_start=True)
            db, system, cognitive = self.make_platform(root)
            runtime = ModuleRuntime(
                system.api,
                db,
                capabilities=cognitive.capabilities,
                module_dirs=[modules_dir],
                strict_startup=True,
            )
            try:
                with self.assertRaises(RuntimeError):
                    runtime.start()

                self.assertFalse(runtime.running)
                self.assertEqual(runtime.get("alpha").state, ModuleState.STOPPED)
                self.assertIsNone(cognitive.capabilities.get("module.alpha.ping"))
            finally:
                cognitive.stop()
                system.stop()

    def test_unhealthy_module_degrades_runtime_health(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as mod_root:
            root = Path(tmp)
            modules_dir = Path(mod_root)
            write_module(modules_dir, "sick", healthy=False)
            db, system, cognitive = self.make_platform(root)
            runtime = ModuleRuntime(
                system.api,
                db,
                capabilities=cognitive.capabilities,
                module_dirs=[modules_dir],
            )
            try:
                runtime.start()

                health = runtime.health()
                self.assertEqual(health["overall"], "degraded")
                self.assertEqual(health["running_count"], 1)
                self.assertEqual(health["healthy_count"], 0)
            finally:
                runtime.stop()
                cognitive.stop()
                system.stop()

    def test_mutation_capability_of_module_stays_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as mod_root:
            root = Path(tmp)
            modules_dir = Path(mod_root)
            write_module(
                modules_dir,
                "mutator",
                capabilities=[
                    {"name": "ping", "risk": "read_only", "handler": "ping"},
                    {"name": "apply", "risk": "mutation", "handler": "ping"},
                ],
            )
            db, system, cognitive = self.make_platform(root)
            runtime = ModuleRuntime(
                system.api,
                db,
                capabilities=cognitive.capabilities,
                module_dirs=[modules_dir],
            )
            try:
                runtime.start()

                mutation = cognitive.capabilities.get("module.mutator.apply")
                self.assertIsNotNone(mutation)
                self.assertIsNone(mutation.handler)
                decision = cognitive.gate.decide(mutation)
                self.assertFalse(decision.allowed)
                self.assertEqual(decision.reason, "requires_action_broker")
            finally:
                runtime.stop()
                cognitive.stop()
                system.stop()

    def test_module_state_survives_runtime_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as mod_root:
            root = Path(tmp)
            modules_dir = Path(mod_root)
            write_module(modules_dir, "alpha")
            db, system, cognitive = self.make_platform(root)
            try:
                first = ModuleRuntime(
                    system.api,
                    db,
                    capabilities=cognitive.capabilities,
                    module_dirs=[modules_dir],
                )
                first.start()
                self.assertEqual(first.get("alpha").applied_migrations, [1])
                first.stop()

                second = ModuleRuntime(
                    system.api,
                    db,
                    capabilities=cognitive.capabilities,
                    module_dirs=[modules_dir],
                )
                second.start()
                try:
                    record = second.get("alpha")
                    self.assertEqual(record.state, ModuleState.RUNNING)
                    self.assertEqual(record.applied_migrations, [])
                    self.assertEqual(record.schema_version, 1)
                finally:
                    second.stop()
            finally:
                cognitive.stop()
                system.stop()


class ReferenceModuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._module_data = tempfile.TemporaryDirectory()
        patcher = patch(
            "sayuri_yukishiro.database.MODULE_DATA_DIR",
            Path(self._module_data.name),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._module_data.cleanup)

    def test_bundled_system_probe_module_starts_and_serves_capability(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = CoreDatabase(root / "core.db")
            system = SystemCore(
                db=db,
                config_path=root / "system.json",
                log_dir=root / "logs",
            )
            system.start()
            cognitive = CognitiveCore(system.api, db)
            cognitive.start()
            runtime = ModuleRuntime(
                system.api,
                db,
                capabilities=cognitive.capabilities,
                module_dirs=[MODULES_DIR],
            )
            try:
                runtime.start()

                record = runtime.get("system_probe")
                self.assertIsNotNone(record)
                self.assertEqual(record.state, ModuleState.RUNNING)
                self.assertEqual(record.schema_version, 1)
                self.assertEqual(runtime.status()["version"], MODULE_RUNTIME_VERSION)
                self.assertEqual(runtime.health()["overall"], "healthy")

                capability = cognitive.capabilities.get("module.system_probe.snapshot")
                self.assertIsNotNone(capability)
                result = capability.handler({"objective": "диагностика"})
                self.assertEqual(result["module_id"], "system_probe")
                self.assertGreaterEqual(result["observations"], 1)
            finally:
                runtime.stop()
                cognitive.stop()
                system.stop()


if __name__ == "__main__":
    unittest.main()
