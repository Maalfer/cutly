"""Resolución de assets y rasterizado de SVG a PNG (resvg)."""

import hashlib
import re
from pathlib import Path

import resvg_py

from cutly.config import get_settings
from cutly.services.sanitize.paths import UnsafePath, ensure_within
from cutly.services.sanitize.svg import sanitize_svg

EXTS = (".svg", ".png", ".webp", ".jpg", ".jpeg")
_COLOR_ATTR = re.compile(r'(fill|stroke)="(#[0-9A-Fa-f]{3,8}|[a-z]+)"')


class AssetNotFound(LookupError):
    pass


def resolve_asset(asset_id: str) -> Path:
    """`icons/arrow-right` → fichero real. Busca en los assets incluidos y en los subidos."""
    s = get_settings()
    for root in (s.data_dir / "assets", s.builtin_assets_dir):
        for ext in EXTS:
            cand = root / f"{asset_id}{ext}"
            try:
                if cand.is_file():
                    return ensure_within(root, cand)
            except UnsafePath:
                continue
    raise AssetNotFound(f"El asset '{asset_id}' no existe. Revisa GET /assets (p. ej. icons/arrow-right)")


def rasterize(asset_id: str, width_px: int, tint: str | None, cache_dir: Path) -> Path:
    """PNG RGBA del asset con el ancho pedido. SVG: saneado + (opcional) recoloreado con `tint`."""
    src = resolve_asset(asset_id)
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(f"{src}:{src.stat().st_mtime_ns}:{width_px}:{tint}".encode()).hexdigest()[:16]
    out = cache_dir / f"{key}.png"
    if out.exists():
        return out
    if src.suffix == ".svg":
        svg = sanitize_svg(src.read_bytes())
        if tint:
            svg = _COLOR_ATTR.sub(lambda m: m.group(0) if m.group(2) == "none" else f'{m.group(1)}="{tint[:7]}"', svg)
        out.write_bytes(bytes(resvg_py.svg_to_bytes(svg_string=svg, width=max(2, width_px))))
    else:  # PNG/JPG/WebP: se deja tal cual; ffmpeg lo escala
        out = src
    return out


def all_asset_ids() -> list[str]:
    """Todos los ids de assets visibles (incluidos y subidos), p. ej. ['icons/arrow-right', ...]."""
    s = get_settings()
    ids: set[str] = set()
    for root in (s.data_dir / "assets", s.builtin_assets_dir):
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if p.suffix.lower() in EXTS and p.parent != root and p.parent.name != "fonts":
                ids.add(f"{p.parent.relative_to(root).as_posix()}/{p.stem}")
    return sorted(ids)
