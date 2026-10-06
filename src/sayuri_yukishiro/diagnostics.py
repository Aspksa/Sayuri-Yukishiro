from __future__ import annotations

import shutil
import socket
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

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


def _check_system_core() -> Check:
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = CoreDatabase(root / "core-smoke.db")
            core = SystemCore(
                db=db,
                config_path=root / "system.json",
                log_dir=root / "logs",
            )
            core.start()
            status = core.status()
            core.stop()
        healthy = status["health"]["overall"] == "healthy"
        return Check(
            "system_core",
            healthy,
            "fatal" if not healthy else "info",
            (
                f"Core {status['core_version']}; "
                f"services={status['health']['healthy_count']}/"
                f"{status['health']['service_count']}"
            ),
        )
    except Exception as exc:
        return Check("system_core", False, "fatal", f"System core failed: {exc}")


def _check_git() -> Check:
    git = shutil.which("git")
    if git:
        return Check("git", True, "info", f"Git available: {git}")
    return Check(
        "git",
        False,
        "warning",
        "Git not found. Runtime can start, but Git auto-update is unavailable.",
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
    return [
        Check("project_root", True, "info", str(PROJECT_ROOT)),
        _check_python(),
        _check_paths(),
        _check_database(),
        _check_system_core(),
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
