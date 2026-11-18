#!/usr/bin/env python3
"""
ocr_buscar.py — Dado el resultado de `ocr --words` (por stdin), devuelve el centro en PUNTOS
LÓGICOS de la palabra buscada, listo para `cliclick`.

Uso:  ocr --words captura.png | python3 ocr_buscar.py <palabra> [n-ésima=1] [escala=2] [x,y,w,h]

- Ignora mayúsculas, tildes y signos de puntuación ("Sesión:" == "sesion").
- n-ésima: si la palabra aparece varias veces, cuál (1 = la primera, de arriba abajo).
- escala: factor físico/lógico (Retina = 2). Calcúlalo, no lo supongas (ver screen_scale()).
- x,y,w,h (opcional, PUNTOS LÓGICOS): busca SOLO dentro de esa región (p. ej. la ventana de una app).
  Sin región se busca en toda la pantalla y se toma la primera coincidencia de arriba abajo, que puede
  estar en OTRA ventana si el texto se repite (error real detectado: el clic fue al texto de otra app).
- Salida: "x,y" (punto lógico). Código 1 si no se encuentra.

Es un fichero aparte (y no un heredoc dentro de un pipe) a propósito: un `python3 - <<EOF` que
además recibe datos por pipe lee los datos como si fueran el programa. Error real detectado.
"""
import re
import sys
import unicodedata


def norm(s):
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^\w]", "", s)


def main():
    if len(sys.argv) < 2:
        sys.exit("uso: ocr --words img | ocr_buscar.py <palabra> [n] [escala]")
    target = norm(sys.argv[1])
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    scale = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
    reg = None
    if len(sys.argv) > 4 and sys.argv[4]:
        reg = tuple(float(v) for v in sys.argv[4].split(","))
    k = 0
    for ln in sys.stdin:
        m = re.match(r"^(.*)\t\[(\d+),(\d+) (\d+)x(\d+)\]", ln.rstrip("\n"))
        if not m:
            continue
        if norm(m.group(1)) == target:
            x, y, w, h = map(int, m.groups()[1:])
            cx, cy = (x + w / 2) / scale, (y + h / 2) / scale
            if reg and not (reg[0] <= cx <= reg[0] + reg[2] and reg[1] <= cy <= reg[1] + reg[3]):
                continue
            k += 1
            if k == n:
                print(f"{cx:.0f},{cy:.0f}")
                return
    sys.exit(1)


if __name__ == "__main__":
    main()
