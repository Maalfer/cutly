#!/usr/bin/env python3
"""
visibilidad.py — Qué % de cada ventana ve REALMENTE una persona (teniendo en cuenta el z-order).

Es la mejora sobre solapes.py: dos ventanas pueden solaparse mucho y aun así verse bien (la de
delante está completa; la de detrás asoma por una franja). Lo que importa es cuánto se VE de cada
una. Una ventana con visible ≈ 0 % está ENTERRADA y no saldrá en el vídeo.

Entrada (stdin), una ventana por línea, ordenadas de MÁS ARRIBA a MÁS ABAJO (z=0 delante):
    z  app  titulo  x  y  w  h  layer  pid        (salida de winlist.swift, separada por TAB)
o en formato simple, también de delante hacia atrás:
    etiqueta  x  y  w  h                           (5 campos; se asume capa normal)

Solo se evalúan las ventanas de capa 0 (las normales); menú, Dock y cursor se ignoran como
ventanas objetivo, pero el Dock y la barra de menús SÍ tapan lo que hay debajo (se restan).

Opciones:
  --min-visible N   marca como ENTERRADA si se ve menos de N % (def. 15)
  --need "app=PCT"  exige un mínimo de visibilidad para una app concreta (repetible).
                    Ej.:  --need Safari=90 --need Terminal=25   (franja asomando)
  --only "A,B"      juzga SOLO esas apps (las demás siguen tapando pero no cuentan como error).
                    Úsalo así: --only Terminal,TextEdit  (apps de fondo como Warp no dan falso positivo)
  --screen WxH      tamaño de la pantalla en puntos lógicos (def.: se autodetecta con la ventana
                    "Dock" de winlist; sin él no se detecta lo que sobresale de la pantalla)
  --exit-code       devuelve !=0 si alguna ventana está enterrada o no cumple su --need
  --cell N          tamaño de celda de la rejilla en px (def. 4; más pequeño = más exacto)

Cómo se calcula: rasteriza el escritorio en una rejilla y "pinta" las ventanas de atrás hacia
delante; al final cuenta cuántas celdas de cada ventana siguen siendo suyas. Sencillo, robusto y
sin dependencias (solo python3).
"""
import sys

def parse(line):
    p = line.rstrip("\n").split("\t")
    if len(p) >= 9:                      # formato winlist.swift
        try:
            return dict(z=int(p[0]), app=p[1], title=p[2], x=int(p[3]), y=int(p[4]),
                        w=int(p[5]), h=int(p[6]), layer=int(p[7]))
        except ValueError:
            return None
    q = line.replace("\t", " ").split()  # formato simple
    if len(q) >= 5:
        try:
            x, y, w, h = (int(float(v)) for v in q[-4:])
            return dict(z=None, app=" ".join(q[:-4]), title="", x=x, y=y, w=w, h=h, layer=0)
        except ValueError:
            return None
    return None

def main():
    a = sys.argv[1:]
    def opt(name, default=None, cast=str):
        return cast(a[a.index(name) + 1]) if name in a else default
    min_vis = opt("--min-visible", 15.0, float)
    cell = opt("--cell", 4, int)
    exit_code = "--exit-code" in a
    scr = opt("--screen", "")
    only = {x.strip().lower() for x in opt("--only", "").split(",") if x.strip()}
    needs = {}
    for i, v in enumerate(a):
        if v == "--need" and i + 1 < len(a) and "=" in a[i + 1]:
            k, val = a[i + 1].split("=", 1)
            needs[k.lower()] = float(val)

    wins = [w for w in (parse(l) for l in sys.stdin) if w and w["w"] > 0 and w["h"] > 0]
    # z=0 es la de más arriba; en formato simple el orden de entrada ya es de delante a atrás
    for i, w in enumerate(wins):
        if w["z"] is None:
            w["z"] = i

    targets = [w for w in wins if w["layer"] == 0]
    if not targets:
        print("(sin ventanas de capa 0)"); return

    SW = SH = None
    if scr and "x" in scr:
        SW, SH = (int(v) for v in scr.lower().split("x"))
    else:                                    # autodetectar: el "Dock" de winlist ocupa toda la pantalla
        for w in wins:
            if w["app"] == "Dock" and w["w"] * w["h"] > 0:
                SW, SH = w["w"], w["h"]; break
    W = max(max(w["x"] + w["w"] for w in wins), SW or 0)
    H = max(max(w["y"] + w["h"] for w in wins), SH or 0)
    W, H = max(W, 1), max(H, 1)
    cols, rows = W // cell + 1, H // cell + 1
    grid = [[-1] * cols for _ in range(rows)]

    def paint(win, idx):
        x0, y0 = max(0, win["x"] // cell), max(0, win["y"] // cell)
        x1, y1 = min(cols, (win["x"] + win["w"]) // cell + 1), min(rows, (win["y"] + win["h"]) // cell + 1)
        for r in range(y0, y1):
            row = grid[r]
            for c in range(x0, x1):
                row[c] = idx

    # pintar de atrás hacia delante: mayor z primero
    ordered = sorted(targets, key=lambda w: -w["z"])
    for i, w in enumerate(ordered):
        paint(w, i)
    # la barra de menús (capa 24) tapa lo que haya debajo
    for w in wins:
        if w["layer"] == 24:
            paint(w, -2)

    if SW and SH:                            # lo que sobresale de la pantalla no sale en el vídeo
        for r in range(rows):
            for c in range(cols):
                if c * cell >= SW or r * cell >= SH:
                    grid[r][c] = -3
    bad = 0
    print(f"{'z':>3}  {'visible':>8}  {'ventana'}")
    for i, w in enumerate(ordered):
        total = visible = 0
        x0, y0 = max(0, w["x"] // cell), max(0, w["y"] // cell)
        x1, y1 = min(cols, (w["x"] + w["w"]) // cell + 1), min(rows, (w["y"] + w["h"]) // cell + 1)
        for r in range(y0, y1):
            for c in range(x0, x1):
                total += 1
                if grid[r][c] == i:
                    visible += 1
        pct = 100 * visible / total if total else 0
        w["pct"] = pct
    for w in sorted(ordered, key=lambda w: w["z"]):
        pct = w["pct"]
        flag = ""
        need = needs.get(w["app"].lower())
        relevante = (not only) or (w["app"].lower() in only)
        if not relevante:
            flag = "  (fondo, ignorada)"
        elif pct < min_vis and need is None:
            flag = "  <-- ENTERRADA (no saldrá en el vídeo)"; bad += 1
        if relevante and need is not None and pct < need:
            flag = f"  <-- NO CUMPLE: pide >= {need:.0f}%"; bad += 1
        if SW and SH and (w["x"] < 0 or w["y"] < 0 or w["x"] + w["w"] > SW or w["y"] + w["h"] > SH):
            ix = max(0, min(w["x"] + w["w"], SW) - max(w["x"], 0)); iy = max(0, min(w["y"] + w["h"], SH) - max(w["y"], 0))
            fuera = 100 - 100 * ix * iy / (w["w"] * w["h"])
            if fuera > 2 and ("fondo" not in flag) and ((not only) or (w["app"].lower() in only)):
                if "<--" not in flag:
                    bad += 1                  # no contar dos veces la misma ventana
                flag += f"  <-- {fuera:.0f}% FUERA DE PANTALLA (saldrá cortada)"
        print(f"{w['z']:>3}  {pct:7.1f}%  {w['app']} | {w['title'][:40]} [{w['x']},{w['y']} {w['w']}x{w['h']}]{flag}")
    # Overlays: ventanas de capa alta que NO son menú/Dock/cursor (notificaciones, avisos del sistema...)
    # Saldrían en el vídeo aunque no sean "ventanas de app". Hay que cerrarlas o activar No molestar.
    # Lo contenido por completo en la barra de menús (p. ej. el indicador de grabación/privacidad
    # "StatusIndicator" de macOS) no tapa ninguna ventana: no es un overlay a corregir.
    mb = next((w for w in wins if w["layer"] == 24), None)
    def en_barra(w):                       # >= 80 % del elemento dentro de la barra (tolera 1-2 px de borde)
        if not mb:
            return False
        ix = max(0, min(w["x"] + w["w"], mb["x"] + mb["w"]) - max(w["x"], mb["x"]))
        iy = max(0, min(w["y"] + w["h"], mb["y"] + mb["h"]) - max(w["y"], mb["y"]))
        return ix * iy >= 0.8 * w["w"] * w["h"]
    ov = [w for w in wins if w["layer"] not in (0, 24) and w["app"] != "Dock"
          and w["title"] not in ("Cursor", "Menubar") and w["w"] * w["h"] > 0 and not en_barra(w)]
    for w in ov:
        print(f"  OVERLAY capa {w['layer']}: {w['app']} | {w['title'][:30]} [{w['x']},{w['y']} {w['w']}x{w['h']}]  <-- saldrá en el vídeo")
        bad += 1
    print(f"-- {len(targets)} ventanas, {bad} con problema (umbral enterrada < {min_vis:.0f}%)")
    if exit_code and bad:
        sys.exit(1)

if __name__ == "__main__":
    main()
