"""Long operations return 202 + a job id (SPEC §12.1); the client polls `/jobs/{job_id}`.

A thread pool in the same process — no Celery, no Redis (§16.7). Screening is numpy-heavy and
releases the GIL in the inner loops, so a worker thread is enough for the one or two concurrent
screens a demo ever runs. `progress` and `stage` carry the real stage name so the UI can show
"screening pairs 41,203 / 2,001,000" instead of an indeterminate spinner (§13.10).
"""
from __future__ import annotations

import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="oci-job")
_LOCK = threading.RLock()


@dataclass
class Job:
    job_id: str
    kind: str
    state: str = "PENDING"                 # PENDING | RUNNING | DONE | FAILED
    progress: float = 0.0                  # 0..1
    stage: str = "queued"
    result: Any = None
    error: Optional[str] = None
    run_id: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None

    def wire(self) -> dict:
        from oci.api.serialize import iso
        return {"job_id": self.job_id, "kind": self.kind, "state": self.state,
                "progress": round(self.progress, 4), "stage": self.stage, "run_id": self.run_id,
                "error": self.error, "created_at": iso(self.created_at),
                "finished_at": iso(self.finished_at) if self.finished_at else None}


_JOBS: dict[str, Job] = {}


def get(job_id: str) -> Optional[Job]:
    with _LOCK:
        return _JOBS.get(job_id)


def all_jobs() -> list[Job]:
    with _LOCK:
        return sorted(_JOBS.values(), key=lambda j: j.created_at, reverse=True)


def submit(kind: str, fn: Callable[[Job], Any]) -> Job:
    """`fn` receives the Job so it can report `stage` / `progress` / `run_id` as it goes."""
    job = Job(job_id=f"job_{uuid.uuid4().hex[:12]}", kind=kind)
    with _LOCK:
        _JOBS[job.job_id] = job

    def _run() -> None:
        job.state, job.stage = "RUNNING", "starting"
        try:
            job.result = fn(job)
            job.state, job.progress, job.stage = "DONE", 1.0, "complete"
        except Exception as e:                      # surfaced, never swallowed (§14.5 in spirit)
            job.state, job.error = "FAILED", f"{type(e).__name__}: {e}"
            job.stage = "failed"
            traceback.print_exc()
        finally:
            job.finished_at = datetime.now(timezone.utc)

    _POOL.submit(_run)
    return job
