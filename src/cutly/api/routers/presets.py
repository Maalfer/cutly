"""Presets de estilo: listar, crear, borrar y aplicar a un proyecto."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from sqlmodel import Session

from cutly.auth import Principal, require_read, require_write
from cutly.db.models import Media
from cutly.db.session import get_session
from cutly.schema.ops import Op, OpError, fmt_validation
from cutly.services.presets import library as lib
from cutly.services.projects import store

router = APIRouter(tags=["presets"])
_ops = TypeAdapter(list[Op])


class PresetCreate(BaseModel):
    kind: str = Field(description="subtitle | text | animation | color | transition | layer")
    name: str = Field(pattern=r"^[a-z0-9_\-]{1,40}$")
    description: str = Field("", max_length=300)
    data: dict[str, Any] = Field(
        description="Los mismos campos que el esquema del proyecto para ese tipo (SubtitleStyle, Color, Animations, Transition…)"
    )


class ApplyIn(BaseModel):
    preset: str = Field(description="'tipo:nombre', p. ej. 'subtitle:reel_karaoke_yellow' o 'transition:quick_fade'")
    layer_id: str | None = Field(
        None,
        description="Capa destino (subtitle: opcional, todas las de subtítulos si falta; text/animation: obligatoria)",
    )
    clip_id: str | None = Field(None, description="Transiciones: clip que entra, o 'all' para todos los empalmes")
    start: float | None = Field(None, ge=0, description="Presets de capa: inicio (s del clip resultante)")
    end: float | None = Field(None, gt=0, description="Presets de capa: fin")
    overrides: dict[str, Any] = Field(
        default_factory=dict,
        description="Cambios sobre el preset (merge patch), p. ej. {'text': 'Hola', 'box': {'x': 0.3}}",
    )
    base_version: int | None = None


@router.get("/presets")
def list_presets(
    kind: str | None = None,
    q: str | None = None,
    _: Principal = Depends(require_read),
    session: Session = Depends(get_session),
):
    """Presets disponibles (incluidos y propios) con lo que fijan y cómo aplicarlos."""
    if kind and kind not in lib.KINDS:
        raise HTTPException(422, f"kind debe ser uno de {list(lib.KINDS)}")
    items = lib.list_presets(session, kind, q)
    return {"count": len(items), "kinds": list(lib.KINDS), "presets": items}


@router.get("/presets/{kind}/{name}")
def get_preset(kind: str, name: str, _: Principal = Depends(require_read), session: Session = Depends(get_session)):
    try:
        return lib.find(session, kind, name)
    except lib.PresetError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/presets")
def create_preset(body: PresetCreate, _: Principal = Depends(require_write), session: Session = Depends(get_session)):
    """Crea (o actualiza) un preset propio, validado contra el esquema del proyecto."""
    try:
        return lib.create_user_preset(session, body.kind, body.name, body.description, body.data)
    except lib.PresetError as e:
        raise HTTPException(409 if "incluido" in str(e) else 422, str(e)) from e


@router.delete("/presets/{kind}/{name}")
def delete_preset(kind: str, name: str, _: Principal = Depends(require_write), session: Session = Depends(get_session)):
    try:
        lib.delete_user_preset(session, kind, name)
    except lib.PresetError as e:
        raise HTTPException(403, str(e)) from e
    except LookupError as e:
        raise HTTPException(404, f"No existe el preset '{kind}:{name}'") from e
    return {"ok": True}


@router.post("/projects/{project_id}/presets/apply")
def apply_preset(
    project_id: str, body: ApplyIn, _: Principal = Depends(require_write), session: Session = Depends(get_session)
):
    """Aplica un preset al proyecto como una operación normal (un paso de historial; se puede deshacer)."""
    from cutly.api.routers.projects import _row, _run, _view  # noqa: F401  (misma respuesta que /ops)

    row = _row(session, project_id)
    media = session.get(Media, row.media_id)
    try:
        kind, name = lib.parse_ref(body.preset)
        preset = lib.find(session, kind, name)
        doc = store.load_doc(session, row)
        ops = _ops.validate_python(
            lib.to_ops(preset, doc, body.layer_id, body.clip_id, body.start, body.end, body.overrides)
        )
    except (lib.PresetError, OpError) as e:
        raise HTTPException(422, str(e)) from e
    except ValidationError as e:
        raise HTTPException(422, fmt_validation(e)) from e
    dur = media.duration if media else None
    return _run(
        session, row, lambda: store.apply_batch(session, row, ops, f"preset {body.preset}", body.base_version, dur)
    )
