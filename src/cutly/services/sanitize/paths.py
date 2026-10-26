"""Validación de nombres y rutas que vienen de fuera."""

import re
import unicodedata
from pathlib import Path

ALLOWED_EXT = {".mp4", ".mkv", ".mov", ".webm", ".ts", ".flv", ".avi", ".m4v"}


class UnsafePath(ValueError):
    pass


def safe_filename(name: str) -> str:
    """Quita directorios, caracteres raros y puntos iniciales; valida la extensión."""
    name = unicodedata.normalize("NFKC", name).replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^\w.\- ]", "_", name).strip(" .")[:120]
    if not name:
        raise UnsafePath("Nombre de archivo vacío o inválido")
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise UnsafePath(f"Extensión {ext or '(ninguna)'} no permitida; usa una de {sorted(ALLOWED_EXT)}")
    return name


def ensure_within(base: Path, path: Path) -> Path:
    """Garantiza que `path` está dentro de `base` (evita ../ y enlaces simbólicos)."""
    base_r, path_r = base.resolve(), path.resolve()
    if base_r != path_r and base_r not in path_r.parents:
        raise UnsafePath("Ruta fuera del directorio permitido")
    return path_r
