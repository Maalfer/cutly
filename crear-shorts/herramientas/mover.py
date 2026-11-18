#!/usr/bin/env python3
"""
mover.py — Mueve el cursor como una persona: trayecto ligeramente curvo, arranca y frena suave,
y la duración crece con la distancia. En vídeo, un cursor que "salta" al botón queda artificial.

Uso:  mover.py X Y [--dur SEG] [--seed N] [--dry-run]
      (X, Y en puntos lógicos, como cliclick)

Cómo: calcula una curva de Bézier cuadrática desde la posición actual hasta el destino, con el
punto de control desplazado en perpendicular (curvatura aleatoria pequeña). Reparte los puntos con
una función "smoothstep" (lento-rápido-lento) y los envía con `teclear` (Swift; eventos de ratón
directos). Alternativa lenta: `cliclick`, que tarda ~100 ms POR movimiento (medido) y no sirve para
trazar un trayecto largo. Termina EXACTAMENTE en el destino.

Backend macOS: `teclear` (Swift). Windows/Linux: mismo cálculo de puntos, otro emisor (xdotool/AHK).
"""
import argparse
import math
import os
import random
import re
import shutil
import subprocess
import sys


def posicion_actual():
    out = subprocess.run(["cliclick", "p:."], capture_output=True, text=True).stdout
    m = re.search(r"(-?\d+)\s*,\s*(-?\d+)", out)
    if not m:
        sys.exit("no pude leer la posición del cursor (¿cliclick instalado y con permiso?)")
    return int(m.group(1)), int(m.group(2))


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
    ap = argparse.ArgumentParser()
    ap.add_argument("x", type=int)
    ap.add_argument("y", type=int)
    ap.add_argument("--dur", type=float, default=None, help="duración en segundos (def.: según distancia)")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    x0, y0 = posicion_actual()
    pts = trayecto(x0, y0, a.x, a.y, a.dur, random.Random(a.seed))
    if a.dry_run:
        print(f"{len(pts)} puntos de ({x0},{y0}) a ({a.x},{a.y})"); return
    kit = os.environ.get("CTRL_KIT", os.path.expanduser("~/Desktop/ctrl-kit"))
    tk = os.path.join(kit, "teclear")
    tk = tk if os.access(tk, os.X_OK) else shutil.which("teclear")
    if tk:
        plan = "".join(f"m {x} {y}\nd 0.022\n" for x, y in pts)
        r = subprocess.run([tk], input=plan, text=True, capture_output=True)
    else:
        print("AVISO: sin `teclear` el movimiento irá a ~100 ms por punto (muy lento). Compílalo.", file=sys.stderr)
        r = subprocess.run(["cliclick"] + [f"m:{x},{y}" for x, y in pts], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"el emisor falló: {r.stderr.strip()}")


if __name__ == "__main__":
    main()
