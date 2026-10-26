"""Verificación: lo que un agente necesita para «ver» un proyecto sin reproducir el vídeo."""

import re
import shutil
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from cutly.auth import Principal, require_read, require_write
from cutly.config import get_settings
from cutly.db.models import Job, Media, Project, Transcript
from cutly.db.session import get_engine, get_session
from cutly.schema.project import ProjectDoc
from cutly.services.projects import store
from cutly.services.render.graph import MediaInfo
from cutly.services.sanitize.paths import ensure_within
from cutly.services.verify import audio as audio_mod
from cutly.services.verify.frames import source_frame
from cutly.worker.queue import enqueue

router = APIRouter(tags=["verify"])
_NAME = re.compile(r"^(f\d{1,2}\.(jpg|png)|sheet\.jpg)$")


class FramesIn(BaseModel):
    times: list[float] = Field(min_length=1, max_length=16, description="Segundos del clip resultante")
    quality: Literal["preview", "draft", "final"] = Field(
        "preview", description="preview=½ resolución, draft=⅓, final=completa"
    )
    format: Literal["jpg", "png"] = "jpg"
    cols: int | None = Field(None, ge=1, le=8, description="Columnas de la hoja de contacto")


def _project(session: Session, pid: str) -> tuple[Project, ProjectDoc]:
    row = session.get(Project, pid)
    if row is None:
        raise HTTPException(404, "Proyecto no encontrado")
    return row, store.load_doc(session, row)


def _snapshot(row: Project, doc: ProjectDoc, **extra) -> dict:
    return {"project_id": row.id, "project_version": row.version, "doc": doc.model_dump(mode="json"), **extra}


def _wait(job_id: str, wait: float) -> Job | None:
    """Espera (sin bloquear al worker) a que el job termine; None si se agota el tiempo."""
    deadline = time.monotonic() + wait
    while True:
        with Session(get_engine()) as s:
            j = s.get(Job, job_id)
            if j and j.status in ("done", "failed", "cancelled"):
                s.expunge(j)
                return j
        if time.monotonic() > deadline:
            return None
        time.sleep(0.4)


def _frame_dir(project_id: str, job_id: str):
    return get_settings().renders_dir / project_id / "frames" / job_id


@router.post("/projects/{project_id}/frames")
def request_frames(
    project_id: str, body: FramesIn, _: Principal = Depends(require_write), session: Session = Depends(get_session)
):
    """Fotogramas con TODAS las capas aplicadas en los instantes pedidos (job). Si hay más de uno, también una hoja de
    contacto con los tiempos. Resultado en `GET /frames/{job_id}/f0.jpg … / sheet.jpg`."""
    row, doc = _project(session, project_id)
    if not doc.timeline:
        raise HTTPException(422, "El proyecto no tiene clips: añade uno con add_clip")
    bad = [t for t in body.times if t < 0 or t > doc.duration]
    if bad:
        raise HTTPException(422, f"Instantes fuera del clip (dura {doc.duration:.2f} s): {bad}")
    return {"job_id": enqueue(session, "frames", _snapshot(row, doc, **body.model_dump())).id}


def _image_or_202(session: Session, row: Project, doc: ProjectDoc, params: dict, name: str, wait: float):
    job = enqueue(session, "frames", _snapshot(row, doc, **params))
    j = _wait(job.id, wait)
    if j is None:
        return JSONResponse(
            {
                "job_id": job.id,
                "status": "running",
                "hint": f"Consulta GET /jobs/{job.id} y luego GET /frames/{job.id}/{name}",
            },
            status_code=202,
        )
    if j.status != "done":
        raise HTTPException(500, f"No se pudo generar el fotograma: {j.error}")
    path = _frame_dir(row.id, j.id) / name
    return Response(path.read_bytes(), media_type="image/jpeg" if name.endswith("jpg") else "image/png",
                    headers={"X-Job-Id": j.id, "X-Warnings": "; ".join((j.result or {}).get("warnings", []))[:500] or "ninguno"})  # fmt: skip


@router.get("/projects/{project_id}/frame")
def get_frame(
    project_id: str,
    t: float = Query(ge=0, description="Segundo del clip resultante"),
    quality: Literal["preview", "draft", "final"] = "preview",
    wait: float = Query(
        40, ge=0, le=90, description="Segundos que espera el resultado antes de devolver 202 con el job"
    ),
    _: Principal = Depends(require_write),
    session: Session = Depends(get_session),
):
    """Un fotograma (JPEG) con las capas aplicadas. Bloquea hasta `wait` s; si no llega, 202 + job_id."""
    row, doc = _project(session, project_id)
    if t > doc.duration:
        raise HTTPException(422, f"t={t} fuera del clip (dura {doc.duration:.2f} s)")
    return _image_or_202(session, row, doc, {"times": [t], "quality": quality, "format": "jpg"}, "f0.jpg", wait)


@router.get("/projects/{project_id}/filmstrip")
def get_filmstrip(
    project_id: str,
    count: int = Query(8, ge=2, le=16),
    start: float = Query(0, ge=0),
    end: float | None = None,
    cols: int = Query(4, ge=1, le=8),
    quality: Literal["preview", "draft"] = "draft",
    wait: float = Query(60, ge=0, le=90),
    _: Principal = Depends(require_write),
    session: Session = Depends(get_session),
):
    """Tira de miniaturas (una sola imagen, con el tiempo de cada fotograma) repartidas por el clip o por [start, end]."""
    row, doc = _project(session, project_id)
    end = doc.duration if end is None else min(end, doc.duration)
    if end - start < 0.2:
        raise HTTPException(422, "Intervalo demasiado corto")
    times = [round(start + (end - start) * (k + 0.5) / count, 2) for k in range(count)]
    return _image_or_202(
        session, row, doc, {"times": times, "quality": quality, "format": "jpg", "cols": cols}, "sheet.jpg", wait
    )


@router.get("/frames/{job_id}/{name}")
def download_frame(
    job_id: str, name: str, _: Principal = Depends(require_read), session: Session = Depends(get_session)
):
    if not _NAME.match(name):
        raise HTTPException(404, "Nombre de archivo no válido (f0.jpg, f1.jpg… o sheet.jpg)")
    job = session.get(Job, job_id)
    if job is None or job.type != "frames":
        raise HTTPException(404, "Job de fotogramas no encontrado")
    if job.status != "done":
        raise HTTPException(409, f"Aún no está listo (estado: {job.status}); consulta GET /jobs/{job_id}")
    d = _frame_dir(job.params["project_id"], job_id)
    path = ensure_within(get_settings().renders_dir, d / name)
    if not path.is_file():
        raise HTTPException(410, "El archivo ya no existe (se limpian a las 24 h) o no se generó; vuelve a pedirlo")
    return FileResponse(path, media_type="image/png" if name.endswith("png") else "image/jpeg")


@router.get("/media/{media_id}/frame")
def media_frame(
    media_id: str,
    t: float = Query(0, ge=0),
    grid: bool = Query(True, description="Dibuja una rejilla 0–1 etiquetada para elegir rectángulos de reencuadre"),
    width: int = Query(720, ge=160, le=1920),
    _: Principal = Depends(require_read),
    session: Session = Depends(get_session),
):
    """Fotograma del vídeo ORIGINAL (sin capas). Con `grid`, las líneas marcan 0.1…0.9 del ancho y del alto: así se
    leen directamente las coordenadas de `facecam`/`game` de `set_reframe`."""
    m = session.get(Media, media_id)
    if m is None:
        raise HTTPException(404, "Medio no encontrado")
    if m.duration and t > m.duration:
        raise HTTPException(422, f"t={t} fuera del vídeo (dura {m.duration:.1f} s)")
    try:
        data = source_frame(m.proxy_path or m.original_path, t, width, grid)
    except RuntimeError as e:
        raise HTTPException(500, str(e)) from e
    return Response(data, media_type="image/jpeg")


@router.get("/projects/{project_id}/audio-stats")
def audio_stats(project_id: str, _: Principal = Depends(require_read), session: Session = Depends(get_session)):
    """Volumen integrado (LUFS), pico, rango dinámico y silencios, en tiempo del clip resultante."""
    row, doc = _project(session, project_id)
    if not doc.timeline:
        raise HTTPException(422, "El proyecto no tiene clips")
    m = session.get(Media, row.media_id)
    meta = m.metadata_json  # type: ignore[union-attr]
    work = get_settings().renders_dir / "tmp" / f"stats_{row.id}"
    try:
        stats = audio_mod.measure(
            doc, MediaInfo(m.original_path, meta["width"], meta["height"], bool(meta.get("has_audio"))), work
        )  # type: ignore[union-attr]
    except RuntimeError as e:
        raise HTTPException(500, str(e)) from e
    finally:
        shutil.rmtree(work, ignore_errors=True)
    lufs = stats.get("integrated_lufs")
    stats["normalization_gain_db"] = (
        round(doc.audio.target_lufs - lufs, 1) if (lufs is not None and doc.audio.normalize) else None
    )
    return stats


@router.post("/projects/{project_id}/checks")
def request_checks(project_id: str, _: Principal = Depends(require_write), session: Session = Depends(get_session)):
    """Comprobaciones automáticas (job): caras tapadas, texto fuera de pantalla o en zonas de la app, rótulos que se
    pisan, cortes a mitad de palabra/frase, audio (volumen, picos, silencios) y más. Resultado en `GET /jobs/{id}`."""
    row, doc = _project(session, project_id)
    return {"job_id": enqueue(session, "checks", _snapshot(row, doc)).id}


@router.get("/projects/{project_id}/checks")
def get_checks(
    project_id: str,
    wait: float = Query(90, ge=0, le=120),
    _: Principal = Depends(require_write),
    session: Session = Depends(get_session),
):
    """Lanza las comprobaciones y espera el resultado (hasta `wait` s). Si no llega a tiempo, 202 + job_id."""
    row, doc = _project(session, project_id)
    job = enqueue(session, "checks", _snapshot(row, doc))
    j = _wait(job.id, wait)
    if j is None:
        return JSONResponse(
            {"job_id": job.id, "status": "running", "hint": f"Consulta GET /jobs/{job.id}"}, status_code=202
        )
    if j.status != "done":
        raise HTTPException(500, f"Fallaron las comprobaciones: {j.error}")
    return {**(j.result or {}), "job_id": j.id, "project_version": row.version}


@router.get("/projects/{project_id}/transcript")
def project_transcript(
    project_id: str,
    format: Literal["json", "text"] = "text",
    _: Principal = Depends(require_read),
    session: Session = Depends(get_session),
):
    """Lo hablado en TIEMPO DEL CLIP RESULTANTE, agrupado en frases: es el reloj que usan las capas, así que sirve
    para poner un icono o un efecto justo cuando se dice una palabra."""
    from cutly.services.render.ass import build_time_map, map_words

    row, doc = _project(session, project_id)
    t = session.exec(select(Transcript).where(Transcript.media_id == row.media_id)).first()
    if t is None:
        raise HTTPException(409, "El vídeo no tiene transcripción: POST /media/{id}/transcribe")
    words = map_words([w for s in t.segments for w in s.get("words", [])], build_time_map(doc.timeline))
    phrases: list[list[tuple[float, float, str]]] = []
    for w in words:
        if (
            not phrases
            or w[0] - phrases[-1][-1][1] > 0.6
            or phrases[-1][-1][2].rstrip("\"'»”)").endswith((".", "!", "?", "…"))
        ):
            phrases.append([])
        phrases[-1].append(w)
    out = [{"start": round(p[0][0], 2), "end": round(p[-1][1], 2), "text": " ".join(x[2] for x in p),
            "words": [{"w": x[2], "start": round(x[0], 2), "end": round(x[1], 2)} for x in p]} for p in phrases]  # fmt: skip
    if format == "json":
        return {"duration": round(doc.duration, 2), "phrases": out}
    lines = [
        f"[{int(p['start']) // 60}:{p['start'] % 60:05.2f}–{int(p['end']) // 60}:{p['end'] % 60:05.2f}] {p['text']}"
        for p in out
    ]
    return Response("\n".join(lines), media_type="text/plain; charset=utf-8")
