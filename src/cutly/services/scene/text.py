"""Texto de las escenas (Pillow): ajuste de línea, énfasis por palabras, revelado y cifrado visual."""

import random
import re
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFont

_SCRAMBLE = "0123456789abcdef#%&@$*+=<>?"


@lru_cache(maxsize=64)
def _font_path(family: str, weight: str, mono: bool) -> str | None:
    from cutly.services.render.fonts import font_file

    try:
        if mono:
            return font_file("DejaVu Sans Mono", weight != "regular")
        if weight == "black" and family == "Poppins":
            return font_file("Poppins ExtraBold", False) or font_file(family, True)
        return font_file(family, weight != "regular")
    except Exception:  # noqa: BLE001 - sin configuración del servidor (p. ej. pruebas aisladas)
        return None


@lru_cache(maxsize=256)
def get_font(family: str, weight: str, mono: bool, px: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = _font_path(family, weight, mono)
    for cand in (path, "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if cand:
            try:
                return ImageFont.truetype(cand, max(4, px))
            except OSError:
                continue
    return ImageFont.load_default(max(4, px))


def wrap_lines(text: str, font, max_w: float | None) -> list[str]:
    out: list[str] = []
    for para in text.split("\n"):
        if not max_w:
            out.append(para)
            continue
        line = ""
        for word in para.split(" "):
            cand = f"{line} {word}".strip()
            if line and font.getlength(cand) > max_w:
                out.append(line)
                line = word
            else:
                line = cand
        out.append(line)
    return out


def scramble_text(text: str, level: float, seed: int, frame: int) -> str:
    """Sustituye una fracción `level` de los caracteres por símbolos que cambian ~12 veces por segundo."""
    if level <= 0:
        return text
    rng = random.Random(seed * 7919 + frame)
    return "".join(c if c in " \n" or rng.random() > level else rng.choice(_SCRAMBLE) for c in text)


@dataclass
class TextBlock:
    mask: np.ndarray  # float32 0-1
    ox: float  # desplazamiento del centro del bloque respecto a la esquina de la máscara
    oy: float
    w: float
    h: float
    hl: np.ndarray | None = None  # máscara de las palabras resaltadas


def render_text(
    text: str, family: str, weight: str, mono: bool, px: float, align: str, max_w: float | None, spacing: float,
    outline_px: float = 0, highlight: tuple[str, ...] = (), reveal: float = 1.0,
) -> TextBlock | None:  # fmt: skip
    """Rasteriza el texto como máscara. `px` y `max_w` ya vienen en píxeles del lienzo."""
    font = get_font(family, weight, mono, round(px))
    lines = wrap_lines(text, font, max_w)
    if reveal < 1.0:  # máquina de escribir: recorta caracteres sobre el texto ya maquetado
        total = sum(len(ln) for ln in lines)
        keep = int(total * max(reveal, 0.0) + 1e-6)
        cut: list[str] = []
        for ln in lines:
            cut.append(ln[: max(0, min(len(ln), keep))])
            keep -= len(ln)
        lines = cut
    lh = px * 1.28
    pad = int(px * 0.3 + outline_px * 2 + 4)
    widths = [_line_w(font, ln, spacing, px) for ln in lines]
    full_w = [_line_w(font, ln, spacing, px) for ln in wrap_lines(text, font, max_w)] if reveal < 1.0 else widths
    bw = max([*full_w, 1.0])
    bh = lh * len(lines)
    W, H = int(bw + pad * 2) + 1, int(bh + pad * 2) + 1
    img = Image.new("L", (W, H), 0)
    himg = Image.new("L", (W, H), 0) if highlight else None
    d, hd = ImageDraw.Draw(img), ImageDraw.Draw(himg) if himg else None
    hl_words = {h.lower() for h in highlight}
    for i, ln in enumerate(lines):
        lw = _line_w(font, ln, spacing, px)
        x = pad + {"left": 0.0, "center": (bw - lw) / 2, "right": bw - lw}[align]
        y = pad + i * lh + (lh - px) / 2 - px * 0.08
        _draw_line(d, hd, font, ln, x, y, spacing, px, outline_px, hl_words)
    mask = np.asarray(img, dtype=np.float32) * (1 / 255)
    hmask = np.asarray(himg, dtype=np.float32) * (1 / 255) if himg else None
    if not mask.any():
        return None
    return TextBlock(mask, W / 2, H / 2, bw, bh, hmask)


def _line_w(font, ln: str, spacing: float, px: float) -> float:
    if not spacing:
        return float(font.getlength(ln))
    return sum(font.getlength(c) + spacing * px for c in ln) - spacing * px if ln else 0.0


def _draw_line(d, hd, font, ln, x, y, spacing, px, outline_px, hl_words):
    stroke = max(0, round(outline_px))
    if not spacing and not hl_words:
        d.text((x, y), ln, font=font, fill=255, stroke_width=stroke, stroke_fill=255)
        return
    cx = x
    for tok in _tokens(ln):
        is_hl = tok.strip(" .,:;!?¿¡()\"'").lower() in hl_words
        target = hd if (is_hl and hd) else d
        if spacing:
            for ch in tok:
                target.text((cx, y), ch, font=font, fill=255, stroke_width=stroke, stroke_fill=255)
                cx += font.getlength(ch) + spacing * px
        else:
            target.text((cx, y), tok, font=font, fill=255, stroke_width=stroke, stroke_fill=255)
            cx += font.getlength(tok)


def _tokens(ln: str) -> list[str]:
    out, cur = [], ""
    for ch in ln:
        if ch == " ":
            if cur:
                out.append(cur)
                cur = ""
            out.append(" ")
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out


_MARK = re.compile(r"\*\*(.+?)\*\*")


def parse_markup(text: str) -> tuple[str, list[str]]:
    """Quita los `**…**` y devuelve (texto limpio, palabras a resaltar)."""
    words: list[str] = []

    def rep(m: re.Match) -> str:
        words.extend(w for w in m.group(1).split() if w)
        return m.group(1)

    return _MARK.sub(rep, text), words
