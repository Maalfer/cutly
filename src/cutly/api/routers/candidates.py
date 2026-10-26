"""Candidatos a clip: los elige el agente (o tú) y los registra aquí; luego se listan, ajustan, aceptan y descartan."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from cutly.auth import Principal, require_read, require_write
from cutly.db.models import ClipCandidate, Media, Transcript
from cutly.db.session import get_session
from cutly.services.candidates.snapping import flatten_words, overlap, snap_to_sentences
from cutly.services.candidates.types import Candidate as Span
from cutly.services.candidates.types import Criterion

router = APIRouter(tags=["candidates"])
MIN_SECONDS, MAX_SECONDS = 3.0, 600.0


class CandidateIn(BaseModel):
    start: float = Field(ge=0, description="Segundos del vídeo ORIGINAL")
    end: float = Field(gt=0)
    title: str = Field("", max_length=120, description="Título corto y atractivo (en el idioma del vídeo)")
    reason: str = Field("", max_length=500, description="Por qué funciona como clip")
    criteria: list[Criterion] = Field(
        default_factory=list,
        description="hook (gancho), complete_story (historia completa), strong_opinion (opinión fuerte), "
        "funny (gracioso), standalone_value (valor para quien no vio el directo)",
    )
    score: float = Field(70, ge=0, le=100, description="90-100 excepcional · 70-89 muy bueno · 50-69 aceptable")


class CandidatesIn(BaseModel):
    candidates: list[CandidateIn] = Field(min_length=1, max_length=50)
    snap: bool = Field(
        True, description="Ajusta inicio/fin al límite de frase más cercano (±8 s) con los tiempos por palabra"
    )
    replace_proposed: bool = Field(
        False, description="Borra antes los candidatos aún sin revisar (`proposed`) de este vídeo"
    )


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


@router.post("/media/{media_id}/candidates")
def create_candidates(
    media_id: str,
    body: CandidatesIn,
    _: Principal = Depends(require_write),
    session: Session = Depends(get_session),
):
    """Registra los clips que has elegido leyendo la transcripción (`GET /media/{id}/transcript?format=text`).

    Todo o nada: si uno es inválido no se crea ninguno. Con `snap` (por defecto) cada clip se ajusta a límites de
    frase. Si un clip se solapa mucho con otro ya existente (no descartado) se omite y aparece en `skipped`."""
    media = session.get(Media, media_id)
    if media is None:
        raise HTTPException(404, "Medio no encontrado")
    t = session.exec(select(Transcript).where(Transcript.media_id == media_id)).first()
    segments = t.segments if t else []
    spans: list[tuple[CandidateIn, float, float]] = []
    for i, c in enumerate(body.candidates):
        start, end = c.start, c.end
        if body.snap and segments:
            near = [x for x in segments if x["end"] > start - 12 and x["start"] < end + 12]
            snapped = snap_to_sentences(flatten_words(near), start, end) if near else None
            if snapped:
                start, end = snapped
        dur = end - start
        if not MIN_SECONDS <= dur <= MAX_SECONDS:
            raise HTTPException(
                422, f"candidates[{i}] dura {dur:.1f} s: debe estar entre {MIN_SECONDS:.0f} y {MAX_SECONDS:.0f} s"
            )
        if media.duration and end > media.duration + 0.5:
            raise HTTPException(
                422, f"candidates[{i}]: el final ({end:.1f}) supera la duración del vídeo ({media.duration:.1f})"
            )
        spans.append((c, round(start, 3), round(end, 3)))
    if body.replace_proposed:
        for old in session.exec(
            select(ClipCandidate).where(ClipCandidate.media_id == media_id, ClipCandidate.status == "proposed")
        ).all():
            session.delete(old)
        session.flush()
    existing = session.exec(
        select(ClipCandidate).where(ClipCandidate.media_id == media_id, ClipCandidate.status != "discarded")
    ).all()
    keep: list[Span] = [Span(e.start, e.end, e.score, e.title, e.reason, list(e.criteria or [])) for e in existing]
    created, skipped = [], []
    for c, start, end in spans:
        mine = Span(start, end, c.score, c.title, c.reason, list(c.criteria))
        clash = next((k for k in keep if (lambda o: o[0] >= 0.3 or o[1] >= 0.6)(overlap(mine, k))), None)
        if clash is not None:
            skipped.append({"start": start, "end": end, "title": c.title, "reason": "se solapa con otro candidato",
                            "overlaps": f"{clash.start:.1f}-{clash.end:.1f}"})  # fmt: skip
            continue
        row = ClipCandidate(media_id=media_id, start=start, end=end, score=c.score, title=c.title.strip(),
                            reason=c.reason.strip(), criteria=list(c.criteria))  # fmt: skip
        session.add(row)
        keep.append(mine)
        created.append(row)
    session.commit()
    for r in created:
        session.refresh(r)
    return {"created": [_view(session, r) for r in created], "skipped": skipped}


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


@router.delete("/candidates/{candidate_id}")
def delete_candidate(candidate_id: str, _: Principal = Depends(require_write), session: Session = Depends(get_session)):
    session.delete(_get(session, candidate_id))
    session.commit()
    return {"ok": True}
