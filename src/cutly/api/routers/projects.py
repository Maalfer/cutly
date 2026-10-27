"""Proyectos de edición: CRUD, operaciones atómicas por lotes, deshacer/rehacer y layers."""

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError
from sqlmodel import Session, select

from cutly.auth import Principal, require_read, require_write
from cutly.db.models import ClipCandidate, Media, Project, now
from cutly.db.session import get_session
from cutly.schema.ops import AddLayer, Op, OpError, RemoveLayer, RippleDelete, UpdateLayer, apply_ops, fmt_validation
from cutly.schema.project import Layer, ProjectDoc, timeline_starts
from cutly.services.projects import store
from cutly.services.projects.check import check_project
from cutly.services.projects.hooks import check_layer
from cutly.services.scene_js.kinetic import TitleSpec, build_title_layer

router = APIRouter(tags=["projects"])


class ProjectCreate(BaseModel):
    media_id: str
    name: str | None = Field(None, max_length=120)
    candidate_id: str | None = Field(
        None, description="Crea el proyecto con el rango de un candidato aceptado/propuesto"
    )
    source_in: float | None = Field(None, ge=0, description="Inicio (s del original) si no hay candidato")
    source_out: float | None = Field(None, gt=0)
    subtitles: bool = Field(True, description="Añade una layer de subtítulos desde la transcripción si existe")
    layout: Literal["vertical", "horizontal"] = Field("vertical", description="vertical = 1080x1920 (reels/shorts, recorte centrado); horizontal = 1920x1080 sin recorte (YouTube, clips largos de un directo)")


class OpsIn(BaseModel):
    ops: list[Op] = Field(min_length=1, max_length=100, description="Se aplican en orden, todo o nada")
    label: str | None = Field(None, max_length=200, description="Nombre del paso en el historial")
    base_version: int | None = Field(None, description="Si se indica y no coincide con la actual: 409")


class StepIn(BaseModel):
    base_version: int | None = None


class LayerIn(BaseModel):
    layer: Layer
    base_version: int | None = None


class LayerPatchIn(BaseModel):
    patch: dict[str, Any]
    base_version: int | None = None


class RenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


def _row(session: Session, project_id: str) -> Project:
    row = session.get(Project, project_id)
    if row is None:
        raise HTTPException(404, "Proyecto no encontrado; lista los existentes con GET /projects")
    return row


def _media(session: Session, media_id: str) -> Media:
    m = session.get(Media, media_id)
    if m is None:
        raise HTTPException(404, "Medio no encontrado")
    return m


def _view(session: Session, row: Project, doc: ProjectDoc | None = None) -> dict:
    doc = doc or store.load_doc(session, row)
    undo, redo = store.can_undo_redo(session, row)
    return {
        "id": row.id, "name": row.name, "media_id": row.media_id, "candidate_id": row.candidate_id,
        "version": row.version, "schema_version": row.schema_version, "duration": doc.duration,
        "can_undo": undo, "can_redo": redo, "updated_at": row.updated_at,
        "warnings": check_project(doc, store.has_transcript(session, row.media_id)),
        "project": doc.model_dump(mode="json"),
    }  # fmt: skip


def _layer_label(layer) -> str | None:
    for attr in ("text", "template", "effect", "asset"):
        v = getattr(layer, attr, None)
        if v:
            return str(v)[:60]
    if getattr(layer, "code", None):
        return f"código HTML ({len(layer.code)} car.)"
    return None


def _summary(doc: ProjectDoc) -> dict:
    """Estado compacto en el reloj del clip RESULTANTE (el de las capas): para reorientarse sin leer el JSON entero."""
    starts = timeline_starts(doc.timeline)
    return {
        "duration": round(doc.duration, 3),
        "output": doc.output.model_dump(),
        "clips": [
            {"id": c.id, "out_start": round(s, 3), "out_end": round(s + c.duration, 3),
             "source_in": round(c.source_in, 3), "source_out": round(c.source_out, 3), "speed": c.speed,
             "transition_in": c.transition_in.name if c.transition_in else None}
            for s, c in zip(starts, doc.timeline, strict=True)
        ],
        "layers": [
            {"id": x.id, "type": x.type, "start": round(x.start, 3), "end": round(x.end, 3), "z": x.z,
             "visible": x.visible, "label": _layer_label(x)}
            for x in sorted(doc.layers, key=lambda y: (y.start, y.z))
        ],
    }  # fmt: skip


def _run(session: Session, row: Project, fn) -> dict:
    try:
        doc = fn()
    except OpError as e:
        raise HTTPException(422, str(e)) from e
    except ValidationError as e:
        raise HTTPException(422, fmt_validation(e)) from e
    except store.Conflict as e:
        raise HTTPException(409, str(e)) from e
    return _view(session, row, doc)


@router.get("/project-schema")
def project_schema(_: Principal = Depends(require_read)):
    """JSON Schema del documento de proyecto (tipos de layer, estilos, animaciones, límites)."""
    return ProjectDoc.model_json_schema()


@router.post("/projects")
def create_project(body: ProjectCreate, _: Principal = Depends(require_write), session: Session = Depends(get_session)):
    """Crea un proyecto de edición a partir de un candidato o de un rango del vídeo original."""
    media = _media(session, body.media_id)
    cand = None
    if body.candidate_id:
        cand = session.get(ClipCandidate, body.candidate_id)
        if cand is None:
            raise HTTPException(404, "Candidato no encontrado")
    try:
        row = store.create_project(session, media, body.name, cand, body.source_in, body.source_out, body.subtitles, body.layout)
    except (OpError, ValidationError) as e:
        raise HTTPException(422, fmt_validation(e) if isinstance(e, ValidationError) else str(e)) from e
    return _view(session, row)


@router.get("/projects")
def list_projects(
    media_id: str | None = None, _: Principal = Depends(require_read), session: Session = Depends(get_session)
):
    q = select(Project).order_by(Project.updated_at.desc())  # type: ignore[attr-defined]
    if media_id:
        q = q.where(Project.media_id == media_id)
    out = []
    for r in session.exec(q).all():
        doc = store.load_doc(session, r)
        out.append({"id": r.id, "name": r.name, "media_id": r.media_id, "version": r.version,
                    "duration": doc.duration, "clips": len(doc.timeline), "layers": len(doc.layers),
                    "updated_at": r.updated_at})  # fmt: skip
    return out


@router.get("/projects/{project_id}")
def get_project(project_id: str, _: Principal = Depends(require_read), session: Session = Depends(get_session)):
    return _view(session, _row(session, project_id))


@router.patch("/projects/{project_id}")
def rename_project(
    project_id: str, body: RenameIn, _: Principal = Depends(require_write), session: Session = Depends(get_session)
):
    row = _row(session, project_id)
    row.name, row.updated_at = body.name, now()
    session.add(row)
    session.commit()
    session.refresh(row)
    return _view(session, row)


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, _: Principal = Depends(require_write), session: Session = Depends(get_session)):
    row = _row(session, project_id)
    store.delete_project_rows(session, row.id)
    session.commit()
    return {"ok": True}


@router.post("/projects/{project_id}/ops")
def apply_operations(
    project_id: str,
    body: OpsIn,
    dry_run: bool = Query(False, description="true: valida y devuelve el resultado SIN guardar (ni historial)"),
    _: Principal = Depends(require_write),
    session: Session = Depends(get_session),
):
    """Aplica un lote de operaciones de forma atómica (todo o nada) como un único paso de historial.

    Operaciones: add_clip, split_clip, delete_clip, move_clip, set_clip_range, set_clip_speed,
    ripple_delete (quita un tramo del resultado y cierra el hueco, recolocando clips y capas), add_layer,
    update_layer, remove_layer, set_reframe, set_audio, set_color, set_output. Con `?dry_run=true` solo valida.
    """
    row = _row(session, project_id)
    media = _media(session, row.media_id)
    if dry_run:  # prueba el lote sin guardar nada ni tocar el historial
        before = store.load_doc(session, row)
        try:
            after = apply_ops(before, body.ops, media.duration, layer_hook=check_layer)
        except OpError as e:
            raise HTTPException(422, str(e)) from e
        except ValidationError as e:
            raise HTTPException(422, fmt_validation(e)) from e
        return {
            "dry_run": True, "ok": True, "duration_before": round(before.duration, 3),
            "duration_after": round(after.duration, 3),
            "warnings": check_project(after, store.has_transcript(session, row.media_id)),
            "summary": _summary(after),
        }  # fmt: skip
    return _run(
        session, row, lambda: store.apply_batch(session, row, body.ops, body.label, body.base_version, media.duration)
    )


@router.post("/projects/{project_id}/undo")
def undo(
    project_id: str,
    body: StepIn | None = None,
    _: Principal = Depends(require_write),
    session: Session = Depends(get_session),
):
    row = _row(session, project_id)
    return _run(session, row, lambda: store.undo(session, row, body.base_version if body else None))


@router.post("/projects/{project_id}/redo")
def redo(
    project_id: str,
    body: StepIn | None = None,
    _: Principal = Depends(require_write),
    session: Session = Depends(get_session),
):
    row = _row(session, project_id)
    return _run(session, row, lambda: store.redo(session, row, body.base_version if body else None))


@router.get("/projects/{project_id}/history")
def project_history(project_id: str, _: Principal = Depends(require_read), session: Session = Depends(get_session)):
    row = _row(session, project_id)
    return {"cursor": row.history_cursor, "entries": store.history(session, row)}


# Atajos para layers (equivalen a una operación suelta; son lo que usarán add_layer/update_layer/remove_layer de MCP)


@router.post("/projects/{project_id}/layers")
def add_layer(
    project_id: str, body: LayerIn, _: Principal = Depends(require_write), session: Session = Depends(get_session)
):
    row = _row(session, project_id)
    media = _media(session, row.media_id)
    ops = [AddLayer(op="add_layer", layer=body.layer)]
    return _run(
        session,
        row,
        lambda: store.apply_batch(
            session, row, ops, f"añadir layer {body.layer.type}", body.base_version, media.duration
        ),
    )


class TitleIn(TitleSpec):
    dry_run: bool = False
    base_version: int | None = None


@router.post("/projects/{project_id}/title")
def add_title(
    project_id: str, body: TitleIn, _: Principal = Depends(require_write), session: Session = Depends(get_session)
):
    """Añade un TÍTULO CINÉTICO: tipografía animada (degradado, letras que se abren, palabras con rebote, máscara…) sobre
    el vídeo, con fondo transparente. Eliges texto y estilo por línea (`title`, `kicker`, `statement`, `impact`, `ghost`) y
    el servidor monta la escena (no escribes HTML). Receta típica de dos líneas: `title` «11 Skills» + `kicker` «a la vez».
    `say` sincroniza una línea con la palabra hablada; `mark` colorea palabras clave. Tiempos en el reloj del clip resultante.
    Compruébalo con `GET /projects/{id}/layers/{layer_id}/composite?times=…`."""
    row = _row(session, project_id)
    media = _media(session, row.media_id)
    try:
        layer = build_title_layer(body)
    except ValidationError as e:
        raise HTTPException(422, fmt_validation(e)) from e
    if body.dry_run:
        before = store.load_doc(session, row)
        try:
            after = apply_ops(before, [AddLayer(op="add_layer", layer=layer)], media.duration, layer_hook=check_layer)
        except OpError as e:
            raise HTTPException(422, str(e)) from e
        except ValidationError as e:
            raise HTTPException(422, fmt_validation(e)) from e
        return {"dry_run": True, "ok": True, "layer_id": layer.id, "summary": _summary(after)}
    out = _run(
        session,
        row,
        lambda: store.apply_batch(
            session, row, [AddLayer(op="add_layer", layer=layer)], f"título: {body.lines[0].text[:30]}", body.base_version, media.duration
        ),
    )
    out["layer_id"] = layer.id
    return out


@router.patch("/projects/{project_id}/layers/{layer_id}")
def update_layer(
    project_id: str,
    layer_id: str,
    body: LayerPatchIn,
    _: Principal = Depends(require_write),
    session: Session = Depends(get_session),
):
    row = _row(session, project_id)
    media = _media(session, row.media_id)
    ops = [UpdateLayer(op="update_layer", layer_id=layer_id, patch=body.patch)]
    return _run(
        session,
        row,
        lambda: store.apply_batch(session, row, ops, f"editar layer {layer_id}", body.base_version, media.duration),
    )


@router.delete("/projects/{project_id}/layers/{layer_id}")
def remove_layer(
    project_id: str, layer_id: str, base_version: int | None = Query(None), _: Principal = Depends(require_write),
    session: Session = Depends(get_session),
):  # fmt: skip
    row = _row(session, project_id)
    media = _media(session, row.media_id)
    ops = [RemoveLayer(op="remove_layer", layer_id=layer_id)]
    return _run(
        session,
        row,
        lambda: store.apply_batch(session, row, ops, f"borrar layer {layer_id}", base_version, media.duration),
    )


@router.get("/projects/{project_id}/summary")
def project_summary(project_id: str, _: Principal = Depends(require_read), session: Session = Depends(get_session)):
    """Resumen compacto del proyecto con TODO en el reloj del clip resultante: clips (con su tramo de salida y de
    origen) y capas ordenadas por tiempo. Úsalo para reorientarte tras varias operaciones sin parsear el JSON completo."""
    row = _row(session, project_id)
    doc = store.load_doc(session, row)
    return {"id": row.id, "version": row.version, **_summary(doc)}


_DEFAULT_FILLERS = ["eh", "ehh", "eeh", "ehm", "em", "emm", "mm", "mmm", "hmm", "ah", "aah", "uh", "um"]


class AutoCutIn(BaseModel):
    silence_min: float = Field(0.7, ge=0.2, le=10, description="Una pausa entre palabras más larga que esto se recorta")
    keep_pad: float = Field(0.15, ge=0.0, le=1.0, description="Respiro que se conserva a cada lado de lo hablado")
    fillers: list[str] | None = Field(
        None, max_length=50,
        description="Muletillas a quitar (palabra suelta, sin tildes ni mayúsculas). Por defecto eh/em/mm/ah/um…; [] = ninguna",
    )  # fmt: skip
    trim_edges: bool = Field(True, description="También recorta el silencio antes de la 1.ª palabra y tras la última")
    repeats: bool = Field(True, description="Quita falsos arranques y repeticiones («es que es que…»): conserva la última toma")
    min_cut: float = Field(0.15, ge=0.05, le=5, description="No hace cortes más cortos que esto")
    max_cuts: int = Field(200, ge=1, le=500)
    dry_run: bool = Field(True, description="true (por defecto): solo propone los cortes; false: los aplica")
    base_version: int | None = None


def _plan_cuts(session: Session, row: Project, doc: ProjectDoc, body: "AutoCutIn"):
    """Pausas largas, silencios de los extremos y muletillas -> (cortes [a, b, motivos] fusionados, versión legible)."""
    import re
    import unicodedata

    from cutly.api.routers.verify import _mapped_words

    words = _mapped_words(session, row, doc)
    if not words:
        raise HTTPException(409, "No hay palabras en este tramo: transcribe el vídeo primero")

    def norm(x: str) -> str:
        d = unicodedata.normalize("NFD", x.lower())
        return re.sub(r"[^a-z0-9ñ]", "", "".join(c for c in d if unicodedata.category(c) != "Mn"))

    fill = {norm(f) for f in (_DEFAULT_FILLERS if body.fillers is None else body.fillers)}
    raw: list[tuple[float, float, str]] = []
    pad = body.keep_pad
    if body.trim_edges and words[0][0] - pad > body.min_cut:
        raw.append((0.0, words[0][0] - pad, "silencio inicial"))
    for prev, nxt in zip(words, words[1:], strict=False):
        if nxt[0] - prev[1] > body.silence_min:
            raw.append((prev[1] + pad, nxt[0] - pad, "pausa"))
    if body.trim_edges and doc.duration - words[-1][1] - pad > body.min_cut:
        raw.append((words[-1][1] + pad, doc.duration, "silencio final"))
    for w in words:
        if norm(w[2]) in fill:
            raw.append((max(0.0, w[0] - 0.03), w[1] + 0.03, f"muletilla «{w[2]}»"))
    if body.repeats:
        # Una secuencia de 1-4 palabras repetida seguida (con poca pausa) = falso arranque: se corta la PRIMERA toma.
        nw = [norm(w[2]) for w in words]
        i = 0
        while i < len(words) - 1:
            hit = 0
            for n in (4, 3, 2, 1):
                if i + 2 * n <= len(words) and nw[i : i + n] == nw[i + n : i + 2 * n] and all(nw[i : i + n]):
                    if n == 1 and (len(nw[i]) > 4 or nw[i] in fill):  # un «sí sí» o «el el»: solo palabras cortas
                        continue
                    if words[i + n][0] - words[i + n - 1][1] <= 0.8:
                        hit = n
                        break
            if hit:
                raw.append((max(0.0, words[i][0] - 0.03), words[i + hit][0] - 0.03, "repetición «" + " ".join(w[2] for w in words[i : i + hit]) + "»"))
                i += hit
            else:
                i += 1
    raw.sort()
    merged: list[list] = []
    for a, b, why in raw:
        if merged and a <= merged[-1][1] + 0.02:
            merged[-1][1] = max(merged[-1][1], b)
            if why not in merged[-1][2]:
                merged[-1][2].append(why)
        else:
            merged.append([a, b, [why]])
    cuts = [c for c in merged if c[1] - c[0] >= body.min_cut][: body.max_cuts]
    out = [{"start": round(a, 2), "end": round(b, 2), "seconds": round(b - a, 2), "reason": " + ".join(w)} for a, b, w in cuts]
    return cuts, out


@router.post("/projects/{project_id}/auto-cut")
def auto_cut(
    project_id: str, body: AutoCutIn, _: Principal = Depends(require_write), session: Session = Depends(get_session)
):
    """Recorta pausas largas y muletillas usando la transcripción (tiempos por palabra). **Por defecto solo propone**
    (`dry_run:true`): revisa `cuts` y vuelve a llamar con `dry_run:false` para aplicarlos en UN paso de historial
    (deshacible), con las capas posteriores adelantadas. Ojo: lo que no es habla (música, juego sin voz) cuenta como
    «silencio»; en directos con partes sin hablar, sube `silence_min` o revisa los cortes antes de aplicarlos."""
    row = _row(session, project_id)
    media = _media(session, row.media_id)
    doc = store.load_doc(session, row)
    cuts, out = _plan_cuts(session, row, doc, body)
    result = {
        "dry_run": body.dry_run, "count": len(out), "seconds_removed": round(sum(c["seconds"] for c in out), 2),
        "duration_before": round(doc.duration, 2), "cuts": out,
    }  # fmt: skip
    if body.dry_run or not cuts:
        result["duration_after"] = round(doc.duration - result["seconds_removed"], 2)
        return result
    ops = [RippleDelete(op="ripple_delete", start=a, end=b) for a, b, _ in reversed(cuts)]  # de atrás adelante
    view = _run(
        session, row,
        lambda: store.apply_batch(session, row, ops, f"auto-cut ({len(cuts)} cortes)", body.base_version, media.duration),
    )  # fmt: skip
    return {**result, "duration_after": view["duration"], "project_version": view["version"], "warnings": view["warnings"]}


class AutopilotIn(BaseModel):
    cut: bool = Field(True, description="Quita pausas largas, silencios de los extremos y muletillas (usa la transcripción)")
    silence_min: float = Field(0.6, ge=0.2, le=10)
    keep_pad: float = Field(0.12, ge=0.0, le=1.0)
    fillers: list[str] | None = None
    subtitle_preset: str | None = Field(
        "subtitle:reel_karaoke_yellow",
        description="Estilo de subtítulos («subtitle:<nombre>», ver /presets); null = no tocar los existentes",
    )
    punch_ins: bool = Field(True, description="Pequeños zooms de impacto en empalmes alternos para disimular los saltos")
    punch_scale: float = Field(1.14, ge=1.03, le=1.6)
    pro: bool = Field(False, description="Estilo pro: en los empalmes alterna zoom con estela (`zoom_blur`) y barrido (`whip_pan`) con un `whoosh_fast` justo antes; los zooms de ritmo llevan estela")
    repeats: bool = Field(True, description="Quita falsos arranques y repeticiones (conserva la última toma)")
    max_static: float = Field(6.0, ge=0, le=60, description="Si pasan más de estos segundos sin ningún cambio visual, añade un zoom al inicio de una frase (0 = desactivado)")
    normalize_audio: bool = True
    denoise: bool = Field(False, description="Reducción de ruido de fondo (más lenta; solo si hay ruido)")
    dry_run: bool = Field(True, description="true (por defecto): solo describe el plan; false: lo aplica en UN paso de historial")
    base_version: int | None = None


@router.post("/projects/{project_id}/autopilot")
def autopilot(
    project_id: str, body: AutopilotIn, _: Principal = Depends(require_write), session: Session = Depends(get_session)
):
    """Edición base profesional de un vídeo en bruto en UNA llamada: recorta muertos y muletillas, pone subtítulos con
    estilo, zooms de impacto en los empalmes y normaliza el audio. Por defecto solo muestra el plan (`dry_run:true`);
    con `dry_run:false` lo aplica como un único paso deshacible. Después: revisa (`/frame`, `/checks`) y añade lo creativo
    (títulos, animaciones, gráficos) encima con `ops`."""
    from cutly.services.presets import library

    row = _row(session, project_id)
    media = _media(session, row.media_id)
    doc = store.load_doc(session, row)
    steps: list[str] = []
    ops: list[Any] = []
    cuts: list = []
    if body.cut:
        cuts, out = _plan_cuts(
            session, row, doc,
            AutoCutIn(silence_min=body.silence_min, keep_pad=body.keep_pad, fillers=body.fillers, repeats=body.repeats, dry_run=False),
        )  # fmt: skip
        if cuts:
            ops += [RippleDelete(op="ripple_delete", start=a, end=b) for a, b, _ in reversed(cuts)]
            steps.append(f"{len(cuts)} cortes ({round(sum(b - a for a, b, _ in cuts), 1)} s menos)")
    removed = sum(b - a for a, b, _ in cuts)
    new_dur = max(0.5, doc.duration - removed)
    if body.subtitle_preset:
        try:
            kind, name = library.parse_ref(body.subtitle_preset)
            preset = library.find(session, kind, name)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(422, f"Preset de subtítulos no válido: {e}") from e
        has_subs = any(layer.type == "subtitle" for layer in doc.layers)
        if has_subs:
            ops += [UpdateLayer(op="update_layer", layer_id=lyr.id, patch={"style": preset["data"]}) for lyr in doc.layers if lyr.type == "subtitle"]
        else:
            ops.append(AddLayer(op="add_layer", layer={"type": "subtitle", "start": 0, "end": new_dur, "style": preset["data"]}))
        steps.append(f"subtítulos «{name}»" + ("" if has_subs else " (capa nueva)"))
    punches = 0
    if body.punch_ins and len(cuts) >= 1:
        done = 0.0
        for i, (a, _b, _w) in enumerate(cuts):
            if i % 2:  # empalmes alternos: el espectador percibe el cambio de plano como intencional
                continue
            at = a - sum(y - x for x, y, _ in cuts[:i])  # posición del empalme en el clip resultante
            if at < 0.3 or at > new_dur - 0.4 or at - done < 3:
                continue
            if body.pro:
                whip = punches % 2 == 1
                ops.append(AddLayer(op="add_layer", layer={
                    "type": "effect", "effect": "whip_pan" if whip else "zoom_blur", "start": round(max(0.0, at - 0.12), 2), "end": round(min(new_dur, at + 0.45), 2),
                    "name": "barrido de empalme" if whip else "zoom con estela",
                    "params": {"direction": "left" if punches % 4 == 1 else "right", "distance": 0.12, "envelope": "in_out", "attack": 0.1, "release": 0.3} if whip
                    else {"scale": round(body.punch_scale + 0.1, 3), "envelope": "in_out", "attack": 0.1, "release": 0.3},
                }))  # fmt: skip
                ops.append(AddLayer(op="add_layer", layer={
                    "type": "audio", "sfx": "whoosh_fast", "start": round(max(0.0, at - 0.2), 2), "end": round(min(new_dur, at + 0.12), 2),
                    "name": "whoosh de empalme", "gain_db": -11,
                }))  # fmt: skip
            else:
                ops.append(AddLayer(op="add_layer", layer={
                    "type": "effect", "effect": "zoom_punch", "start": round(max(0.0, at - 0.1), 2), "end": round(min(new_dur, at + 1.1), 2),
                    "name": "zoom de empalme", "params": {"scale": body.punch_scale, "envelope": "decay"},
                }))  # fmt: skip
            punches += 1
            done = at
        if punches:
            steps.append(f"{punches} " + ("empalmes con estela/barrido y whoosh" if body.pro else "zooms de impacto en empalmes"))
    rhythm = 0
    if body.punch_ins and body.max_static > 0:
        from cutly.api.routers.verify import _mapped_words

        try:
            ws = _mapped_words(session, row, doc)
        except HTTPException:
            ws = []

        def to_new(t: float) -> float | None:  # tiempo del clip actual -> tiempo tras los cortes (None si cae dentro de un corte)
            gone = 0.0
            for a, b, _ in cuts:
                if t < a:
                    break
                if t < b:
                    return None
                gone += b - a
            return t - gone

        events = sorted([0.0, new_dur] + [float(o.layer["start"] if isinstance(o.layer, dict) else o.layer.start) for o in ops if isinstance(o, AddLayer) and (o.layer.get("type") if isinstance(o.layer, dict) else o.layer.type) == "effect"]
                        + [x.start for x in doc.layers if x.type != "subtitle" and x.start > 0])  # fmt: skip
        events = [e for e in events if e <= new_dur]
        starts_s: list[float] = []  # inicios de frase (tras pausa o signo de cierre), en el reloj nuevo
        for k, (a, _b, w) in enumerate(ws):
            if k == 0 or a - ws[k - 1][1] >= 0.3 or ws[k - 1][2].rstrip()[-1:] in ".?!…":
                tn = to_new(a)
                if tn is not None:
                    starts_s.append(tn)
        for tn in starts_s:
            prev = max((e for e in events if e <= tn), default=0.0)
            nxt = min((e for e in events if e > tn), default=new_dur)
            if tn - prev >= body.max_static and tn < new_dur - 0.8 and nxt - tn > 0.5:
                ops.append(AddLayer(op="add_layer", layer={
                    "type": "effect", "effect": "zoom_blur" if body.pro else "zoom_punch", "start": round(max(0.0, tn - 0.05), 2), "end": round(min(new_dur, tn + (0.7 if body.pro else 1.3)), 2),
                    "name": "zoom de ritmo", "params": ({"scale": round(body.punch_scale + 0.08, 3), "envelope": "in_out", "attack": 0.12, "release": 0.4,
                                                          "focus_x": 0.42 if rhythm % 2 else 0.58, "blur_frames": 3} if body.pro else
                                                         {"scale": round(body.punch_scale + (0.06 if rhythm % 2 else 0), 3), "envelope": "decay",
                                                          "focus_x": 0.42 if rhythm % 2 else 0.58}),
                }))  # fmt: skip
                events.append(tn)
                events.sort()
                rhythm += 1
        if rhythm:
            steps.append(f"{rhythm} zooms de ritmo (sin cambio visual > {body.max_static:g} s)")
    if body.normalize_audio or body.denoise:
        from cutly.schema.ops import SetAudio

        ops.append(SetAudio(op="set_audio", patch={"normalize": body.normalize_audio, "denoise": body.denoise}))
        steps.append("audio " + ", ".join(x for x, f in (("normalizado a -14 LUFS", body.normalize_audio), ("sin ruido", body.denoise)) if f))
    result: dict[str, Any] = {
        "dry_run": body.dry_run, "steps": steps, "duration_before": round(doc.duration, 2), "duration_after": round(new_dur, 2),
        "cuts": [{"start": round(a, 2), "end": round(b, 2), "reason": " + ".join(w)} for a, b, w in cuts][:60],
    }  # fmt: skip
    if not ops:
        return {**result, "note": "Nada que hacer: sin transcripción no se pueden detectar cortes; transcribe primero"}
    if body.dry_run:
        try:
            after = apply_ops(doc, ops, media.duration, layer_hook=check_layer)
        except OpError as e:
            raise HTTPException(422, str(e)) from e
        except ValidationError as e:
            raise HTTPException(422, fmt_validation(e)) from e
        return {**result, "duration_after": round(after.duration, 2), "ok": True, "next": "repite con dry_run:false para aplicar"}
    view = _run(
        session, row,
        lambda: store.apply_batch(session, row, ops, "autopilot: " + "; ".join(steps), body.base_version, media.duration),
    )  # fmt: skip
    return {**result, "duration_after": view["duration"], "project_version": view["version"], "warnings": view["warnings"]}


@router.get("/projects/{project_id}/pacing")
def pacing(project_id: str, max_static: float = Query(6.0, ge=2, le=60), _: Principal = Depends(require_read), session: Session = Depends(get_session)):
    """Ritmo del clip resultante: palabras por minuto por tramos de 10 s, el hook (primeros 3 s), el cierre, los tramos
    SIN cambio visual más largos que `max_static` (empalme, efecto, rótulo, animación…) con lo que se dice en ellos, y la
    pausa más larga. Úsalo para decidir dónde falta dinamismo."""
    from cutly.api.routers.verify import _mapped_words

    row = _row(session, project_id)
    doc = store.load_doc(session, row)
    try:
        ws = _mapped_words(session, row, doc)
    except HTTPException:
        ws = []
    dur = doc.duration
    events = sorted({0.0, round(dur, 3), *timeline_starts(doc.timeline), *[x.start for x in doc.layers if x.type != "subtitle" and x.visible]})
    events = [e for e in events if e <= dur]

    def said(a: float, b: float) -> str:
        return " ".join(w[2] for w in ws if a <= w[0] < b)[:140]

    static = [
        {"start": round(a, 1), "end": round(b, 1), "seconds": round(b - a, 1), "says": said(a, b)}
        for a, b in zip(events, events[1:], strict=False) if b - a > max_static
    ]  # fmt: skip
    windows = []
    for t0 in range(0, int(dur) + 1, 10):
        n = sum(1 for w in ws if t0 <= w[0] < t0 + 10)
        if t0 < dur:
            windows.append({"from": t0, "wpm": round(n * 6)})
    gaps = [(ws[i + 1][0] - ws[i][1], ws[i][1]) for i in range(len(ws) - 1)]
    gap = max(gaps, default=(0.0, 0.0))
    return {
        "duration": round(dur, 2), "words": len(ws), "wpm_overall": round(len(ws) / dur * 60) if dur else 0,
        "wpm_by_10s": windows, "hook_says": said(0, 3), "ending_says": said(max(0.0, dur - 4), dur + 1),
        "visual_events": len(events) - 2, "static_spans": static[:15],
        "longest_pause": {"seconds": round(gap[0], 2), "at": round(gap[1], 2)},
        "advice": [a for a in (
            "El hook (primeros 3 s) está vacío: empieza antes con la primera frase o pon un rótulo inicial." if not said(0, 3) else None,
            f"{len(static)} tramos > {max_static:g} s sin cambio visual: rótulo/resaltado/zoom en los cortos; en los de 9 s o más, mejor una "
            "animación DIBUJADA (capa scene: iconos, contador, resaltado que crece, texto escrito — ver cutly_scene_kit) que un simple zoom."
            if static else None,
            "Ritmo de habla bajo (<110 ppm): considera cortar más o acelerar 1.05-1.1x." if ws and len(ws) / max(dur, 1) * 60 < 110 else None,
            "Hay una pausa > 1,5 s: revísala o recórtala." if gap[0] > 1.5 else None,
        ) if a],
    }  # fmt: skip
