"""Medios: subida simple, listado, borrado, proxy, peaks."""

import uuid

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from cutly.auth import Principal, require_read, require_write
from cutly.config import get_settings
from cutly.db.models import Media
from cutly.db.session import get_session
from cutly.services.ingest.ffprobe import ProbeError
from cutly.services.ingest.media_store import delete_media, register_media
from cutly.services.sanitize.paths import UnsafePath, safe_filename
from cutly.worker.handlers import PEAKS_RATE
from cutly.worker.queue import enqueue

router = APIRouter(tags=["media"])


def _media(session: Session, media_id: str) -> Media:
    m = session.get(Media, media_id)
    if m is None:
        raise HTTPException(404, "Medio no encontrado; lista los disponibles con GET /media")
    return m


def _view(m: Media) -> dict:
    return {
        "id": m.id, "filename": m.filename, "duration": m.duration, "size_bytes": m.size_bytes,
        "status": m.status, "has_proxy": bool(m.proxy_path), "has_peaks": bool(m.peaks_path),
        "metadata": m.metadata_json, "created_at": m.created_at,
    }  # fmt: skip


@router.post("/media/simple")
async def simple_upload(
    request: Request,
    filename: str = Query(description="Nombre del archivo (con extensión)"),
    _: Principal = Depends(require_write),
    session: Session = Depends(get_session),
):
    """Subida simple para archivos pequeños: cuerpo = bytes crudos (curl --data-binary @f).

    Para directos largos usa la subida por trozos (/uploads).
    """
    s = get_settings()
    try:
        name = safe_filename(filename)
    except UnsafePath as e:
        raise HTTPException(422, str(e)) from e
    s.uploads_dir.mkdir(parents=True, exist_ok=True)
    tmp = s.uploads_dir / f"simple_{uuid.uuid4().hex}.bin"
    written = 0
    try:
        with open(tmp, "wb") as f:
            async for data in request.stream():
                written += len(data)
                if written > s.simple_upload_max_bytes:
                    raise HTTPException(413, "Demasiado grande para la subida simple; usa /uploads por trozos")
                f.write(data)
        media, jobs = register_media(session, tmp, name)
    except ProbeError as e:
        raise HTTPException(422, str(e)) from e
    finally:
        tmp.unlink(missing_ok=True)
    return {"media_id": media.id, "jobs": jobs}


@router.get("/media")
def list_media(
    limit: int = Query(50, le=200),
    offset: int = 0,
    _: Principal = Depends(require_read),
    session: Session = Depends(get_session),
):
    rows = session.exec(select(Media).order_by(Media.created_at.desc()).offset(offset).limit(limit)).all()  # type: ignore[attr-defined]
    return [_view(m) for m in rows]


@router.get("/media/{media_id}")
def get_media(media_id: str, _: Principal = Depends(require_read), session: Session = Depends(get_session)):
    return _view(_media(session, media_id))


@router.delete("/media/{media_id}")
def remove_media(media_id: str, _: Principal = Depends(require_write), session: Session = Depends(get_session)):
    """Borra el medio, su transcripción, candidatos, proyectos y todos sus archivos del disco.

    Es transaccional: los archivos se apartan antes del commit y se restauran si la BD falla. Devuelve
    un resumen (proyectos borrados, jobs cancelados, rutas y bytes liberados).
    """
    return delete_media(session, _media(session, media_id))


@router.post("/media/purge-orphans")
def purge_orphans_endpoint(_: Principal = Depends(require_write)):
    """Limpia del disco carpetas de medios sin fila en la BD, papelera y subidas abandonadas."""
    from cutly.services.ingest.media_store import purge_orphans

    return purge_orphans()


@router.post("/media/{media_id}/proxy")
def regenerate_proxy(media_id: str, _: Principal = Depends(require_write), session: Session = Depends(get_session)):
    _media(session, media_id)
    return {"job_id": enqueue(session, "media.proxy", {"media_id": media_id}).id}


@router.post("/media/{media_id}/peaks")
def regenerate_peaks(media_id: str, _: Principal = Depends(require_write), session: Session = Depends(get_session)):
    _media(session, media_id)
    return {"job_id": enqueue(session, "media.peaks", {"media_id": media_id}).id}


@router.get("/media/{media_id}/proxy.mp4")
def proxy_file(media_id: str, _: Principal = Depends(require_read), session: Session = Depends(get_session)):
    """Proxy 540p con soporte de rangos (en producción lo sirve Nginx)."""
    m = _media(session, media_id)
    if not m.proxy_path:
        raise HTTPException(409, "El proxy aún no está listo; consulta el job de proxy")
    return FileResponse(m.proxy_path, media_type="video/mp4")


@router.get("/media/{media_id}/peaks")
def get_peaks(
    media_id: str,
    start: float = Query(0, ge=0, description="Segundo inicial"),
    end: float | None = Query(None, description="Segundo final (por defecto, el final)"),
    bins: int = Query(0, ge=0, le=20000, description="Si >0, reduce a este nº de columnas"),
    _: Principal = Depends(require_read),
    session: Session = Depends(get_session),
):
    """Forma de onda: min/max por columna en int8 (-128..127). `scale`=128 para normalizar."""
    m = _media(session, media_id)
    if not m.peaks_path:
        raise HTTPException(409, "Los peaks aún no están listos (o el vídeo no tiene audio)")
    arr = np.load(m.peaks_path, mmap_mode="r")
    i0 = int(start * PEAKS_RATE)
    i1 = len(arr) if end is None else min(len(arr), int(end * PEAKS_RATE))
    part = np.asarray(arr[i0:i1])
    if bins and len(part) > bins:
        edges = np.linspace(0, len(part), bins + 1).astype(int)[:-1]
        mins = np.minimum.reduceat(part[:, 0], edges)
        maxs = np.maximum.reduceat(part[:, 1], edges)
    else:
        mins, maxs = part[:, 0], part[:, 1]
    return {
        "rate": PEAKS_RATE, "start": start, "scale": 128, "count": len(mins),
        "min": mins.tolist(), "max": maxs.tolist(),
    }  # fmt: skip
