"""Capa `scene` → secuencia de PNG (RGBA, o RGB si es opaca) que FFmpeg superpone, como los iconos animados."""

import math
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from cutly.schema.project import SceneLayer
from cutly.schema.scene import Scene
from cutly.services.render.animation import eval_props, is_animated
from cutly.services.scene.engine import Player
from cutly.services.scene.templates import expand

MAX_SECONDS = 120
MAX_PIXELS = 4096 * 4096


@dataclass
class SceneSequence:
    pattern: str  # ruta con %05d para ffmpeg
    x: int
    y: int
    frames: int
    t0: float  # segundos (desde el inicio de la capa) del primer fotograma generado


def _anchor(anchor: str) -> tuple[float, float]:
    h = "left" if anchor.endswith("left") else "right" if anchor.endswith("right") else "center"
    v = anchor.split("_")[0] if "_" in anchor else "center"
    return {"left": 0.0, "center": 0.5, "right": 1.0}[h], {"top": 0.0, "center": 0.5, "bottom": 1.0}[v]


def box_pixels(layer: SceneLayer, scene: Scene, W: int, H: int) -> tuple[int, int, int, int]:
    """(x, y, ancho, alto) de la caja de la escena en píxeles del fotograma de salida."""
    b = layer.box
    bw = max(2, round(b.w * W))
    bh = max(2, round(b.h * H)) if b.h else max(2, round(bw * scene.world.h / scene.world.w))
    bw, bh = bw + bw % 2, bh + bh % 2
    fx, fy = _anchor(b.anchor)
    return round(b.x * W - bw * fx), round(b.y * H - bh * fy), bw, bh


def render_scene_sequence(
    layer: SceneLayer, W: int, H: int, fps: int, outdir: Path, warnings: list[str],
    window: tuple[float, float] | None = None,
) -> SceneSequence | None:  # fmt: skip
    """`window` = (t0, t1) en segundos del clip resultante: solo se generan los fotogramas que lo tocan."""
    scene = expand(layer)
    x0, y0, bw, bh = box_pixels(layer, scene, W, H)
    if bw * bh > MAX_PIXELS:
        warnings.append(f"La escena '{layer.id}' es demasiado grande ({bw}x{bh}): no se renderiza")
        return None
    if x0 >= W or y0 >= H or x0 + bw <= 0 or y0 + bh <= 0:
        warnings.append(f"La escena '{layer.id}' queda fuera de la pantalla: no se renderiza")
        return None
    length = layer.end - layer.start
    if length > MAX_SECONDS:
        warnings.append(f"La escena '{layer.id}' se limita a {MAX_SECONDS} s")
        length = MAX_SECONDS
    i0, i1 = 0, math.ceil(length * fps) + 1
    if window:
        i0 = max(0, math.floor((window[0] - layer.start) * fps) - 1)
        i1 = min(i1, math.ceil((window[1] - layer.start) * fps) + 2)
        if i1 <= i0:
            return None
    player = Player(scene, bw, bh, layer.fit)
    outdir.mkdir(parents=True, exist_ok=True)
    prev: np.ndarray | None = None
    prev_path: Path | None = None
    prev_fut = None
    pending: list = []

    def link(src_fut, src: Path, dst: Path) -> None:
        src_fut.result()  # el original ya tiene que estar escrito
        os.link(src, dst)

    # Un único formato de píxel en toda la secuencia: si mezcla RGB y RGBA, FFmpeg reconfigura el grafo y corta el vídeo.
    rgb_only = player.opaque and layer.opacity >= 0.999 and not is_animated(layer)

    def save(arr: np.ndarray, path: Path) -> None:
        Image.fromarray(arr[..., :3] if rgb_only else arr).save(path, compress_level=1)

    with ThreadPoolExecutor(
        max_workers=2
    ) as pool:  # zlib libera el GIL: se codifica un PNG mientras se dibuja el siguiente
        for n, i in enumerate(range(i0, i1)):
            t = i / fps
            op = eval_props(layer, t, layer.box.x, layer.box.y).opacity
            arr = player.frame(t, op)
            path = outdir / f"f{n:05d}.png"
            if prev is not None and prev_path is not None and np.array_equal(arr, prev):
                pending.append(pool.submit(link, prev_fut, prev_path, path))  # idéntico al anterior: sin recodificar
                continue
            prev_fut = pool.submit(save, arr, path)
            pending.append(prev_fut)
            prev, prev_path = arr, path
            while len(pending) > 4:  # limita los fotogramas en memoria
                pending.pop(0).result()
        for fut in pending:
            fut.result()
    return SceneSequence(str(outdir / "f%05d.png"), x0, y0, i1 - i0, i0 / fps)
