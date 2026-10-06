from __future__ import annotations

import json
import os
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from ..paths import DATA_DIR, PROJECT_ROOT, UPDATE_DIR, project_version
from ..process_utils import process_alive
from ..update_state import (
    append_update_log,
    load_update_state,
    save_update_state,
    utc_now,
)
from ..updater import UpdateInspection, inspect_update
from .events import EventBus
from .jobs import JobManager
from .service import ManagedService


_BUSY_PHASES = {
    "checking",
    "prepared",
    "waiting_for_shutdown",
    "backing_up",
    "applying",
    "verifying",
    "rolling_back",
    "restarting",
}


class UpdateService(ManagedService):
    name = "update_service"

    def __init__(
        self,
        jobs: JobManager,
        events: EventBus,
        *,
        root: Path = PROJECT_ROOT,
        update_dir: Path = UPDATE_DIR,
        data_dir: Path = DATA_DIR,
        port: int = 8765,
    ) -> None:
        super().__init__()
        self._jobs = jobs
        self._events = events
        self._root = root
        self._update_dir = update_dir
        self._data_dir = data_dir
        self._state_path = update_dir / "status.json"
        self._plan_path = update_dir / "apply-plan.json"
        self._port = port
        self._state_lock = RLock()

    def on_start(self) -> None:
        self._update_dir.mkdir(parents=True, exist_ok=True)
        state = load_update_state(self._state_path)
        state["current_version"] = project_version()

        phase = str(state.get("phase") or "idle")
        if phase in _BUSY_PHASES:
            helper_pid = int(state.get("helper_pid") or 0)
            if helper_pid > 0 and process_alive(helper_pid):
                state["message"] = (
                    "Внешний update-helper продолжает операцию; "
                    "новая проверка временно заблокирована."
                )
                state = append_update_log(
                    state,
                    f"Найден активный update-helper PID {helper_pid}.",
                )
            else:
                state["phase"] = "failed"
                state["progress"] = 100
                state["can_apply"] = False
                state["helper_pid"] = None
                state["message"] = (
                    "Предыдущая операция обновления была прервана. "
                    "Запустите проверку обновлений заново."
                )
                state["rollback"] = {
                    "status": "interrupted",
                    "recoverable": True,
                }
                state = append_update_log(
                    state,
                    state["message"],
                    level="warning",
                )

        save_update_state(state, self._state_path)

    def status(self) -> dict[str, Any]:
        with self._state_lock:
            state = load_update_state(self._state_path)
            state["current_version"] = project_version()
            return deepcopy(state)

    def request_check(self) -> str:
        with self._state_lock:
            state = load_update_state(self._state_path)
            if state.get("phase") in _BUSY_PHASES:
                raise RuntimeError(
                    f"Update operation is busy: {state.get('phase')}"
                )
            state["phase"] = "checking"
            state["progress"] = 5
            state["message"] = "Проверяю доступные обновления…"
            state["can_apply"] = False
            state["helper_pid"] = None
            state = append_update_log(state, "Запущена проверка обновлений.")
            save_update_state(state, self._state_path)

        job_id = self._jobs.submit("update.check", self._check_worker)
        self._events.publish(
            "update.check.started",
            {"job_id": job_id},
            source="core",
        )
        return job_id

    def _check_worker(self) -> dict[str, Any]:
        try:
            inspection = inspect_update(fetch=True, root=self._root)
            state = self._state_from_inspection(inspection)
            self._events.publish(
                "update.check.completed",
                {
                    "status": inspection.status,
                    "update_available": inspection.update_available,
                    "available_version": inspection.available_version,
                },
                source="core",
            )
            return state
        except Exception as exc:
            with self._state_lock:
                state = load_update_state(self._state_path)
                state["phase"] = "error"
                state["progress"] = 100
                state["can_apply"] = False
                state["message"] = f"Ошибка проверки обновлений: {exc}"
                state = append_update_log(
                    state,
                    state["message"],
                    level="error",
                )
                save_update_state(state, self._state_path)
            raise

    def _state_from_inspection(
        self,
        inspection: UpdateInspection,
    ) -> dict[str, Any]:
        phase_map = {
            "available": "available",
            "up_to_date": "up_to_date",
            "blocked": "blocked",
            "diverged": "blocked",
            "unavailable": "unavailable",
            "error": "error",
        }
        upstream = inspection.upstream
        with self._state_lock:
            state = load_update_state(self._state_path)
            state.update(
                {
                    "phase": phase_map.get(inspection.status, inspection.status),
                    "progress": 100,
                    "message": inspection.message,
                    "current_version": (
                        inspection.current_version or project_version()
                    ),
                    "available_version": inspection.available_version,
                    "update_available": inspection.update_available,
                    "can_apply": inspection.can_apply,
                    "dirty": inspection.dirty,
                    "diverged": inspection.diverged,
                    "branch": upstream.branch if upstream else None,
                    "upstream": upstream.upstream_ref if upstream else None,
                    "current_sha": inspection.current_sha,
                    "target_sha": inspection.target_sha,
                    "changes": list(inspection.changes),
                    "last_check": utc_now(),
                    "helper_pid": None,
                }
            )
            if inspection.update_available:
                version = inspection.available_version or "неизвестная версия"
                state = append_update_log(
                    state,
                    f"Доступно обновление: {version}.",
                )
            elif inspection.status == "up_to_date":
                state = append_update_log(
                    state,
                    "Установлена актуальная версия.",
                )
            else:
                level = "error" if inspection.status == "error" else "warning"
                state = append_update_log(
                    state,
                    inspection.message,
                    level=level,
                )
            save_update_state(state, self._state_path)
            return deepcopy(state)

    def prepare_apply(self) -> dict[str, Any]:
        with self._state_lock:
            state = load_update_state(self._state_path)
            if state.get("phase") != "available":
                raise RuntimeError("No checked update is ready to apply.")
            if not state.get("can_apply"):
                raise RuntimeError(
                    "Update is blocked by the current repository state."
                )

        recheck = inspect_update(fetch=False, root=self._root)
        if not recheck.can_apply:
            self._state_from_inspection(recheck)
            raise RuntimeError(recheck.message)

        with self._state_lock:
            state = load_update_state(self._state_path)
            expected_target = state.get("target_sha")
            if not expected_target or recheck.target_sha != expected_target:
                self._state_from_inspection(recheck)
                raise RuntimeError(
                    "Upstream changed after the last check; check updates again."
                )

            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup_path = self._update_dir / (
                f"backup-{stamp}-{str(recheck.current_sha)[:12]}.zip"
            )
            db_backup_dir = self._update_dir / (
                f"db-backup-{stamp}-{str(recheck.current_sha)[:12]}"
            )
            plan = {
                "schema_version": 2,
                "root": str(self._root),
                "data_dir": str(self._data_dir),
                "state_path": str(self._state_path),
                "backup_path": str(backup_path),
                "db_backup_dir": str(db_backup_dir),
                "parent_pid": os.getpid(),
                "python_executable": sys.executable,
                "port": self._port,
                "shutdown_token": os.environ.get(
                    "SAYURI_SHUTDOWN_TOKEN", ""
                ),
                "before_sha": recheck.current_sha,
                "target_sha": recheck.target_sha,
                "upstream": (
                    recheck.upstream.upstream_ref
                    if recheck.upstream
                    else None
                ),
                "current_version": recheck.current_version,
                "available_version": recheck.available_version,
                "created_at": utc_now(),
            }
            self._update_dir.mkdir(parents=True, exist_ok=True)
            temp_plan = self._plan_path.with_suffix(".json.tmp")
            temp_plan.write_text(
                json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temp_plan, self._plan_path)

            state["phase"] = "prepared"
            state["progress"] = 8
            state["message"] = "План обновления подготовлен."
            state["can_apply"] = False
            state["backup_path"] = str(backup_path)
            state["database_backup_path"] = str(db_backup_dir)
            state["plan_path"] = str(self._plan_path)
            state = append_update_log(
                state,
                "План обновления подготовлен; запускается внешний helper.",
            )
            save_update_state(state, self._state_path)

        helper = self._spawn_helper(self._plan_path)
        with self._state_lock:
            state = load_update_state(self._state_path)
            state["phase"] = "waiting_for_shutdown"
            state["progress"] = 10
            state["message"] = (
                "Helper запущен. Sayuri завершает работу перед заменой файлов."
            )
            state["helper_pid"] = helper.pid
            state = append_update_log(
                state,
                f"Update helper запущен, PID {helper.pid}.",
            )
            save_update_state(state, self._state_path)

        self._events.publish(
            "update.apply.prepared",
            {
                "helper_pid": helper.pid,
                "target_sha": recheck.target_sha,
                "available_version": recheck.available_version,
            },
            source="core",
        )
        return self.status()

    def _spawn_helper(self, plan: Path) -> subprocess.Popen[Any]:
        command = [
            sys.executable,
            "-m",
            "sayuri_yukishiro.update_helper",
            "--plan",
            str(plan),
        ]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(self._root / "src")
        kwargs: dict[str, Any] = {
            "cwd": self._root,
            "env": env,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if os.name == "nt":
            kwargs["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.DETACHED_PROCESS
            )
        else:
            kwargs["start_new_session"] = True
        return subprocess.Popen(command, **kwargs)
