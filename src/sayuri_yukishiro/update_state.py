from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import UPDATE_DIR


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def default_update_state() -> dict[str, Any]:
    return {
        "phase": "idle",
        "progress": 0,
        "message": "Обновления ещё не проверялись.",
        "current_version": None,
        "available_version": None,
        "update_available": False,
        "can_apply": False,
        "dirty": False,
        "diverged": False,
        "branch": None,
        "upstream": None,
        "current_sha": None,
        "target_sha": None,
        "changes": [],
        "backup_path": None,
        "plan_path": None,
        "helper_pid": None,
        "restart_pid": None,
        "last_check": None,
        "last_update": None,
        "rollback": None,
        "log": [],
    }


def state_path() -> Path:
    return UPDATE_DIR / "status.json"


def plan_path() -> Path:
    return UPDATE_DIR / "apply-plan.json"


def helper_log_path() -> Path:
    return UPDATE_DIR / "helper.log"


def load_update_state(path: Path | None = None) -> dict[str, Any]:
    target = path or state_path()
    if not target.is_file():
        return default_update_state()
    try:
        loaded = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_update_state()
    if not isinstance(loaded, dict):
        return default_update_state()

    state = default_update_state()
    state.update(loaded)
    if not isinstance(state.get("changes"), list):
        state["changes"] = []
    if not isinstance(state.get("log"), list):
        state["log"] = []
    return state


def save_update_state(
    state: dict[str, Any],
    path: Path | None = None,
) -> None:
    target = path or state_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    temp.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(temp, target)


def append_update_log(
    state: dict[str, Any],
    message: str,
    *,
    level: str = "info",
    limit: int = 200,
) -> dict[str, Any]:
    copied = deepcopy(state)
    entries = list(copied.get("log", []))
    entries.append(
        {
            "time": utc_now(),
            "level": level,
            "message": message,
        }
    )
    copied["log"] = entries[-max(1, limit) :]
    return copied
