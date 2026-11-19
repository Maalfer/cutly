#!/usr/bin/env python3
"""
transcribir.py — Transcripción con timestamps por palabra (faster-whisper), con la configuración MEDIDA como la
mejor relación precisión/recursos para este proyecto (ver editor/BENCHMARK-WHISPER.md).

    python transcribir.py VIDEO_O_AUDIO [--modelo large-v3-turbo] [--salida RUTA_SIN_EXTENSION]

Escribe RUTA.json (segmentos + palabras con inicio/fin), RUTA.srt y RUTA.txt (línea N del .txt = segmento N del .srt).
Por defecto la salida va junto al vídeo, como `<nombre>_transcripcion.*`.

Decisiones (todas medidas, no por costumbre):
  - Modelo por defecto `large-v3-turbo`: en CPU tarda la mitad que `large-v3`, usa ~40 % menos RAM y en el audio de
    prueba se equivocó MENOS (WER 1,2 % frente a 2,4 %). `large-v3` queda como SEGUNDA OPINIÓN para un tramo dudoso.
  - `vad_filter=True`: sin él, Whisper inventa "Gracias" / "Gracias por ver el vídeo" en los silencios y se salta
    trozos con voz real (medido: la pasada sin VAD perdió ~30 s de narración). Es la mejora que más importa.
  - `condition_on_previous_text=False`: evita que una alucinación se arrastre al resto del archivo (equivale a -mc 0).
  - El audio se decodifica con ffmpeg y se pasa como array: la decodificación interna de faster-whisper (PyAV)
    falla en algunas instalaciones de Windows ("open() got an unexpected keyword argument 'metadata_errors'").
  - Los timestamps de CUALQUIER modelo fallan entre 50 y 500 ms en algunas palabras: NO cortes directamente con
    ellos. Afina cada corte con la energía del audio a 10 ms y verifica re-transcribiendo el empalme.
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from short_desde_toma import FFMPEG  # noqa: E402  (localiza ffmpeg en Windows/macOS/Linux)


def srt_time(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("entrada")
    ap.add_argument("--modelo", default="large-v3-turbo",
                    help="large-v3-turbo (defecto) | large-v3 (segunda opinión) | otro de faster-whisper")
    ap.add_argument("--salida", help="ruta sin extensión (defecto: junto a la entrada, <nombre>_transcripcion)")
    ap.add_argument("--idioma", default="es")
    ap.add_argument("--dispositivo", default="auto", help="auto | cpu | cuda (CUDA solo con GPU NVIDIA)")
    a = ap.parse_args()

    from faster_whisper import WhisperModel

    base = a.salida or os.path.splitext(a.entrada)[0] + "_transcripcion"
    pcm = subprocess.run([FFMPEG, "-v", "error", "-i", a.entrada, "-vn", "-ac", "1", "-ar", "16000",
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768
    dev = a.dispositivo
    if dev == "auto":
        try:
            import ctranslate2
            dev = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:
            dev = "cpu"
    modelo = WhisperModel(a.modelo, device=dev, compute_type="int8" if dev == "cpu" else "float16")
    segs, _ = modelo.transcribe(audio, language=a.idioma, word_timestamps=True, vad_filter=True,
                                condition_on_previous_text=False, beam_size=5)
    out = []
    for s in segs:
        out.append({"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text.strip(),
                    "words": [[round(w.start, 3), round(w.end, 3), w.word.strip()] for w in s.words]})
        print(f"[{s.start:8.2f}-{s.end:8.2f}] {s.text.strip()}", flush=True)
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump({"modelo": a.modelo, "dispositivo": dev, "segmentos": out}, f, ensure_ascii=False, indent=1)
    with open(base + ".srt", "w", encoding="utf-8") as f:
        for i, s in enumerate(out, 1):
            f.write(f"{i}\n{srt_time(s['start'])} --> {srt_time(s['end'])}\n{s['text']}\n\n")
    with open(base + ".txt", "w", encoding="utf-8") as f:
        f.write("\n".join(s["text"] for s in out) + "\n")
    print(f"escrito: {base}.json / .srt / .txt  (modelo {a.modelo}, {dev})")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
