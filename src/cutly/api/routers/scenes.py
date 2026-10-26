"""Escenas animadas (capa `scene`): catálogo de plantillas, esquema y vista previa sin crear un proyecto."""

import io
import threading
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from PIL import Image
from pydantic import BaseModel, Field, ValidationError

from cutly.auth import Principal, require_read, require_write
from cutly.schema.scene import Scene
from cutly.services.scene import templates as TP
from cutly.services.scene.engine import Player

router = APIRouter(tags=["scenes"])
_busy = threading.Lock()  # una vista previa a la vez: el VPS es modesto
MAX_TIMES = 12


class SceneSource(BaseModel):
    template: str | None = Field(None, description="Nombre de plantilla (GET /scenes/templates)")
    params: dict[str, Any] = Field(default_factory=dict)
    scene: dict[str, Any] | None = Field(None, description="Escena completa escrita a mano (alternativa a template)")
    duration: float = Field(
        10, ge=0.5, le=120, description="Duración de la capa en segundos (las plantillas se ajustan a ella)"
    )


class PreviewBody(SceneSource):
    times: list[float] = Field(
        default_factory=lambda: [0.5], max_length=MAX_TIMES, description="Instantes (s desde el inicio de la capa)"
    )
    width: int = Field(960, ge=160, le=1920, description="Ancho en píxeles de CADA fotograma")
    fit: str = Field("contain", pattern="^(contain|cover)$")
    cols: int = Field(3, ge=1, le=6)


def resolve_scene(src: SceneSource) -> Scene:
    if (src.template is None) == (src.scene is None):
        raise HTTPException(422, "Indica `template` (+ `params`) o `scene`, pero no ambas ni ninguna")
    try:
        if src.template is not None:
            return TP.build_template(src.template, src.params, src.duration)
        return Scene.model_validate(src.scene)
    except TP.TemplateError as e:
        raise HTTPException(422, str(e)) from e
    except ValidationError as e:
        errs = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()[:6])
        raise HTTPException(422, f"Escena inválida: {errs}") from e


@router.get("/scenes/templates")
def list_templates(q: str | None = None, _: Principal = Depends(require_read)):
    """Plantillas de animación disponibles, con sus parámetros y una capa `scene` de ejemplo lista para `add_layer`."""
    out = [TP.describe(t) for t in TP.REGISTRY.values()]
    if q:
        ql = q.lower()
        out = [t for t in out if ql in " ".join([t["name"], t["title"], t["description"], *t["tags"]]).lower()]
    return {"templates": out}


@router.get("/scenes/templates/{name}")
def describe_template(name: str, _: Principal = Depends(require_read)):
    try:
        return TP.describe(TP.get_template(name))
    except TP.TemplateError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/scenes/build")
def build_scene(body: SceneSource, _: Principal = Depends(require_read)):
    """Expande una plantilla a su escena completa (JSON editable): úsala como punto de partida para personalizarla
    y ponla en `layer.scene` (con `template` vacío)."""
    return resolve_scene(body).model_dump(mode="json", exclude_none=True)


@router.get("/scenes/schema")
def scene_schema(_: Principal = Depends(require_read)):
    """JSON Schema completo de una escena (objetos node/text/card/link/dot/ring/burst/meter, cámara, fondo)."""
    return Scene.model_json_schema()


@router.post("/scenes/preview")
def preview(body: PreviewBody, _: Principal = Depends(require_write)):
    """PNG con uno o varios fotogramas de una escena (hoja de contacto si hay varios `times`): el bucle de
    diseño de una animación sin montar un proyecto. Los tiempos van desde el inicio de la capa."""
    scene = resolve_scene(body)
    if not _busy.acquire(timeout=20):
        raise HTTPException(503, "Hay otra vista previa en curso; reintenta en unos segundos")
    try:
        w = body.width
        h = max(2, round(w * scene.world.h / scene.world.w))
        pl = Player(scene, w, h, body.fit)
        frames = [Image.fromarray(pl.frame(max(0.0, t))).convert("RGB") for t in body.times]
        n = len(frames)
        cols = min(body.cols, n)
        rows = -(-n // cols)
        sheet = Image.new("RGB", (cols * w, rows * h), (0, 0, 0))
        from PIL import ImageDraw

        d = ImageDraw.Draw(sheet)
        for i, fr in enumerate(frames):
            sheet.paste(fr, ((i % cols) * w, (i // cols) * h))
            if n > 1:
                d.text(((i % cols) * w + 8, (i // cols) * h + 6), f"t={body.times[i]:g}s", fill=(255, 255, 255))
        buf = io.BytesIO()
        sheet.save(buf, "PNG", compress_level=3)
        return Response(buf.getvalue(), media_type="image/png")
    finally:
        _busy.release()
