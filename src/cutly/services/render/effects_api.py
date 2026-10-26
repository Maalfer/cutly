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
    "pad", "hflip", "vflip", "colorlevels", "colortemperature", "tmix", "lenscorrection", "edgedetect",
}  # fmt: skip
_FILTER = re.compile(r"^([a-z0-9_]+)(=([A-Za-z0-9_.,:'()+\-*/<>=!&|%@ ]*))?$")


class EffectBuildError(ValueError):
    pass


@dataclass
class EffectCtx:
    t0: float  # inicio y fin de la layer, en segundos del clip resultante
    t1: float
    width: int
    height: int
    fps: int


def f(v: float) -> str:
    """Número para un grafo de FFmpeg (sin notación científica, sin ceros sobrantes)."""
    return (f"{v:.5f}".rstrip("0").rstrip(".")) or "0"


def env(kind: str, ctx: EffectCtx, attack: float = 0.15, release: float = 0.3) -> str:
    """Expresión 0..1 en función de `t`, nula fuera de la ventana de la layer.

    hold: 1 en toda la ventana · pulse: sube y baja suave (seno) · in_out: rampas de entrada y salida ·
    decay: golpe inicial que se apaga · ramp: crece linealmente hasta el final.
    """
    t0, t1 = f(ctx.t0), f(ctx.t1)
    dur = max(ctx.t1 - ctx.t0, 0.05)
    win = f"between(t,{t0},{t1})"
    if kind == "hold":
        return win
    if kind == "pulse":
        return f"{win}*sin(PI*(t-{t0})/{f(dur)})"
    if kind == "decay":
        # el argumento se acota a 0..1: fuera de la ventana, exp(+grande) se desbordaría a infinito y 0*inf = NaN
        return f"{win}*exp(-6*min(1,max(0,(t-{t0})/{f(dur)})))"
    if kind == "ramp":
        return f"{win}*(t-{t0})/{f(dur)}"
    a, r = f(max(min(attack, dur / 2), 0.02)), f(max(min(release, dur / 2), 0.02))
    return f"{win}*min(1,(t-{t0})/{a})*min(1,({t1}-t)/{r})"  # in_out


def window(ctx: EffectCtx) -> str:
    """Condición `enable` para filtros con línea de tiempo."""
    return f"between(t,{f(ctx.t0)},{f(ctx.t1)})"


def validate_filters(filters: list[str]) -> list[str]:
    """Cada filtro debe ser `nombre=opciones` con nombre permitido y solo caracteres seguros."""
    for flt in filters:
        m = _FILTER.match(flt)
        if not m:
            raise EffectBuildError(f"Filtro con caracteres no permitidos: {flt!r}")
        if m.group(1) not in ALLOWED_FILTERS:
            raise EffectBuildError(
                f"Filtro '{m.group(1)}' no permitido. Permitidos: {', '.join(sorted(ALLOWED_FILTERS))}"
            )
        if flt.count("'") % 2:
            raise EffectBuildError(f"Comillas sin cerrar en el filtro: {flt!r}")
    return filters
