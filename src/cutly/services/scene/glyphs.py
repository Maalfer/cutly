"""Glifos vectoriales de los nodos (servidor, router, candado…), definidos en coordenadas unitarias.

Unidad: 1.0 = alto del nodo; el origen es el centro. Cada glifo es una lista de operaciones:
  ("fill", forma)    relleno (color `fill` del nodo)
  ("stroke", forma)  contorno (color del nodo, grosor del nodo)
  ("solid", forma)   relleno con el color del nodo (LED, cerradura…)
Formas: ("rr", cx, cy, w, h, r) · ("c", cx, cy, r) · ("e", cx, cy, rx, ry, a0, a1) · ("l", x1, y1, x2, y2) ·
("p", [(x, y)…], cerrado)
"""

import math

import cv2
import numpy as np

from cutly.services.scene import canvas as C


def _rr(cx, cy, w, h, r):
    return ("rr", cx, cy, w, h, r)


def _c(cx, cy, r):
    return ("c", cx, cy, r)


def _l(x1, y1, x2, y2):
    return ("l", x1, y1, x2, y2)


def _p(pts, closed=True):
    return ("p", pts, closed)


def _e(cx, cy, rx, ry, a0=0, a1=360):
    return ("e", cx, cy, rx, ry, a0, a1)


def _gear() -> list[tuple[float, float]]:
    pts = []
    for i in range(16):
        a = math.pi * 2 * i / 16 - math.pi / 16
        r = 0.5 if (i // 1) % 2 == 0 else 0.38
        pts.append((r * math.cos(a), r * math.sin(a)))
    # dientes: 8 salientes
    out = []
    for i in range(8):
        a = math.pi * 2 * i / 8
        for da, r in ((-0.26, 0.38), (-0.17, 0.5), (0.17, 0.5), (0.26, 0.38)):
            out.append((r * math.cos(a + da), r * math.sin(a + da)))
    return out


def _user_body() -> list[tuple[float, float]]:
    return [(0.42 * math.cos(math.radians(a)), 0.5 + 0.5 * -math.sin(math.radians(a))) for a in range(0, 181, 12)]


GLYPHS: dict[str, list] = {
    "server": [
        *[
            op
            for i in (-1, 0, 1)
            for op in (
                ("fill", _rr(0, i * 0.31, 0.95, 0.27, 0.05)),
                ("stroke", _rr(0, i * 0.31, 0.95, 0.27, 0.05)),
                ("solid", _c(-0.36, i * 0.31, 0.035)),
                ("stroke", _l(-0.18, i * 0.31, 0.32, i * 0.31)),
            )
        ],
    ],
    "router": [
        ("fill", _c(0, 0, 0.5)),
        ("stroke", _c(0, 0, 0.5)),
        ("stroke", _l(-0.22, -0.08, 0.22, -0.08)),
        ("stroke", _l(-0.22, 0.08, 0.22, 0.08)),
    ],  # fmt: skip
    "computer": [
        ("fill", _rr(0, -0.1, 0.92, 0.62, 0.06)),
        ("stroke", _rr(0, -0.1, 0.92, 0.62, 0.06)),
        ("stroke", _rr(0, -0.1, 0.76, 0.46, 0.03)),
        ("stroke", _l(0, 0.21, 0, 0.36)),
        ("stroke", _l(-0.22, 0.38, 0.22, 0.38)),
    ],  # fmt: skip
    "phone": [
        ("fill", _rr(0, 0, 0.52, 0.98, 0.1)),
        ("stroke", _rr(0, 0, 0.52, 0.98, 0.1)),
        ("stroke", _l(-0.07, -0.41, 0.07, -0.41)),
        ("stroke", _c(0, 0.41, 0.03)),
    ],  # fmt: skip
    "cloud": [
        ("cloudfill", None),
    ],
    "database": [
        ("fill", _rr(0, 0.02, 0.7, 0.66, 0.0)),
        ("fill", _e(0, 0.35, 0.35, 0.12)),
        ("stroke", _e(0, 0.35, 0.35, 0.12, 0, 180)),
        ("stroke", _l(-0.35, -0.3, -0.35, 0.35)),
        ("stroke", _l(0.35, -0.3, 0.35, 0.35)),
        ("stroke", _e(0, 0.08, 0.35, 0.12, 0, 180)),
        ("stroke", _e(0, -0.12, 0.35, 0.12, 0, 180)),
        ("fill", _e(0, -0.32, 0.35, 0.12)),
        ("stroke", _e(0, -0.32, 0.35, 0.12)),
    ],  # fmt: skip
    "lock": [
        ("stroke", _e(0, -0.1, 0.2, 0.27, 180, 360)),
        ("stroke", _l(-0.2, -0.1, -0.2, 0.02)),
        ("stroke", _l(0.2, -0.1, 0.2, 0.02)),
        ("fill", _rr(0, 0.14, 0.64, 0.46, 0.07)),
        ("stroke", _rr(0, 0.14, 0.64, 0.46, 0.07)),
        ("solid", _c(0, 0.11, 0.055)),
        ("stroke", _l(0, 0.12, 0, 0.25)),
    ],  # fmt: skip
    "key": [
        ("fill", _c(-0.25, 0, 0.2)),
        ("stroke", _c(-0.25, 0, 0.2)),
        ("solid", _c(-0.25, 0, 0.06)),
        ("stroke", _l(-0.05, 0, 0.45, 0)),
        ("stroke", _l(0.3, 0, 0.3, 0.13)),
        ("stroke", _l(0.43, 0, 0.43, 0.1)),
    ],  # fmt: skip
    "shield": [
        ("fill", _p([(0, -0.5), (0.4, -0.36), (0.37, 0.08), (0, 0.5), (-0.37, 0.08), (-0.4, -0.36)])),
        ("stroke", _p([(0, -0.5), (0.4, -0.36), (0.37, 0.08), (0, 0.5), (-0.37, 0.08), (-0.4, -0.36)])),
        ("stroke", _p([(-0.16, 0.0), (-0.04, 0.13), (0.18, -0.13)], False)),
    ],
    "globe": [
        ("fill", _c(0, 0, 0.5)),
        ("stroke", _c(0, 0, 0.5)),
        ("stroke", _e(0, 0, 0.21, 0.5)),
        ("stroke", _l(-0.5, 0, 0.5, 0)),
        ("stroke", _l(-0.43, -0.25, 0.43, -0.25)),
        ("stroke", _l(-0.43, 0.25, 0.43, 0.25)),
    ],  # fmt: skip
    "doc": [
        ("fill", _p([(-0.32, -0.5), (0.1, -0.5), (0.32, -0.28), (0.32, 0.5), (-0.32, 0.5)])),
        ("stroke", _p([(-0.32, -0.5), (0.1, -0.5), (0.32, -0.28), (0.32, 0.5), (-0.32, 0.5)])),
        ("stroke", _p([(0.1, -0.5), (0.1, -0.28), (0.32, -0.28)], False)),
        ("stroke", _l(-0.2, -0.05, 0.2, -0.05)),
        ("stroke", _l(-0.2, 0.1, 0.2, 0.1)),
        ("stroke", _l(-0.2, 0.25, 0.05, 0.25)),
    ],  # fmt: skip
    "user": [
        ("fill", _p(_user_body())),
        ("stroke", _p(_user_body(), False)),
        ("fill", _c(0, -0.2, 0.22)),
        ("stroke", _c(0, -0.2, 0.22)),
    ],  # fmt: skip
    "circle": [("fill", _c(0, 0, 0.5)), ("stroke", _c(0, 0, 0.5))],
    "box": [("fill", _rr(0, 0, 1.0, 0.8, 0.12)), ("stroke", _rr(0, 0, 1.0, 0.8, 0.12))],
    "pill": [("fill", _rr(0, 0, 1.0, 0.5, 0.25)), ("stroke", _rr(0, 0, 1.0, 0.5, 0.25))],
    "chip": [
        ("fill", _rr(0, 0, 0.62, 0.62, 0.07)),
        ("stroke", _rr(0, 0, 0.62, 0.62, 0.07)),
        ("stroke", _rr(0, 0, 0.34, 0.34, 0.03)),
        *[("stroke", _l(s * 0.31 + s * 0.12, k, s * 0.31, k)) for s in (-1, 1) for k in (-0.17, 0, 0.17)],
        *[("stroke", _l(k, s * 0.31 + s * 0.12, k, s * 0.31)) for s in (-1, 1) for k in (-0.17, 0, 0.17)],
    ],  # fmt: skip
    "bolt": [("solid", _p([(0.1, -0.5), (-0.28, 0.06), (-0.02, 0.06), (-0.1, 0.5), (0.28, -0.1), (0.02, -0.1)]))],
    "check": [("stroke", _p([(-0.4, 0.02), (-0.12, 0.3), (0.42, -0.3)], False))],
    "cross": [("stroke", _l(-0.3, -0.3, 0.3, 0.3)), ("stroke", _l(0.3, -0.3, -0.3, 0.3))],
    "warning": [
        ("fill", _p([(0, -0.5), (0.5, 0.4), (-0.5, 0.4)])),
        ("stroke", _p([(0, -0.5), (0.5, 0.4), (-0.5, 0.4)])),
        ("stroke", _l(0, -0.16, 0, 0.1)),
        ("solid", _c(0, 0.25, 0.04)),
    ],  # fmt: skip
    "gear": [("fill", _p(_gear())), ("stroke", _p(_gear())), ("stroke", _c(0, 0, 0.14))],
    "mail": [
        ("fill", _rr(0, 0, 0.98, 0.68, 0.07)),
        ("stroke", _rr(0, 0, 0.98, 0.68, 0.07)),
        ("stroke", _p([(-0.48, -0.3), (0, 0.05), (0.48, -0.3)], False)),
    ],  # fmt: skip
    "packet": [
        ("fill", _rr(0, 0, 0.98, 0.78, 0.12)),
        ("stroke", _rr(0, 0, 0.98, 0.78, 0.12)),
        ("solid", _rr(0, -0.27, 0.98, 0.24, 0.1)),
    ],  # fmt: skip
}

# Proporción ancho/alto aproximada para calcular cajas de contorno.
ASPECT = {"server": 0.95, "computer": 0.92, "box": 1.0, "pill": 1.0, "mail": 0.98, "packet": 0.98, "phone": 0.52,
          "doc": 0.64, "user": 0.84, "lock": 0.64, "key": 0.95, "cloud": 0.95}  # fmt: skip


def _xf(x: float, y: float, cx: float, cy: float, s: float, cos: float, sin: float) -> tuple[float, float]:
    return cx + (x * cos - y * sin) * s, cy + (x * sin + y * cos) * s


def draw_glyph(
    cv: C.Canvas, kind: str, cx: float, cy: float, size: float, color: np.ndarray, fill: np.ndarray,
    stroke_w: float, rot: float = 0.0, alpha: float = 1.0, fill_alpha: float = 1.0,
) -> None:  # fmt: skip
    """Dibuja el glifo `kind` centrado en (cx, cy) con alto `size` (píxeles del lienzo)."""
    rad = math.radians(rot)
    cos, sin = math.cos(rad), math.sin(rad)
    half = size * 0.75 + stroke_w * 2
    bbox = (cx - half, cy - half, cx + half, cy + half)

    def pt(x, y):
        return _xf(x, y, cx, cy, size, cos, sin)

    def shape(img, ox, oy, sh, fillit: bool):
        k = sh[0]
        if k == "rr":
            _, x, y, w, h, r = sh
            C.d_poly(img, ox, oy, [pt(px, py) for px, py in C.rrect_pts(x, y, w, h, r)], fill=fillit, thick=stroke_w)
        elif k == "c":
            _, x, y, r = sh
            px, py = pt(x, y)
            C.d_circle(img, ox, oy, px, py, r * size, fill=fillit, thick=stroke_w)
        elif k == "e":
            _, x, y, rx, ry, a0, a1 = sh
            px, py = pt(x, y)
            C.d_ellipse(img, ox, oy, px, py, rx * size, ry * size, a0, a1, rot, fill=fillit, thick=stroke_w)
        elif k == "l":
            _, x1, y1, x2, y2 = sh
            (ax, ay), (bx, by) = pt(x1, y1), pt(x2, y2)
            C.d_line(img, ox, oy, ax, ay, bx, by, stroke_w)
        elif k == "p":
            _, pts, closed = sh
            C.d_poly(img, ox, oy, [pt(px, py) for px, py in pts], fill=fillit, closed=closed, thick=stroke_w)

    if kind == "cloud":
        parts = [(-0.24, 0.06, 0.2), (0.0, -0.1, 0.28), (0.26, 0.06, 0.2), (-0.1, 0.1, 0.22), (0.1, 0.1, 0.22)]

        def cloud_fill(img, ox, oy):
            for x, y, r in parts:
                px, py = pt(x, y)
                C.d_circle(img, ox, oy, px, py, r * size)
            px, py = pt(0, 0.14)
            C.d_rrect(img, ox, oy, px, py, 0.72 * size, 0.24 * size, 0.12 * size)

        def cloud_edge(img, ox, oy):
            cloud_fill(img, ox, oy)
            k = max(3, int(2 * stroke_w) | 1)
            filled = img.copy()
            img[:] = cv2.subtract(filled, cv2.erode(filled, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))))

        cv.paint(bbox, fill, alpha * fill_alpha, cloud_fill)
        cv.paint(bbox, color, alpha, cloud_edge)
        return
    # operaciones consecutivas del mismo tipo se dibujan juntas; el orden entre grupos respeta la superposición
    groups: list[tuple[str, list]] = []
    for op, sh in GLYPHS.get(kind, GLYPHS["circle"]):
        if groups and groups[-1][0] == op:
            groups[-1][1].append(sh)
        else:
            groups.append((op, [sh]))
    for op, shapes in groups:
        col, a = (fill, alpha * fill_alpha) if op == "fill" else (color, alpha)

        def draw(img, ox, oy, shapes=shapes, op=op):
            for sh in shapes:
                shape(img, ox, oy, sh, fillit=op != "stroke")

        cv.paint(bbox, col, a, draw)
