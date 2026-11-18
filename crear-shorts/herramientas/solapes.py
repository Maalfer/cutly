#!/usr/bin/env python3
"""
solapes.py — Detector de ventanas superpuestas (multiplataforma).

Lee por stdin la lista de ventanas visibles (una por línea) y avisa de cuáles se
SOLAPAN, para garantizar que ninguna quede tapando a otra y estropee el vídeo.
La matemática (intersección de rectángulos) es universal; solo cambia el comando
que ENUMERA las ventanas en cada SO (ver abajo y PORTABILIDAD.md §2).

Formato de cada línea (separado por TAB o por varios espacios):
    <etiqueta> <x> <y> <w> <h>                 (5 campos)
    <app> <titulo> <x> <y> <w> <h>             (6+ campos: los 4 ÚLTIMOS son x y w h)

Cómo alimentarlo según el sistema:
  macOS   : osascript enum... | python3 solapes.py        (ver 03-gestion-ventanas.md)
  Linux X11: wmctrl -lG | awk '{print $8"\\t"$3"\\t"$4"\\t"$5"\\t"$6}' | python3 solapes.py
  Windows : PowerShell (EnumWindows+GetWindowRect) -> "titulo\\tx\\ty\\tw\\th" | python3 solapes.py

Opciones:
  --min-pct N   umbral de solape para avisar, en % del área de la ventana más pequeña (def. 5)
  --exit-code   devuelve código !=0 si hay algún solape (útil como "gate" antes de grabar)

Salida: lista de pares solapados con su % y un resumen. Pensado para usarse como verificación
obligatoria ANTES de cada toma (ver 03-gestion-ventanas.md, "Gate anti-solape").
"""
import sys

def parse(line):
    parts = line.replace("\t", " ").split()
    if len(parts) < 5:
        return None
    try:
        x, y, w, h = (int(float(v)) for v in parts[-4:])
    except ValueError:
        return None
    label = " ".join(parts[:-4]) or "?"
    return (label, x, y, w, h)

def overlap_area(a, b):
    _, ax, ay, aw, ah = a
    _, bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    return ix * iy

def main():
    min_pct = 5.0
    exit_code = False
    args = sys.argv[1:]
    if "--min-pct" in args:
        min_pct = float(args[args.index("--min-pct") + 1])
    if "--exit-code" in args:
        exit_code = True

    wins = []
    for ln in sys.stdin:
        r = parse(ln.rstrip("\n"))
        if r and r[3] > 0 and r[4] > 0:
            wins.append(r)

    found = 0
    for i in range(len(wins)):
        for j in range(i + 1, len(wins)):
            a, b = wins[i], wins[j]
            area = overlap_area(a, b)
            if area <= 0:
                continue
            amin = min(a[3] * a[4], b[3] * b[4])
            pct = 100 * area / amin if amin else 0
            if pct >= min_pct:
                found += 1
                print(f"SOLAPE {pct:5.1f}%  [{a[0]}]  x  [{b[0]}]")
    print(f"-- {len(wins)} ventanas, {found} solapamientos (umbral {min_pct:.0f}%)")
    if found:
        print("   -> REUBICA/OCULTA ventanas y vuelve a comprobar ANTES de grabar.")
    if exit_code and found:
        sys.exit(1)

if __name__ == "__main__":
    main()
