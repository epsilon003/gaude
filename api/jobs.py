"""
In-memory background job tracking for repo ingestion.

Ingestion takes minutes — a web API shouldn't hold a connection open that
long. FastAPI's BackgroundTasks runs the actual ingest_repository() call off
the request thread; this module tracks its progress in a per-job queue that
an SSE endpoint can stream from.

Deliberately NOT Celery/Redis: at this project's scale (a handful of repos,
single-process deployment), that's infrastructure the free-tier-first
philosophy behind this whole project doesn't need yet. If ingestion volume
ever grows enough to need a real task queue, this module is the one thing
that would need replacing — nothing else in rag_core depends on how
ingestion is scheduled.
"""
from __future__ import annotations

import queue
import threading
import uuid
from dataclasses import dataclass, field

from rag_core.ingestion import ingest_repository


@dataclass
class IngestJob:
    id: str
    status: str = "pending"  # pending | running | done | error
    events: queue.Queue = field(default_factory=queue.Queue)
    result: dict | None = None
    error: str | None = None


_jobs: dict[str, IngestJob] = {}
_jobs_lock = threading.Lock()


def create_job() -> IngestJob:
    job = IngestJob(id=str(uuid.uuid4()))
    with _jobs_lock:
        _jobs[job.id] = job
    return job


def get_job(job_id: str) -> IngestJob | None:
    with _jobs_lock:
        return _jobs.get(job_id)


def run_ingestion(job: IngestJob, repo_url: str) -> None:
    """Runs synchronously — intended to be scheduled via FastAPI's
    BackgroundTasks, which runs sync callables in a thread pool automatically
    (non-blocking to the server's event loop)."""
    job.status = "running"

    def _progress(msg: str) -> None:
        job.events.put({"event": "progress", "message": msg})

    try:
        summary = ingest_repository(repo_url, progress=_progress)
        job.result = summary
        job.status = "done"
        job.events.put({"event": "done", "summary": summary})
    except Exception as exc:  # noqa: BLE001
        job.status = "error"
        job.error = str(exc)
        job.events.put({"event": "error", "message": str(exc)})
    finally:
        # Sentinel: tells the SSE stream consumer this job has no more events.
        job.events.put(None)
