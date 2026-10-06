from __future__ import annotations

import shutil
import socket
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from .cognitive.engine import CognitiveCore
from .core.runtime import SystemCore
from .database import CoreDatabase
from .paths import DATA_DIR, PROJECT_ROOT, ensure_runtime_dirs


@dataclass
class Check:
    name: str
    ok: bool
    severity: str
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


def _check_python() -> Check:
    version = sys.version_info
    ok = version >= (3, 11)
    return Check(
        "python",
        ok,
        "fatal" if not ok else "info",
        f"Python {version.major}.{version.minor}.{version.micro}; required >= 3.11",
    )


def _check_paths() -> Check:
    try:
        ensure_runtime_dirs()
        probe = DATA_DIR / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return Check("storage", True, "info", f"Writable project storage: {DATA_DIR}")
    except OSError as exc:
        return Check("storage", False, "fatal", f"Storage is not writable: {exc}")


def _check_database() -> Check:
    try:
        db = CoreDatabase()
        db.initialize()
        result = db.quick_check()
        return Check(
            "database",
            result.lower() == "ok",
            "fatal" if result.lower() != "ok" else "info",
            f"SQLite quick_check: {result}; {db.path}",
        )
    except Exception as exc:
        return Check("database", False, "fatal", f"SQLite initialization failed: {exc}")


def _check_cores() -> list[Check]:
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = CoreDatabase(root / "core-smoke.db")
            core = SystemCore(
                db=db,
                config_path=root / "system.json",
                log_dir=root / "logs",
                update_dir=root / "update",
            )
            core.start()
            system_status = core.status()

            cognitive = CognitiveCore(core.api, db)
            cognitive.start()
            session = cognitive.create_session(
                "Проверь состояние когнитивного ядра",
                context={"project": "diagnostics"},
            )
            completed = cognitive.run_safe(session.id)
            cognitive_status = cognitive.status()
            receipt_count = len(cognitive.receipts(session.id))
            cognitive.stop()
            core.stop()

        system_healthy = system_status["health"]["overall"] == "healthy"
        cognitive_healthy = (
            cognitive_status["running"]
            and completed.status == "completed"
            and completed.verification.complete
            and receipt_count == len(completed.plan.steps)
        )
        return [
            Check(
                "system_core",
                system_healthy,
                "fatal" if not system_healthy else "info",
                (
                    f"Core {system_status['core_version']}; "
                    f"services={system_status['health']['healthy_count']}/"
                    f"{system_status['health']['service_count']}"
                ),
            ),
            Check(
                "cognitive_core",
                cognitive_healthy,
                "fatal" if not cognitive_healthy else "info",
                (
                    f"Cognitive {cognitive_status['version']}; "
                    f"provider={cognitive_status['provider']}; "
                    f"receipts={receipt_count}"
                ),
            ),
        ]
    except Exception as exc:
        detail = f"Core diagnostics failed: {exc}"
        return [
            Check("system_core", False, "fatal", detail),
            Check("cognitive_core", False, "fatal", detail),
        ]


def _check_git() -> Check:
    git = shutil.which("git")
    if git:
        return Check("git", True, "info", f"Git available: {git}")
    return Check(
        "git",
        False,
        "warning",
        "Git not found. Runtime can start, but «Обновления проекта» is unavailable.",
    )


def _check_port(port: int) -> Check:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        in_use = sock.connect_ex(("127.0.0.1", port)) == 0
    if in_use:
        return Check(
            "port",
            False,
            "warning",
            f"Port {port} is already in use. An existing Sayuri instance may already be running.",
        )
    return Check("port", True, "info", f"Port {port} is available.")


def run_diagnostics(port: int = 8765) -> list[Check]:
    core_checks = _check_cores()
    return [
        Check("project_root", True, "info", str(PROJECT_ROOT)),
        _check_python(),
        _check_paths(),
        _check_database(),
        *core_checks,
        _check_git(),
        _check_port(port),
    ]


def has_fatal_failures(checks: list[Check]) -> bool:
    return any((not check.ok) and check.severity == "fatal" for check in checks)


def print_report(checks: list[Check]) -> None:
    print("Sayuri Yukishiro diagnostics")
    print("-" * 60)
    for check in checks:
        if check.ok:
            mark = "OK"
        elif check.severity == "warning":
            mark = "WARN"
        else:
            mark = "FAIL"
        print(f"[{mark:<4}] {check.name:<14} {check.detail}")
    print("-" * 60)
