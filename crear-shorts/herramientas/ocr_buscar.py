#!/usr/bin/env python3
"""
ocr_buscar.py — Dado el resultado de `ocr --words` (por stdin), devuelve el centro en PUNTOS
LÓGICOS de la palabra buscada, listo para `cliclick`.

Uso:  ocr --words captura.png | python3 ocr_buscar.py <palabra> [n-ésima=1] [escala=2]

- Ignora mayúsculas, tildes y signos de puntuación ("Sesión:" == "sesion").
- n-ésima: si la palabra aparece varias veces, cuál (1 = la primera, de arriba abajo).
- escala: factor físico/lógico (Retina = 2). Calcúlalo, no lo supongas (ver screen_scale()).
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
    k = 0
    for ln in sys.stdin:
        m = re.match(r"^(.*)\t\[(\d+),(\d+) (\d+)x(\d+)\]", ln.rstrip("\n"))
        if not m:
            continue
        if norm(m.group(1)) == target:
            k += 1
            if k == n:
                x, y, w, h = map(int, m.groups()[1:])
                print(f"{(x + w / 2) / scale:.0f},{(y + h / 2) / scale:.0f}")
                return
    sys.exit(1)


if __name__ == "__main__":
    main()
