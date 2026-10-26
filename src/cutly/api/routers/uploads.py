"""Subida por trozos reanudable (web y API).

Flujo: POST /uploads → PUT /uploads/{id}/chunks/{n} (en cualquier orden, repetible)
→ GET /uploads/{id} para reanudar → POST /uploads/{id}/complete.
"""

import hashlib
import math
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlmodel import Session, func, select

from cutly.auth import Principal, require_read, require_write
from cutly.config import get_settings
from cutly.db.models import Upload, UploadChunk
from cutly.db.session import get_session
from cutly.services.ingest.ffprobe import ProbeError
from cutly.services.ingest.media_store import register_media
from cutly.services.sanitize.paths import UnsafePath, ensure_within, safe_filename

router = APIRouter(tags=["uploads"])


class UploadCreate(BaseModel):
    filename: str = Field(description="Nombre original; se sanea. Extensiones: mp4, mkv, mov, webm, ts, flv, avi, m4v")
    size: int = Field(gt=0, description="Tamaño total en bytes")
    chunk_size: int | None = Field(
        None, ge=256 * 1024, le=64 * 1024**2,
        description="Tamaño de trozo deseado (256 KB–64 MB). Trozos de 2–8 MB aguantan mejor enlaces lentos",
    )  # fmt: skip


def _get(session: Session, upload_id: str) -> Upload:
    up = session.get(Upload, upload_id)
    if up is None:
        raise HTTPException(404, "Subida no encontrada (¿caducada o ya completada y limpiada?)")
    return up


def _received(session: Session, upload_id: str) -> list[int]:
    return list(session.exec(select(UploadChunk.n).where(UploadChunk.upload_id == upload_id).order_by(UploadChunk.n)))


def _view(up: Upload, received: list[int]) -> dict:
    return {
        "upload_id": up.id, "filename": up.filename, "size": up.size, "chunk_size": up.chunk_size,
        "total_chunks": up.total_chunks, "received": received, "status": up.status,
        "media_id": up.media_id,
    }  # fmt: skip


@router.post("/uploads")
def create_upload(
    body: UploadCreate,
    _: Principal = Depends(require_write),
    session: Session = Depends(get_session),
):
    """Crea una subida. Reserva el archivo (disperso) y devuelve el tamaño de trozo a usar."""
    s = get_settings()
    if body.size > s.max_upload_bytes:
        raise HTTPException(413, f"Supera el límite de subida ({s.max_upload_bytes} bytes)")
    s.uploads_dir.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(s.uploads_dir).free < body.size * 1.1:
        raise HTTPException(507, "No hay espacio en disco suficiente para esta subida")
    try:
        name = safe_filename(body.filename)
    except UnsafePath as e:
        raise HTTPException(422, str(e)) from e
    chunk = body.chunk_size or s.upload_chunk_bytes
    up = Upload(filename=name, size=body.size, chunk_size=chunk, path="", total_chunks=math.ceil(body.size / chunk))
    path = ensure_within(s.uploads_dir, s.uploads_dir / f"{up.id}.bin")
    with open(path, "wb") as f:
        f.truncate(body.size)
    up.path = str(path)
    session.add(up)
    session.commit()
    return _view(up, [])


@router.get("/uploads/{upload_id}")
def get_upload(upload_id: str, _: Principal = Depends(require_read), session: Session = Depends(get_session)):
    """Estado de la subida: lista de trozos recibidos para poder reanudar."""
    up = _get(session, upload_id)
    return _view(up, _received(session, upload_id))


@router.put("/uploads/{upload_id}/chunks/{n}")
async def put_chunk(
    upload_id: str,
    n: int,
    request: Request,
    x_chunk_sha256: str | None = Header(default=None, description="SHA-256 hex del trozo (opcional)"),
    _: Principal = Depends(require_write),
    session: Session = Depends(get_session),
):
    """Cuerpo = bytes crudos del trozo. Idempotente: repetir un trozo lo sobrescribe."""
    up = _get(session, upload_id)
    if up.status != "uploading":
        raise HTTPException(409, "La subida ya está completada")
    if not 0 <= n < up.total_chunks:
        raise HTTPException(422, f"Trozo {n} fuera de rango (0..{up.total_chunks - 1})")
    expected = up.chunk_size if n < up.total_chunks - 1 else up.size - n * up.chunk_size
    h, written = hashlib.sha256(), 0
    path = ensure_within(get_settings().uploads_dir, Path(up.path))
    with open(path, "r+b") as f:
        f.seek(n * up.chunk_size)
        async for data in request.stream():
            written += len(data)
            if written > expected:
                raise HTTPException(413, f"El trozo {n} debe medir {expected} bytes")
            h.update(data)
            f.write(data)
    if written != expected:
        raise HTTPException(400, f"El trozo {n} debe medir {expected} bytes y llegaron {written}")
    if x_chunk_sha256 and x_chunk_sha256.lower() != h.hexdigest():
        raise HTTPException(422, f"SHA-256 del trozo {n} no coincide; vuelve a enviarlo")
    session.merge(UploadChunk(upload_id=upload_id, n=n))
    session.commit()
    count = session.exec(select(func.count()).select_from(UploadChunk).where(UploadChunk.upload_id == upload_id)).one()
    return {"n": n, "received_count": count, "total_chunks": up.total_chunks}


@router.post("/uploads/{upload_id}/complete")
def complete_upload(upload_id: str, _: Principal = Depends(require_write), session: Session = Depends(get_session)):
    """Verifica que están todos los trozos, valida el vídeo y encola proxy y peaks."""
    up = _get(session, upload_id)
    if up.status == "complete":
        return {"media_id": up.media_id, "jobs": []}
    have = set(_received(session, upload_id))
    missing = [i for i in range(up.total_chunks) if i not in have]
    if missing:
        raise HTTPException(409, f"Faltan {len(missing)} trozos: {missing[:50]}")
    try:
        media, jobs = register_media(session, Path(up.path), up.filename)
    except ProbeError as e:
        Path(up.path).unlink(missing_ok=True)
        raise HTTPException(422, str(e)) from e
    up.status, up.media_id = "complete", media.id
    session.add(up)
    for c in session.exec(select(UploadChunk).where(UploadChunk.upload_id == upload_id)).all():
        session.delete(c)
    session.commit()
    return {"media_id": media.id, "jobs": jobs}
