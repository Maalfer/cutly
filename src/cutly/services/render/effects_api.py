"""API para autores de efectos: utilidades para construir filtros de FFmpeg de forma segura.

Un efecto recibe `params` (ya validados contra su esquema) y un `EffectCtx` con la ventana de tiempo de la layer,
y devuelve una lista de filtros (`["scale=...", "crop=..."]`) que se encadenan sobre el vídeo ya compuesto.
"""

import re
from dataclasses import dataclass

# Filtros que un efecto puede usar. Cualquier otro se rechaza (los efectos subidos por API no ejecutan nada raro).
ALLOWED_FILTERS = {
    "scale", "crop", "eq", "rgbashift", "vignette", "noise", "drawbox", "hue", "gblur", "boxblur", "colorbalance",
    "curves", "negate", "fade", "unsharp", "lutyuv", "lutrgb", "format", "setsar", "colorchannelmixer", "chromashift",
    "pad", "hflip", "vflip", "rotate", "colorlevels", "colortemperature", "tmix", "tblend", "lenscorrection", "edgedetect",
}  # fmt: skip
_FILTER = re.compile(r"^([a-z0-9_]+)(=([A-Za-z0-9_.,:'()+\-*/<>=!&|%@ \[\]]*))?$")


class EffectBuildError(ValueError):
    pass


@dataclass
class EffectCtx:
    t0: float
    t1: float
    width: int
    height: int
    fps: int


def f(v: float) -> str:
    return (f"{v:.5f}".rstrip("0").rstrip(".")) or "0"


def env(kind: str, ctx: EffectCtx, attack: float = 0.15, release: float = 0.3) -> str:
    t0, t1 = f(ctx.t0), f(ctx.t1)
    dur = max(ctx.t1 - ctx.t0, 0.05)
    win = f"between(t,{t0},{t1})"
    if kind == "hold":
        return win
    if kind == "pulse":
        return f"{win}*sin(PI*(t-{t0})/{f(dur)})"
    if kind == "decay":
        return f"{win}*exp(-6*min(1,max(0,(t-{t0})/{f(dur)})))"
    if kind == "ramp":
        return f"{win}*(t-{t0})/{f(dur)}"
    a, r = f(max(min(attack, dur / 2), 0.02)), f(max(min(release, dur / 2), 0.02))
    return f"{win}*min(1,(t-{t0})/{a})*min(1,({t1}-t)/{r})"


def window(ctx: EffectCtx) -> str:
    return f"between(t,{f(ctx.t0)},{f(ctx.t1)})"


def _split_filter_nodes(flt: str) -> list[str]:
    nodes = []
    current = []
    in_quotes = False
    bracket_depth = 0
    i = 0
    while i < len(flt):
        c = flt[i]
        if c == "'":
            in_quotes = not in_quotes
            current.append(c)
            i += 1
            continue
        if not in_quotes:
            if c == '[':
                bracket_depth += 1
                current.append(c)
                i += 1
                continue
            if c == ']':
                bracket_depth -= 1
                if bracket_depth < 0:
                    raise EffectBuildError(f"Corchetes mal formados en el filtro: {flt!r}")
                current.append(c)
                i += 1
                continue
            if bracket_depth == 0 and c == ';':
                nodes.append(''.join(current).strip())
                current = []
                i += 1
                continue
            if bracket_depth == 0 and c == ',':
                nodes.append(''.join(current).strip())
                current = []
                i += 1
                continue
        current.append(c)
        i += 1
    if in_quotes:
        raise EffectBuildError(f"Comillas sin cerrar en el filtro: {flt!r}")
    if bracket_depth != 0:
        raise EffectBuildError(f"Corchetes mal formados en el filtro: {flt!r}")
    nodes.append(''.join(current).strip())
    return [n for n in nodes if n]


def validate_filters(filters: list[str]) -> list[str]:
    for flt in filters:
        if not isinstance(flt, str):
            raise EffectBuildError(f"Filtro inválido: {flt!r}")
        nodes = _split_filter_nodes(flt)
        if len(nodes) != 1:
            raise EffectBuildError(f"No se permiten múltiples filtros encadenados: {flt!r}")
        node = nodes[0]
        m = _FILTER.match(node)
        if not m:
            raise EffectBuildError(f"Filtro con caracteres no permitidos: {node!r}")
        if m.group(1) not in ALLOWED_FILTERS:
            raise EffectBuildError(
                f"Filtro '{m.group(1)}' no permitido. Permitidos: {', '.join(sorted(ALLOWED_FILTERS))}"
            )
        if node.count("'") % 2:
            raise EffectBuildError(f"Comillas sin cerrar en el filtro: {node!r}")
    return filters
