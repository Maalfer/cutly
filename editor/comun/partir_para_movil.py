#!/usr/bin/env python3
"""
partir_para_movil.py — Parte un vídeo en trozos que quepan en el chat de Claude (Remote Control desde el móvil:
máximo 30 MiB por archivo) SIN recodificar: los mismos datos de imagen y sonido, misma calidad que el original.

    python editor/comun/partir_para_movil.py VIDEO.mp4 [--max-mib 29] [--salida CARPETA]

El usuario lo pidió así (2026-11-20): una copia comprimida NO le vale, quiere el original. Si el vídeo ya cabe, se
copia tal cual. Los cortes caen en fotogramas clave (cada ~4 s en los Shorts), así que cada trozo mide un poco más o
menos que la división exacta; se comprueba que ninguno pase del límite. Entre trozos se nota un pequeño salto: avísale
de que en el vídeo de verdad no existe. Imprime las rutas para mandarlas con SendUserFile.
"""
import argparse
import math
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
from nucleo import medios  # noqa: E402
from nucleo.ffmpeg import FFMPEG  # noqa: E402

MIB = 1024 * 1024


def partir(video, max_mib, salida):
    os.makedirs(salida, exist_ok=True)
    base = os.path.splitext(os.path.basename(video))[0]
    tam = os.path.getsize(video)
    if tam <= max_mib * MIB:
        destino = os.path.join(salida, os.path.basename(video))
        shutil.copyfile(video, destino)
        return [destino]
    dur = medios.duracion(video)
    for n in range(math.ceil(tam / (max_mib * MIB)), 20):
        for viejo in os.listdir(salida):
            if viejo.startswith(base + "_parte"):
                os.remove(os.path.join(salida, viejo))
        patron = os.path.join(salida, f"{base}_parte%d.mp4")
        subprocess.run([FFMPEG, "-v", "error", "-y", "-i", video, "-map", "0", "-c", "copy", "-f", "segment",
                        "-segment_time", f"{dur / n:.3f}", "-reset_timestamps", "1",
                        "-segment_format_options", "movflags=+faststart", patron], check=True)
        partes = sorted((os.path.join(salida, f) for f in os.listdir(salida) if f.startswith(base + "_parte")),
                        key=lambda p: int(p.rsplit("_parte", 1)[1].split(".")[0]))
        if all(os.path.getsize(p) <= max_mib * MIB for p in partes):
            return partes
    sys.exit("no se ha podido partir por debajo del límite")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("video")
    ap.add_argument("--max-mib", type=float, default=29.0, help="tamaño máximo por trozo (el chat admite 30 MiB)")
    ap.add_argument("--salida", default=os.path.join(tempfile.gettempdir(), "cutly-movil"))
    a = ap.parse_args()
    for p in partir(a.video, a.max_mib, a.salida):
        print(f"{p}  {os.path.getsize(p) / MIB:.1f} MiB  {medios.duracion(p):.2f} s")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
