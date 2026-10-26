"""Motor de animación único: evalúa en cualquier instante las propiedades de una layer.

Lo usan tanto el render de texto/formas (ASS, por tramos) como el de iconos/imágenes (secuencia de
fotogramas), y el preview del navegador implementa la misma matemática (ver docs/ADDING_EFFECTS.md).

Propiedades relativas a la caja base de la layer: desplazamiento (fracciones del fotograma), escala,
opacidad final, rotación extra (grados).
"""

import math
from dataclasses import dataclass

from cutly.schema.project import Animations, LayerBase

SAMPLE_FPS = 15  # muestreo de las curvas (cada tramo se interpola linealmente)


@dataclass
class Props:
    dx: float = 0.0
    dy: float = 0.0
    scale: float = 1.0
    opacity: float = 1.0
    rot: float = 0.0

    def same(self, o: "Props", eps: float = 1e-3) -> bool:
        return all(abs(a - b) < eps for a, b in ((self.dx, o.dx), (self.dy, o.dy), (self.scale, o.scale),
                                                 (self.opacity, o.opacity), (self.rot, o.rot * 1.0)))  # fmt: skip


# --- Easing ------------------------------------------------------------------------------------------------


def _bounce(p: float) -> float:
    n1, d1 = 7.5625, 2.75
    if p < 1 / d1:
        return n1 * p * p
    if p < 2 / d1:
        p -= 1.5 / d1
        return n1 * p * p + 0.75
    if p < 2.5 / d1:
        p -= 2.25 / d1
        return n1 * p * p + 0.9375
    p -= 2.625 / d1
    return n1 * p * p + 0.984375


def ease(name: str, p: float) -> float:
    p = min(max(p, 0.0), 1.0)
    match name:
        case "linear":
            return p
        case "ease_in":
            return p**3
        case "ease_out":
            return 1 - (1 - p) ** 3
        case "ease_in_out":
            return 4 * p**3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2
        case "ease_out_back":
            c1, c3 = 1.70158, 2.70158
            return 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2
        case "ease_out_bounce":
            return _bounce(p)
        case "ease_out_elastic":
            return (
                0.0 if p == 0 else 1.0 if p == 1 else 2 ** (-10 * p) * math.sin((p * 10 - 0.75) * (2 * math.pi) / 3) + 1
            )
    return p


# --- Presets de entrada/salida -------------------------------------------------------------------------------------

_DX, _DY = 0.15, 0.10  # recorrido de los deslizamientos (fracción del fotograma)


def _preset(name: str, p: float, leaving: bool) -> Props:
    """Efecto de la entrada con progreso p (0 = invisible/fuera, 1 = reposo). La salida usa 1-q con ease_in."""
    e = ease("ease_in" if leaving else "ease_out", p)
    if name == "fade":
        return Props(opacity=e)
    if name == "pop":
        s = ease("ease_in" if leaving else "ease_out_back", p)
        return Props(scale=0.5 + 0.5 * s, opacity=min(1.0, p * 3))
    if name in ("zoom_in", "zoom"):
        return Props(scale=0.3 + 0.7 * e, opacity=min(1.0, p * 2))
    if name == "zoom_out":
        return Props(scale=1.0 + 0.7 * (1.0 - e), opacity=e)
    if name in ("spin_in", "spin"):
        return Props(scale=0.3 + 0.7 * e, rot=-180 * (1 - e), opacity=min(1.0, p * 2))
    if name == "rotate":
        return Props(scale=0.7 + 0.3 * e, rot=-360 * (1 - e), opacity=e)
    if name == "flip":
        return Props(scale=abs(math.cos(math.pi * (1 - e))), rot=0, opacity=e)
    if name == "bounce":
        b = ease("ease_in" if leaving else "ease_out_bounce", p)
        return Props(dy=-0.12 * (1 - b), opacity=min(1.0, p * 4))
    if name == "fade_scale":
        return Props(scale=0.8 + 0.2 * e, opacity=e)
    if name == "scale_up":
        return Props(scale=0.5 + 0.5 * e, opacity=min(1.0, p * 2))
    if name == "scale_down":
        return Props(scale=1.5 - 0.5 * e, opacity=e)
    if name == "blur_fade":
        return Props(scale=0.9 + 0.1 * e, opacity=e)
    if name == "drop":
        b = ease("ease_in" if leaving else "ease_out_bounce", p)
        return Props(dy=-0.3 * (1 - b), opacity=min(1.0, p * 3))
    off = {
        "slide_up": (0, _DY),
        "slide_down": (0, -_DY),
        "slide_left": (_DX, 0),
        "slide_right": (-_DX, 0),
        "slide_up_big": (0, 0.3),
        "slide_down_big": (0, -0.3),
        "slide_left_big": (0.4, 0),
        "slide_right_big": (-0.4, 0),
        "from_top": (0, _DY),
        "from_bottom": (0, -_DY),
        "from_left": (_DX, 0),
        "from_right": (-_DX, 0),
    }.get(name)
    if off:
        return Props(dx=off[0] * (1 - e), dy=off[1] * (1 - e), opacity=min(1.0, p * 2.5))
    return Props()


def _loop(name: str, tau: float, period: float, amount: float) -> Props:
    w = math.sin(2 * math.pi * tau / period)
    if name in ("pulse", "breathing"):
        return Props(scale=1 + amount * w)
    if name == "wiggle":
        return Props(rot=amount * 40 * w)
    if name in ("float", "hover"):
        return Props(dy=amount * 0.15 * w)
    if name == "blink":
        return Props(opacity=1 - amount * 4 * (0.5 - 0.5 * w) if amount else 1.0)
    if name in ("shake", "tremble"):
        return Props(dx=amount * 0.2 * math.sin(2 * math.pi * 3 * tau / period))
    if name == "swing":
        return Props(rot=amount * 20 * math.sin(2 * math.pi * tau / period))
    if name == "zoom_pulse":
        return Props(scale=1 + amount * 0.1 * w)
    if name == "bounce_loop":
        return Props(dy=-amount * 0.08 * max(0.0, w))
    if name == "spin_loop":
        return Props(rot=amount * 360 * (tau / period) % 360)
    return Props()


# --- Evaluación ----------------------------------------------------------------------------------------------------


def _kf_value(kfs: list, attr: str, base: float, tau: float) -> float | None:
    pts = [(k.t, getattr(k, attr), k.easing) for k in kfs if getattr(k, attr) is not None]
    if not pts:
        return None
    pts.sort(key=lambda x: x[0])
    if pts[0][0] > 0:
        pts.insert(0, (0.0, base, "linear"))  # parte del valor base
    if tau <= pts[0][0]:
        return pts[0][1]
    for (t0, v0, _), (t1, v1, easing) in zip(pts, pts[1:], strict=False):
        if tau <= t1:
            return v0 + (v1 - v0) * ease(easing, (tau - t0) / max(t1 - t0, 1e-6))
    return pts[-1][1]


def eval_props(layer: LayerBase, tau: float, base_x: float, base_y: float, base_rot: float = 0.0) -> Props:
    """Propiedades de la layer en `tau` segundos desde su inicio."""
    an: Animations = layer.animations
    length = layer.end - layer.start
    out = Props(opacity=layer.opacity)
    # fotogramas clave (valores absolutos → desplazamientos respecto a la caja base)
    if an.keyframes:
        x = _kf_value(an.keyframes, "x", base_x, tau)
        y = _kf_value(an.keyframes, "y", base_y, tau)
        sc = _kf_value(an.keyframes, "scale", 1.0, tau)
        op = _kf_value(an.keyframes, "opacity", layer.opacity, tau)
        rt = _kf_value(an.keyframes, "rotation", base_rot, tau)
        out.dx = 0 if x is None else x - base_x
        out.dy = 0 if y is None else y - base_y
        out.scale = 1.0 if sc is None else sc
        out.opacity = layer.opacity if op is None else op
        out.rot = 0 if rt is None else rt - base_rot
    for anim, leaving in ((an.enter, False), (an.exit, True)):
        if anim is None:
            continue
        d = min(anim.dur, length)
        if not leaving and tau < d:
            p = _preset(anim.name, tau / d, False)
        elif leaving and tau > length - d:
            p = _preset(anim.name, (length - tau) / d, True)
        else:
            continue
        out.dx, out.dy, out.scale, out.rot = out.dx + p.dx, out.dy + p.dy, out.scale * p.scale, out.rot + p.rot
        out.opacity *= p.opacity
    if an.loop:
        lp = _loop(an.loop.name, tau, an.loop.period, an.loop.amount)
        out.dx, out.dy, out.scale, out.rot = out.dx + lp.dx, out.dy + lp.dy, out.scale * lp.scale, out.rot + lp.rot
        out.opacity *= lp.opacity
    out.opacity = min(max(out.opacity, 0.0), 1.0)
    out.scale = max(out.scale, 0.01)
    return out


def is_animated(layer: LayerBase) -> bool:
    a = layer.animations
    return bool(a.enter or a.exit or a.loop or a.keyframes)


def sample_times(layer: LayerBase) -> list[float]:
    """Instantes de muestreo: los bordes de cada animación y una rejilla fina solo donde algo se mueve."""
    a, length = layer.animations, layer.end - layer.start
    spans: list[tuple[float, float]] = []
    if a.enter:
        spans.append((0.0, min(a.enter.dur, length)))
    if a.exit:
        spans.append((max(length - a.exit.dur, 0.0), length))
    if a.keyframes:
        spans.append((0.0, min(max(k.t for k in a.keyframes), length)))
    if a.loop:
        spans.append((0.0, length))
    merged: list[list[float]] = []
    for s, e in sorted(spans):
        if merged and s <= merged[-1][1] + 1e-6:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    times = {0.0, length}
    step = 1.0 / SAMPLE_FPS
    for s, e in merged:
        n = max(1, math.ceil((e - s) / step))
        times.update(s + (e - s) * i / n for i in range(n + 1))
    return sorted(t for t in times if 0 <= t <= length)
