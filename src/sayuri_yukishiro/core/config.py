from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Any

from .service import ManagedService


DEFAULT_CONFIG: dict[str, Any] = {
    "core": {
        "max_workers": 4,
        "job_history_limit": 500,
        "recovery_enabled": True,
    },
    "logging": {"level": "INFO", "max_bytes": 2000000, "backup_count": 3},
}


class ConfigurationService(ManagedService):
    name = "configuration"

    def __init__(self, config_path: Path | None = None) -> None:
        super().__init__()
        self._config_path = config_path
        self._data: dict[str, Any] = deepcopy(DEFAULT_CONFIG)
        self._data_lock = RLock()

    def on_start(self) -> None:
        data = deepcopy(DEFAULT_CONFIG)
        if self._config_path is not None and self._config_path.is_file():
            loaded = json.loads(self._config_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("System configuration root must be an object")
            self._deep_merge(data, loaded)

        if os.environ.get("SAYURI_CORE_MAX_WORKERS"):
            data["core"]["max_workers"] = int(os.environ["SAYURI_CORE_MAX_WORKERS"])
        if os.environ.get("SAYURI_JOB_HISTORY_LIMIT"):
            data["core"]["job_history_limit"] = int(os.environ["SAYURI_JOB_HISTORY_LIMIT"])
        if os.environ.get("SAYURI_RECOVERY_ENABLED"):
            data["core"]["recovery_enabled"] = os.environ["SAYURI_RECOVERY_ENABLED"].strip().lower() not in {"0","false","no","off"}
        if os.environ.get("SAYURI_LOG_LEVEL"):
            data["logging"]["level"] = os.environ["SAYURI_LOG_LEVEL"].upper()

        with self._data_lock:
            self._data = data

    def get(self, path: str, default: Any = None) -> Any:
        with self._data_lock:
            current: Any = self._data
            for part in path.split("."):
                if not isinstance(current, dict) or part not in current:
                    return default
                current = current[part]
            return deepcopy(current)

    @classmethod
    def _deep_merge(cls, target: dict[str, Any], source: dict[str, Any]) -> None:
        for key, value in source.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                cls._deep_merge(target[key], value)
            else:
                target[key] = value
