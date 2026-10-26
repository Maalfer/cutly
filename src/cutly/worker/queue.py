"""Encolado de jobs: RQ+Redis en producción, ejecución inmediata en modo inline."""

from sqlmodel import Session

from cutly.config import get_settings
from cutly.db.models import Job


def enqueue(session: Session, job_type: str, params: dict) -> Job:
    job = Job(type=job_type, params=params)
    session.add(job)
    session.commit()
    session.refresh(job)
    settings = get_settings()
    if settings.queue_mode == "inline":
        from cutly.worker.jobs import run_job

        run_job(job.id)
        session.refresh(job)
    else:
        from redis import Redis
        from rq import Queue

        Queue(connection=Redis.from_url(settings.redis_url)).enqueue(
            "cutly.worker.jobs.run_job", job.id, job_timeout=settings.job_timeout_s
        )
    return job
