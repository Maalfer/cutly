#!/usr/bin/env python3
"""
tipear.py — GENERADOR del plan de tecleo de una persona (para vídeos realistas). Lógica pura, sin emisor:
lo ejecuta vm_control.py (type/typeurl) dentro de la VM con xdotool.

  - velocidad media configurable (--wpm), con variación entre pulsaciones;
  - pausa mayor tras espacios, más tras signos (.,;:!?) y más tras salto de línea; pausas de "pensar";
  - mayúsculas/símbolos algo más lentos; errores ocasionales (--typos): tecla vecina, retroceso y corrección.

Plan = lista de eventos ("k",c) ("bs",) ("ret",) ("tab",) ("d",seg). Uso suelto, solo para medir:
    tipear.py "texto" [--wpm 55] [--typos 0.015] [--seed N]
"""
import argparse
import random
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


def duration(events):
    return sum(e[1] for e in events if e[0] == "d")


def main():
    ap = argparse.ArgumentParser(description="Muestra la duración estimada del plan de tecleo.")
    ap.add_argument("text", help='texto, o "-" para leer de stdin')
    ap.add_argument("--wpm", type=float, default=55.0)
    ap.add_argument("--typos", type=float, default=0.015)
    ap.add_argument("--seed", type=int, default=None)
    a = ap.parse_args()
    text = sys.stdin.read().rstrip("\n") if a.text == "-" else a.text
    ev = plan(text, a.wpm, a.typos, random.Random(a.seed))
    n = sum(1 for e in ev if e[0] == "k")
    print(f"{len(text)} caracteres, {n} pulsaciones, duración estimada {duration(ev):.1f}s")


if __name__ == "__main__":
    main()
