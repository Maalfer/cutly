"""Secuencias de fotogramas RGBA para capas de icono/imagen animadas (Pillow).

FFmpeg no anima bien una imagen suelta (escala, rotación y opacidad a la vez con easing), así que cada
fotograma se compone aquí con el mismo motor de animación que el texto. Los fotogramas se recortan a la
caja que cubre todo el movimiento y se sacan como PNG; FFmpeg los superpone en una posición fija.
"""

import math
import os
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from cutly.schema.project import IconLayer, ImageLayer
from cutly.services.render.animation import eval_props

MAX_SECONDS = 60  # tope de duración animada por layer
_FY = {"top": 0.0, "center": 0.5, "bottom": 1.0}
_FX = {"left": 0.0, "center": 0.5, "right": 1.0}


@dataclass
class Sequence:
    pattern: str  # ruta con %05d para ffmpeg
    x: int
    y: int
    frames: int


def _anchor(anchor: str) -> tuple[float, float]:
    h = "left" if anchor.endswith("left") else "right" if anchor.endswith("right") else "center"
    v = anchor.split("_")[0] if "_" in anchor else "center"
    return _FX[h], _FY[v]


def render_sequence(
    png: Path, layer: IconLayer | ImageLayer, width: int, height: int, fps: int, outdir: Path, warnings: list[str]
) -> Sequence | None:  # fmt: skip
    box = layer.box
    base = Image.open(png).convert("RGBA")
    w = max(2, round(box.w * width))
    h = max(2, round(box.h * height)) if box.h else max(2, round(w * base.height / base.width))
    base = base.resize((w, h), Image.LANCZOS)
    fx, fy = _anchor(box.anchor)
    cx0, cy0 = box.x * width - w * fx + w / 2, box.y * height - h * fy + h / 2
    length = min(layer.end - layer.start, MAX_SECONDS)
    if layer.end - layer.start > MAX_SECONDS:
        warnings.append(f"La layer '{layer.id}' animada se limita a {MAX_SECONDS} s")
    n = math.ceil(length * fps) + 1

    frames = []  # (props, cx, cy, sw, sh, angle, bbox)
    ux0 = uy0 = 10**9
    ux1 = uy1 = -(10**9)
    for i in range(n):
        p = eval_props(layer, i / fps, box.x, box.y, box.rotation)
        cx, cy = cx0 + p.dx * width, cy0 + p.dy * height
        sw, sh = max(2, round(w * p.scale)), max(2, round(h * p.scale))
        ang = box.rotation + p.rot
        rad = math.radians(ang)
        bw = abs(sw * math.cos(rad)) + abs(sh * math.sin(rad))
        bh = abs(sw * math.sin(rad)) + abs(sh * math.cos(rad))
        if p.opacity > 0.002:
            ux0, uy0 = min(ux0, cx - bw / 2), min(uy0, cy - bh / 2)
            ux1, uy1 = max(ux1, cx + bw / 2), max(uy1, cy + bh / 2)
        frames.append((p, cx, cy, sw, sh, ang))
    ux0, uy0 = max(0, math.floor(ux0) - 2), max(0, math.floor(uy0) - 2)
    ux1, uy1 = min(width, math.ceil(ux1) + 2), min(height, math.ceil(uy1) + 2)
    if ux1 - ux0 < 2 or uy1 - uy0 < 2:
        warnings.append(f"La layer '{layer.id}' queda fuera de la pantalla o invisible: no se renderiza")
        return None
    cw, ch = ux1 - ux0, uy1 - uy0
    outdir.mkdir(parents=True, exist_ok=True)
    prev_key, prev_path = None, None
    for i, (p, cx, cy, sw, sh, ang) in enumerate(frames):
        path = outdir / f"f{i:05d}.png"
        key = (round(cx, 1), round(cy, 1), sw, sh, round(ang, 2), round(p.opacity, 3))
        if key == prev_key and prev_path is not None:
            os.link(prev_path, path)  # fotograma idéntico al anterior: sin recomponer ni recodificar
            continue
        spr = base.resize((sw, sh), Image.BICUBIC) if (sw, sh) != (w, h) else base.copy()
        if abs(ang) > 0.01:
            spr = spr.rotate(
                -ang, resample=Image.BICUBIC, expand=True
            )  # positivo = sentido horario, como en ASS y FFmpeg
        if p.opacity < 0.999:
            spr.putalpha(spr.getchannel("A").point(lambda v, o=p.opacity: int(v * o)))
        canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        canvas.paste(spr, (round(cx - spr.width / 2) - ux0, round(cy - spr.height / 2) - uy0))
        canvas.save(path, compress_level=1)
        prev_key, prev_path = key, path
    return Sequence(str(outdir / "f%05d.png"), ux0, uy0, n)
