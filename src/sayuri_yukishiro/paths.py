from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
CORE_DATA_DIR = DATA_DIR / "core"
MODULE_DATA_DIR = DATA_DIR / "modules"
LOG_DIR = DATA_DIR / "logs"
CACHE_DIR = DATA_DIR / "cache"
WEB_DIR = PROJECT_ROOT / "web"
VERSION_FILE = PROJECT_ROOT / "VERSION"


def ensure_runtime_dirs() -> None:
    for path in (DATA_DIR, CORE_DATA_DIR, MODULE_DATA_DIR, LOG_DIR, CACHE_DIR):
        path.mkdir(parents=True, exist_ok=True)


def project_version() -> str:
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0-unknown"
