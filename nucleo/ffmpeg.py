"""Localiza ffmpeg/ffprobe del ANFITRIÓN en Windows, macOS y Linux.

    from nucleo.ffmpeg import FFMPEG, FFPROBE      # se resuelven al usarlos; si faltan, sale con instrucciones
    from nucleo.ffmpeg import localizar            # None si no está (para quien puede funcionar sin él)
    from nucleo.ffmpeg import salida_atomica       # escribe el VÍDEO FINAL sin dejarlo roto a medias

En Windows (winget) el PATH no se refresca en terminales ya abiertas: se busca también en la carpeta de winget.
"""
import glob
import os
import shutil
import subprocess
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


def salida_atomica(cmd, destino, check=False, **kw):
    """Corre `cmd` (una orden de ffmpeg SIN el fichero de salida al final: se le añade uno propio) y solo si
    termina bien deja el resultado en `destino` (os.replace, instantáneo). Si el proceso se corta a medias
    (memoria, Ctrl+C, la VM, lo que sea) nunca queda un .mp4 roto con el nombre bueno — el vídeo entregable
    o está completo o no existe. Nombre temporal con ".tmp." (como ya espera estudio/paneles/resultados.py
    para no listar intermedios): <destino>.tmp.<extensión>. Mismo contrato que subprocess.run: con
    check=True lanza CalledProcessError si falla (tras limpiar el temporal); si no, el llamador mira
    r.returncode como siempre."""
    base, ext = os.path.splitext(destino)
    tmp = f"{base}.tmp{ext}"
    r = subprocess.run([*cmd, tmp], **kw)
    if r.returncode == 0:
        os.replace(tmp, destino)
    elif os.path.exists(tmp):
        os.remove(tmp)
    if check:
        r.check_returncode()
    return r


def __getattr__(nombre):  # PEP 562: FFMPEG / FFPROBE se buscan solo cuando alguien los importa
    if nombre in ("FFMPEG", "FFPROBE"):
        valor = requerir(nombre.lower())
        globals()[nombre] = valor
        return valor
    raise AttributeError(nombre)
