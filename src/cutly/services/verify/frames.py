"""Fotogramas del proyecto con todas las capas aplicadas, y hojas de contacto con sus tiempos."""

import math
import subprocess
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from cutly.config import get_settings
from cutly.schema.project import ProjectDoc
from cutly.services.render.graph import MediaInfo, RenderOpts, build_plan, ffmpeg_command
from cutly.worker.subprocess_runner import run_ffmpeg

QUALITY = {"preview": 0.5, "draft": 1 / 3, "final": 1.0}


def fmt_clock(t: float) -> str:
    m, s = divmod(t, 60)
    return f"{int(m)}:{s:04.1f}"


def render_frames(
    doc: ProjectDoc,
    media: MediaInfo,
    words: list[dict],
    times: list[float],
    scale: float,
    workdir: Path,
    out_dir: Path,
    fonts_dir: Path | None,
    cancelled: Callable[[], bool] = lambda: False,
    on_progress: Callable[[float], None] = lambda p: None,
    ext: str = "jpg",
) -> tuple[list[Path], list[str]]:
    """Un JPEG por instante. Cada fotograma sale de un render de ventana mínima (no decodifica el clip entero)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    workdir.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []
    warnings: list[str] = []
    for i, t in enumerate(times):
        t = min(max(t, 0.0), max(doc.duration - 0.1, 0.0))
        opts = RenderOpts(workdir=workdir, scale=scale, with_audio=False, fonts_dir=fonts_dir)
        plan = build_plan(doc, media, words, opts, window=(t, min(t + 0.5, doc.duration)))
        graph = workdir / f"g{i}.txt"
        graph.write_text(plan.graph, encoding="utf-8")
        out = out_dir / f"f{i}.{ext}"
        run_ffmpeg(
            ffmpeg_command(plan, graph, out, opts, frame_only=True), duration=None,
            timeout=get_settings().job_timeout_s, cancelled=cancelled,
        )  # fmt: skip
        files.extend([out])
        warnings += [w for w in plan.warnings if w not in warnings]
        on_progress((i + 1) / len(times))
    return files, warnings


def _font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    p = get_settings().builtin_assets_dir / "fonts" / "Poppins-Bold.ttf"
    try:
        return ImageFont.truetype(str(p), size)
    except OSError:
        return ImageFont.load_default()


def contact_sheet(files: list[Path], times: list[float], out: Path, cols: int = 4, cell_w: int = 270) -> Path:
    """Cuadrícula de fotogramas con su tiempo (m:ss.d) en cada esquina: lo que hace falta para «ver» un clip de un vistazo."""
    imgs = [Image.open(f).convert("RGB") for f in files]
    cols = max(1, min(cols, len(imgs)))
    rows = math.ceil(len(imgs) / cols)
    ch = round(cell_w * imgs[0].height / imgs[0].width)
    sheet = Image.new("RGB", (cols * cell_w, rows * ch), (16, 16, 20))
    font = _font(max(12, cell_w // 14))
    for k, (im, t) in enumerate(zip(imgs, times, strict=True)):
        cell = im.resize((cell_w, ch), Image.LANCZOS)
        d = ImageDraw.Draw(cell)
        label = fmt_clock(t)
        box = d.textbbox((0, 0), label, font=font)
        d.rectangle((0, 0, box[2] + 10, box[3] + 8), fill=(0, 0, 0))
        d.text((5, 2), label, font=font, fill=(255, 212, 0))
        sheet.paste(cell, ((k % cols) * cell_w, (k // cols) * ch))
    sheet.save(out, quality=88)
    return out


def source_frame(path: str, t: float, width: int, grid: bool) -> bytes:
    """Fotograma del vídeo ORIGINAL (sin capas) con rejilla opcional 0–1: sirve para elegir rectángulos de reencuadre."""
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{max(t, 0):.3f}", "-i", path, "-frames:v", "1",
           "-vf", f"scale={width}:-2", "-f", "image2pipe", "-vcodec", "png", "-"]  # fmt: skip
    r = subprocess.run(cmd, capture_output=True, timeout=60)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError(f"No se pudo extraer el fotograma: {r.stderr.decode(errors='replace')[-200:]}")
    import io

    im = Image.open(io.BytesIO(r.stdout)).convert("RGB")
    if grid:
        d = ImageDraw.Draw(im, "RGBA")
        font = _font(max(11, im.width // 40))
        for k in range(1, 10):
            x, y = round(im.width * k / 10), round(im.height * k / 10)
            d.line([(x, 0), (x, im.height)], fill=(255, 212, 0, 120), width=1)
            d.line([(0, y), (im.width, y)], fill=(255, 212, 0, 120), width=1)
            for pos in ((x + 3, 2), (2, y + 2)):
                d.text(
                    pos,
                    f"{k / 10:.1f}",
                    font=font,
                    fill=(255, 255, 255, 230),
                    stroke_width=2,
                    stroke_fill=(0, 0, 0, 255),
                )
    out = io.BytesIO()
    im.save(out, "JPEG", quality=88)
    return out.getvalue()
