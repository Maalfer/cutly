"""Saneado de campos de texto libre controlados por el usuario (nombres de proyecto, API keys...).

No se intenta un escapado HTML (eso ya lo hace el cliente al pintar texto), sino que se elimina
cualquier carácter capaz de abrir o cerrar una etiqueta, así el valor nunca puede formar marcado
aunque acabe en un contexto que lo interprete como HTML (email, export, panel de admin, SSR...).
"""

import re
import unicodedata

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HTML_MARKUP = re.compile(r"[<>]")


def sanitize_label(value: str) -> str:
    """Normaliza, quita caracteres de control y los que podrían formar una etiqueta HTML."""
    value = unicodedata.normalize("NFC", value)
    value = _CONTROL_CHARS.sub("", value)
    value = _HTML_MARKUP.sub("", value)
    return value.strip()
