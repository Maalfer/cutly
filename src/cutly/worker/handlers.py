"""Handlers de jobs de ingesta: proxy de previsualización y peaks de forma de onda."""

import os
from pathlib import Path

import numpy as np
from sqlmodel import Session

from cutly.config import get_settings
from cutly.db.models import Media
from cutly.db.session import get_engine
from cutly.services.ingest.media_store import media_dir
from cutly.worker.jobs import JobContext, handler
from cutly.worker.subprocess_runner import run_ffmpeg, run_ffmpeg_pipe

PEAKS_RATE = 20  # pares (min,max) por segundo
PEAKS_SR = 8000


def _media(session: Session, ctx: JobContext) -> Media:
    media = session.get(Media, ctx.params["media_id"])
    if media is None:
        raise RuntimeError("El medio ya no existe (¿borrado mientras se procesaba?)")
    return media


def _maybe_ready(session: Session, media: Media) -> None:
    if media.proxy_path and (media.peaks_path or not media.metadata_json.get("has_audio")):
        media.status = "ready"
        session.add(media)
        session.commit()


@handler("media.proxy")
def make_proxy(ctx: JobContext) -> dict:
    """H.264 con el lado corto a 540 px (540p en horizontal, 540x960 en vertical), keyframe cada 1 s y +faststart."""
    s = get_settings()
    with Session(get_engine()) as session:
        media = _media(session, ctx)
        src, duration = media.original_path, media.duration
        out = media_dir(media.id) / "proxy.mp4"
    tmp = out.with_suffix(".part.mp4")
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-y", "-i", src,
        "-map", "0:v:0", "-map", "0:a:0?",
        "-vf", "scale='if(gt(iw,ih),-2,540)':'if(gt(iw,ih),540,-2)':flags=fast_bilinear,format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "27",
        "-force_key_frames", "expr:gte(t,n_forced*1)", "-sc_threshold", "0",
        "-c:a", "aac", "-b:a", "96k", "-ac", "2",
        "-threads", str(s.ffmpeg_threads),
        "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(tmp),
    ]  # fmt: skip
    try:
        run_ffmpeg(
            cmd, duration=duration, timeout=s.job_timeout_s,
            cancelled=ctx.cancelled, on_progress=ctx.progress,
        )  # fmt: skip
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    os.replace(tmp, out)
    with Session(get_engine()) as session:
        media = _media(session, ctx)
        media.proxy_path = str(out)
        session.add(media)
        session.commit()
        _maybe_ready(session, media)
    return {"proxy": str(out)}


@handler("media.peaks")
def make_peaks(ctx: JobContext) -> dict:
    """Min/max de audio a 20 pares/s en un .npy int8; el navegador nunca decodifica audio."""
    s = get_settings()
    with Session(get_engine()) as session:
        media = _media(session, ctx)
        src, duration = media.original_path, media.duration or 0
        if not media.metadata_json.get("has_audio"):
            _maybe_ready(session, media)
            return {"peaks": None, "reason": "sin pista de audio"}
        out = media_dir(media.id) / "peaks.npy"
    bucket = PEAKS_SR // PEAKS_RATE
    parts: list[np.ndarray] = []
    carry = b""

    def consume(data: bytes, final: bool = False):
        nonlocal carry
        buf = carry + data
        n = len(buf) // (2 * bucket) * (2 * bucket)
        if final and len(buf) > n:  # último cubo parcial
            n = len(buf) // 2 * 2
        arr = np.frombuffer(buf[:n], dtype="<i2")
        carry = buf[n:]
        if arr.size == 0:
            return
        full = arr.size // bucket * bucket
        if full:
            a = arr[:full].reshape(-1, bucket)
            parts.append(np.stack([a.min(1) >> 8, a.max(1) >> 8], axis=1).astype(np.int8))
        if arr.size > full:
            a = arr[full:]
            parts.append(np.array([[a.min() >> 8, a.max() >> 8]], dtype=np.int8))

    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-i", src, "-map", "0:a:0",
        "-ac", "1", "-ar", str(PEAKS_SR), "-f", "s16le", "-",
    ]  # fmt: skip
    run_ffmpeg_pipe(
        cmd, on_chunk=consume, expected_bytes=int(duration * PEAKS_SR * 2),
        timeout=s.job_timeout_s, cancelled=ctx.cancelled, on_progress=ctx.progress,
    )  # fmt: skip
    consume(b"", final=True)
    peaks = np.concatenate(parts) if parts else np.zeros((0, 2), dtype=np.int8)
    tmp = Path(str(out) + ".part")
    with open(tmp, "wb") as f:
        np.save(f, peaks)
    os.replace(tmp, out)
    with Session(get_engine()) as session:
        media = _media(session, ctx)
        media.peaks_path = str(out)
        session.add(media)
        session.commit()
        _maybe_ready(session, media)
    return {"peaks": str(out), "bins": int(peaks.shape[0])}
