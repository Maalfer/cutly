"""Localiza ffmpeg/ffprobe del ANFITRIÓN en Windows, macOS y Linux.

    from nucleo.ffmpeg import FFMPEG, FFPROBE      # se resuelven al usarlos; si faltan, sale con instrucciones
    from nucleo.ffmpeg import localizar            # None si no está (para quien puede funcionar sin él)

En Windows (winget) el PATH no se refresca en terminales ya abiertas: se busca también en la carpeta de winget.
"""
import glob
import os
import shutil
import sys


def localizar(nombre):
    c = shutil.which(nombre)
    if c:
        return c
    for g in glob.glob(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages",
                                    "Gyan.FFmpeg*", "ffmpeg-*", "bin", nombre + ".exe")):
        return g
    return None


def requerir(nombre):
    c = localizar(nombre)
    if not c:
        sys.exit(f"falta {nombre} (Windows: winget install Gyan.FFmpeg; macOS: brew install ffmpeg; "
                 f"Linux: apt install ffmpeg; ver PORTABILIDAD.md)")
    return c


def __getattr__(nombre):  # PEP 562: FFMPEG / FFPROBE se buscan solo cuando alguien los importa
    if nombre in ("FFMPEG", "FFPROBE"):
        valor = requerir(nombre.lower())
        globals()[nombre] = valor
        return valor
    raise AttributeError(nombre)
