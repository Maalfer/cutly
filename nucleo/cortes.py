"""Registro de cortes editor/videos-editados/_cortes.log: los tramos exactos de cada clip/Short construido.

Es lo único que permite auditar o rehacer un vídeo después. SOLO se añade al final: nunca se recrea ni se reescribe
(si aparece ausente o truncado es algo transitorio —p. ej. la Papelera—, no una señal para empezar de cero).
"""
import os

from nucleo.rutas import SALIDA

LOG = os.path.join(SALIDA, "_cortes.log")


def anotar(texto):
    """Añade `texto` al final del registro (APPEND)."""
    os.makedirs(SALIDA, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(texto)
