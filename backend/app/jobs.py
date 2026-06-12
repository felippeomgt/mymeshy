"""Job manager: a single worker thread serializes GPU work; job records are
kept in memory and persisted to data/jobs.json so history survives restarts."""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from typing import Callable, Optional

from .config import get_settings

log = logging.getLogger("mymeshy.jobs")


@dataclass
class Job:
    id: str
    type: str  # text_to_3d | image_to_3d | texture
    params: dict
    status: str = "queued"  # queued | running | done | error | cancelled
    stage: str = ""
    progress: float = 0.0
    message: str = ""
    error: Optional[str] = None
    asset_id: Optional[str] = None
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))

    def public(self) -> dict:
        return asdict(self)


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._cancel_flags: dict[str, threading.Event] = {}
        self._queue: "queue.Queue[tuple[Job, Callable]]" = queue.Queue()
        self._lock = threading.Lock()
        self._worker = threading.Thread(target=self._run, daemon=True, name="mymeshy-worker")
        self._load_history()
        self._worker.start()

    # ---- persistence -----------------------------------------------------
    def _load_history(self) -> None:
        p = get_settings().jobs_file
        if not p.is_file():
            return
        try:
            for d in json.loads(p.read_text(encoding="utf-8")):
                if d.get("status") in ("queued", "running"):
                    d["status"] = "error"
                    d["error"] = "Backend restarted while the job was running"
                job = Job(**{k: v for k, v in d.items() if k in Job.__dataclass_fields__})
                self._jobs[job.id] = job
                self._order.append(job.id)
        except (json.JSONDecodeError, TypeError) as exc:
            log.warning("Could not load job history: %s", exc)

    def _save(self) -> None:
        with self._lock:
            data = [self._jobs[i].public() for i in self._order[-200:]]
        try:
            get_settings().jobs_file.write_text(json.dumps(data, indent=1), encoding="utf-8")
        except OSError as exc:
            log.warning("Could not persist jobs: %s", exc)

    # ---- public API --------------------------------------------------------
    def submit(self, job_type: str, params: dict, work: Callable[[Job, Callable, Callable], dict]) -> Job:
        """``work(job, progress_cb, cancelled) -> asset meta dict``"""
        job = Job(id=uuid.uuid4().hex[:12], type=job_type, params=params)
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
            self._cancel_flags[job.id] = threading.Event()
        self._queue.put((job, work))
        self._save()
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def list(self) -> list[dict]:
        with self._lock:
            return [self._jobs[i].public() for i in reversed(self._order)]

    def cancel(self, job_id: str) -> Optional[Job]:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        flag = self._cancel_flags.get(job_id)
        if flag is not None:
            flag.set()
        if job.status == "queued":
            job.status = "cancelled"
            job.message = "Cancelled before start"
            self._save()
        return job

    # ---- worker ------------------------------------------------------------
    def _run(self) -> None:
        while True:
            job, work = self._queue.get()
            flag = self._cancel_flags[job.id]
            if flag.is_set() or job.status == "cancelled":
                continue

            job.status = "running"
            job.message = "Starting"
            self._save()

            def progress_cb(p: float, stage: str, message: str) -> None:
                job.progress = round(p, 4)
                job.stage = stage
                job.message = message

            try:
                meta = work(job, progress_cb, flag.is_set)
                job.asset_id = meta["id"]
                job.status = "done"
                job.progress = 1.0
                job.stage = "done"
                job.message = "Asset ready"
            except Exception as exc:
                from .pipeline.runner import JobCancelled

                if isinstance(exc, JobCancelled) or flag.is_set():
                    job.status = "cancelled"
                    job.message = "Cancelled"
                else:
                    log.error("Job %s failed:\n%s", job.id, traceback.format_exc())
                    job.status = "error"
                    job.error = f"{type(exc).__name__}: {exc}"
                    job.message = "Failed"
            finally:
                self._save()


_manager: Optional[JobManager] = None


def get_job_manager() -> JobManager:
    global _manager
    if _manager is None:
        _manager = JobManager()
    return _manager
