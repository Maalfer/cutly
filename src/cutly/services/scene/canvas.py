"""Lienzo RGBA (float32, alfa premultiplicado) y utilidades de dibujo antialias con OpenCV/Pillow.

Cada forma se dibuja primero como máscara de 8 bits en su caja mínima y se compone con `Canvas.over`; así el coste
es proporcional al área del objeto y no al del fotograma.
"""

import math
from collections.abc import Callable
from functools import lru_cache

import cv2
import numpy as np

SH = 4  # bits de subpíxel de OpenCV
ONE = 1 << SH


def parse_color(hex_color: str) -> tuple[np.ndarray, float]:
    """'#RRGGBB[AA]' → (rgb float32 0-1, alfa 0-1)."""
    h = hex_color.lstrip("#")
    rgb = np.array([int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)], dtype=np.float32)
    return rgb, (int(h[6:8], 16) / 255 if len(h) == 8 else 1.0)


def mix(a: np.ndarray, b: np.ndarray, k: float) -> np.ndarray:
    return a + (b - a) * k


class Canvas:
    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.c = np.zeros((h, w, 3), np.float32)  # color premultiplicado
        self.a = np.zeros((h, w), np.float32)

    def clip(self, x0: float, y0: float, x1: float, y1: float) -> tuple[int, int, int, int] | None:
        ix0, iy0 = max(0, math.floor(x0)), max(0, math.floor(y0))
        ix1, iy1 = min(self.w, math.ceil(x1)), min(self.h, math.ceil(y1))
        if ix1 <= ix0 or iy1 <= iy0:
            return None
        return ix0, iy0, ix1, iy1

    def over(self, mask: np.ndarray, x0: int, y0: int, color: np.ndarray, alpha: float = 1.0) -> None:
        """Compone `color` con la máscara (float 0-1) cuya esquina superior izquierda está en (x0, y0)."""
        h, w = mask.shape
        cx0, cy0 = max(x0, 0), max(y0, 0)
        cx1, cy1 = min(x0 + w, self.w), min(y0 + h, self.h)
        if cx1 <= cx0 or cy1 <= cy0 or alpha <= 0:
            return
        m = mask[cy0 - y0 : cy1 - y0, cx0 - x0 : cx1 - x0]
        if alpha < 1:
            m = m * alpha
        inv = 1.0 - m
        dc = self.c[cy0:cy1, cx0:cx1]
        da = self.a[cy0:cy1, cx0:cx1]
        dc *= inv[..., None]
        dc += m[..., None] * color
        da *= inv
        da += m

    def paint(
        self,
        bbox: tuple[float, float, float, float],
        color: np.ndarray,
        alpha: float,
        draw: Callable[[np.ndarray, int, int], None],
    ) -> None:
        """Dibuja con `draw(img_uint8, ox, oy)` (coordenadas del lienzo menos el origen) y compone el resultado."""
        if alpha <= 0.002:
            return
        box = self.clip(*bbox)
        if box is None:
            return
        x0, y0, x1, y1 = box
        img = np.zeros((y1 - y0, x1 - x0), np.uint8)
        draw(img, x0, y0)
        bx, by, bw, bh = cv2.boundingRect(img)  # solo se compone la parte realmente dibujada
        if bw == 0 or bh == 0:
            return
        if bw * bh < img.size * 0.7:
            img = img[by : by + bh, bx : bx + bw]
            x0, y0 = x0 + bx, y0 + by
        self.over(img.astype(np.float32) * (1 / 255), x0, y0, color, alpha)

    def to_rgba(self, opaque: bool = False) -> np.ndarray:
        """uint8 RGBA con alfa recto. `opaque=True` (alfa = 1 en todo el lienzo) evita la división por el alfa."""
        out = np.empty((self.h, self.w, 4), np.uint8)
        if opaque:
            tmp = self.c * 255.0
            tmp += 0.5
            np.minimum(tmp, 255.0, out=tmp)
            out[..., :3] = tmp
            out[..., 3] = 255
            return out
        a = np.maximum(self.a, 1e-5)
        rgb = np.clip(self.c / a[..., None], 0, 1)
        out[..., :3] = (rgb * 255 + 0.5).astype(np.uint8)
        out[..., 3] = (np.clip(self.a, 0, 1) * 255 + 0.5).astype(np.uint8)
        return out


# --- Primitivas OpenCV con subpíxel -----------------------------------------------------------------------------


def _p(x: float, y: float, ox: int, oy: int) -> tuple[int, int]:
    return round((x - ox) * ONE), round((y - oy) * ONE)


def d_circle(img, ox, oy, x, y, r, fill=True, thick=1):
    cv2.circle(img, _p(x, y, ox, oy), max(1, round(r * ONE)), 255, -1 if fill else max(1, round(thick)),
               cv2.LINE_AA, SH)  # fmt: skip


def d_line(img, ox, oy, x1, y1, x2, y2, thick):
    cv2.line(img, _p(x1, y1, ox, oy), _p(x2, y2, ox, oy), 255, max(1, round(thick)), cv2.LINE_AA, SH)


def d_poly(img, ox, oy, pts, fill=True, closed=True, thick=1):
    arr = np.array([_p(x, y, ox, oy) for x, y in pts], np.int32).reshape(-1, 1, 2)
    if fill:
        cv2.fillPoly(img, [arr], 255, cv2.LINE_AA, SH)
    else:
        cv2.polylines(img, [arr], closed, 255, max(1, round(thick)), cv2.LINE_AA, SH)


def d_ellipse(img, ox, oy, x, y, rx, ry, a0=0, a1=360, rot=0, fill=True, thick=1):
    cv2.ellipse(img, _p(x, y, ox, oy), (max(1, round(rx * ONE)), max(1, round(ry * ONE))), rot, a0, a1, 255,
                -1 if fill else max(1, round(thick)), cv2.LINE_AA, SH)  # fmt: skip


def rrect_pts(cx: float, cy: float, w: float, h: float, r: float, n: int = 7) -> list[tuple[float, float]]:
    r = max(0.0, min(r, w / 2, h / 2))
    pts: list[tuple[float, float]] = []
    for (ccx, ccy), a0 in (
        ((cx + w / 2 - r, cy - h / 2 + r), -90),
        ((cx + w / 2 - r, cy + h / 2 - r), 0),
        ((cx - w / 2 + r, cy + h / 2 - r), 90),
        ((cx - w / 2 + r, cy - h / 2 + r), 180),
    ):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((ccx + r * math.cos(a), ccy + r * math.sin(a)))
    return pts


def d_rrect(img, ox, oy, cx, cy, w, h, r, fill=True, thick=1):
    d_poly(img, ox, oy, rrect_pts(cx, cy, w, h, r), fill=fill, closed=True, thick=thick)


@lru_cache(maxsize=64)
def glow_sprite(radius: int) -> np.ndarray:
    """Halo radial suave (alfa 0-1) de lado 2*radius."""
    radius = max(2, radius)
    ax = (np.arange(2 * radius, dtype=np.float32) - radius + 0.5) / radius
    d = np.sqrt(ax[None, :] ** 2 + ax[:, None] ** 2)
    return np.clip(1.0 - d, 0.0, 1.0) ** 2


def glow(cv: Canvas, x: float, y: float, radius: float, color: np.ndarray, alpha: float) -> None:
    if alpha <= 0.003 or radius < 2:
        return
    r = max(2, int(round(radius / 2.0)) * 2)
    cv.over(glow_sprite(r), round(x) - r, round(y) - r, color, alpha)


@lru_cache(maxsize=8)
def rounded_mask(w: int, h: int, radius: int) -> np.ndarray:
    img = np.zeros((h, w), np.uint8)
    d_rrect(img, 0, 0, w / 2, h / 2, w, h, radius)
    return img.astype(np.float32) * (1 / 255)
