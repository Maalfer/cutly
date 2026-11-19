"""Dónde vive cada cosa del repo. Se calcula desde este archivo: cutly puede estar en cualquier carpeta."""
import os

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
EDITOR = os.path.join(REPO, "editor")

# carpetas de trabajo (locales, no se versionan). CUTLY_CRUDO / CUTLY_SALIDA las redirigen (p. ej. en pruebas,
# para no tocar el material real ni el _cortes.log de verdad).
CRUDO = os.environ.get("CUTLY_CRUDO") or os.path.join(EDITOR, "crudo")             # tomas, directos, cara.mp4...
SALIDA = os.environ.get("CUTLY_SALIDA") or os.path.join(EDITOR, "videos-editados")  # clips/Shorts + _cortes.log

# recursos compartidos por las líneas de edición
COMUN = os.path.join(EDITOR, "comun")
GLOSARIO = os.path.join(COMUN, "glosario.json")        # correcciones de términos técnicos de Whisper
FUENTES = os.path.join(COMUN, "fuentes")               # letra de los subtítulos (Inter, OFL)

SHORTS = os.path.join(EDITOR, "shorts")
DIRECTOS = os.path.join(EDITOR, "directos")


def en_crudo(nombre, ext):
    """editor/crudo/<nombre>.<ext>"""
    return os.path.join(CRUDO, f"{nombre}.{ext}")
