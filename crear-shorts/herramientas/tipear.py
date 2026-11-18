#!/usr/bin/env python3
"""
tipear.py — Teclea texto como lo haría una persona (para grabar vídeos realistas).

En un vídeo, el texto que aparece de golpe se ve artificial. Este script escribe carácter a
carácter con un ritmo humano:
  - velocidad media configurable (--wpm), con variación aleatoria entre pulsaciones;
  - pausa algo mayor tras espacios, más tras signos (.,;:!?) y más tras salto de línea;
  - pequeñas pausas de "pensar" cada pocas palabras;
  - letras repetidas más rápidas, mayúsculas/símbolos algo más lentos;
  - errores ocasionales (--typos): pulsa una tecla vecina, "se da cuenta", retrocede y corrige.

Uso:
    tipear.py "texto a escribir" [--wpm 55] [--typos 0.015] [--seed N] [--dry-run]
    echo "texto" | tipear.py - --wpm 40

Importante: escribe en la app que tenga el FOCO. Antes comprueba el foco (usa `type_human`
de mac-control.sh, que se niega a teclear si el foco no es el esperado).

Backend (macOS): preferido `teclear` (Swift, eventos Unicode: funcionan á é ú ü ñ ¿ € con cualquier
distribución de teclado). Alternativa: AppleScript `keystroke`, que PIERDE las tildes (á -> a) con
teclado Spanish-ISO: solo se usa si no existe `teclear`, y avisa. El PLAN de pulsaciones y retardos (plan()) es
independiente del sistema; para Windows/Linux basta otro "emisor" (xdotool key / SendKeys / AHK)
que recorra el mismo plan — ver PORTABILIDAD.md.

Opciones:
  --wpm N       palabras por minuto de referencia (def. 55; más bajo = más pausado y legible)
  --typos P     probabilidad de error por letra (def. 0.015; 0 = sin errores)
  --seed N      semilla: misma entrada + misma semilla = mismo ritmo (reproducible)
  --dry-run     no teclea; imprime el plan y la duración estimada
"""
import argparse
import os
import random
import shutil
import subprocess
import sys

# Vecinas en un teclado QWERTY (para simular un error "de dedo")
_ROWS = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]
NEIGH = {}
for r, row in enumerate(_ROWS):
    for i, ch in enumerate(row):
        n = []
        if i > 0:
            n.append(row[i - 1])
        if i < len(row) - 1:
            n.append(row[i + 1])
        NEIGH[ch] = n

PUNCT = set(".,;:!?")
SLOWER = set("0123456789@#$%&*()[]{}<>|\\/~^_=+-\"'`")


def plan(text, wpm=55.0, typos=0.015, rng=None):
    """Devuelve una lista de eventos: ("k", c) tecla, ("bs",) retroceso, ("ret",), ("tab",), ("d", s) espera."""
    rng = rng or random.Random()
    base = 60.0 / (max(wpm, 5.0) * 5.0)        # segundos por carácter (1 palabra = 5 caracteres)
    ev = []
    words_since_think = 0
    next_think = rng.randint(6, 14)
    prev = ""

    def jitter():
        return min(2.6, max(0.35, rng.lognormvariate(0.0, 0.33)))

    for ch in text:
        if ch == "\n":
            ev += [("d", base * 2.5 * jitter()), ("ret",)]
            prev = ch
            continue
        if ch == "\t":
            ev += [("d", base * jitter()), ("tab",)]
            prev = ch
            continue

        d = base * jitter()
        if ch == " ":
            d *= 1.25
            words_since_think += 1
            if words_since_think >= next_think:       # pausa de "pensar"
                d += rng.uniform(0.25, 0.8)
                words_since_think = 0
                next_think = rng.randint(6, 14)
        elif ch in SLOWER:
            d *= 1.3
        elif ch.isupper():
            d *= 1.15
        if prev in PUNCT:
            d *= 1.9
        if ch == prev and ch.isalpha():
            d *= 0.8                                   # letra repetida: más rápida
        ev.append(("d", d))

        low = ch.lower()
        if typos > 0 and ch.isalpha() and low in NEIGH and rng.random() < typos:
            wrong = rng.choice(NEIGH[low])
            wrong = wrong.upper() if ch.isupper() else wrong
            ev += [("k", wrong), ("d", rng.uniform(0.18, 0.55)), ("bs",), ("d", rng.uniform(0.08, 0.22))]
        ev.append(("k", ch))
        prev = ch
    return ev


def _as_quote(c):
    return '"' + c.replace("\\", "\\\\").replace('"', '\\"') + '"'


def to_applescript(events):
    """Un solo osascript con todos los retardos: más preciso que lanzar un proceso por tecla."""
    L = ['tell application "System Events"']
    for e in events:
        if e[0] == "k":
            L.append(f"keystroke {_as_quote(e[1])}")
        elif e[0] == "bs":
            L.append("key code 51")
        elif e[0] == "ret":
            L.append("key code 36")
        elif e[0] == "tab":
            L.append("key code 48")
        elif e[0] == "d":
            L.append(f"delay {e[1]:.3f}")
    L.append("end tell")
    return "\n".join(L) + "\n"


def to_teclear(events):
    """Protocolo de `teclear`: k <HEX> | bs | ret | tab | d <seg>"""
    L = []
    for e in events:
        if e[0] == "k":
            L.append(f"k {ord(e[1]):X}")
        elif e[0] in ("bs", "ret", "tab"):
            L.append(e[0])
        elif e[0] == "d":
            L.append(f"d {e[1]:.3f}")
    return "\n".join(L) + "\n"


def find_teclear():
    kit = os.environ.get("CTRL_KIT", os.path.expanduser("~/Desktop/ctrl-kit"))
    p = os.path.join(kit, "teclear")
    return p if os.access(p, os.X_OK) else shutil.which("teclear")


def duration(events):
    return sum(e[1] for e in events if e[0] == "d")


def main():
    ap = argparse.ArgumentParser(description="Teclea como una persona.")
    ap.add_argument("text", help='texto, o "-" para leer de stdin')
    ap.add_argument("--wpm", type=float, default=55.0)
    ap.add_argument("--typos", type=float, default=0.015)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    text = sys.stdin.read() if a.text == "-" else a.text
    text = text.rstrip("\n") if a.text == "-" else text
    ev = plan(text, a.wpm, a.typos, random.Random(a.seed))
    if a.dry_run:
        n = sum(1 for e in ev if e[0] == "k")
        print(f"{len(text)} caracteres, {n} pulsaciones, duración estimada {duration(ev):.1f}s "
              f"({len(text)/max(duration(ev),0.01):.1f} car/s)")
        return
    tk = find_teclear()
    if tk:
        r = subprocess.run([tk], input=to_teclear(ev), text=True, capture_output=True)
    else:
        if any(ord(c) > 127 and c not in "ñÑ¿¡" for c in text):
            print("AVISO: sin `teclear`, las vocales con tilde saldrán sin tilde (á->a). "
                  "Compila teclear.swift (ver cabecera).", file=sys.stderr)
        r = subprocess.run(["osascript", "-"], input=to_applescript(ev), text=True, capture_output=True)
    if r.returncode:
        sys.exit(f"el emisor falló: {r.stderr.strip()}")


if __name__ == "__main__":
    main()
