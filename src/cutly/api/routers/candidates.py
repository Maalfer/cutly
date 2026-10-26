"""Candidatos a clip: proponer (IA), listar, ajustar, aceptar y descartar."""

import os
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from cutly.auth import Principal, require_read, require_write
from cutly.config import get_settings
from cutly.db.models import ClipCandidate, Media, Transcript
from cutly.db.session import get_session
from cutly.services.candidates.types import ALL_CRITERIA, Criterion
from cutly.worker.queue import enqueue

router = APIRouter(tags=["candidates"])


class ProposeIn(BaseModel):
    criteria: list[Criterion] = Field(
        default=list(ALL_CRITERIA),
        description="hook (gancho), complete_story (historia completa), strong_opinion (opinión fuerte), "
        "funny (gracioso), standalone_value (valor para quien no vio el directo)",
    )
    min_seconds: float = Field(25, ge=10, le=120)
    max_seconds: float = Field(90, ge=15, le=180, description="Duración típica máxima")
    long_max_seconds: float = Field(300, ge=30, le=600, description="Tope para los pocos clips de varios minutos")
    max_candidates: int = Field(20, ge=1, le=50)
    per_chunk: int = Field(6, ge=1, le=12, description="Máximo de candidatos que se piden por bloque de ~25 min")
    instructions: str = Field("", max_length=1000, description="Indicaciones extra (temas que interesan, tono…)")


class CandidatePatch(BaseModel):
    start: float | None = Field(None, ge=0)
    end: float | None = Field(None, ge=0)
    title: str | None = Field(None, max_length=120)
    reason: str | None = Field(None, max_length=500)


def _get(session: Session, cid: str) -> ClipCandidate:
    c = session.get(ClipCandidate, cid)
    if c is None:
        raise HTTPException(404, "Candidato no encontrado; lista los de un vídeo con GET /media/{id}/candidates")
    return c


def _view(session: Session, c: ClipCandidate, with_text: bool = True) -> dict:
    d = c.model_dump()
    d["duration"] = round(c.end - c.start, 2)
    if with_text:
        t = session.exec(select(Transcript).where(Transcript.media_id == c.media_id)).first()
        segs = [s["text"] for s in (t.segments if t else []) if s["end"] > c.start and s["start"] < c.end]
        d["text"] = " ".join(segs)[:1500]
    return d


@router.post("/media/{media_id}/candidates/propose")
def propose(
    media_id: str,
    body: ProposeIn | None = None,
    _: Principal = Depends(require_write),
    session: Session = Depends(get_session),
):
    """Lanza la búsqueda de clips con IA (job largo). Sustituye los candidatos aún no revisados
    (`proposed`); conserva los aceptados y descartados."""
    if session.get(Media, media_id) is None:
        raise HTTPException(404, "Medio no encontrado")
    if session.exec(select(Transcript.id).where(Transcript.media_id == media_id)).first() is None:
        raise HTTPException(409, "Primero hay que transcribir el vídeo: POST /media/{id}/transcribe")
    if get_settings().candidates_backend == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(503, "Falta ANTHROPIC_API_KEY en el servidor (.env); sin ella no se pueden proponer clips")
    b = body or ProposeIn()
    if b.max_seconds < b.min_seconds:
        raise HTTPException(422, "max_seconds no puede ser menor que min_seconds")
    params = b.model_dump()
    return {"job_id": enqueue(session, "candidates.propose", {"media_id": media_id, "params": params}).id}


@router.get("/media/{media_id}/candidates")
def list_candidates(
    media_id: str,
    status: Literal["proposed", "accepted", "discarded"] | None = None,
    _: Principal = Depends(require_read),
    session: Session = Depends(get_session),
):
    q = select(ClipCandidate).where(ClipCandidate.media_id == media_id).order_by(ClipCandidate.score.desc())  # type: ignore[attr-defined]
    if status:
        q = q.where(ClipCandidate.status == status)
    return [_view(session, c) for c in session.exec(q).all()]


@router.get("/candidates/{candidate_id}")
def get_candidate(candidate_id: str, _: Principal = Depends(require_read), session: Session = Depends(get_session)):
    return _view(session, _get(session, candidate_id))


@router.patch("/candidates/{candidate_id}")
def patch_candidate(
    candidate_id: str,
    body: CandidatePatch,
    _: Principal = Depends(require_write),
    session: Session = Depends(get_session),
):
    """Ajusta inicio/fin (segundos del vídeo original) o los textos de un candidato."""
    c = _get(session, candidate_id)
    media = session.get(Media, c.media_id)
    start = c.start if body.start is None else body.start
    end = c.end if body.end is None else body.end
    if end - start < 3:
        raise HTTPException(422, f"El clip debe durar al menos 3 s (ahora {end - start:.1f} s)")
    if body.end is not None and media and media.duration and end > media.duration + 0.5:
        raise HTTPException(422, f"El final ({end:.1f}) supera la duración del vídeo ({media.duration:.1f})")
    c.start, c.end = start, end
    if body.title is not None:
        c.title = body.title
    if body.reason is not None:
        c.reason = body.reason
    session.add(c)
    session.commit()
    session.refresh(c)
    return _view(session, c)


def _set_status(session: Session, cid: str, status: str) -> dict:
    c = _get(session, cid)
    c.status = status
    session.add(c)
    session.commit()
    session.refresh(c)
    return _view(session, c, with_text=False)


@router.post("/candidates/{candidate_id}/accept")
def accept(candidate_id: str, _: Principal = Depends(require_write), session: Session = Depends(get_session)):
    return _set_status(session, candidate_id, "accepted")


@router.post("/candidates/{candidate_id}/discard")
def discard(candidate_id: str, _: Principal = Depends(require_write), session: Session = Depends(get_session)):
    return _set_status(session, candidate_id, "discarded")
