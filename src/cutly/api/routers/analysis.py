"""Análisis de directos largos: esquema, cambios de tema y propuestas de tramos de 5-10 min (ver services/analysis/stream.py)."""

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from cutly.auth import Principal, require_read, require_write
from cutly.db.models import ClipCandidate, Media, Transcript
from cutly.db.session import get_session
from cutly.services.analysis import stream as S
from cutly.services.candidates.snapping import flatten_words, snap_to_sentences

router = APIRouter(tags=["analysis"])
MAX_CLIP = 600.0  # tope de un candidato (routers/candidates.py)


def _load(session: Session, media_id: str):
    media = session.get(Media, media_id)
    if media is None:
        raise HTTPException(404, "Medio no encontrado")
    t = session.exec(select(Transcript).where(Transcript.media_id == media_id)).first()
    if t is None or not t.segments:
        raise HTTPException(409, "Sin transcripción: lánzala primero (POST /media/{id}/transcribe) y espera a que termine")
    peaks = None
    if media.peaks_path:
        try:
            peaks = np.load(media.peaks_path, mmap_mode="r")
        except (OSError, ValueError):
            peaks = None
    return media, t.segments, peaks


def _windows(session: Session, media_id: str, window: float):
    media, segs, peaks = _load(session, media_id)
    dur = float(media.duration or max((s["end"] for s in segs), default=0))
    return media, segs, S.build_windows(segs, dur, window, peaks)


@router.get("/media/{media_id}/outline")
def outline(
    media_id: str,
    window: float = Query(120, ge=30, le=600, description="Segundos por línea del esquema"),
    start: float = Query(0, ge=0, description="Desde (s del original)"),
    end: float | None = Query(None, gt=0),
    _: Principal = Depends(require_read),
    session: Session = Depends(get_session),
):
    """Esquema de TODO el directo en una pantalla: por ventana, el tiempo, palabras clave, un extracto y las señales
    (energía de la voz, palabras/min, intercambios, preguntas, aire muerto) más el «interés» y si hay cambio de tema.
    Úsalo para localizar zonas interesantes sin leer el directo entero; después lee solo esas con GET /media/{id}/transcript."""
    media, segs, wins = _windows(session, media_id, window)
    hi = end if end is not None else float("inf")
    rows = []
    for w in wins:
        if w.end <= start or w.start >= hi:
            continue
        rows.append({
            "start": round(w.start, 1), "end": round(w.end, 1), "t": f"{S.fmt_t(w.start)}-{S.fmt_t(w.end)}",
            "interest": round(w.interest, 2), "topic_change": w.boundary >= 0.6, "keywords": S.keywords(w.counts, wins, 5),
            "wpm": round(w.wpm), "speech": round(w.speech, 2), "energy": round(w.energy, 3), "turns_per_min": round(w.turns, 1),
            "questions": w.questions, "exclaims": w.exclaims, "text": w.text[:200],
        })  # fmt: skip
    top = sorted(rows, key=lambda r: -r["interest"])[:5]
    return {
        "media_id": media_id, "duration": media.duration, "window": window, "has_audio_energy": any(w.energy > 0 for w in wins),
        "hint": "interest: 0 = normal, >1 = destaca, <-1 = flojo o aire muerto. topic_change = el tema cambia respecto a la ventana anterior.",
        "most_interesting": [r["t"] for r in top], "windows": rows,
    }  # fmt: skip


class SuggestIn(BaseModel):
    min_minutes: float = Field(5, ge=1, le=10, description="Duración mínima de cada tramo")
    max_minutes: float = Field(10, ge=1, le=10, description="Duración máxima (tope 10 min)")
    count: int = Field(8, ge=1, le=30)
    window: float = Field(60, ge=30, le=180, description="Resolución del análisis (s)")
    exclude_ranges: list[tuple[float, float]] = Field(default_factory=list, description="Tramos ya usados: [[inicio, fin], …] (s del original)")
    save: bool = Field(False, description="Registra las propuestas como candidatos (estado `proposed`) con un título provisional")
    replace_proposed: bool = Field(False, description="Con `save`: borra antes los candidatos aún sin revisar de este vídeo")


@router.post("/media/{media_id}/suggest-segments")
def suggest_segments(
    media_id: str, body: SuggestIn, _: Principal = Depends(require_write), session: Session = Depends(get_session)
):
    """Propone los mejores tramos de `min_minutes`-`max_minutes` del directo: interés sostenido, empiezan y acaban en cambios de
    tema y en límite de frase, sin aire muerto y sin solaparse. Es una HEURÍSTICA para elegir qué revisar: lee el texto de cada
    propuesta (GET /media/{id}/transcript?start=&end=), descarta las flojas y ponles título antes de montar nada."""
    if body.max_minutes < body.min_minutes:
        raise HTTPException(422, "max_minutes debe ser mayor o igual que min_minutes")
    media, segs, wins = _windows(session, media_id, body.window)
    props = S.propose(wins, body.min_minutes * 60, min(body.max_minutes * 60, MAX_CLIP), body.count, exclude=[tuple(r) for r in body.exclude_ranges])
    words = flatten_words(segs)
    out = []
    for p in props:
        s, e = p.start, p.end
        near = [x for x in words if x["end"] > s - 12 and x["start"] < e + 12]
        snapped = snap_to_sentences(near, s, e) if near else None
        if snapped:
            s, e = snapped
        if e - s > MAX_CLIP:  # el ajuste a frase no puede pasar del tope de un candidato
            e = max(w["end"] for w in words if w["end"] <= s + MAX_CLIP)
        out.append({
            "start": round(s, 2), "end": round(e, 2), "duration": round(e - s, 1), "t": f"{S.fmt_t(s)}-{S.fmt_t(e)}",
            "score": p.score, "keywords": p.keywords, "suggested_title": " · ".join(p.keywords[:3]) or "tramo",
            "signals": {"interest": round(p.interest, 2), "wpm": round(p.wpm), "questions": p.questions, "dead_air": round(p.dead_air, 2), "inner_topic_changes": p.inner_topics},
            "starts_with": p.first, "ends_with": p.last,
        })  # fmt: skip
    created = []
    if body.save and out:
        if body.replace_proposed:
            for old in session.exec(select(ClipCandidate).where(ClipCandidate.media_id == media_id, ClipCandidate.status == "proposed")).all():
                session.delete(old)
            session.flush()
        for o in out:
            row = ClipCandidate(
                media_id=media_id, start=o["start"], end=o["end"], score=o["score"], title=o["suggested_title"][:120],
                reason=f"Propuesta automática: interés {o['signals']['interest']}, {o['signals']['wpm']} palabras/min, {o['signals']['questions']} preguntas. Revisa el texto antes de aceptarla.",
                criteria=[],
            )  # fmt: skip
            session.add(row)
            created.append(row)
        session.commit()
        for r in created:
            session.refresh(r)
    return {
        "media_id": media_id, "duration": media.duration,
        "note": "Heurística de energía de voz, ritmo e intercambios: lee el texto de cada tramo y descarta lo flojo antes de montar.",
        "segments": out, "registered": [c.id for c in created],
    }  # fmt: skip
