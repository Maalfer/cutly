"""Registro de efectos: listar, describir, crear efectos declarativos por API y servir el preview del navegador."""

import json
import re
import shutil
import subprocess
import tempfile
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from cutly.auth import Principal, require_read, require_write
from cutly.registry import effects as R
from cutly.services.render.effects_api import EffectBuildError, EffectCtx

router = APIRouter(tags=["effects"])
_KEY = re.compile(r"^[a-z][a-z0-9_]{0,29}$")


class EffectCreate(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$", description="Identificador: minúsculas, números y _")
    title: str = Field(max_length=80)
    description: str = Field(max_length=600, description="Qué hace y cuándo usarlo")
    category: str = Field("usuario", max_length=30)
    tags: list[str] = Field(default_factory=list, max_length=12)
    params_schema: dict[str, Any] = Field(
        description='{"type":"object","properties":{"x":{"type":"number","minimum":0,"maximum":1,"default":0.5}}}'
    )
    chain: list[str] = Field(
        min_length=1, max_length=8,
        description="Filtros de FFmpeg con huecos {param}, {env} (intensidad 0..1 en el tiempo), {t0}, {t1}, {W}, {H}, {window}. "
        "Solo filtros de la lista blanca (GET /effects/allowed-filters).",
    )


def _check_schema(schema: dict) -> None:
    props = schema.get("properties")
    if schema.get("type") != "object" or not isinstance(props, dict) or len(props) > 20:
        raise HTTPException(422, "params_schema debe ser un objeto con 'properties' (máx. 20 parámetros)")
    for key, spec in props.items():
        if (
            not _KEY.match(key)
            or not isinstance(spec, dict)
            or spec.get("type") not in ("number", "integer", "string", "boolean")
        ):
            raise HTTPException(
                422, f"Parámetro '{key}' inválido: nombre en minúsculas y type number|integer|string|boolean"
            )
        if spec["type"] in ("number", "integer") and not all(k in spec for k in ("minimum", "maximum", "default")):
            raise HTTPException(
                422, f"El parámetro numérico '{key}' necesita minimum, maximum y default (acotan lo que llega a FFmpeg)"
            )
        if spec["type"] == "string" and not ("enum" in spec or "pattern" in spec):
            raise HTTPException(
                422,
                f"El parámetro de texto '{key}' necesita 'enum' o 'pattern' (no se admite texto libre en un filtro)",
            )
        if "default" not in spec:
            raise HTTPException(422, f"El parámetro '{key}' necesita 'default'")


def _dry_run(defn: R.EffectDef) -> None:
    """Prueba la cadena con FFmpeg sobre un vídeo de prueba mínimo."""
    try:
        chain = ",".join(R.build_filters(defn, {}, EffectCtx(0.2, 0.8, 128, 128, 10)))
    except Exception as e:
        raise HTTPException(422, f"La cadena de filtros no es válida: {e}") from e
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=128x128:rate=10:duration=1",
           "-vf", chain, "-frames:v", "10", "-f", "null", "-"]
    # cwd dedicado: aunque la lista blanca de opciones ya impide que un filtro lea o escriba rutas,
    # FFmpeg no necesita acceso al directorio de trabajo real del proceso para esta prueba.
    with tempfile.TemporaryDirectory() as tmp:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=tmp)
        except subprocess.TimeoutExpired as e:
            raise HTTPException(422, "La cadena de filtros tarda demasiado en una prueba mínima") from e
    if r.returncode != 0:
        # No se devuelve el stderr de FFmpeg: podría revelar si una ruta del sistema existe o no.
        raise HTTPException(422, "La cadena de filtros no es válida para FFmpeg")


@router.get("/effects")
def list_effects(q: str | None = None, category: str | None = None, _: Principal = Depends(require_read)):
    out = [e.public() for e in R.all_effects()]
    if category:
        out = [e for e in out if e["category"] == category]
    if q:
        ql = q.lower()
        out = [e for e in out if ql in " ".join([e["name"], e["title"], e["description"], *e["tags"]]).lower()]
    return {"effects": out, "broken": R.errors()}


@router.get("/effects/allowed-filters")
def allowed_filters(_: Principal = Depends(require_read)):
    from cutly.services.render.effects_api import ALLOWED_FILTERS

    return sorted(ALLOWED_FILTERS)


@router.get("/effects/{name}")
def describe_effect(name: str, _: Principal = Depends(require_read)):
    try:
        return R.get(name).public()
    except R.EffectParamError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/effects/{name}/preview.js")
def effect_preview(name: str, _: Principal = Depends(require_read)):
    try:
        e = R.get(name)
    except R.EffectParamError as ex:
        raise HTTPException(404, str(ex)) from ex
    if not e.path or not (e.path / "preview.js").is_file():
        raise HTTPException(404, "Este efecto no tiene preview en el navegador")
    return FileResponse(e.path / "preview.js", media_type="text/javascript")


@router.post("/effects")
def create_effect(body: EffectCreate, _: Principal = Depends(require_write)):
    if body.name in {e.name for e in R.all_effects() if e.source == "builtin"}:
        raise HTTPException(409, f"'{body.name}' es un efecto incluido; elige otro nombre")
    _check_schema(body.params_schema)
    meta = {"name": body.name, "title": body.title, "description": body.description, "category": body.category,
            "tags": body.tags, "params_schema": body.params_schema, "chain": body.chain}
    probe = R.EffectDef(name=body.name, title=body.title, description=body.description, category=body.category,
                        params_schema=body.params_schema, source="user", template=body.chain)
    try:
        R.build_filters(probe, {}, EffectCtx(1.0, 2.0, 1080, 1920, 30))
    except (EffectBuildError, R.EffectParamError) as e:
        raise HTTPException(422, f"La cadena de filtros no es válida: {e}") from e
    _dry_run(probe)
    d = R.user_dir() / body.name
    d.mkdir(parents=True, exist_ok=True)
    (d / "effect.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    R.reload()
    return R.get(body.name).public()


@router.delete("/effects/{name}")
def delete_effect(name: str, _: Principal = Depends(require_write)):
    try:
        e = R.get(name)
    except R.EffectParamError as ex:
        raise HTTPException(404, str(ex)) from ex
    if e.source != "user" or e.path is None:
        raise HTTPException(403, "Solo se pueden borrar los efectos creados por API")
    shutil.rmtree(e.path, ignore_errors=True)
    R.reload()
    return {"ok": True}


@router.post("/effects-reload")
def reload_effects(_: Principal = Depends(require_write)):
    R.reload()
    return {"count": len(R.all_effects()), "broken": R.errors()}

