from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Callable
from uuid import uuid4

from ..database import CoreDatabase
from .service import ManagedService


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class JobStatus:
    id: str
    name: str
    status: str
    created_at: str
    updated_at: str
    result: Any = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class JobManager(ManagedService):
    name = "job_manager"

    def __init__(self, db: CoreDatabase, max_workers: int = 4) -> None:
        super().__init__()
        self._db = db
        self._max_workers = max(1, int(max_workers))
        self._executor: ThreadPoolExecutor | None = None
        self._jobs: dict[str, JobStatus] = {}
        self._futures: dict[str, Future[Any]] = {}
        self._jobs_lock = RLock()

    def on_start(self) -> None:
        self._db.mark_unfinished_jobs_interrupted()
        self._executor = ThreadPoolExecutor(
            max_workers=self._max_workers,
            thread_name_prefix="sayuri-core",
        )

    def on_stop(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=True, cancel_futures=False)
            self._executor = None

    def submit(
        self,
        name: str,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> str:
        executor = self._executor
        if executor is None:
            raise RuntimeError("Job manager is not running")

        job_id = str(uuid4())
        now = _utc_now()
        item = JobStatus(job_id, name, "pending", now, now)
        with self._jobs_lock:
            self._jobs[job_id] = item
        self._db.create_core_job(job_id, name, "pending")

        future = executor.submit(self._run_job, job_id, func, args, kwargs)
        with self._jobs_lock:
            self._futures[job_id] = future
        return job_id

    def _run_job(
        self,
        job_id: str,
        func: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        self._update(job_id, "running")
        try:
            result = func(*args, **kwargs)
        except Exception as exc:
            self._update(job_id, "failed", error=str(exc))
            raise
        self._update(job_id, "completed", result=result)
        return result

    def _update(
        self,
        job_id: str,
        status: str,
        *,
        result: Any = None,
        error: str | None = None,
    ) -> None:
        with self._jobs_lock:
            item = self._jobs[job_id]
            item.status = status
            item.updated_at = _utc_now()
            item.result = result
            item.error = error
        self._db.update_core_job(job_id, status, result=result, error=error)

    def wait(self, job_id: str, timeout: float | None = None) -> Any:
        with self._jobs_lock:
            future = self._futures[job_id]
        return future.result(timeout=timeout)

    def get(self, job_id: str) -> dict[str, Any]:
        with self._jobs_lock:
            return self._jobs[job_id].to_dict()

    def snapshot(self) -> list[dict[str, Any]]:
        with self._jobs_lock:
            return [item.to_dict() for item in self._jobs.values()]
