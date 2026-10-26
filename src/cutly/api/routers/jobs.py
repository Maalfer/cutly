from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from cutly.auth import Principal, require_read, require_write
from cutly.db.models import Job, now
from cutly.db.session import get_session

router = APIRouter(tags=["jobs"])


@router.get("/jobs")
def list_jobs(
    status: str | None = None,
    limit: int = Query(50, le=200),
    _: Principal = Depends(require_read),
    session: Session = Depends(get_session),
):
    q = select(Job).order_by(Job.created_at.desc()).limit(limit)  # type: ignore[attr-defined]
    if status:
        q = q.where(Job.status == status)
    return [j.model_dump() for j in session.exec(q).all()]


@router.get("/jobs/{job_id}")
def get_job(job_id: str, _: Principal = Depends(require_read), session: Session = Depends(get_session)):
    """Consulta por polling: status queued|running|done|failed|cancelled, progress 0..1."""
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job no encontrado")
    return job.model_dump()


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, _: Principal = Depends(require_write), session: Session = Depends(get_session)):
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job no encontrado")
    if job.status in ("queued", "running"):
        job.status, job.updated_at = "cancelled", now()
        session.add(job)
        session.commit()
        session.refresh(job)
    return job.model_dump()
