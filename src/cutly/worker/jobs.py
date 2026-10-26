"""Ejecución de jobs en el worker: estado, progreso throttled y cancelación vía BD."""

import time
from collections.abc import Callable

from sqlmodel import Session

from cutly.db.models import Job, now
from cutly.db.session import get_engine
from cutly.worker.subprocess_runner import JobCancelled

HANDLERS: dict[str, Callable[["JobContext"], dict | None]] = {}


def handler(job_type: str):
    def deco(fn):
        HANDLERS[job_type] = fn
        return fn

    return deco


class JobContext:
    def __init__(self, job_id: str, params: dict):
        self.job_id = job_id
        self.params = params
        self._last_progress = 0.0
        self._last_check = 0.0
        self._cancelled = False

    def progress(self, value: float) -> None:
        t = time.monotonic()
        if t - self._last_progress < 1.0 and value < 0.99:
            return
        self._last_progress = t
        with Session(get_engine()) as s:
            job = s.get(Job, self.job_id)
            if job and job.status == "running":
                job.progress, job.updated_at = round(value, 4), now()
                s.add(job)
                s.commit()

    def cancelled(self) -> bool:
        t = time.monotonic()
        if self._cancelled or t - self._last_check < 0.5:
            return self._cancelled
        self._last_check = t
        with Session(get_engine()) as s:
            job = s.get(Job, self.job_id)
            self._cancelled = job is None or job.status == "cancelled"
        return self._cancelled


def _finish(job_id: str, **fields) -> None:
    with Session(get_engine()) as s:
        job = s.get(Job, job_id)
        if job is None:
            return
        if job.status == "cancelled":  # la cancelación manda sobre cualquier otro final
            fields = {"status": "cancelled"}
        for k, v in fields.items():
            setattr(job, k, v)
        job.updated_at = now()
        s.add(job)
        s.commit()


def run_job(job_id: str) -> None:
    from cutly.worker import (  # noqa: F401
        handlers,
        render_handler,
        transcribe_handler,
        verify_handler,
    )

    with Session(get_engine()) as s:
        job = s.get(Job, job_id)
        if job is None or job.status != "queued":
            return  # cancelado antes de empezar
        job.status = "running"
        job.updated_at = now()
        params, jtype = job.params, job.type
        s.add(job)
        s.commit()
    ctx = JobContext(job_id, params)
    try:
        fn = HANDLERS.get(jtype)
        if fn is None:
            raise RuntimeError(f"Tipo de job desconocido: {jtype}")
        result = fn(ctx)
        _finish(job_id, status="done", progress=1.0, result=result or {})
    except JobCancelled:
        _finish(job_id, status="cancelled")
    except Exception as e:  # noqa: BLE001
        _finish(job_id, status="failed", error=str(e)[:2000])
