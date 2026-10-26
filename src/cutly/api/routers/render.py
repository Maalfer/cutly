"""Render de proyectos: lanzar, listar y descargar."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from cutly.auth import Principal, require_read, require_write
from cutly.config import get_settings
from cutly.db.models import Job, Media, Project
from cutly.db.session import get_session
from cutly.services.projects import store
from cutly.services.sanitize.paths import ensure_within
from cutly.worker.queue import enqueue

router = APIRouter(tags=["render"])


class RenderIn(BaseModel):
    quality: Literal["final", "draft"] = "final"
    start: float | None = Field(
        None, ge=0, description="Renderiza solo desde este segundo del clip resultante (vista previa de un tramo)"
    )
    end: float | None = Field(None, gt=0, description="…hasta este segundo")


def _enqueue(session: Session, row: Project, quality: str, start: float | None = None, end: float | None = None) -> str:
    doc = store.load_doc(session, row)
    if not doc.timeline:
        raise HTTPException(422, "El proyecto no tiene clips: añade uno con la operación add_clip antes de renderizar")
    if start is not None or end is not None:
        s0, e0 = start or 0.0, min(end if end is not None else doc.duration, doc.duration)
        if e0 - s0 < 0.2:
            raise HTTPException(
                422, f"Tramo demasiado corto o fuera del clip (dura {doc.duration:.2f} s): start={s0}, end={e0}"
            )
    params = {
        "project_id": row.id,
        "project_version": row.version,
        "quality": quality,
        "doc": doc.model_dump(mode="json"),
        "start": start,
        "end": end,
    }
    return enqueue(session, "render", params).id


@router.post("/projects/{project_id}/render")
def render_project(
    project_id: str,
    body: RenderIn | None = None,
    _: Principal = Depends(require_write),
    session: Session = Depends(get_session),
):
    """Renderiza el proyecto tal y como está ahora. `draft` = borrador rápido de baja calidad (desde el proxy);
    `final` = calidad completa. Devuelve un job; al terminar, `result.path` y `GET /renders/{job_id}/download`."""
    row = session.get(Project, project_id)
    if row is None:
        raise HTTPException(404, "Proyecto no encontrado")
    b = body or RenderIn()
    return {"job_id": _enqueue(session, row, b.quality, b.start, b.end)}


@router.post("/media/{media_id}/render-all")
def render_all(
    media_id: str,
    body: RenderIn | None = None,
    _: Principal = Depends(require_write),
    session: Session = Depends(get_session),
):
    """Encola el render de todos los proyectos de un vídeo que tengan clips."""
    if session.get(Media, media_id) is None:
        raise HTTPException(404, "Medio no encontrado")
    q = (body or RenderIn()).quality
    jobs = {}
    for row in session.exec(select(Project).where(Project.media_id == media_id)).all():
        if store.load_doc(session, row).timeline:
            jobs[row.id] = _enqueue(session, row, q)
    return {"jobs": jobs}


@router.get("/projects/{project_id}/renders")
def list_renders(project_id: str, _: Principal = Depends(require_read), session: Session = Depends(get_session)):
    jobs = session.exec(select(Job).where(Job.type == "render").order_by(Job.created_at.desc()).limit(200)).all()  # type: ignore[attr-defined]
    return [
        {"job_id": j.id, "status": j.status, "progress": j.progress, "created_at": j.created_at,
         "quality": (j.params or {}).get("quality"), "project_version": (j.params or {}).get("project_version"),
         "result": {k: v for k, v in (j.result or {}).items() if k != "path"} or None, "error": j.error}
        for j in jobs if (j.params or {}).get("project_id") == project_id
    ]  # fmt: skip


@router.get("/renders/{job_id}/download")
def download_render(job_id: str, _: Principal = Depends(require_read), session: Session = Depends(get_session)):
    job = session.get(Job, job_id)
    if job is None or job.type != "render":
        raise HTTPException(404, "Render no encontrado")
    if job.status != "done" or not job.result:
        raise HTTPException(409, f"El render no está listo (estado: {job.status}); consulta GET /jobs/{job_id}")
    path = ensure_within(get_settings().renders_dir, __import__("pathlib").Path(job.result["path"]))
    if not path.is_file():
        raise HTTPException(410, "El archivo ya no existe (limpieza automática); vuelve a renderizar")
    return FileResponse(path, media_type="video/mp4", filename=f"{job.params.get('project_id', 'clip')}-{job.id}.mp4")
