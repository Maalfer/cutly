#!/usr/bin/env python3
"""
energia.py — Energía del audio cada 10 ms entre T0 y T1, para afinar un corte entre palabras (cualquier línea:
Short, fusión o directo). Lógica: nucleo/audio.py.

    python editor/comun/energia.py VIDEO_O_AUDIO T0 T1

Imprime el nivel (rms) y la energía de alta frecuencia (hf) en dB. Corta en el valle entre palabras. Una sibilante
final ("pass") tiene rms bajo pero hf alto: la palabra acaba donde cae el hf, no donde cae el rms (error real: cortar
por el rms se comió la "s"). Evita cortar dentro de un chasquido o una respiración.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
from nucleo import audio, medios  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Energía del audio cada 10 ms (rms y alta frecuencia) entre T0 y T1.")
    ap.add_argument("video")
    ap.add_argument("t0", type=float)
    ap.add_argument("t1", type=float)
    a = ap.parse_args()
    rms, hf = audio.energia(medios.audio_mono(a.video))     # cada 10 ms
    for i in range(int(a.t0 * 100), min(int(a.t1 * 100), len(rms))):
        barra = "#" * max(0, int(rms[i] + 70) // 2)
        print(f"{i / 100:8.2f}  rms {rms[i]:5.0f}  hf {hf[i]:5.0f}  {barra}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
