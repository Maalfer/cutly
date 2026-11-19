"""Contrato entre la Fase 1 (crear-shorts: la IA graba la demo en la VM) y la Fase 2 (editor: construir el Short).

Una TOMA llamada NOMBRE deja en editor/crudo/:
    NOMBRE.mp4           la grabación (H.264, 30 fps constantes, sin audio)
    NOMBRE.steps.jsonl   un evento JSON por línea, en orden:
                           {"op": "...", "args": [...], "t_wall": epoch, "t_video": s desde el inicio del vídeo, ...}
                         ops que lee la edición: mark (label), focus (args x,y[,w,h]), move (args x,y), typeurl (dur)
    NOMBRE.mapa.md       mapa de edición legible (un bloque por mark)

Quien escribe: crear-shorts/herramientas/vm/registro.py y vm/toma.py. Quien lee: editor/shorts/short_desde_toma.py.
Si cambias un campo, cambia los dos lados (y pruebas/test_toma.py).
"""
from nucleo.archivos import leer_jsonl
from nucleo.rutas import en_crudo


def ruta(nombre, ext):
    """editor/crudo/<toma>.<ext> (ext: mp4 | steps.jsonl | mapa.md)."""
    return en_crudo(nombre, ext)


def cargar_eventos(path):
    return leer_jsonl(path)
