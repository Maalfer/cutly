#!/usr/bin/env python3
"""
normalizar_audio.py — Normaliza el audio de un clip 16:9 ya construido a -14 LUFS (techo -1 dBTP), en DOS
pasadas (medir -> aplicar con los valores medidos, `linear=true`) según editor/directos/CLAUDE.md §5.1. El
vídeo NUNCA se toca (-c:v copy): esto es solo un cambio de volumen, no de contenido ni de encuadre.

Por qué es un paso OBLIGATORIO del flujo, no opcional: auditoría del 2026-11-20 sobre un clip construido con el
pipeline ANTES de que existiera este paso (video-mio.mp4, fuera del repo, solo de referencia) midió
-25,6 LUFS — 11,6 LU por debajo del objetivo, sin que nadie lo hubiera "bajado a mano": el audio sale
sistemáticamente bajo si este paso no se aplica. No es una preferencia estética, es corregir un defecto medido.

Uso:
    python editor/directos/normalizar_audio.py <clip.mp4> [<clip_salida.mp4>] [-a ABITRATE] [-i OBJETIVO_LUFS] [-t TECHO_DBTP]

Si no se da <clip_salida.mp4>, normaliza EN EL SITIO (sobrescribe la entrada) -- el uso habitual, justo después
de construir_clip.sh (y de aplicar_zoom.py si toca), antes de la verificación final de la sección 8.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
from nucleo import cortes  # noqa: E402
from nucleo.ffmpeg import FFMPEG, requerir, salida_atomica  # noqa: E402

OBJETIVO_I = -14.0
TECHO_TP = -1.0
ABITRATE = "192k"


def medir(path, objetivo_i, techo_tp):
    """Primera pasada de loudnorm (solo análisis, -f null): devuelve sus estadísticas JSON."""
    r = subprocess.run([requerir("ffmpeg"), "-i", path, "-af",
                        f"loudnorm=I={objetivo_i}:TP={techo_tp}:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.search(r"\{[^{}]*\}", r.stderr, re.S)
    if not m:
        sys.exit("no se pudo medir loudnorm (primera pasada):\n" + r.stderr[-1500:])
    return json.loads(m.group(0))


def construir(entrada, salida, abitrate, objetivo_i, techo_tp):
    stats = medir(entrada, objetivo_i, techo_tp)
    filtro = (f"loudnorm=I={objetivo_i}:TP={techo_tp}:"
              f"measured_I={stats['input_i']}:measured_TP={stats['input_tp']}:"
              f"measured_LRA={stats['input_lra']}:measured_thresh={stats['input_thresh']}:"
              f"offset={stats['target_offset']}:linear=true")
    cmd = [FFMPEG, "-v", "error", "-y", "-i", entrada, "-c:v", "copy", "-af", filtro,
           "-ar", "48000", "-c:a", "aac", "-b:a", abitrate]
    r = salida_atomica(cmd, salida, capture_output=True, text=True)
    if r.returncode:
        sys.exit("ffmpeg falló:\n" + r.stderr[-1500:])
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entrada")
    ap.add_argument("salida", nargs="?", help="por defecto, normaliza en el sitio (sobrescribe la entrada)")
    ap.add_argument("-a", "--abitrate", default=ABITRATE, help=f"bitrate de audio de salida (defecto {ABITRATE})")
    ap.add_argument("-i", "--objetivo", type=float, default=OBJETIVO_I, metavar="LUFS", help=f"defecto {OBJETIVO_I}")
    ap.add_argument("-t", "--techo", type=float, default=TECHO_TP, metavar="DBTP", help=f"defecto {TECHO_TP}")
    ap.add_argument("--titulo", help="para la entrada del _cortes.log (por defecto, el nombre del archivo)")
    a = ap.parse_args()

    if not os.path.exists(a.entrada):
        sys.exit(f"no existe {a.entrada}")
    salida = a.salida or a.entrada

    stats = construir(a.entrada, salida, a.abitrate, a.objetivo, a.techo)
    despues = medir(salida, a.objetivo, a.techo)

    antes_i, despues_i = float(stats["input_i"]), float(despues["input_i"])
    print(f"audio normalizado: {salida}")
    print(f"LUFS: {antes_i:.1f} -> {despues_i:.1f} (objetivo {a.objetivo:.1f} +/-1)")
    ok = abs(despues_i - a.objetivo) <= 1.0
    print("OK" if ok else "REVISAR: fuera de +/-1 LU del objetivo")

    titulo = a.titulo or os.path.splitext(os.path.basename(salida))[0]
    cortes.anotar(f"\n[{datetime.now():%Y-%m-%d %H:%M}] {os.path.basename(salida)}  "
                  f"(audio normalizado: {antes_i:.1f} -> {despues_i:.1f} LUFS, objetivo {a.objetivo:.1f})\n")

    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
