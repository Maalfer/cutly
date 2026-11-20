#!/usr/bin/env python3
"""
transcribir.py — Transcripción con timestamps por palabra (faster-whisper, large-v3-turbo + VAD). Lógica y decisiones
medidas: nucleo/transcripcion.py y editor/comun/BENCHMARK-WHISPER.md.

    python editor/comun/transcribir.py VIDEO_O_AUDIO [--modelo large-v3-turbo] [--salida RUTA_SIN_EXTENSION]
                                       [--subtitulos] [--dispositivo auto|cpu|cuda]

Escribe RUTA.json (segmentos + palabras con inicio/fin), RUTA.srt y RUTA.txt (línea N del .txt = segmento N del .srt).
Por defecto la salida va junto al vídeo, como `<nombre>_transcripcion.*`.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
from nucleo import medios, transcripcion  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("entrada")
    ap.add_argument("--modelo", default=transcripcion.MODELO_DEFECTO,
                    help="large-v3-turbo (defecto) | large-v3 (segunda opinión) | otro de faster-whisper")
    ap.add_argument("--salida", help="ruta sin extensión (defecto: junto a la entrada, <nombre>_transcripcion)")
    ap.add_argument("--idioma", default="es")
    ap.add_argument("--dispositivo", default="auto", help="auto | cpu | cuda (CUDA solo con GPU NVIDIA)")
    ap.add_argument("--subtitulos", action="store_true",
                    help="modo SUBTÍTULOS, solo para el Short FINAL (sin silencios): texto de contexto puntuado con el "
                         "vocabulario del glosario + contexto encadenado entre ventanas -> texto con puntos, comas y "
                         "mayúsculas correctas. NO lo uses en grabaciones con silencios largos: encadenar contexto es lo "
                         "que provoca alucinaciones en silencios.")
    a = ap.parse_args()

    base = a.salida or transcripcion.ruta_por_defecto(a.entrada)
    segs, dev = transcripcion.transcribir(
        medios.audio_mono(a.entrada), a.modelo, a.idioma, a.dispositivo, a.subtitulos,
        al_segmento=lambda s: print(f"[{s['start']:8.2f}-{s['end']:8.2f}] {s['text']}", flush=True))
    transcripcion.escribir(base, segs, a.modelo, dev, a.subtitulos)
    print(f"escrito: {base}.json / .srt / .txt  (modelo {a.modelo}, {dev})")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
