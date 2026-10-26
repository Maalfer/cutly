"""Geometría de las capas en el fotograma de SALIDA (0–1) y correspondencia con el vídeo original.

Son estimaciones razonables (el texto real lo compone libass): sirven para detectar problemas de composición como
texto fuera de pantalla, rótulos que se pisan o iconos sobre la cara, sin tener que renderizar.
"""

import math
from dataclasses import dataclass
from functools import lru_cache

from cutly.schema.project import (
    IconLayer,
    ImageLayer,
    Reframe,
    ShapeLayer,
    SubtitleLayer,
    TextLayer,
)

Rect4 = tuple[float, float, float, float]  # x0, y0, x1, y1 normalizados

# ancho medio de carácter / tamaño de fuente, en negrita
CHAR_W = {
    "Anton": 0.42,
    "Bebas Neue": 0.38,
    "Bangers": 0.46,
    "Poppins": 0.60,
    "Poppins ExtraBold": 0.63,
    "default": 0.62,
    "DejaVu Sans": 0.62,
}
_FX = {"left": 0.0, "center": 0.5, "right": 1.0}


def _anchor(anchor: str) -> tuple[float, float]:
    h = "left" if anchor.endswith("left") else "right" if anchor.endswith("right") else "center"
    v = anchor.split("_")[0] if "_" in anchor else "center"
    return _FX[h], {"top": 0.0, "center": 0.5, "bottom": 1.0}[v]


@lru_cache(maxsize=32)
def _pil(path: str, px: int):
    from PIL import ImageFont

    return ImageFont.truetype(path, px)


def _measured(text, font, size, uppercase, bold, box_w, W, H) -> tuple[float, float, int] | None:
    """Medida con la fuente REAL (la que usa libass) y ajuste de línea voraz por palabras; None si no se encuentra."""
    from cutly.services.render.fonts import font_file

    path = font_file(font, bold)
    if not path:
        return None
    px = max(8, round(size * H))
    try:
        fnt = _pil(path, px)
        asc, desc = fnt.getmetrics()
        # libass fija ascendente+descendente = Fontsize (no el em): se escala a ese criterio
        fnt = _pil(path, max(8, round(px * px / max(asc + desc, 1))))
    except OSError:
        return None
    max_w = box_w * W
    lines, widest = 0, 0.0
    for raw in text.split("\n"):
        raw = raw.upper() if uppercase else raw
        cur = ""
        for word in raw.split():
            wl = fnt.getlength(word)
            if wl > max_w:  # una palabra más ancha que la caja se desborda: cuenta como varias líneas
                lines += math.ceil(wl / max_w) - 1
                widest = max(widest, max_w)
            trial = f"{cur} {word}".strip()
            if cur and fnt.getlength(trial) > max_w:
                widest = max(widest, fnt.getlength(cur))
                lines, cur = lines + 1, word
            else:
                cur = trial
        widest = max(widest, fnt.getlength(cur))
        lines += 1
    return min(box_w, (widest + px * 0.8) / W), lines * size * 1.1 + size * 0.35, lines


def text_metrics(
    text: str, font: str, size: float, uppercase: bool, box_w: float, W: int, H: int, bold: bool = True
) -> tuple[float, float, int]:
    """(ancho, alto, nº de líneas) normalizados, con el ajuste de línea por el ancho de la caja."""
    real = _measured(text, font, size, uppercase, bold, box_w, W, H)
    if real:
        return real
    cw = CHAR_W.get(font, CHAR_W["default"]) * (1.1 if uppercase else 1.0)
    char_px = size * H * cw
    per_line = max(1, int((box_w * W * 0.92) / char_px))
    lines = 0
    longest = 0
    for ln in text.split("\n"):
        n = max(1, math.ceil(len(ln) / per_line))
        lines += n
        longest = max(longest, min(len(ln), per_line))
    width = min(box_w, (longest * char_px) / W + size * H * 0.8 / W)
    height = lines * size * 1.25 + size * 0.5
    return width, height, lines


def layer_rect(layer, W: int, H: int) -> Rect4 | None:
    """Rectángulo estimado de una capa visible; None si no ocupa espacio (efectos)."""
    if isinstance(layer, TextLayer):
        w, h, _ = text_metrics(
            layer.text, layer.style.font, layer.style.size, layer.style.uppercase, layer.box.w, W, H, layer.style.bold
        )
        fx, fy = _anchor(layer.box.anchor)
        x0, y0 = layer.box.x - w * fx, layer.box.y - h * fy
        return (x0, y0, x0 + w, y0 + h)
    if isinstance(layer, IconLayer | ImageLayer):
        w = layer.box.w
        h = layer.box.h if layer.box.h else w * W / H  # el icono es cuadrado en píxeles
        fx, fy = _anchor(layer.box.anchor)
        x0, y0 = layer.box.x - w * fx, layer.box.y - h * fy
        return (x0, y0, x0 + w, y0 + h)
    if isinstance(layer, ShapeLayer):
        w = layer.box.w
        h = layer.box.h if layer.box.h else w * W / H
        fx, fy = _anchor(layer.box.anchor)
        x0, y0 = layer.box.x - w * fx, layer.box.y - h * fy
        return (x0, y0, x0 + w, y0 + h)
    if isinstance(layer, SubtitleLayer):
        st = layer.style
        h = st.max_lines * st.size * 1.25 + st.size * 0.4
        return (0.06, st.position_y - h / 2, 0.94, st.position_y + h / 2)
    return None


def intersection(a: Rect4, b: Rect4) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return max(w, 0.0) * max(h, 0.0)


def area(a: Rect4) -> float:
    return max(a[2] - a[0], 0.0) * max(a[3] - a[1], 0.0)


def overlap_ratio(a: Rect4, b: Rect4) -> float:
    """Intersección sobre el área de la menor."""
    m = min(area(a), area(b))
    return intersection(a, b) / m if m > 0 else 0.0


# --- reencuadre: del original a la salida -------------------------------------------------------------------------------------


@dataclass
class Frame:
    sw: int
    sh: int
    W: int
    H: int


def _into_band(r: Rect4, region: Rect4, fr: Frame, band: Rect4, fit: str) -> Rect4 | None:
    """Rectángulo `r` (en coords de origen 0–1) colocado dentro de la banda de salida `band` mostrando `region`."""
    rw, rh = (region[2] - region[0]) * fr.sw, (region[3] - region[1]) * fr.sh
    bw, bh = (band[2] - band[0]) * fr.W, (band[3] - band[1]) * fr.H
    s = max(bw / rw, bh / rh) if fit == "cover" else min(bw / rw, bh / rh)
    ox, oy = (rw * s - bw) / 2, (rh * s - bh) / 2  # recorte (cover) o margen negativo (contain)
    x0 = ((r[0] - region[0]) * fr.sw * s - ox) / fr.W + band[0]
    x1 = ((r[2] - region[0]) * fr.sw * s - ox) / fr.W + band[0]
    y0 = ((r[1] - region[1]) * fr.sh * s - oy) / fr.H + band[1]
    y1 = ((r[3] - region[1]) * fr.sh * s - oy) / fr.H + band[1]
    x0, y0, x1, y1 = max(x0, band[0]), max(y0, band[1]), min(x1, band[2]), min(y1, band[3])
    return (x0, y0, x1, y1) if x1 > x0 and y1 > y0 else None


def source_rect_to_output(r: Rect4, rf: Reframe, fr: Frame) -> list[Rect4]:
    """Dónde acaba un rectángulo del original (0–1) en el fotograma de salida según el reencuadre."""
    full: Rect4 = (0.0, 0.0, 1.0, 1.0)
    out: list[Rect4 | None] = []
    if rf.mode == "center":
        aspect = fr.W / fr.H
        cw, ch = (fr.sh * aspect, fr.sh) if fr.sw / fr.sh > aspect else (fr.sw, fr.sw / aspect)
        x = min(max(rf.center_x * fr.sw - cw / 2, 0), fr.sw - cw)
        y = (fr.sh - ch) / 2
        region: Rect4 = (x / fr.sw, y / fr.sh, (x + cw) / fr.sw, (y + ch) / fr.sh)
        out.append(_into_band(r, region, fr, full, "cover"))
    elif rf.mode == "stack" and rf.facecam and rf.game:
        split = round(fr.H * rf.stack_split / 2) * 2 / fr.H
        fc, gm = rf.facecam, rf.game
        out.append(_into_band(r, (fc.x, fc.y, fc.x + fc.w, fc.y + fc.h), fr, (0, 0, 1, split), "cover"))
        out.append(_into_band(r, (gm.x, gm.y, gm.x + gm.w, gm.y + gm.h), fr, (0, split, 1, 1), rf.game_fit))
    else:
        reg = rf.facecam if rf.mode == "facecam" else rf.game
        if reg is not None:
            out.append(
                _into_band(
                    r,
                    (reg.x, reg.y, reg.x + reg.w, reg.y + reg.h),
                    fr,
                    full,
                    "cover" if rf.mode == "facecam" else rf.game_fit,
                )
            )
    return [o for o in out if o]
