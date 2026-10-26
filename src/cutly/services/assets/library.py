"""Biblioteca de assets: los incluidos (assets/manifest.json) y los subidos (tabla Asset + data/assets/)."""

import io
import json
import re
import subprocess
from functools import lru_cache
from pathlib import Path

import resvg_py
from PIL import Image, ImageDraw, ImageFont
from sqlmodel import Session, select

from cutly.config import get_settings
from cutly.db.models import Asset
from cutly.services.render.rasterize import EXTS
from cutly.services.sanitize.paths import ensure_within
from cutly.services.sanitize.svg import SvgError, sanitize_svg

KIND_DIR = {"icon": "icons", "image": "images", "overlay": "overlays", "font": "fonts"}
DIR_KIND = {v: k for k, v in KIND_DIR.items()}
NAME_RE = re.compile(r"^[a-z0-9_\-]{1,40}$")
MAX_BYTES = {"icon": 200_000, "overlay": 5_000_000, "image": 5_000_000, "font": 5_000_000}
FONT_MAGIC = (b"\x00\x01\x00\x00", b"OTTO", b"true", b"ttcf")


class AssetError(ValueError):
    """Error de validación con mensaje accionable (se devuelve como 422)."""


def _builtin_dir() -> Path:
    return get_settings().builtin_assets_dir


def _user_dir() -> Path:
    return get_settings().data_dir / "assets"


@lru_cache(maxsize=4)
def _manifest(path: str, mtime: float) -> dict[str, dict]:
    return {a["id"]: a for a in json.loads(Path(path).read_text(encoding="utf-8")).get("assets", [])}


def builtin_assets() -> list[dict]:
    root = _builtin_dir()
    mf = root / "manifest.json"
    meta = _manifest(str(mf), mf.stat().st_mtime) if mf.is_file() else {}
    found: dict[str, dict] = {}
    for d in sorted(p for p in root.iterdir() if p.is_dir() and p.name in DIR_KIND):
        for p in sorted(d.iterdir()):
            if p.suffix.lower() not in (*EXTS, ".ttf", ".otf"):
                continue
            aid = f"{d.name}/{p.stem}"
            base = meta.get(
                aid,
                {
                    "id": aid,
                    "kind": DIR_KIND[d.name],
                    "tags": re.split(r"[-_]", p.stem),
                    "description": "",
                    "license": "",
                },
            )
            found[aid] = {**base, "source": "builtin"}
    return list(found.values())


def user_assets(session: Session) -> list[dict]:
    return [
        {
            "id": a.id,
            "kind": a.kind,
            "tags": a.tags,
            "description": a.description,
            "license": a.license,
            "source": "user",
        }
        for a in session.exec(select(Asset)).all()
    ]


def all_assets(session: Session) -> list[dict]:
    return builtin_assets() + user_assets(session)


def search(items: list[dict], kind: str | None = None, tag: str | None = None, q: str | None = None) -> list[dict]:
    out = items
    if kind:
        out = [a for a in out if a["kind"] == kind]
    if tag:
        t = tag.lower()
        out = [a for a in out if any(t == x.lower() or t in x.lower() for x in a["tags"])]
    if q:
        words = q.lower().split()
        out = [
            a
            for a in out
            if all(
                w in " ".join([a["id"], a.get("description", ""), *a["tags"], a.get("family", "")]).lower()
                for w in words
            )
        ]
    return out


def find(session: Session, asset_id: str) -> dict | None:
    return next((a for a in all_assets(session) if a["id"] == asset_id), None)


def file_of(asset: dict) -> Path:
    root = _builtin_dir() if asset["source"] == "builtin" else _user_dir()
    for ext in (*EXTS, ".ttf", ".otf"):
        p = root / f"{asset['id']}{ext}"
        if p.is_file():
            return ensure_within(root, p)
    raise FileNotFoundError(asset["id"])


# --- vistas previas ----------------------------------------------------------------------------------------------------------


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default()


def _label_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return _font(_builtin_dir() / "fonts" / "Poppins-Bold.ttf", size)


def preview_image(asset: dict, size: int = 256) -> Image.Image:
    """RGBA de la vista previa: icono/imagen rasterizados al ancho `size`; fuente: texto de muestra."""
    p = file_of(asset)
    if asset["kind"] == "font":
        im = Image.new("RGBA", (size * 2, size // 2), (28, 28, 30, 255))
        d = ImageDraw.Draw(im)
        d.text((12, size // 8), "Aa Linux 123", font=_font(p, size // 4), fill=(255, 255, 255, 255))
        return im
    if p.suffix.lower() == ".svg":
        png = resvg_py.svg_to_bytes(svg_string=sanitize_svg(p.read_bytes()), width=size)
        return Image.open(io.BytesIO(bytes(png))).convert("RGBA")
    im = Image.open(p).convert("RGBA")
    im.thumbnail((size, size))
    return im


def preview_png(asset: dict, size: int = 256) -> bytes:
    out = io.BytesIO()
    preview_image(asset, size).save(out, "PNG")
    return out.getvalue()


def contact_sheet(assets: list[dict], cols: int = 6, cell: int = 132) -> bytes:
    """Hoja con todos los assets (icono + id): permite ver de un vistazo qué hay y cómo se llama."""
    cols = max(1, min(cols, len(assets) or 1))
    rows = -(-len(assets) // cols)
    label_h = 30
    sheet = Image.new("RGB", (cols * cell, rows * (cell + label_h)), (24, 24, 28))
    d = ImageDraw.Draw(sheet)
    font = _label_font(11)
    for k, a in enumerate(assets):
        x, y = (k % cols) * cell, (k // cols) * (cell + label_h)
        d.rectangle((x + 2, y + 2, x + cell - 3, y + cell + label_h - 3), outline=(48, 48, 56))
        try:
            im = preview_image(a, cell - 28)
            im.thumbnail((cell - 28, cell - 28))
            sheet.paste(im, (x + (cell - im.width) // 2, y + 8 + (cell - 28 - im.height) // 2), im)
        except Exception:  # noqa: BLE001  (un asset roto no debe impedir ver el resto)
            d.text((x + 10, y + 50), "?", font=font, fill=(255, 80, 80))
        label = a["id"].split("/", 1)[-1]
        d.text((x + 6, y + cell - 14), label[:22], font=font, fill=(255, 212, 0))
        d.text((x + 6, y + cell), a["id"].split("/")[0], font=_label_font(9), fill=(150, 150, 160))
    out = io.BytesIO()
    sheet.save(out, "PNG")
    return out.getvalue()


# --- subida y borrado -------------------------------------------------------------------------------------------------------------


def _validate(kind: str, data: bytes) -> tuple[bytes, str]:
    """Devuelve (bytes a guardar, extensión). Lanza AssetError si algo no es seguro o no es lo que dice ser."""
    if kind not in KIND_DIR:
        raise AssetError(f"kind debe ser uno de {sorted(KIND_DIR)}")
    if not data:
        raise AssetError("El cuerpo de la petición está vacío: envía los bytes del archivo")
    if len(data) > MAX_BYTES[kind]:
        raise AssetError(f"El archivo supera el máximo para '{kind}' ({MAX_BYTES[kind] // 1000} KB)")
    if kind == "font":
        if not data.startswith(FONT_MAGIC):
            raise AssetError("No parece una fuente TrueType/OpenType (.ttf/.otf)")
        return data, ".otf" if data.startswith(b"OTTO") else ".ttf"
    head = data.lstrip()[:256].lower()
    if b"<svg" in head or head.startswith(b"<?xml"):
        try:
            return sanitize_svg(data).encode(), ".svg"
        except SvgError as e:
            raise AssetError(f"SVG rechazado: {e}") from e
    if kind == "icon":
        raise AssetError("Los iconos deben ser SVG")
    try:
        im = Image.open(io.BytesIO(data))
        im.verify()
        fmt = (im.format or "").upper()
        w, h = Image.open(io.BytesIO(data)).size
    except Exception as e:  # noqa: BLE001
        raise AssetError("La imagen no es válida o está dañada") from e
    if fmt not in ("PNG", "JPEG", "WEBP"):
        raise AssetError(f"Formato {fmt or 'desconocido'} no admitido (usa PNG, JPEG, WebP o SVG)")
    if max(w, h) > 4096:
        raise AssetError(f"La imagen mide {w}×{h}; el máximo es 4096 px por lado")
    return data, {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}[fmt]


def save_user_asset(
    session: Session, name: str, kind: str, data: bytes, tags: list[str], description: str, license_: str, replace: bool
) -> dict:
    if not NAME_RE.match(name):
        raise AssetError("name: solo minúsculas, números, '-' y '_' (hasta 40 caracteres)")
    body, ext = _validate(kind, data)
    aid = f"{KIND_DIR[kind]}/{name}"
    if any(a["id"] == aid for a in builtin_assets()):
        raise AssetError(f"'{aid}' es un asset incluido; elige otro nombre")
    existing = session.get(Asset, aid)
    if existing and not replace:
        raise AssetError(f"'{aid}' ya existe; usa replace=true para sustituirlo")
    family = ""
    root = _user_dir()
    target = (
        ensure_within(root, root / f"{aid}{ext}")
        if (root / KIND_DIR[kind]).mkdir(parents=True, exist_ok=True) is None
        else root
    )
    if existing:
        for old in (root / KIND_DIR[kind]).glob(f"{name}.*"):
            old.unlink(missing_ok=True)
    target.write_bytes(body)
    if kind == "font":
        r = subprocess.run(
            ["fc-scan", "--format", "%{family}", str(target)], capture_output=True, text=True, timeout=20
        )
        family = r.stdout.split(",")[0].strip()
        if not family:
            target.unlink(missing_ok=True)
            raise AssetError("La fuente no se pudo leer (¿archivo corrupto?)")
        description = description or f"Fuente subida; úsala con style.font = '{family}'"
    row = Asset(
        id=aid,
        kind=kind,
        path=str(target),
        tags=[t.strip().lower() for t in tags if t.strip()][:12],
        description=description[:300],
        license=license_[:80],
    )
    session.merge(row)
    session.commit()
    out = {
        "id": aid,
        "kind": kind,
        "tags": row.tags,
        "description": row.description,
        "license": row.license,
        "source": "user",
    }
    if family:
        out["family"] = family
    return out


def delete_user_asset(session: Session, asset_id: str) -> None:
    row = session.get(Asset, asset_id)
    if row is None:
        if any(a["id"] == asset_id for a in builtin_assets()):
            raise AssetError("Los assets incluidos no se pueden borrar")
        raise LookupError(asset_id)
    Path(row.path).unlink(missing_ok=True)
    session.delete(row)
    session.commit()
