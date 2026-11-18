#!/usr/bin/env python3
"""
ocr_buscar.py — Dado el resultado de `ocr --words` (por stdin), devuelve el centro en PUNTOS
LÓGICOS de la palabra buscada, listo para `cliclick`.

Uso:  ocr --words captura.png | python3 ocr_buscar.py <palabra> [n-ésima=1] [escala=2] [x,y,w,h] [subcadena]

- Ignora mayúsculas, tildes y signos de puntuación ("Sesión:" == "sesion").
- n-ésima: si la palabra aparece varias veces, cuál (1 = la primera, de arriba abajo).
- escala: factor físico/lógico (Retina = 2). Calcúlalo, no lo supongas (ver screen_scale()).
- x,y,w,h (opcional, PUNTOS LÓGICOS): busca SOLO dentro de esa región (p. ej. la ventana de una app).
  Sin región se busca en toda la pantalla y se toma la primera coincidencia de arriba abajo, que puede
  estar en OTRA ventana si el texto se repite (error real detectado: el clic fue al texto de otra app).
- subcadena (opcional): apunta a un TROZO dentro de la palabra (p. ej. el valor "1001" en
  "/cuenta?id=1001"). Se calcula por proporción de caracteres: exacto en fuentes MONOESPACIADAS
  (editores, terminales, Burp); aproximado en fuentes proporcionales. Sin ella se apunta al centro,
  que en una palabra larga cae en medio y NO en el trozo que buscas (error real medido).
- Coincidencia: primero EXACTA; si no hay ninguna, por CONTENIDO ("id=1001" dentro de "/cuenta?id=1001").
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


def buscar(lineas, target, n, scale, reg, sub, modo):
    k = 0
    for ln in lineas:
        m = re.match(r"^(.*)\t\[(\d+),(\d+) (\d+)x(\d+)\]", ln.rstrip("\n"))
        if not m:
            continue
        tok = m.group(1)
        nt = norm(tok)
        ok = (nt == target) if modo == "exacta" else (len(target) >= 3 and target in nt)
        if not ok:
            continue
        x, y, w, h = map(int, m.groups()[1:])
        frac = 0.5
        if sub and tok:
            i = tok.lower().find(sub.lower())
            if i >= 0:
                frac = (i + len(sub) / 2) / len(tok)
        cx, cy = (x + w * frac) / scale, (y + h / 2) / scale
        if reg and not (reg[0] <= cx <= reg[0] + reg[2] and reg[1] <= cy <= reg[1] + reg[3]):
            continue
        k += 1
        if k == n:
            return f"{cx:.0f},{cy:.0f}"
    return None


def main():
    if len(sys.argv) < 2:
        sys.exit("uso: ocr --words img | ocr_buscar.py <palabra> [n] [escala] [x,y,w,h] [subcadena]")
    target = norm(sys.argv[1])
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    scale = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
    reg = tuple(float(v) for v in sys.argv[4].split(",")) if len(sys.argv) > 4 and sys.argv[4] else None
    sub = sys.argv[5] if len(sys.argv) > 5 else ""
    lineas = sys.stdin.readlines()
    for modo in ("exacta", "contiene"):
        r = buscar(lineas, target, n, scale, reg, sub, modo)
        if r:
            print(r)
            return
    sys.exit(1)


if __name__ == "__main__":
    main()
