"""Job `render`: ProjectDoc → MP4 con FFmpeg."""

import shutil
from pathlib import Path

from sqlmodel import Session, select

from cutly.config import get_settings
from cutly.db.models import Media, Transcript
from cutly.db.session import get_engine
from cutly.schema.project import ProjectDoc
from cutly.services.ingest.ffprobe import probe
from cutly.services.render.fonts import merged_fonts_dir
from cutly.services.render.graph import (
    MediaInfo,
    RenderOpts,
    build_measure_command,
    build_plan,
    ffmpeg_command,
    gain_from_loudness,
)
from cutly.worker.jobs import JobContext, handler
from cutly.worker.subprocess_runner import run_ffmpeg


def words_for(doc: ProjectDoc, segments: list[dict]) -> list[dict]:
    """Solo las palabras que caen dentro de algún clip (un directo de 6 h tiene decenas de miles)."""
    out = []
    for seg in segments:
        for w in seg.get("words", []):
            if any(w["end"] > c.source_in and w["start"] < c.source_out for c in doc.timeline):
                out.append(w)
    return out


@handler("render")
def render(ctx: JobContext) -> dict:
    s = get_settings()
    doc = ProjectDoc.model_validate(ctx.params["doc"])  # instantánea tomada al encolar
    draft = ctx.params.get("quality") == "draft"
    with Session(get_engine()) as session:
        media = session.get(Media, doc.media_id)
        if media is None:
            raise RuntimeError("El vídeo original ya no existe")
        t = session.exec(select(Transcript).where(Transcript.media_id == media.id)).first()
        segments = t.segments if t else []
        src_path, has_audio = media.original_path, bool(media.metadata_json.get("has_audio"))
        if draft and media.proxy_path:  # el borrador sale del proxy 540p: mucho más rápido
            src_path = media.proxy_path
    info = probe(Path(src_path))
    out_dir = s.renders_dir / ctx.params["project_id"]
    work = s.renders_dir / "tmp" / ctx.job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{ctx.job_id}.mp4"
    work.mkdir(parents=True, exist_ok=True)
    opts = RenderOpts(
        workdir=work, draft=draft, encoder=s.video_encoder, threads=s.ffmpeg_threads, fonts_dir=merged_fonts_dir(work)
    )
    try:
        minfo = MediaInfo(src_path, info["width"], info["height"], has_audio)
        gain = None
        if doc.audio.normalize and has_audio:  # pasada 1: medir el volumen (solo audio, casi sin memoria)
            text = run_ffmpeg(
                build_measure_command(doc, minfo, work), duration=None, timeout=s.job_timeout_s, cancelled=ctx.cancelled
            )
            gain = gain_from_loudness(text, doc.audio.target_lufs)
        window = None
        if ctx.params.get("start") is not None or ctx.params.get("end") is not None:
            window = (ctx.params.get("start") or 0.0, ctx.params.get("end") or doc.duration)
        plan = build_plan(doc, minfo, words_for(doc, segments), opts, norm_gain_db=gain, window=window)
        if doc.audio.normalize and has_audio and gain is None:
            plan.warnings.append("Audio sin señal medible (casi silencio): no se normalizó")
        graph_file = work / "graph.txt"
        graph_file.write_text(plan.graph, encoding="utf-8")
        tmp_out = out.with_suffix(".part.mp4")
        run_ffmpeg(
            ffmpeg_command(plan, graph_file, tmp_out, opts), duration=plan.duration, timeout=s.job_timeout_s,
            cancelled=ctx.cancelled, on_progress=ctx.progress,
        )  # fmt: skip
        tmp_out.replace(out)
    except BaseException:
        out.with_suffix(".part.mp4").unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return {
        "path": str(out), "size": out.stat().st_size, "duration": plan.duration, "width": plan.width,
        "height": plan.height, "quality": "draft" if draft else "final", "warnings": plan.warnings,
        "project_id": ctx.params["project_id"], "project_version": ctx.params.get("project_version"),
    }  # fmt: skip
