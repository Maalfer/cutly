"""Fuentes disponibles para el render (incluidas, subidas y del sistema) y directorio fusionado para libass."""

import os
import subprocess
from functools import lru_cache
from pathlib import Path

from cutly.config import get_settings

SYSTEM_FAMILIES = [
    "DejaVu Sans",
    "DejaVu Serif",
    "DejaVu Sans Mono",
    "Liberation Sans",
    "Liberation Serif",
    "Liberation Mono",
]
EXTS = {".ttf", ".otf"}


def font_dirs() -> list[Path]:
    s = get_settings()
    return [d for d in (s.builtin_assets_dir / "fonts", s.data_dir / "assets" / "fonts") if d.is_dir()]


@lru_cache(maxsize=64)
def _families_of(path: str, mtime: float) -> tuple[str, ...]:
    """Nombres con los que fontconfig (y por tanto libass) conoce esa fuente."""
    try:
        out = subprocess.run(
            ["fc-scan", "--format", "%{family}\\n", path], capture_output=True, text=True, timeout=20
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ()
    names: list[str] = []
    for line in out.splitlines():
        names += [n.strip() for n in line.split(",") if n.strip()]
    return tuple(dict.fromkeys(names))


def available_fonts() -> dict[str, str]:
    """{familia: origen} con todo lo que se puede poner en `style.font` (además de 'default')."""
    found = {n: "sistema" for n in SYSTEM_FAMILIES}
    for d in font_dirs():
        origin = "incluida" if d == get_settings().builtin_assets_dir / "fonts" else "subida"
        for p in sorted(d.iterdir()):
            if p.suffix.lower() in EXTS:
                for fam in _families_of(str(p), p.stat().st_mtime):
                    found[fam] = origin
    return found


def merged_fonts_dir(workdir: Path) -> Path | None:
    """Enlaces a todas las fuentes en una sola carpeta (el filtro `ass` solo admite una `fontsdir`)."""
    files = [p for d in font_dirs() for p in d.iterdir() if p.suffix.lower() in EXTS]
    if not files:
        return None
    out = workdir / "fonts"
    out.mkdir(parents=True, exist_ok=True)
    for p in files:
        link = out / p.name
        if not link.exists():
            os.symlink(p.resolve(), link)
    return out


@lru_cache(maxsize=64)
def font_file(family: str, bold: bool) -> str | None:
    """Ruta del archivo de fuente que usará libass para (familia, negrita); None si no se encuentra."""
    fam = "DejaVu Sans" if family == "default" else family
    best: tuple[int, str] | None = None
    for d in font_dirs():
        for p in sorted(d.iterdir()):
            if p.suffix.lower() not in EXTS:
                continue
            if fam in _families_of(str(p), p.stat().st_mtime):
                is_bold = "bold" in p.stem.lower() and "extrabold" not in p.stem.lower()
                score = 2 if is_bold == bold else 1
                if best is None or score > best[0]:
                    best = (score, str(p))
    if best:
        return best[1]
    try:  # fuentes del sistema
        out = subprocess.run(
            ["fc-match", "-f", "%{file}", f"{fam}:{'bold' if bold else 'regular'}"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out or None
