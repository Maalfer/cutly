"""Alta y baja de medios: mover el archivo, sondear y encolar proxy/peaks."""

import logging
import shutil
import time
from pathlib import Path

from sqlmodel import Session, select

from cutly.config import get_settings
from cutly.db.models import ClipCandidate, Job, Media, Project, Transcript
from cutly.services.ingest.ffprobe import probe
from cutly.worker.queue import enqueue

log = logging.getLogger(__name__)

# Antigüedad mínima de una carpeta sin fila en la BD para considerarla huérfana (evita carreras con
# una subida que acaba de crear la carpeta y aún no ha hecho commit).
ORPHAN_MIN_AGE_S = 3600


def media_dir(media_id: str) -> Path:
    return get_settings().media_dir / media_id


def register_media(session: Session, src: Path, filename: str) -> tuple[Media, list[str]]:
    """Sondea `src` (lanza ProbeError si no es vídeo), lo mueve a su carpeta y encola el proceso."""
    info = probe(src)
    media = Media(filename=filename, original_path="", status="processing")
    d = media_dir(media.id)
    d.mkdir(parents=True, exist_ok=True)
    dest = d / f"original{Path(filename).suffix.lower()}"
    shutil.move(str(src), dest)
    media.original_path = str(dest)
    media.size_bytes = dest.stat().st_size
    media.duration = info["duration"]
    media.metadata_json = info
    session.add(media)
    session.commit()
    session.refresh(media)
    jobs = [
        enqueue(session, "media.peaks", {"media_id": media.id}).id,
        enqueue(session, "media.proxy", {"media_id": media.id}).id,
    ]
    return media, jobs


# --- Borrado transaccional ---------------------------------------------------------------------------------


def _trash_dir() -> Path:
    d = get_settings().data_dir / ".trash"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _move_into_trash(paths: list[Path], trash: Path) -> list[tuple[Path, Path]]:
    """Renombra (atómico en el mismo sistema de ficheros) cada ruta existente dentro de `trash`.

    Devuelve [(original, destino)] para poder restaurar si la transacción de BD falla.
    """
    moved: list[tuple[Path, Path]] = []
    for i, src in enumerate(paths):
        if not src.exists():
            continue
        dst = trash / f"{i}-{src.name}"
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            src.rename(dst)  # atómico si comparten FS
        except OSError:
            shutil.move(str(src), str(dst))
        moved.append((src, dst))
    return moved


def _restore(moved: list[tuple[Path, Path]]) -> None:
    for src, dst in reversed(moved):
        if not dst.exists():
            continue
        try:
            src.parent.mkdir(parents=True, exist_ok=True)
            dst.rename(src)
        except OSError:
            shutil.move(str(dst), str(src))


def _jobs_for(session: Session, media_id: str, project_ids: set[str]) -> list[Job]:
    out: list[Job] = []
    for job in session.exec(select(Job)).all():
        p = job.params or {}
        if p.get("media_id") == media_id or p.get("project_id") in project_ids:
            out.append(job)
    return out


def delete_media(session: Session, media: Media) -> dict:
    """Borra el medio y TODO lo asociado (BD y disco) de forma segura.

    Orden: cancelar jobs → mover archivos a una papelera temporal (atómico) → borrar filas y commit →
    borrar la papelera. Si el commit falla, los archivos se restauran. Devuelve un resumen de lo borrado.
    """
    from cutly.services.projects.store import delete_project_rows

    media_path = media_dir(media.id)
    projects = session.exec(select(Project).where(Project.media_id == media.id)).all()
    project_ids = {p.id for p in projects}

    # 1) Los jobs en curso comprueban la BD: al borrar sus filas se cancelan solos en el siguiente check.
    jobs = _jobs_for(session, media.id, project_ids)
    for job in jobs:
        session.delete(job)
    session.flush()

    # 2) Apartar los archivos antes de tocar la BD (rename atómico; nada se pierde si algo falla).
    render_dirs = [get_settings().renders_dir / pid for pid in project_ids]
    all_paths = [media_path, *render_dirs]
    freed = sum(_size(p) for p in all_paths)
    trash = _trash_dir() / f"media-{media.id}-{int(time.time() * 1000)}"
    moved = _move_into_trash(all_paths, trash)

    # 3) Borrar filas y confirmar.
    try:
        for p in projects:
            delete_project_rows(session, p.id, remove_files=False)
        for model in (Transcript, ClipCandidate):
            for row in session.exec(select(model).where(model.media_id == media.id)).all():
                session.delete(row)
        session.flush()
        session.delete(media)
        session.commit()
    except Exception:
        session.rollback()
        _restore(moved)
        shutil.rmtree(trash, ignore_errors=True)
        raise

    # 4) Ya no hay filas: borrar definitivamente. Si algo falla queda en .trash y se reintenta al arrancar.
    for src, _ in moved:
        if src == media_path:  # un job rezagado pudo recrear la carpeta
            shutil.rmtree(src, ignore_errors=True)
    shutil.rmtree(trash, ignore_errors=True)
    if trash.exists():
        log.warning("No se pudo vaciar la papelera %s; se reintentará al arrancar", trash)

    return {
        "ok": True,
        "media_id": media.id,
        "projects_deleted": len(project_ids),
        "jobs_cancelled": len(jobs),
        "paths_removed": [str(src) for src, _ in moved],
        "freed_bytes": freed,
    }


def _size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for p in path.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            pass
    return total


def purge_orphans() -> dict:
    """Limpia archivos sin fila en la BD: papelera, carpetas de medios huérfanas y uploads abandonados.

    Pensado para ejecutarse al arrancar (idempotente y seguro: solo toca cosas con antigüedad mínima y
    nunca durante una subida en curso).
    """
    s = get_settings()
    removed: list[str] = []

    trash = _trash_dir()
    for d in trash.iterdir():
        try:
            if time.time() - d.stat().st_mtime <= ORPHAN_MIN_AGE_S:
                continue  # un borrado en curso: no tocarlo
        except OSError:
            continue
        shutil.rmtree(d, ignore_errors=True)
        if not d.exists():
            removed.append(str(d))

    if s.media_dir.exists():
        from cutly.db.session import get_engine

        with Session(get_engine()) as session:
            known = {m.id for m in session.exec(select(Media)).all()}
        now = time.time()
        for d in s.media_dir.iterdir():
            if not d.is_dir() or d.name in known:
                continue
            try:
                old = now - d.stat().st_mtime > ORPHAN_MIN_AGE_S
            except OSError:
                old = False
            if old:
                shutil.rmtree(d, ignore_errors=True)
                if not d.exists():
                    removed.append(str(d))

    # Uploads abandonados: filas "uploading" sin completar en 7 días, con sus trozos y su .bin.
    try:
        from datetime import UTC, datetime, timedelta

        from sqlmodel import col, delete

        from cutly.db.models import Upload, UploadChunk

        cutoff = datetime.now(UTC) - timedelta(days=7)
        with Session(get_engine()) as session:
            stale = session.exec(
                select(Upload).where(Upload.status != "complete", col(Upload.created_at) < cutoff)
            ).all()
            for up in stale:
                session.exec(delete(UploadChunk).where(col(UploadChunk.upload_id) == up.id))
                session.delete(up)
                try:
                    Path(up.path).unlink(missing_ok=True)
                except OSError:
                    pass
                removed.append(up.path)
            session.commit()
    except Exception:  # noqa: BLE001 - la limpieza nunca debe romper el arranque
        log.exception("purge_orphans: no se pudieron limpiar las subidas abandonadas")

    # Uploads huérfanos (sin fila en Upload) con más de un día.
    try:
        from cutly.db.models import Upload

        with Session(get_engine()) as session:
            live = {u.id for u in session.exec(select(Upload)).all()}
        now = time.time()
        if s.uploads_dir.exists():
            for f in s.uploads_dir.iterdir():
                stem = f.name.split(".", 1)[0]
                if stem in live:
                    continue
                try:
                    if f.is_file() and now - f.stat().st_mtime > 86400:
                        f.unlink(missing_ok=True)
                        removed.append(str(f))
                except OSError:
                    pass
    except Exception:  # noqa: BLE001 - la limpieza nunca debe romper el arranque
        log.exception("purge_orphans: no se pudieron revisar los uploads")

    return {"removed": removed}
