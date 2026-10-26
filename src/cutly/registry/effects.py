"""Registro de efectos con autodescubrimiento.

- Efectos de código: `effects/<nombre>/{effect.json, build.py, preview.js}` en el repositorio (de confianza).
- Efectos declarativos: `<data>/effects/<nombre>/effect.json` con una cadena de filtros con huecos `{param}`;
  se pueden subir por API y solo pueden usar los filtros de la lista blanca.
"""

import importlib.util
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from cutly.config import get_settings
from cutly.services.render.effects_api import EffectBuildError, EffectCtx, env, f, validate_filters

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
ENVELOPES = ["pulse", "in_out", "decay", "hold", "ramp"]


class EffectParamError(ValueError):
    pass


@dataclass
class EffectDef:
    name: str
    title: str
    description: str
    category: str
    params_schema: dict
    source: str  # builtin | user
    render_backend: str = "ffmpeg"
    fidelity: str = "exact"  # exactitud del render
    preview_fidelity: str = "approximate"  # exactitud del preview del navegador
    tags: list[str] = field(default_factory=list)
    path: Path | None = None
    builder: Callable[[dict, EffectCtx], list[str]] | None = None
    template: list[str] | None = None  # efectos declarativos

    def public(self) -> dict:
        d = {k: getattr(self, k) for k in ("name", "title", "description", "category", "render_backend", "fidelity",
                                          "preview_fidelity", "tags", "source", "params_schema")}  # fmt: skip
        d["has_preview"] = bool(self.path and (self.path / "preview.js").is_file())
        d["example_layer"] = {
            "type": "effect", "effect": self.name, "start": 2.0, "end": 3.0,
            "params": {k: v.get("default") for k, v in self.params_schema.get("properties", {}).items() if "default" in v},
        }  # fmt: skip
        return d


def builtin_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "effects"


def user_dir() -> Path:
    return get_settings().data_dir / "effects"


def validate_params(schema: dict, params: dict) -> dict:
    """Subconjunto de JSON Schema: type, minimum, maximum, enum, pattern, maxLength, default, required."""
    props = schema.get("properties", {})
    unknown = sorted(set(params) - set(props))
    if unknown:
        raise EffectParamError(f"Parámetros desconocidos: {unknown}. Válidos: {sorted(props)}")
    out = {}
    for name, spec in props.items():
        v = params.get(name, spec.get("default"))
        if v is None:
            if name in schema.get("required", []):
                raise EffectParamError(f"Falta el parámetro obligatorio '{name}'")
            continue
        t = spec.get("type")
        if t == "number" and (isinstance(v, bool) or not isinstance(v, int | float)):
            raise EffectParamError(f"'{name}' debe ser un número")
        if t == "integer" and (isinstance(v, bool) or not isinstance(v, int)):
            raise EffectParamError(f"'{name}' debe ser un entero")
        if t == "boolean" and not isinstance(v, bool):
            raise EffectParamError(f"'{name}' debe ser true o false")
        if t == "string" and not isinstance(v, str):
            raise EffectParamError(f"'{name}' debe ser texto")
        if "minimum" in spec and v < spec["minimum"]:
            raise EffectParamError(f"'{name}'={v} es menor que el mínimo {spec['minimum']}")
        if "maximum" in spec and v > spec["maximum"]:
            raise EffectParamError(f"'{name}'={v} es mayor que el máximo {spec['maximum']}")
        if "enum" in spec and v not in spec["enum"]:
            raise EffectParamError(f"'{name}'='{v}' no es válido. Opciones: {spec['enum']}")
        if "pattern" in spec and not re.match(spec["pattern"], str(v)):
            raise EffectParamError(f"'{name}'='{v}' no tiene el formato esperado ({spec['pattern']})")
        if "maxLength" in spec and len(str(v)) > spec["maxLength"]:
            raise EffectParamError(f"'{name}' es demasiado largo (máx. {spec['maxLength']})")
        out[name] = v
    return out


def _load_builtin(d: Path) -> EffectDef:
    meta = json.loads((d / "effect.json").read_text(encoding="utf-8"))
    if meta["name"] != d.name or not NAME_RE.match(meta["name"]):
        raise ValueError(f"effect.json de {d.name}: 'name' debe coincidir con la carpeta ({NAME_RE.pattern})")
    spec = importlib.util.spec_from_file_location(f"cutly_effect_{d.name}", d / "build.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return EffectDef(
        name=meta["name"], title=meta["title"], description=meta["description"], category=meta.get("category", "otros"),
        params_schema=meta.get("params_schema", {"type": "object", "properties": {}}), source="builtin",
        render_backend=meta.get("render_backend", "ffmpeg"), fidelity=meta.get("fidelity", "exact"),
        preview_fidelity=meta.get("preview_fidelity", "approximate"), tags=meta.get("tags", []), path=d, builder=mod.build,
    )  # fmt: skip


def _load_user(d: Path) -> EffectDef:
    meta = json.loads((d / "effect.json").read_text(encoding="utf-8"))
    return EffectDef(
        name=meta["name"], title=meta["title"], description=meta["description"], category=meta.get("category", "usuario"),
        params_schema=meta["params_schema"], source="user", fidelity="exact", preview_fidelity="approximate",
        tags=meta.get("tags", []), path=d, template=meta["chain"],
    )  # fmt: skip


@lru_cache
def _all() -> dict[str, EffectDef]:
    found: dict[str, EffectDef] = {}
    errors: dict[str, str] = {}
    for root, loader in ((builtin_dir(), _load_builtin), (user_dir(), _load_user)):
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir()):
            if d.name.startswith("_") or not (d / "effect.json").is_file():
                continue
            try:
                e = loader(d)
                if e.name in found and e.source == "user":
                    raise ValueError("el nombre ya lo usa un efecto incluido")
                found[e.name] = e
            except Exception as ex:  # noqa: BLE001  (un efecto roto no tumba el registro)
                errors[d.name] = str(ex)
    found["__errors__"] = errors  # type: ignore[assignment]
    return found


def reload() -> None:
    _all.cache_clear()


def errors() -> dict[str, str]:
    return _all().get("__errors__", {})  # type: ignore[return-value]


def all_effects() -> list[EffectDef]:
    return sorted((e for k, e in _all().items() if k != "__errors__"), key=lambda e: (e.category, e.name))


def get(name: str) -> EffectDef:
    e = _all().get(name)
    if e is None or name == "__errors__":
        import difflib

        near = difflib.get_close_matches(name, [x.name for x in all_effects()], n=3)
        hint = f" ¿Quizá {', '.join(near)}?" if near else ""
        raise EffectParamError(f"El efecto '{name}' no existe.{hint} Lista: GET /effects")
    return e


def build_filters(defn: EffectDef, params: dict, ctx: EffectCtx) -> list[str]:
    p = validate_params(defn.params_schema, params)
    if defn.render_backend != "ffmpeg":
        raise EffectBuildError(
            f"El efecto '{defn.name}' necesita el renderer '{defn.render_backend}', no disponible en este servidor"
        )
    if defn.builder:
        filters = defn.builder(p, ctx)
    else:  # declarativo: sustituye {param}, {env}, {t0}, {t1}, {W}, {H}, {window}
        e = env(str(p.get("envelope", "in_out")), ctx, float(p.get("attack", 0.15)), float(p.get("release", 0.3)))
        subs = {**{k: (f(v) if isinstance(v, float | int) and not isinstance(v, bool) else str(v)) for k, v in p.items()},
                "env": e, "t0": f(ctx.t0), "t1": f(ctx.t1), "W": str(ctx.width), "H": str(ctx.height),
                "window": f"between(t,{f(ctx.t0)},{f(ctx.t1)})"}  # fmt: skip
        filters = []
        for tpl in defn.template or []:
            try:
                filters.append(tpl.format(**subs))
            except KeyError as ex:
                raise EffectBuildError(f"La plantilla usa {{{ex.args[0]}}}, que no es un parámetro del efecto") from ex
    return validate_filters(filters)


def normalized_params(name: str, params: dict) -> dict:
    """Valida los parámetros de una layer de efecto y devuelve los normalizados (con valores por defecto)."""
    return validate_params(get(name).params_schema, params)
