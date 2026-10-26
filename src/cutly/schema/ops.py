"""Operaciones atómicas sobre el proyecto. Un lote de operaciones es todo-o-nada y un solo paso de historial."""

from collections.abc import Callable
from typing import Annotated, Any, Literal

from pydantic import Field, TypeAdapter, ValidationError

from cutly.schema.project import (
    Audio,
    Color,
    Layer,
    Output,
    ProjectDoc,
    Reframe,
    Strict,
    SubtitleLayer,
    TimelineClip,
    Transition,
    timeline_starts,
)

_layer_adapter = TypeAdapter(Layer)


class OpError(ValueError):
    """Error de una operación, con un mensaje que dice qué corregir."""


def fmt_validation(e: ValidationError) -> str:
    parts = []
    for err in e.errors()[:6]:
        loc = ".".join(str(x) for x in err["loc"] if x not in ("function-after[_times(), TextLayer]",))
        parts.append(f"{loc}: {err['msg']}" if loc else err["msg"])
    return "; ".join(parts)


def merge_patch(target: Any, patch: Any) -> Any:
    """RFC 7386: los objetos se fusionan, null borra la clave, el resto se reemplaza."""
    if not isinstance(patch, dict):
        return patch
    out = dict(target) if isinstance(target, dict) else {}
    for k, v in patch.items():
        if v is None:
            out.pop(k, None)
        else:
            out[k] = merge_patch(out.get(k), v)
    return out


# --- Definición de operaciones --------------------------------------------------------------------------


class AddClip(Strict):
    op: Literal["add_clip"]
    source_in: float = Field(ge=0, description="Inicio en el vídeo original (s)")
    source_out: float = Field(gt=0, description="Fin en el vídeo original (s)")
    index: int | None = Field(None, ge=0, description="Posición en la línea de tiempo; por defecto al final")
    speed: float = Field(1.0, ge=0.25, le=4)


class SplitClip(Strict):
    op: Literal["split_clip"]
    clip_id: str
    at_source: float | None = Field(None, description="Punto de corte en segundos del vídeo original")
    at_output: float | None = Field(None, description="Punto de corte en segundos del clip resultante")


class DeleteClip(Strict):
    op: Literal["delete_clip"]
    clip_id: str


class MoveClip(Strict):
    op: Literal["move_clip"]
    clip_id: str
    to_index: int | None = Field(None, ge=0)
    start_at: float | None = Field(None, ge=0)


class SetClipRange(Strict):
    op: Literal["set_clip_range"]
    clip_id: str
    source_in: float | None = Field(None, ge=0)
    source_out: float | None = Field(None, gt=0)
    start_at: float | None = None


class SetClipSpeed(Strict):
    op: Literal["set_clip_speed"]
    clip_id: str
    speed: float = Field(ge=0.25, le=4)


class SetTransition(Strict):
    op: Literal["set_transition"]
    clip_id: str = Field(
        description="Clip al que se le pone la transición de ENTRADA (une con el anterior; no vale para el primero)"
    )
    transition: Transition | None = Field(description="null la quita")


class AddLayer(Strict):
    op: Literal["add_layer"]
    layer: Layer


class UpdateLayer(Strict):
    op: Literal["update_layer"]
    layer_id: str
    patch: dict[str, Any] = Field(description="JSON merge patch: los objetos se fusionan, null borra la clave")


class RemoveLayer(Strict):
    op: Literal["remove_layer"]
    layer_id: str


class SetReframe(Strict):
    op: Literal["set_reframe"]
    patch: dict[str, Any]


class SetAudio(Strict):
    op: Literal["set_audio"]
    patch: dict[str, Any]


class SetColor(Strict):
    op: Literal["set_color"]
    patch: dict[str, Any]


class SetOutput(Strict):
    op: Literal["set_output"]
    patch: dict[str, Any]


Op = Annotated[
    AddClip | SplitClip | DeleteClip | MoveClip | SetClipRange | SetClipSpeed | AddLayer
    | SetTransition | UpdateLayer | RemoveLayer | SetReframe | SetAudio | SetColor | SetOutput,
    Field(discriminator="op"),
]  # fmt: skip


# --- Aplicación ------------------------------------------------------------------------------------------


def _clip(doc: ProjectDoc, clip_id: str) -> tuple[int, TimelineClip]:
    for i, c in enumerate(doc.timeline):
        if c.id == clip_id:
            return i, c
    have = ", ".join(f"{c.id} ({c.source_in:g}–{c.source_out:g})" for c in doc.timeline) or "ninguno"
    raise OpError(f"El clip '{clip_id}' no existe. Clips del proyecto: {have}")


def _layer(doc: ProjectDoc, layer_id: str) -> tuple[int, Layer]:
    for i, layer in enumerate(doc.layers):
        if layer.id == layer_id:
            return i, layer
    have = ", ".join(f"{layer.id} ({layer.type})" for layer in doc.layers) or "ninguna"
    raise OpError(f"La layer '{layer_id}' no existe. Layers del proyecto: {have}")


def _patched(model_cls, current, patch: dict, what: str):
    try:
        return model_cls.model_validate(merge_patch(current.model_dump(mode="json"), patch))
    except ValidationError as e:
        raise OpError(f"{what} inválido: {fmt_validation(e)}") from e


def apply_op(doc: ProjectDoc, op: Any) -> None:
    """Muta `doc` (que es una copia de trabajo)."""
    match op:
        case AddClip():
            clip = TimelineClip(source_in=op.source_in, source_out=op.source_out, speed=op.speed)
            idx = len(doc.timeline) if op.index is None else min(op.index, len(doc.timeline))
            doc.timeline.insert(idx, clip)
        case SplitClip():
            if (op.at_source is None) == (op.at_output is None):
                raise OpError("split_clip necesita exactamente uno de `at_source` o `at_output`")
            i, c = _clip(doc, op.clip_id)
            if op.at_source is not None:
                at = op.at_source
            else:
                offset = timeline_starts(doc.timeline)[i]
                if not offset <= op.at_output < offset + c.duration:  # type: ignore[operator]
                    raise OpError(
                        f"at_output={op.at_output} cae fuera del clip '{c.id}', que ocupa "
                        f"{offset:g}–{offset + c.duration:g} s del resultado"
                    )
                at = c.source_in + (op.at_output - offset) * c.speed  # type: ignore[operator]
            if not c.source_in + 0.1 < at < c.source_out - 0.1:
                raise OpError(
                    f"El corte {at:g} debe quedar dentro del clip '{c.id}' ({c.source_in:g}–{c.source_out:g})"
                )
            second = TimelineClip(source_in=at, source_out=c.source_out, speed=c.speed)
            c.source_out = at
            doc.timeline.insert(i + 1, second)
        case DeleteClip():
            i, _ = _clip(doc, op.clip_id)
            del doc.timeline[i]
        case MoveClip():
            i, c = _clip(doc, op.clip_id)
            if op.to_index is not None:
                if op.to_index >= len(doc.timeline):
                    raise OpError(f"to_index={op.to_index} fuera de rango (0–{len(doc.timeline) - 1})")
                doc.timeline.insert(op.to_index, doc.timeline.pop(i))
            if op.start_at is not None:
                c.start_at = op.start_at
        case SetClipRange():
            _, c = _clip(doc, op.clip_id)
            if op.source_in is None and op.source_out is None and op.start_at is None:
                raise OpError("set_clip_range necesita source_in, source_out y/o start_at")
            c.source_in = c.source_in if op.source_in is None else op.source_in
            c.source_out = c.source_out if op.source_out is None else op.source_out
            if op.start_at is not None:
                new_start = max(0.0, float(op.start_at))
                md = (c.source_out - c.source_in) / (c.speed or 1)
                starts = timeline_starts(doc.timeline)
                for j, oc in enumerate(doc.timeline):
                    if j == doc.timeline.index(c) or oc is c:
                        continue
                    s2 = starts[j]
                    if not (new_start + md <= s2 + 1e-3 or new_start >= s2 + oc.duration - 1e-3):
                        raise OpError("No se pueden solapar clips; deja un hueco o mueve el otro clip")
                c.start_at = new_start
        case SetClipSpeed():
            _, c = _clip(doc, op.clip_id)
            c.speed = op.speed
        case SetTransition():
            _, c = _clip(doc, op.clip_id)
            c.transition_in = op.transition
        case AddLayer():
            if any(layer.id == op.layer.id for layer in doc.layers):
                raise OpError(f"Ya existe una layer con id '{op.layer.id}'; usa update_layer o elige otro id")
            doc.layers.append(op.layer)
        case UpdateLayer():
            i, layer = _layer(doc, op.layer_id)
            for forbidden in ("id", "type"):
                if forbidden in op.patch and op.patch[forbidden] != getattr(layer, forbidden):
                    raise OpError(f"No se puede cambiar `{forbidden}` de una layer; bórrala y crea otra")
            try:
                doc.layers[i] = _layer_adapter.validate_python(merge_patch(layer.model_dump(mode="json"), op.patch))
            except ValidationError as e:
                raise OpError(f"Layer '{op.layer_id}' inválida tras el cambio: {fmt_validation(e)}") from e
        case RemoveLayer():
            i, _ = _layer(doc, op.layer_id)
            del doc.layers[i]
        case SetReframe():
            doc.reframe = _patched(Reframe, doc.reframe, op.patch, "reframe")
        case SetAudio():
            doc.audio = _patched(Audio, doc.audio, op.patch, "audio")
        case SetColor():
            doc.color = _patched(Color, doc.color, op.patch, "color")
        case SetOutput():
            doc.output = _patched(Output, doc.output, op.patch, "output")
        case _:
            raise OpError(f"Operación desconocida: {op!r}")


def apply_ops(
    doc: ProjectDoc, ops: list[Any], media_duration: float | None, layer_hook: Callable[[Any], None] | None = None
) -> ProjectDoc:
    """Aplica el lote sobre una copia y valida el resultado completo. Lanza OpError sin tocar `doc`."""
    work = ProjectDoc.model_validate(doc.model_dump(mode="json"))
    old_duration = work.duration
    for n, op in enumerate(ops, 1):
        try:
            apply_op(work, op)
        except OpError as e:
            raise OpError(f"Operación {n} ({getattr(op, 'op', '?')}): {e}") from e
        except ValidationError as e:
            raise OpError(f"Operación {n} ({getattr(op, 'op', '?')}): {fmt_validation(e)}") from e
    try:
        work = ProjectDoc.model_validate(work.model_dump(mode="json"))
    except ValidationError as e:
        raise OpError(f"El proyecto resultante no es válido: {fmt_validation(e)}") from e
    if layer_hook:  # valida y normaliza capas (efectos, assets, fuentes) contra los registros del servidor
        for layer in work.layers:
            layer_hook(layer)
    if media_duration:
        for c in work.timeline:
            if c.source_out > media_duration + 0.5:
                raise OpError(
                    f"El clip '{c.id}' termina en {c.source_out:g} s pero el vídeo original dura {media_duration:g} s"
                )
    # Los subtítulos que cubrían todo el clip siguen cubriéndolo si cambia la duración.
    new_duration = work.duration
    if new_duration and abs(new_duration - old_duration) > 0.001:
        for layer in work.layers:
            if isinstance(layer, SubtitleLayer) and layer.start == 0 and abs(layer.end - old_duration) < 0.01:
                layer.end = new_duration
    return work
