from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from .update_state import (
    append_update_log,
    load_update_state,
    save_update_state,
    utc_now,
)


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _git(
    root: Path,
    *args: str,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


class UpdateHelper:
    def __init__(self, plan_file: Path) -> None:
        self.plan_file = plan_file
        self.plan = json.loads(plan_file.read_text(encoding="utf-8"))
        self.root = Path(self.plan["root"]).resolve()
        self.state_path = Path(self.plan["state_path"])
        self.backup_path = Path(self.plan["backup_path"])
        self.python = str(self.plan["python_executable"])
        self.parent_pid = int(self.plan["parent_pid"])
        self.before_sha = str(self.plan["before_sha"])
        self.target_sha = str(self.plan["target_sha"])
        self.port = int(self.plan.get("port", 8765))
        self.shutdown_token = str(self.plan.get("shutdown_token", ""))
        self.log_path = self.state_path.parent / "helper.log"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _log(self, message: str, *, level: str = "info") -> None:
        state = load_update_state(self.state_path)
        state = append_update_log(state, message, level=level)
        save_update_state(state, self.state_path)
        with self.log_path.open("a", encoding="utf-8") as stream:
            stream.write(f"{utc_now()} | {level.upper()} | {message}\n")

    def _phase(
        self,
        phase: str,
        progress: int,
        message: str,
        **extra: Any,
    ) -> None:
        state = load_update_state(self.state_path)
        state["phase"] = phase
        state["progress"] = max(0, min(100, int(progress)))
        state["message"] = message
        state.update(extra)
        state = append_update_log(state, message)
        save_update_state(state, self.state_path)
        with self.log_path.open("a", encoding="utf-8") as stream:
            stream.write(f"{utc_now()} | INFO | {message}\n")

    def wait_for_parent(self, timeout: float = 60.0) -> None:
        self._phase(
            "waiting_for_shutdown",
            12,
            "Ожидаю мягкой остановки Sayuri.",
        )
        deadline = time.monotonic() + timeout
        while _process_alive(self.parent_pid):
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    "Sayuri did not stop before update timeout."
                )
            time.sleep(0.25)

    def backup(self) -> None:
        self._phase(
            "backing_up",
            20,
            "Создаю резервную копию текущего tracked-состояния проекта.",
        )
        self.backup_path.parent.mkdir(parents=True, exist_ok=True)
        proc = _git(
            self.root,
            "archive",
            "--format=zip",
            f"--output={self.backup_path}",
            self.before_sha,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                proc.stderr.strip() or "Git backup archive failed."
            )
        if not self.backup_path.is_file():
            raise RuntimeError("Backup archive was not created.")
        state = load_update_state(self.state_path)
        state["backup_path"] = str(self.backup_path)
        save_update_state(state, self.state_path)
        self._log(f"Backup создан: {self.backup_path}")

    def apply(self) -> None:
        self._phase(
            "applying",
            35,
            "Применяю проверенный fast-forward update.",
        )
        dirty = _git(self.root, "status", "--porcelain")
        if dirty.returncode != 0:
            raise RuntimeError("Unable to inspect worktree before apply.")
        if dirty.stdout.strip():
            raise RuntimeError(
                "Worktree changed after update check; apply refused."
            )

        head = _git(self.root, "rev-parse", "HEAD")
        current = head.stdout.strip() if head.returncode == 0 else ""
        if current != self.before_sha:
            raise RuntimeError(
                "HEAD changed after update check; apply refused."
            )

        ancestor = _git(
            self.root,
            "merge-base",
            "--is-ancestor",
            self.before_sha,
            self.target_sha,
        )
        if ancestor.returncode != 0:
            raise RuntimeError(
                "Target commit is not a fast-forward descendant."
            )

        merged = _git(
            self.root,
            "merge",
            "--ff-only",
            "--quiet",
            self.target_sha,
        )
        if merged.returncode != 0:
            raise RuntimeError(
                merged.stderr.strip() or "Fast-forward apply failed."
            )
        self._log(
            f"Проект обновлён {self.before_sha[:12]} -> "
            f"{self.target_sha[:12]}."
        )

    def verify(self) -> None:
        self._phase(
            "verifying",
            50,
            "Проверяю обновлённый проект перед перезапуском.",
        )
        env = os.environ.copy()
        env["PYTHONPATH"] = str(self.root / "src")
        commands = [
            (
                58,
                [self.python, "scripts/validate_update_protocol.py"],
                "Протокол обновлений",
            ),
            (
                66,
                [
                    self.python,
                    "-m",
                    "compileall",
                    "-q",
                    "src",
                    "scripts",
                    "tests",
                ],
                "Компиляция Python",
            ),
            (
                74,
                [
                    self.python,
                    "-m",
                    "unittest",
                    "discover",
                    "-s",
                    "tests",
                    "-v",
                ],
                "Unit/regression tests",
            ),
            (
                82,
                [
                    self.python,
                    "-m",
                    "sayuri_yukishiro.main",
                    "--preflight",
                    "--no-update",
                ],
                "Runtime preflight",
            ),
        ]
        with self.log_path.open("a", encoding="utf-8") as output:
            for progress, command, label in commands:
                self._phase(
                    "verifying",
                    progress,
                    f"Проверка: {label}.",
                )
                proc = subprocess.run(
                    command,
                    cwd=self.root,
                    env=env,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    timeout=300,
                    check=False,
                )
                if proc.returncode != 0:
                    raise RuntimeError(
                        f"Post-update verification failed: {label}."
                    )

    def _start_core(self) -> subprocess.Popen[Any]:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(self.root / "src")
        env["SAYURI_PORT"] = str(self.port)
        env["SAYURI_SHUTDOWN_TOKEN"] = self.shutdown_token
        command = [
            self.python,
            "-m",
            "sayuri_yukishiro.main",
            "--serve",
        ]
        kwargs: dict[str, Any] = {
            "cwd": self.root,
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

    def _wait_health(
        self,
        process: subprocess.Popen[Any],
        timeout: float = 25.0,
    ) -> dict[str, Any]:
        url = f"http://127.0.0.1:{self.port}/api/health"
        deadline = time.monotonic() + timeout
        last_error = ""
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(
                    f"Restarted core exited with code {process.returncode}."
                )
            try:
                with urllib.request.urlopen(url, timeout=1.0) as response:
                    payload = json.loads(
                        response.read().decode("utf-8")
                    )
                if payload.get("status") == "ok":
                    return payload
                last_error = str(payload)
            except Exception as exc:
                last_error = str(exc)
            time.sleep(0.5)
        raise TimeoutError(
            f"Restarted core did not become healthy: {last_error}"
        )

    @staticmethod
    def _terminate_process(process: subprocess.Popen[Any]) -> None:
        if process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def restart(self) -> subprocess.Popen[Any]:
        self._phase(
            "restarting",
            90,
            "Перезапускаю Sayuri после обновления.",
        )
        process = self._start_core()
        health = self._wait_health(process)
        state = load_update_state(self.state_path)
        state.update(
            {
                "phase": "completed",
                "progress": 100,
                "message": "Обновление успешно установлено.",
                "current_version": (
                    health.get("version")
                    or self.plan.get("available_version")
                ),
                "available_version": health.get("version"),
                "update_available": False,
                "can_apply": False,
                "current_sha": self.target_sha,
                "target_sha": self.target_sha,
                "restart_pid": process.pid,
                "last_update": utc_now(),
                "rollback": None,
            }
        )
        state = append_update_log(
            state,
            f"Sayuri успешно перезапущена, PID {process.pid}.",
        )
        save_update_state(state, self.state_path)
        return process

    def rollback(self, reason: str) -> subprocess.Popen[Any] | None:
        self._phase(
            "rolling_back",
            86,
            f"Проверка не пройдена. Выполняю откат: {reason}",
        )
        reset = _git(
            self.root,
            "reset",
            "--hard",
            self.before_sha,
        )
        if reset.returncode != 0:
            state = load_update_state(self.state_path)
            state.update(
                {
                    "phase": "failed",
                    "progress": 100,
                    "message": "Автоматический откат не удался.",
                    "rollback": {
                        "status": "failed",
                        "reason": reason,
                        "error": (
                            reset.stderr.strip()
                            or "git reset --hard failed"
                        ),
                    },
                }
            )
            state = append_update_log(
                state,
                state["message"],
                level="error",
            )
            save_update_state(state, self.state_path)
            return None

        self._log(
            f"Откат выполнен до {self.before_sha[:12]}.",
            level="warning",
        )
        process = self._start_core()
        try:
            health = self._wait_health(process)
        except Exception as exc:
            self._terminate_process(process)
            state = load_update_state(self.state_path)
            state.update(
                {
                    "phase": "failed",
                    "progress": 100,
                    "message": (
                        "Откат файлов выполнен, но Sayuri не "
                        "перезапустилась."
                    ),
                    "rollback": {
                        "status": "restart_failed",
                        "reason": reason,
                        "error": str(exc),
                    },
                }
            )
            state = append_update_log(
                state,
                state["message"],
                level="error",
            )
            save_update_state(state, self.state_path)
            return None

        state = load_update_state(self.state_path)
        state.update(
            {
                "phase": "rolled_back",
                "progress": 100,
                "message": (
                    "Обновление отменено: восстановлена предыдущая версия."
                ),
                "current_version": (
                    health.get("version")
                    or self.plan.get("current_version")
                ),
                "update_available": True,
                "can_apply": False,
                "current_sha": self.before_sha,
                "restart_pid": process.pid,
                "last_update": utc_now(),
                "rollback": {
                    "status": "completed",
                    "reason": reason,
                },
            }
        )
        state = append_update_log(
            state,
            f"Предыдущая версия перезапущена, PID {process.pid}.",
            level="warning",
        )
        save_update_state(state, self.state_path)
        return process

    def run(self) -> int:
        updated = False
        try:
            self.wait_for_parent()
            self.backup()
            self.apply()
            updated = True
            self.verify()
            self.restart()
            return 0
        except Exception as exc:
            self._log(f"Update helper error: {exc}", level="error")
            if updated:
                self.rollback(str(exc))
            else:
                state = load_update_state(self.state_path)
                state.update(
                    {
                        "phase": "failed",
                        "progress": 100,
                        "message": f"Обновление не применено: {exc}",
                        "can_apply": False,
                        "rollback": {
                            "status": "not_required",
                            "reason": str(exc),
                        },
                    }
                )
                state = append_update_log(
                    state,
                    state["message"],
                    level="error",
                )
                save_update_state(state, self.state_path)
            return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sayuri-update-helper")
    parser.add_argument("--plan", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return UpdateHelper(Path(args.plan)).run()


if __name__ == "__main__":
    sys.exit(main())
