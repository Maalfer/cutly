"""Miniaturas del material (un fotograma con ffmpeg), en caché fuera del repo y generadas en segundo plano."""
import hashlib
import os
import subprocess
import tempfile

from nucleo.ffmpeg import localizar
from nucleo.material import AUDIO, IMAGEN

CACHE = os.path.join(tempfile.gettempdir(), "cutly_miniaturas")
ALTO = 180


def ruta_cache(path):
    st = os.stat(path)
    clave = f"{os.path.abspath(path)}|{st.st_size}|{int(st.st_mtime)}".encode("utf-8")
    return os.path.join(CACHE, hashlib.sha1(clave).hexdigest()[:16] + ".png")


def miniatura(path, duracion=None):
    """PNG de la miniatura (generándolo si no está en caché) o None (audio, o si ffmpeg no puede)."""
    if path.lower().endswith(AUDIO):
        return None
    if path.lower().endswith(IMAGEN):
        return path
    destino = ruta_cache(path)
    if os.path.exists(destino):
        return destino
    os.makedirs(CACHE, exist_ok=True)
    ff = localizar("ffmpeg")
    if not ff:
        return None
    t = min(1.0, (duracion or 3) / 3)               # un poco dentro: el primer fotograma suele ser negro
    r = subprocess.run([ff, "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", path, "-frames:v", "1",
                        "-vf", f"scale=-2:{ALTO}", destino], capture_output=True)
    return destino if r.returncode == 0 and os.path.exists(destino) else None
