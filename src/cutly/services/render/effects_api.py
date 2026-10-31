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

# Para cada filtro permitido, solo estas opciones (nombre completo o alias corto de FFmpeg) pueden aparecer.
# Que el nombre del filtro esté en la lista blanca no basta: algunos (p. ej. curves con plot=/psfile=) tienen
# opciones que leen o escriben rutas del sistema de ficheros. Aquí solo se expone el subconjunto sin esa semántica.
ALLOWED_FILTER_OPTIONS: dict[str, set[str]] = {
    "scale": {"w", "h", "flags", "eval", "interl", "force_original_aspect_ratio", "force_divisible_by", "enable"},
    "crop": {"w", "h", "x", "y", "keep_aspect", "exact", "enable"},
    "eq": {"contrast", "brightness", "saturation", "gamma", "gamma_r", "gamma_g", "gamma_b", "gamma_weight", "eval", "enable"},
    "rgbashift": {"rh", "rv", "gh", "gv", "bh", "bv", "ah", "av", "edge", "enable"},
    "vignette": {"angle", "a", "x0", "y0", "mode", "eval", "dither", "aspect", "enable"},
    "noise": {
        "all_seed", "all_strength", "alls", "allf",
        "c0_seed", "c0_strength", "c0s", "c0f", "c1_seed", "c1_strength", "c1s", "c1f",
        "c2_seed", "c2_strength", "c2s", "c2f", "c3_seed", "c3_strength", "c3s", "c3f", "enable",
    },  # fmt: skip
    "drawbox": {"x", "y", "w", "h", "color", "c", "thickness", "t", "replace", "box", "enable"},
    "hue": {"h", "s", "H", "b", "eval", "enable"},
    "gblur": {"sigma", "sigmaV", "steps", "planes", "enable"},
    "boxblur": {
        "luma_radius", "lr", "luma_power", "lp", "chroma_radius", "cr", "chroma_power", "cp",
        "alpha_radius", "ar", "alpha_power", "ap", "enable",
    },  # fmt: skip
    "colorbalance": {"rs", "gs", "bs", "rm", "gm", "bm", "rh", "gh", "bh", "pl", "enable"},
    "curves": {"preset", "master", "m", "r", "g", "b", "all", "red", "green", "blue", "interp", "eval", "enable"},
    "negate": {"negate_alpha", "enable"},
    "fade": {"type", "t", "start_frame", "s", "nb_frames", "n", "alpha", "start_time", "st", "duration", "d", "color", "c", "enable"},
    "unsharp": {
        "luma_msize_x", "lx", "luma_msize_y", "ly", "luma_amount", "la",
        "chroma_msize_x", "cx", "chroma_msize_y", "cy", "chroma_amount", "ca",
        "alpha_msize_x", "ax", "alpha_msize_y", "ay", "alpha_amount", "aa", "enable",
    },  # fmt: skip
    "lutyuv": {"c0", "c1", "c2", "c3", "y", "u", "v", "a", "enable"},
    "lutrgb": {"c0", "c1", "c2", "c3", "r", "g", "b", "a", "enable"},
    "format": {"pix_fmts", "enable"},
    "setsar": {"sar", "r", "max", "enable"},
    "colorchannelmixer": {
        "rr", "rg", "rb", "ra", "gr", "gg", "gb", "ga", "br", "bg", "bb", "ba",
        "ar", "ag", "ab", "aa", "pc", "pa", "enable",
    },  # fmt: skip
    "chromashift": {"cbh", "cbv", "crh", "crv", "edge", "enable"},
    "pad": {"width", "w", "height", "h", "x", "y", "color", "c", "eval", "aspect", "enable"},
    "hflip": {"enable"},
    "vflip": {"enable"},
    "rotate": {"angle", "a", "out_w", "ow", "out_h", "oh", "fillcolor", "c", "bilinear", "enable"},
    "colorlevels": {
        "rimin", "gimin", "bimin", "aimin", "romin", "gomin", "bomin", "aomin",
        "rimax", "gimax", "bimax", "aimax", "romax", "gomax", "bomax", "aomax", "preserve", "enable",
    },  # fmt: skip
    "colortemperature": {"temperature", "mix", "pl", "enable"},
    "tmix": {"frames", "weights", "scale", "planes", "enable"},
    "tblend": {
        "c0_mode", "c1_mode", "c2_mode", "c3_mode", "all_mode",
        "c0_expr", "c1_expr", "c2_expr", "c3_expr", "all_expr",
        "c0_opacity", "c1_opacity", "c2_opacity", "c3_opacity", "all_opacity",
        "shortest", "repeatlast", "enable",
    },  # fmt: skip
    "lenscorrection": {"cx", "cy", "k1", "k2", "i", "fc", "enable"},
    "edgedetect": {"low", "high", "mode", "planes", "enable"},
}
assert ALLOWED_FILTER_OPTIONS.keys() == ALLOWED_FILTERS

_FILTER = re.compile(r"^([a-z0-9_]+)(=([A-Za-z0-9_.,:'()+\-*/<>=!&|%@ \[\]]*))?$")
_OPTION_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=")


def _split_options(opts: str) -> list[str]:
    """Divide las opciones de un filtro por ':' de nivel superior (respeta las comillas simples)."""
    tokens, current, in_quotes = [], [], False
    for c in opts:
        if c == "'":
            in_quotes = not in_quotes
            current.append(c)
        elif c == ":" and not in_quotes:
            tokens.append("".join(current))
            current = []
        else:
            current.append(c)
    tokens.append("".join(current))
    return tokens


def _check_options(name: str, opts: str) -> None:
    """Cada opción con nombre (`clave=valor`) debe estar en la lista blanca del filtro `name`.

    Los valores posicionales (sin `clave=`) se dejan pasar: ninguno de los filtros permitidos interpreta
    un valor posicional como ruta de fichero.
    """
    allowed = ALLOWED_FILTER_OPTIONS[name]
    for token in _split_options(opts):
        m = _OPTION_KEY.match(token)
        if m and m.group(1) not in allowed:
            raise EffectBuildError(
                f"Opción '{m.group(1)}' no permitida en el filtro '{name}'. Permitidas: {', '.join(sorted(allowed))}"
            )


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
        _check_options(m.group(1), m.group(3) or "")
    return filters

