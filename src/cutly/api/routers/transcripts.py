"""Transcripción: lanzar job, leer (JSON o texto compacto) y editar segmentos."""

import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from cutly.auth import Principal, require_read, require_write
from cutly.db.models import Media, Transcript
from cutly.db.session import get_session
from cutly.services.transcribe.cleanup import apply_text_edit, apply_word_edits
from cutly.worker.queue import enqueue

router = APIRouter(tags=["transcripts"])


class TranscribeIn(BaseModel):
    language: str | None = Field(
        default="es", pattern=r"^[a-z]{2,3}$", description="Código ISO (es, en…). null = autodetectar"
    )

    vocabulary: str | None = Field(
        default=None, max_length=500,
        description="Términos que aparecen en el vídeo (comandos, marcas, nombres) para que Whisper los acierte: "
        "p. ej. 'apt, flatpak, sudo apt install, Audacity, ciberseguridad'",
    )  # fmt: skip
    beam_size: int | None = Field(
        default=None, ge=1, le=8, description="Más alto = más preciso y más lento (por defecto 1)"
    )


class WordEdit(BaseModel):
    op: Literal["replace", "merge", "delete"]
    index: int = Field(ge=0, description="Posición de la palabra en el segmento (0 = primera)")
    text: str = Field("", max_length=60, description="Texto nuevo (replace/merge)")
    to: int | None = Field(None, ge=0, description="Última palabra a unir (merge); por defecto la siguiente")


class WordEdits(BaseModel):
    edits: list[WordEdit] = Field(min_length=1, max_length=50)


class SegmentEdit(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


def _get(session: Session, media_id: str) -> Transcript:
    if session.get(Media, media_id) is None:
        raise HTTPException(404, "Medio no encontrado")
    t = session.exec(select(Transcript).where(Transcript.media_id == media_id)).first()
    if t is None:
        raise HTTPException(404, "Este medio no tiene transcripción; lánzala con POST /media/{id}/transcribe")
    return t


def _ts(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


@router.post("/media/{media_id}/transcribe")
def start_transcription(
    media_id: str,
    body: TranscribeIn | None = None,
    _: Principal = Depends(require_write),
    session: Session = Depends(get_session),
):
    """Lanza la transcripción (job largo; consulta GET /jobs/{id}). Reemplaza la anterior al terminar."""
    m = session.get(Media, media_id)
    if m is None:
        raise HTTPException(404, "Medio no encontrado")
    if not m.metadata_json.get("has_audio"):
        raise HTTPException(422, "El vídeo no tiene pista de audio")
    language = (body or TranscribeIn()).language
    b = body or TranscribeIn()
    params = {"media_id": media_id, "language": language, "vocabulary": b.vocabulary, "beam_size": b.beam_size}
    return {"job_id": enqueue(session, "transcribe", params).id}


@router.get("/media/{media_id}/transcript")
def get_transcript(
    media_id: str,
    start: float = Query(0, ge=0),
    end: float | None = None,
    format: str = Query("json", pattern="^(json|text)$"),
    words: bool = True,
    _: Principal = Depends(require_read),
    session: Session = Depends(get_session),
):
    """`format=text` devuelve líneas `[HH:MM:SS] #id texto`, compactas para leer de un vistazo."""
    t = _get(session, media_id)
    segs = [s for s in t.segments if s["end"] > start and (end is None or s["start"] < end)]
    if format == "text":
        return {"language": t.language, "text": "\n".join(f"[{_ts(s['start'])}] #{s['id']} {s['text']}" for s in segs)}
    if not words:
        segs = [{k: v for k, v in s.items() if k != "words"} for s in segs]
    return {"id": t.id, "media_id": media_id, "language": t.language, "segments": segs}


@router.patch("/media/{media_id}/transcript/segments/{segment_id}")
def edit_segment(
    media_id: str,
    segment_id: int,
    body: SegmentEdit,
    _: Principal = Depends(require_write),
    session: Session = Depends(get_session),
):
    """Corrige el texto de un segmento. Si cambia el nº de palabras, se reparten los tiempos."""
    t = _get(session, media_id)
    segs = list(t.segments)
    idx = next((i for i, s in enumerate(segs) if s["id"] == segment_id), None)
    if idx is None:
        raise HTTPException(404, f"Segmento {segment_id} no existe")
    if re.search(r"[\x00-\x08\x0b-\x1f]", body.text):
        raise HTTPException(422, "El texto contiene caracteres de control")
    segs[idx] = apply_text_edit(segs[idx], body.text)
    t.segments = segs  # reasignar: SQLAlchemy no detecta mutaciones internas del JSON
    session.add(t)
    session.commit()
    return segs[idx]


@router.patch("/media/{media_id}/transcript/segments/{segment_id}/words")
def edit_words(
    media_id: str,
    segment_id: int,
    body: WordEdits,
    _: Principal = Depends(require_write),
    session: Session = Depends(get_session),
):
    """Corrige palabras concretas (replace/merge/delete) sin perder el tiempo de las demás: lo que hace falta para
    arreglar términos técnicos mal transcritos manteniendo los subtítulos sincronizados."""
    t = _get(session, media_id)
    segs = list(t.segments)
    idx = next((i for i, s in enumerate(segs) if s["id"] == segment_id), None)
    if idx is None:
        raise HTTPException(404, f"Segmento {segment_id} no existe")
    try:
        segs[idx] = apply_word_edits(segs[idx], [e.model_dump() for e in body.edits])
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    t.segments = segs
    session.add(t)
    session.commit()
    return segs[idx]
