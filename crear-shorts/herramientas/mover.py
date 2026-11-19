#!/usr/bin/env python3
"""
mover.py — GENERADOR del trayecto de un ratón humano: curva de Bézier ligeramente curva, lento-rápido-lento,
microtemblor y llegada exacta. La duración crece con la distancia. Un cursor que salta al botón delata a la máquina.

Es lógica pura (sin emisor): lo ejecuta vm_control.py (move) dentro de la VM con xdotool, como parte de una línea de
tiempo sin deriva. Uso suelto, solo para inspeccionar:  mover.py X0 Y0 X Y [--dur S] [--seed N]
"""
import argparse
import math
import random
import sys


def trayecto(x0, y0, x1, y1, dur=None, rng=None):
    rng = rng or random.Random()
    dist = math.hypot(x1 - x0, y1 - y0)
    if dist < 2:
        # El cursor YA está en el destino. Un clic sin ningún movimiento previo se pierde o se malinterpreta
        # (medido en Burp/Java: un doble clic en el MISMO píxel que el anterior seleccionaba "nada"; fallaba
        # 3 de 8 veces) y además una persona no clica dos veces en el píxel exacto sin mover la mano.
        # Pequeño desvío de 4-9 px y vuelta, con movimientos reales de ratón.
        dx, dy = rng.choice([-1, 1]) * rng.randint(4, 9), rng.choice([-1, 1]) * rng.randint(3, 7)
        pts = [(round(x1 + dx * f), round(y1 + dy * f)) for f in (0.25, 0.6, 1.0, 0.7, 0.35, 0.1)]
        return pts + [(x1, y1)]
    dur = dur if dur else min(1.6, 0.35 + dist / 1100.0 * rng.uniform(0.8, 1.2))
    n = max(8, int(dur / 0.03))
    # punto de control: a mitad de camino, desplazado en perpendicular (curvatura 4-12 % de la distancia)
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    nx, ny = -(y1 - y0) / dist, (x1 - x0) / dist
    off = dist * rng.uniform(0.04, 0.12) * rng.choice([-1, 1])
    cx, cy = mx + nx * off, my + ny * off
    pts = []
    for i in range(1, n + 1):
        t = i / n
        s = t * t * (3 - 2 * t)                       # smoothstep: lento-rápido-lento
        bx = (1 - s) ** 2 * x0 + 2 * (1 - s) * s * cx + s * s * x1
        by = (1 - s) ** 2 * y0 + 2 * (1 - s) * s * cy + s * s * y1
        if i < n:                                     # microtemblor, nunca en el último punto
            bx += rng.uniform(-0.6, 0.6)
            by += rng.uniform(-0.6, 0.6)
        pts.append((round(bx), round(by)))
    pts[-1] = (x1, y1)                                # llegada exacta
    return pts


def main():
    ap = argparse.ArgumentParser(description="Genera (no ejecuta) un trayecto humano de ratón. El emisor es vm_control.py.")
    ap.add_argument("x0", type=int); ap.add_argument("y0", type=int)
    ap.add_argument("x", type=int); ap.add_argument("y", type=int)
    ap.add_argument("--dur", type=float, default=None)
    ap.add_argument("--seed", type=int, default=None)
    a = ap.parse_args()
    pts = trayecto(a.x0, a.y0, a.x, a.y, a.dur, random.Random(a.seed))
    print(f"{len(pts)} puntos de ({a.x0},{a.y0}) a ({a.x},{a.y})")
    for p in pts:
        print(*p)


if __name__ == "__main__":
    main()
