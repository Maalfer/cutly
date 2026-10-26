"""Jobs de verificación: `frames` (fotogramas con capas + hoja de contacto) y `checks` (comprobaciones automáticas)."""

import shutil
import time
from pathlib import Path

from sqlmodel import Session, select

from cutly.config import get_settings
from cutly.db.models import Media, Transcript
from cutly.db.session import get_engine
from cutly.schema.project import ProjectDoc
from cutly.services.ingest.ffprobe import probe
from cutly.services.render.fonts import merged_fonts_dir
from cutly.services.render.graph import MediaInfo
from cutly.services.verify import audio as audio_mod
from cutly.services.verify.checks import run_checks
from cutly.services.verify.faces import detect_faces
from cutly.services.verify.frames import QUALITY, contact_sheet, render_frames
from cutly.worker.jobs import JobContext, handler

KEEP_FRAMES_S = 24 * 3600


def prune_old_frames() -> None:
    now = time.time()
    for d in get_settings().renders_dir.glob("*/frames/*"):
        if d.is_dir() and now - d.stat().st_mtime > KEEP_FRAMES_S:
            shutil.rmtree(d, ignore_errors=True)


def _load(doc: ProjectDoc) -> tuple[Media, list[dict]]:
    with Session(get_engine()) as session:
        media = session.get(Media, doc.media_id)
        if media is None:
            raise RuntimeError("El vídeo original ya no existe")
        t = session.exec(select(Transcript).where(Transcript.media_id == media.id)).first()
        words = [w for s in (t.segments if t else []) for w in s.get("words", [])]
        session.expunge(media)
    return media, words


def _clip_words(doc: ProjectDoc, words: list[dict]) -> list[dict]:
    return [w for w in words if any(w["end"] > c.source_in and w["start"] < c.source_out for c in doc.timeline)]


@handler("frames")
def frames(ctx: JobContext) -> dict:
    s = get_settings()
    doc = ProjectDoc.model_validate(ctx.params["doc"])
    scale = QUALITY[ctx.params.get("quality", "preview")]
    times = [float(t) for t in ctx.params["times"]]
    media, words = _load(doc)
    src = media.proxy_path if (scale <= 0.5 and media.proxy_path) else media.original_path
    info = probe(Path(src))
    minfo = MediaInfo(src, info["width"], info["height"], bool(media.metadata_json.get("has_audio")))
    out_dir = s.renders_dir / ctx.params["project_id"] / "frames" / ctx.job_id
    work = s.renders_dir / "tmp" / ctx.job_id
    work.mkdir(parents=True, exist_ok=True)
    prune_old_frames()
    try:
        ext = ctx.params.get("format", "jpg")
        files, warns = render_frames(
            doc, minfo, _clip_words(doc, words), times, scale, work, out_dir, merged_fonts_dir(work),
            ctx.cancelled, ctx.progress, ext=ext,
        )  # fmt: skip
        sheet = None
        if len(files) > 1:
            cols = int(ctx.params.get("cols") or min(4, len(files)))
            contact_sheet(files, times, out_dir / "sheet.jpg", cols=cols)
            sheet = "sheet.jpg"
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return {
        "frames": [{"t": t, "file": f.name} for t, f in zip(times, files, strict=True)], "sheet": sheet,
        "width": int(doc.output.width * scale) // 2 * 2, "height": int(doc.output.height * scale) // 2 * 2,
        "quality": ctx.params.get("quality", "preview"), "warnings": warns,
    }  # fmt: skip


@handler("checks")
def checks(ctx: JobContext) -> dict:
    s = get_settings()
    doc = ProjectDoc.model_validate(ctx.params["doc"])
    media, words = _load(doc)
    meta = media.metadata_json
    proxy = media.proxy_path or media.original_path
    work = s.renders_dir / "tmp" / ctx.job_id
    work.mkdir(parents=True, exist_ok=True)
    try:
        ctx.progress(0.1)
        stats = None
        if meta.get("has_audio") and doc.timeline:
            stats = audio_mod.measure(
                doc, MediaInfo(media.original_path, meta["width"], meta["height"], True), work, s.job_timeout_s
            )
        ctx.progress(0.4)
        result = run_checks(
            doc, {"width": meta["width"], "height": meta["height"], "duration": media.duration}, _clip_words(doc, words),
            faces_at=lambda t: detect_faces(proxy, t), audio=stats, has_transcript=bool(words),
        )  # fmt: skip
        result["audio"] = stats
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return result
