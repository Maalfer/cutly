"""Presets: estilos reutilizables (subtítulos, texto, animación, color, transición, capas completas).

Los incluidos viven en `presets/<tipo>/<nombre>.json`; los del usuario, en la tabla Preset. Un preset es solo datos
validados contra el esquema real del proyecto: aplicarlo equivale a una operación normal (con su historial/deshacer).
"""

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter, ValidationError
from sqlmodel import Session, select

from cutly.db.models import Preset
from cutly.schema.ops import OpError, fmt_validation, merge_patch
from cutly.schema.project import Animations, Color, Layer, SubtitleLayer, SubtitleStyle, TextLayer, Transition

KINDS = ("subtitle", "text", "animation", "color", "transition", "layer")
NAME_RE = re.compile(r"^[a-z0-9_\-]{1,40}$")
_layer_adapter = TypeAdapter(Layer)


class PresetError(ValueError):
    pass


def presets_dir() -> Path:
    from cutly.config import get_settings

    return get_settings().builtin_assets_dir.parent / "presets"


def validate_data(kind: str, data: dict) -> dict:
    """Valida `data` contra el modelo del tipo; devuelve los datos tal cual (solo lo que el preset fija)."""
    if kind not in KINDS:
        raise PresetError(f"kind debe ser uno de {list(KINDS)}")
    try:
        if kind == "subtitle":
            SubtitleStyle.model_validate(data)
        elif kind == "text":
            extra = set(data) - {"style", "box", "animations"}
            if extra:
                raise PresetError(f"Un preset de texto solo admite style, box y animations (sobran {sorted(extra)})")
            TextLayer.model_validate({"start": 0, "end": 1, "text": "x", **data})
        elif kind == "animation":
            Animations.model_validate(data)
        elif kind == "color":
            Color.model_validate(data)
        elif kind == "transition":
            Transition.model_validate(data)
        else:
            probe = {"start": 0, "end": 1, **data}
            if probe.get("type") == "text":
                probe.setdefault("text", "x")
            if probe.get("type") in ("icon", "image"):
                probe.setdefault("asset", "icons/star")
            if probe.get("type") == "effect":
                probe.setdefault("effect", "flash")
            if probe.get("type") == "subtitle":
                raise PresetError("Para subtítulos usa un preset de tipo 'subtitle'")
            _layer_adapter.validate_python(probe)
    except ValidationError as e:
        raise PresetError(fmt_validation(e)) from e
    return data


@lru_cache(maxsize=2)
def _builtin(root: str, stamp: float) -> list[dict]:
    out = []
    for kind in KINDS:
        for p in sorted((Path(root) / kind).glob("*.json")) if (Path(root) / kind).is_dir() else []:
            d = json.loads(p.read_text(encoding="utf-8"))
            out.append(
                {
                    "kind": kind,
                    "name": d["name"],
                    "description": d.get("description", ""),
                    "data": d["data"],
                    "source": "builtin",
                }
            )
    return out


def builtin_presets() -> list[dict]:
    root = presets_dir()
    stamp = max((p.stat().st_mtime for p in root.rglob("*.json")), default=0.0) if root.is_dir() else 0.0
    return _builtin(str(root), stamp)


def user_presets(session: Session) -> list[dict]:
    return [
        {"kind": p.kind, "name": p.name, "description": p.description, "data": p.data, "source": "user"}
        for p in session.exec(select(Preset)).all()
    ]


def list_presets(session: Session, kind: str | None = None, q: str | None = None) -> list[dict]:
    out = builtin_presets() + user_presets(session)
    if kind:
        out = [p for p in out if p["kind"] == kind]
    if q:
        words = q.lower().split()
        out = [p for p in out if all(w in f"{p['name']} {p['description']} {p['kind']}".lower() for w in words)]
    return out


def find(session: Session, kind: str, name: str) -> dict:
    for p in list_presets(session, kind):
        if p["name"] == name:
            return p
    import difflib

    near = difflib.get_close_matches(name, [p["name"] for p in list_presets(session, kind)], n=4, cutoff=0.4)
    raise PresetError(
        f"No existe el preset '{kind}:{name}'."
        + (f" ¿Quizá {', '.join(near)}?" if near else f" Lista: GET /presets?kind={kind}")
    )


def parse_ref(ref: str) -> tuple[str, str]:
    if ":" not in ref:
        raise PresetError("`preset` debe ser 'tipo:nombre', p. ej. 'subtitle:reel_karaoke_yellow'")
    kind, _, name = ref.partition(":")
    return kind.strip(), name.strip()


def create_user_preset(session: Session, kind: str, name: str, description: str, data: dict) -> dict:
    if not NAME_RE.match(name):
        raise PresetError("name: solo minúsculas, números, '-' y '_' (hasta 40 caracteres)")
    validate_data(kind, data)
    if any(p["kind"] == kind and p["name"] == name and p["source"] == "builtin" for p in builtin_presets()):
        raise PresetError(f"'{kind}:{name}' es un preset incluido; elige otro nombre")
    row = session.exec(select(Preset).where(Preset.kind == kind, Preset.name == name)).first()
    if row:
        row.description, row.data = description, data
    else:
        row = Preset(kind=kind, name=name, description=description, data=data)
    session.add(row)
    session.commit()
    return {"kind": kind, "name": name, "description": description, "data": data, "source": "user"}


def delete_user_preset(session: Session, kind: str, name: str) -> None:
    row = session.exec(select(Preset).where(Preset.kind == kind, Preset.name == name)).first()
    if row is None:
        if any(p["kind"] == kind and p["name"] == name for p in builtin_presets()):
            raise PresetError("Los presets incluidos no se pueden borrar")
        raise LookupError(f"{kind}:{name}")
    session.delete(row)
    session.commit()


def to_ops(
    preset: dict,
    doc,
    layer_id: str | None,
    clip_id: str | None,
    start: float | None,
    end: float | None,
    overrides: dict,
) -> list[dict[str, Any]]:
    """Traduce aplicar un preset a operaciones del proyecto (todas se aplican como un solo paso de historial)."""
    kind, data = preset["kind"], merge_patch(preset["data"], overrides) if overrides else preset["data"]
    if kind == "color":
        return [{"op": "set_color", "patch": data}]
    if kind == "subtitle":
        subs = [
            layer
            for layer in doc.layers
            if isinstance(layer, SubtitleLayer) and (layer_id is None or layer.id == layer_id)
        ]
        if layer_id and not subs:
            raise OpError(f"La layer '{layer_id}' no es de subtítulos o no existe")
        if not subs:  # no había subtítulos: se crea la capa con el estilo
            return [
                {
                    "op": "add_layer",
                    "layer": {"type": "subtitle", "start": start or 0, "end": end or doc.duration, "style": data},
                }
            ]
        return [{"op": "update_layer", "layer_id": s.id, "patch": {"style": data}} for s in subs]
    if kind == "transition":
        if not clip_id:
            raise OpError(
                "Un preset de transición necesita `clip_id` (el clip que entra) o 'all' para todos los empalmes"
            )
        targets = [c.id for c in doc.timeline[1:]] if clip_id == "all" else [clip_id]
        if not targets:
            raise OpError("La línea de tiempo tiene un solo clip: no hay empalmes a los que poner transición")
        return [{"op": "set_transition", "clip_id": cid, "transition": data} for cid in targets]
    if kind in ("text", "animation"):
        if layer_id:
            patch = data if kind == "text" else {"animations": data}
            return [{"op": "update_layer", "layer_id": layer_id, "patch": patch}]
        if kind == "text" and start is not None and end is not None and overrides.get("text"):
            return [{"op": "add_layer", "layer": {"type": "text", "start": start, "end": end, **data}}]
        raise OpError(
            "Indica `layer_id` (la capa a la que aplicarlo)"
            + (" o bien start, end y overrides.text para crear un texto nuevo" if kind == "text" else "")
        )
    # layer: capa completa nueva
    if start is None or end is None:
        raise OpError("Un preset de capa necesita `start` y `end` (segundos del clip resultante)")
    return [{"op": "add_layer", "layer": {"start": start, "end": end, **data}}]
