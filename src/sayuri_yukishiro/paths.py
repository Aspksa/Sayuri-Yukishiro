from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _runtime_data_dir() -> Path:
    raw = os.environ.get("SAYURI_DATA_DIR", "").strip()
    if not raw:
        return PROJECT_ROOT / "data"
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve(strict=False)


DATA_DIR = _runtime_data_dir()
CORE_DATA_DIR = DATA_DIR / "core"
MODULE_DATA_DIR = DATA_DIR / "modules"
LOG_DIR = DATA_DIR / "logs"
CACHE_DIR = DATA_DIR / "cache"
UPDATE_DIR = DATA_DIR / "update"
WEB_DIR = PROJECT_ROOT / "web"
VERSION_FILE = PROJECT_ROOT / "VERSION"


def ensure_runtime_dirs() -> None:
    for path in (DATA_DIR, CORE_DATA_DIR, MODULE_DATA_DIR, LOG_DIR, CACHE_DIR, UPDATE_DIR):
        path.mkdir(parents=True, exist_ok=True)


def project_version() -> str:
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0-unknown"
