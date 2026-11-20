"""Localiza ffmpeg/ffprobe del ANFITRIÓN en Windows, macOS y Linux.

    from nucleo.ffmpeg import FFMPEG, FFPROBE      # se resuelven al usarlos; si faltan, sale con instrucciones
    from nucleo.ffmpeg import localizar            # None si no está (para quien puede funcionar sin él)
    from nucleo.ffmpeg import salida_atomica       # escribe el VÍDEO FINAL sin dejarlo roto a medias
    from nucleo.ffmpeg import ruta_temporal        # nombre de su temporal (y de los intermedios): <base>.tmp.<ext>

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
    r.returncode como siempre.

    Si `destino` está abierto en otro programa (Windows no deja reemplazar un archivo abierto: medido con el
    reproductor de cutly estudio, que lo suelta solo al ver aparecer el temporal), reintenta unos segundos y, si
    sigue bloqueado, lanza ArchivoBloqueado diciendo qué cerrar. En ningún caso queda el temporal suelto."""
    tmp = ruta_temporal(destino)
    try:
        r = subprocess.run([*cmd, tmp], **kw)
        if r.returncode == 0:
            reemplazar(tmp, destino)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    if check:
        r.check_returncode()
    return r


class ArchivoBloqueado(PermissionError):
    pass


def ruta_temporal(destino, ext=None):
    """<destino sin extensión>.tmp.<ext> — el nombre que usan salida_atomica y los intermedios. Mientras exista
    uno, ese vídeo se está rehaciendo (o un intento falló): la app suelta el original y el verificador no lo da
    por bueno."""
    base, ext0 = os.path.splitext(destino)
    return f"{base}.tmp{ext or ext0}"


def temporales_de(destino):
    """Temporales vivos de `destino` (cualquier extensión: el intermedio de fusionar es .tmp.mov)."""
    return glob.glob(glob.escape(os.path.splitext(destino)[0]) + ".tmp.*")


def reemplazar(origen, destino, espera=15.0, cada=0.5):
    """os.replace con reintentos si `destino` está abierto en otro programa (PermissionError en Windows)."""
    import time
    limite = time.monotonic() + espera
    while True:
        try:
            os.replace(origen, destino)
            return
        except PermissionError as e:
            if time.monotonic() >= limite:
                raise ArchivoBloqueado(
                    f"no se puede reemplazar {destino}: lo tiene abierto otro programa (¿un reproductor?). "
                    f"Ciérralo y vuelve a lanzar la orden; el resultado nuevo se ha descartado.") from e
            time.sleep(cada)


def __getattr__(nombre):  # PEP 562: FFMPEG / FFPROBE se buscan solo cuando alguien los importa
    if nombre in ("FFMPEG", "FFPROBE"):
        valor = requerir(nombre.lower())
        globals()[nombre] = valor
        return valor
    raise AttributeError(nombre)
