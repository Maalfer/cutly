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
from cutly.services.verify.geometry import Rect4
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


# --- Palabras y escenas de código DENTRO del proyecto (contexto real: tamaño, parámetros y lo que se dice) ----------


def _mapped_words(session: Session, row: Project, doc: ProjectDoc) -> list[tuple[float, float, str]]:
    """Palabras dichas en tiempo del clip resultante: (inicio, fin, texto)."""
    from cutly.services.render.ass import build_time_map, map_words

    t = session.exec(select(Transcript).where(Transcript.media_id == row.media_id)).first()
    if t is None:
        raise HTTPException(409, "El vídeo no tiene transcripción: POST /media/{id}/transcribe")
    return map_words([w for sg in t.segments for w in sg.get("words", [])], build_time_map(doc.timeline))


def _norm(x: str) -> str:
    import unicodedata

    d = unicodedata.normalize("NFD", x.lower())
    return re.sub(r"[^a-z0-9ñ ]", "", "".join(c for c in d if unicodedata.category(c) != "Mn"))


@router.get("/projects/{project_id}/safe-zones")
def safe_zones(
    project_id: str,
    samples: int = Query(8, ge=3, le=16),
    _: Principal = Depends(require_read),
    session: Session = Depends(get_session),
):
    """Dónde cae la cara (si la hay) en el fotograma de SALIDA y qué franjas quedan libres para poner texto/rótulos,
    ANTES de montar nada (evita el ciclo «coloca -> cutly_review -> covers_face -> mueve»). Muestrea `samples`
    instantes repartidos por el clip resultante, detecta caras en el original y las lleva al reencuadre actual.
    Ya tiene en cuenta la franja inferior de la app (y > 0.82) y el borde derecho (botones)."""
    from cutly.services.verify.checks import UI_BOTTOM, UI_RIGHT_X, output_to_source
    from cutly.services.verify.faces import detect_faces
    from cutly.services.verify.geometry import Frame, source_rect_to_output

    row, doc = _project(session, project_id)
    media = session.get(Media, row.media_id)
    if media is None:
        raise HTTPException(404, "Vídeo no encontrado")
    if not doc.timeline:
        return {"has_face": False, "note": "Línea de tiempo vacía"}
    meta = media.metadata_json or {}
    proxy = media.proxy_path or media.original_path
    fr = Frame(meta.get("width", doc.output.width), meta.get("height", doc.output.height), doc.output.width, doc.output.height)
    dur = doc.duration
    times = [round(dur * (k + 0.5) / samples, 2) for k in range(samples)]
    per_sample = []
    bands: list[Rect4] = []
    for t in times:
        st = output_to_source(doc, t)
        if st is None:
            continue
        rects = [r for f in detect_faces(proxy, st) for r in source_rect_to_output(f, doc.reframe, fr)]
        if rects:
            x0 = min(r[0] for r in rects); y0 = min(r[1] for r in rects)
            x1 = max(r[2] for r in rects); y1 = max(r[3] for r in rects)
            bands.append((x0, y0, x1, y1))
            per_sample.append({"t": t, "face": [round(v, 3) for v in (x0, y0, x1, y1)]})
        else:
            per_sample.append({"t": t, "face": None})
    if not bands:
        return {
            "has_face": False, "duration": round(dur, 2), "samples": per_sample,
            "free_y_bands": [[0.0, round(UI_BOTTOM - 0.02, 2)]],
            "note": "No se detectó cara en estos instantes (puede que no mire a cámara o que no haya facecam): el único límite es la franja inferior de la app.",
        }  # fmt: skip
    fy0, fy1 = min(b[1] for b in bands), max(b[3] for b in bands)  # franja vertical que ocupa la cara en CUALQUIER muestra
    fx0, fx1 = min(b[0] for b in bands), max(b[2] for b in bands)
    pad = 0.03
    free: list[list[float]] = []
    if fy0 - pad > 0.02:
        free.append([0.0, round(fy0 - pad, 2)])
    if UI_BOTTOM - pad > fy1 + pad:
        free.append([round(fy1 + pad, 2), round(UI_BOTTOM - 0.02, 2)])
    return {
        "has_face": True, "duration": round(dur, 2), "samples_checked": len(times), "samples": per_sample,
        "face_band_y": [round(fy0, 3), round(fy1, 3)], "face_band_x": [round(fx0, 3), round(fx1, 3)],
        "free_y_bands": free, "ui_reserved": {"bottom_y": UI_BOTTOM, "right_x": UI_RIGHT_X},
        "advice": (
            f"Pon rótulos/texto en y≈{round((free[0][0] + free[0][1]) / 2, 2)} (encima de la cara)" if free and free[0][1] - free[0][0] > 0.08 else
            (f"Pon rótulos/texto en y≈{round((free[-1][0] + free[-1][1]) / 2, 2)} (debajo de la cara, encima de la zona de botones)" if free else
             "La cara ocupa casi toda la franja segura: usa cajas pequeñas (bg_color semitransparente) o colócalas en x<0.2/x>0.8 si la cara está centrada")
        ),
    }  # fmt: skip


def _search_words(words, q: str, context: int, limit: int) -> dict:
    needle = [x for x in _norm(q).split() if x]
    if not needle:
        raise HTTPException(422, f"La búsqueda «{q}» no contiene letras ni números")
    norm = [_norm(w[2]) for w in words]
    out = []
    for i in range(len(words) - len(needle) + 1):
        if norm[i : i + len(needle)] == needle:
            j = i + len(needle) - 1
            lo, hi = max(0, i - context), min(len(words), j + 1 + context)
            out.append({"start": round(words[i][0], 2), "end": round(words[j][1], 2),
                        "text": " ".join(w[2] for w in words[i : j + 1]),
                        "context": " ".join(w[2] for w in words[lo:hi])})  # fmt: skip
            if len(out) >= limit:
                break
    return {"query": q, "count": len(out), "matches": out}


@router.get("/projects/{project_id}/words")
def search_words(
    project_id: str,
    q: str = Query(..., min_length=1, max_length=120, description="Palabra o frase (sin importar tildes/mayúsculas)"),
    context: int = Query(4, ge=0, le=12, description="Palabras de contexto a cada lado"),
    limit: int = Query(30, ge=1, le=200),
    _: Principal = Depends(require_read),
    session: Session = Depends(get_session),
):
    """¿En qué segundo se dice «cupón»? Busca una palabra o frase en lo hablado y devuelve cada aparición con su
    `start`/`end` en TIEMPO DEL CLIP RESULTANTE (el reloj de las capas) y el contexto, para colocar un icono, un
    efecto o una escena `scene` justo ahí. Dentro de una capa `scene` con `code`, lo dicho llega como `CUTLY_WORDS`.
    Para varios términos de una vez (evita una llamada por palabra): POST a esta misma ruta con `{"queries": [...]}`."""
    row, doc = _project(session, project_id)
    return _search_words(_mapped_words(session, row, doc), q, context, limit)


class WordsBatchIn(BaseModel):
    queries: list[str] = Field(min_length=1, max_length=40, description="Varias palabras/frases a localizar de una vez")
    context: int = Field(4, ge=0, le=12)
    limit: int = Field(10, ge=1, le=100, description="Máximo de apariciones POR término")


@router.post("/projects/{project_id}/words")
def search_words_batch(
    project_id: str, body: WordsBatchIn, _: Principal = Depends(require_read), session: Session = Depends(get_session)
):
    """Igual que `GET .../words` pero para VARIOS términos en una sola llamada: devuelve un resultado por cada uno
    de `queries`, en el mismo orden. Úsalo para ubicar de golpe todas las palabras que vas a destacar en el vídeo."""
    row, doc = _project(session, project_id)
    words = _mapped_words(session, row, doc)
    return {"results": [_search_words(words, q, body.context, body.limit) for q in body.queries]}


def _scene_layer(doc: ProjectDoc, layer_id: str):
    from cutly.schema.project import SceneLayer

    layer = next((x for x in doc.layers if x.id == layer_id), None)
    if layer is None:
        raise HTTPException(404, f"No hay ninguna capa '{layer_id}' en el proyecto")
    if not isinstance(layer, SceneLayer) or layer.code is None:
        raise HTTPException(422, f"La capa '{layer_id}' no es una escena con `code`")
    return layer


def _layer_words(session: Session, row: Project, doc: ProjectDoc, layer) -> list[dict]:
    try:
        mapped = _mapped_words(session, row, doc)
    except HTTPException:
        return []  # sin transcripción: la escena corre igual, con CUTLY_WORDS = []
    return [
        {"w": t, "start": round(a - layer.start, 3), "end": round(b - layer.start, 3)}
        for a, b, t in mapped
        if b > layer.start and a < layer.end
    ]


@router.post("/projects/{project_id}/layers/{layer_id}/lint")
def lint_layer(
    project_id: str, layer_id: str, _: Principal = Depends(require_write), session: Session = Depends(get_session)
):
    """`POST /scenes/lint` de una escena `code` ya montada, en su contexto REAL: tamaño de salida de su caja, sus
    `params`, su duración y las palabras que se dicen durante ella (`CUTLY_WORDS`). No hace falta reenviar el código."""
    from cutly.api.routers import scenes as sc
    from cutly.services.scene_js.lint import lint_scene
    from cutly.services.scene_js.renderer import JsSceneError, box_pixels

    row, doc = _project(session, project_id)
    layer = _scene_layer(doc, layer_id)
    _, _, bw, bh = box_pixels(layer, doc.output.width, doc.output.height)
    words = _layer_words(session, row, doc, layer)
    if not sc._busy.acquire(timeout=20):
        raise HTTPException(503, "Hay otra vista previa o validación en curso; reintenta en unos segundos")
    try:
        res = lint_scene(layer.code, bw, bh, layer.end - layer.start, layer.params, layer.fps or 20, words)
    except JsSceneError as e:
        raise HTTPException(422, str(e)) from e
    except ImportError as e:
        raise HTTPException(503, f"Este servidor no tiene instalado el motor de navegador ({e})") from e
    finally:
        sc._busy.release()
    return {**res.as_dict(), "layer_id": layer_id, "words_in_layer": len(words)}


@router.get("/projects/{project_id}/layers/{layer_id}/scene-preview")
def preview_layer(
    project_id: str,
    layer_id: str,
    times: str = Query("1,4,8", description="Segundos DESDE EL INICIO DE LA CAPA, separados por comas (máx. 12)"),
    width: int = Query(540, ge=160, le=1080),
    cols: int = Query(3, ge=1, le=6),
    _: Principal = Depends(require_write),
    session: Session = Depends(get_session),
):
    """Hoja de contacto PNG de una escena `code` ya montada, con sus `params` y sus palabras reales. Solo la escena
    (sobre fondo opaco); para verla compuesta sobre el vídeo usa `/projects/{id}/frame`. Cada instante cuesta una
    simulación desde cero: pide pocos."""
    from cutly.api.routers import scenes as sc
    from cutly.services.scene_js.renderer import JsSceneError, box_pixels, render_js_preview

    row, doc = _project(session, project_id)
    layer = _scene_layer(doc, layer_id)
    try:
        ts = sorted({max(0.0, float(x)) for x in times.split(",") if x.strip()})
    except ValueError as e:
        raise HTTPException(422, "`times` debe ser una lista de números separada por comas") from e
    if not ts:
        raise HTTPException(422, "Indica al menos un instante en `times`")
    _, _, bw, bh = box_pixels(layer, doc.output.width, doc.output.height)
    h = round(width * bh / bw)
    words = _layer_words(session, row, doc, layer)
    if not sc._busy.acquire(timeout=20):
        raise HTTPException(503, "Hay otra vista previa o validación en curso; reintenta en unos segundos")
    try:
        frames = render_js_preview(layer.code, width, h, ts, layer.fps or 20, layer.params, words, layer.transparent)
    except JsSceneError as e:
        raise HTTPException(422, str(e)) from e
    except ImportError as e:
        raise HTTPException(503, f"Este servidor no tiene instalado el motor de navegador ({e})") from e
    finally:
        sc._busy.release()
    if not frames:
        raise HTTPException(422, "Ningún instante pedido cayó dentro de la animación")
    return sc._sheet(frames, ts, cols)


@router.get("/projects/{project_id}/layers/{layer_id}/composite")
def composite_layer(
    project_id: str,
    layer_id: str,
    times: str = Query("1,4,8", description="Segundos DESDE EL INICIO DE LA CAPA, separados por comas (máx. 8)"),
    quality: Literal["preview", "draft"] = "preview",
    cols: int = Query(3, ge=1, le=4),
    wait: float = Query(60, ge=0, le=90),
    _: Principal = Depends(require_write),
    session: Session = Depends(get_session),
):
    """La escena `code` COMPUESTA sobre el vídeo (con el resto de capas), para juzgar el aspecto real: ¿tapa la cara?,
    ¿choca con los subtítulos?, ¿se lee sobre el fondo? Mucho más barato que `/projects/{id}/frame` con escenas de código:
    ese simula la animación desde cero por CADA fotograma; aquí el vídeo base sale sin la escena (solo FFmpeg) y la escena
    se simula UNA vez para todos los instantes y se pega en su caja. Aproximaciones: va por encima de todas las capas
    (ignora `z`), aplica `opacity` pero no `animations.enter/exit`. Para la verificación exacta final usa `/frame`."""
    from PIL import Image

    from cutly.api.routers import scenes as sc
    from cutly.services.scene_js.renderer import JsSceneError, box_pixels, render_js_preview

    row, doc = _project(session, project_id)
    layer = _scene_layer(doc, layer_id)
    try:
        rel = sorted({round(max(0.0, float(x)), 3) for x in times.split(",") if x.strip()})
    except ValueError as e:
        raise HTTPException(422, "`times` debe ser una lista de números separada por comas") from e
    if not rel or len(rel) > 8:
        raise HTTPException(422, "Indica entre 1 y 8 instantes en `times`")
    absolute = [round(layer.start + t, 3) for t in rel]
    bad = [t for t in absolute if t > doc.duration]
    if bad:
        raise HTTPException(422, f"Instantes fuera del clip (dura {doc.duration:.2f} s): {bad}")

    base = doc.model_copy(
        update={"layers": [x.model_copy(update={"visible": False}) if x.id == layer_id else x for x in doc.layers]}
    )
    job = enqueue(session, "frames", _snapshot(row, base, times=absolute, quality=quality, format="png"))
    j = _wait(job.id, wait)
    if j is None:
        return JSONResponse({"job_id": job.id, "status": "running", "hint": f"Consulta GET /jobs/{job.id}"}, status_code=202)  # fmt: skip
    if j.status != "done":
        raise HTTPException(500, f"No se pudo generar el vídeo base: {j.error}")
    fdir = _frame_dir(row.id, j.id)
    bases = [Image.open(fdir / f"f{i}.png").convert("RGB") for i in range(len(absolute))]
    k = bases[0].width / doc.output.width  # escala de los fotogramas respecto a la salida

    x0, y0, bw, bh = box_pixels(layer, doc.output.width, doc.output.height)
    inside = [t for t in rel if t < layer.end - layer.start]
    words = _layer_words(session, row, doc, layer)
    scene: dict[float, Image.Image] = {}
    if inside:
        if not sc._busy.acquire(timeout=20):
            raise HTTPException(503, "Hay otra vista previa o validación en curso; reintenta en unos segundos")
        try:
            frames = render_js_preview(layer.code, bw, bh, inside, layer.fps or doc.output.fps, layer.params, words, layer.transparent)
        except JsSceneError as e:
            raise HTTPException(422, str(e)) from e
        except ImportError as e:
            raise HTTPException(503, f"Este servidor no tiene instalado el motor de navegador ({e})") from e
        finally:
            sc._busy.release()
        scene = dict(zip(sorted(set(inside)), frames, strict=False))
    out = []
    for t, img in zip(rel, bases, strict=True):
        fr = scene.get(t)
        if fr is not None:
            small = fr.resize((max(2, round(bw * k)), max(2, round(bh * k))), Image.LANCZOS)
            op = min(max(layer.opacity, 0.0), 1.0)
            if small.mode == "RGBA":  # escena transparente: su propio alfa, atenuado por la opacidad de la capa
                mask = small.getchannel("A").point(lambda a: round(a * op))
                small = small.convert("RGB")
            else:
                mask = Image.new("L", small.size, round(255 * op))
            img.paste(small, (round(x0 * k), round(y0 * k)), mask)
        out.append(img)
    return sc._sheet(out, absolute, cols)
